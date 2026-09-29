import hashlib
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import requests

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from opportunities.models import ImportRun, Source, SourceRecord


SOURCES = {
    "afe": {
        "name": "AFE Funding Pages",
        "website": "https://endowment.org/",
        "host": "endowment.org",
        "pages": [
            (
                "Floriculture Research Funding",
                "https://endowment.org/apply/research",
            ),
            (
                "Fred C. Gloeckner Foundation Research Fund",
                "https://endowment.org/gloeckner",
            ),
            (
                "Educational Grants",
                "https://endowment.org/grant/educational-grants",
            ),
        ],
    },
    "hri": {
        "name": "HRI Funding Pages",
        "website": "https://www.hriresearch.org/",
        "host": "hriresearch.org",
        "pages": [
            (
                "HRI Research Grants",
                "https://www.hriresearch.org/research-application-and-requirements",
            ),
        ],
    },
}


class PageTextParser(HTMLParser):
    SKIP = {
        "script", "style", "nav", "header", "footer",
        "aside", "form", "noscript", "svg",
    }
    BREAKS = {
        "p", "div", "section", "article", "h1", "h2",
        "h3", "h4", "li", "br", "tr",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skipped = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skipped += 1
        elif not self.skipped and tag in self.BREAKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skipped:
            self.skipped -= 1
        elif not self.skipped and tag in self.BREAKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skipped:
            self.parts.append(data)

    def text(self):
        lines = [
            " ".join(line.split())
            for line in "".join(self.parts).splitlines()
        ]
        return "\n".join(line for line in lines if line)


def fetch_page(url, host):
    for _ in range(5):
        parsed = urlsplit(url)

        if (
            parsed.scheme != "https"
            or parsed.hostname not in {host, "www." + host}
        ):
            raise ValueError("Redirect left the official funding website.")

        response = requests.get(
            url,
            timeout=(10, 30),
            allow_redirects=False,
            headers={"User-Agent": "ResearchOpportunityPlatform/0.1"},
        )

        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("Location")
            if not location:
                raise ValueError("Redirect has no destination.")
            url = urljoin(url, location)
            continue

        response.raise_for_status()

        if "text/html" not in response.headers.get(
            "Content-Type", ""
        ).lower():
            raise ValueError("The source is not an HTML page.")

        if len(response.content) > 2_000_000:
            raise ValueError("The page exceeds the size limit.")

        parser = PageTextParser()
        parser.feed(response.text)
        text = parser.text()

        if not text:
            raise ValueError("No readable page text was found.")

        return {
            "url": url,
            "text": text,
            "fetched_at": timezone.now().isoformat(),
        }

    raise ValueError("Too many redirects.")


class Command(BaseCommand):
    help = "Stage official AFE and HRI funding pages."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            choices=["afe", "hri"],
            help="Import one source; omit to import both.",
        )

    def handle(self, *args, **options):
        selected = (
            [options["source"]]
            if options["source"]
            else list(SOURCES)
        )

        total_errors = 0

        for key in selected:
            config = SOURCES[key]

            source, _ = Source.objects.get_or_create(
                name=config["name"],
                defaults={
                    "url": config["website"],
                    "source_type": "website",
                    "active": True,
                },
            )

            run = ImportRun.objects.create(
                source=source,
                status="running",
            )

            found = 0
            created_count = 0
            updated_count = 0
            errors = []

            try:
                for title, url in config["pages"]:
                    try:
                        page = fetch_page(url, config["host"])
                    except (requests.RequestException, ValueError) as exc:
                        errors.append(f"{title}: {exc}")
                        self.stderr.write(f"Error: {title}: {exc}")
                        continue

                    external_id = hashlib.sha256(
                        url.encode("utf-8")
                    ).hexdigest()

                    record, created = SourceRecord.objects.get_or_create(
                        source=source,
                        external_id=external_id,
                        defaults={
                            "import_run": run,
                            "title": title,
                            "source_url": page["url"],
                            "raw_data": {
                                "program": {"title": title},
                                "page": page,
                            },
                            "processing_status": "new",
                        },
                    )

                    found += 1

                    if created:
                        created_count += 1
                    else:
                        raw = dict(record.raw_data or {})
                        old_page = raw.get("page") or {}

                        changed = (
                            old_page.get("text") != page["text"]
                            or old_page.get("url") != page["url"]
                        )

                        raw["program"] = {"title": title}
                        raw["page"] = page

                        record.import_run = run
                        record.title = title
                        record.source_url = page["url"]
                        record.raw_data = raw

                        if changed:
                            updated_count += 1
                            if record.processing_status == "processed":
                                record.processing_status = "review"

                        record.save()

                    self.stdout.write(f"Staged: {title}")

                run.status = "failed" if errors else "completed"
                run.finished_at = timezone.now()
                run.records_found = found
                run.records_created = created_count
                run.records_updated = updated_count
                run.error_message = "\n".join(errors)

                run.coverage = {
                    "scope": "Configured funding landing pages",
                    "configured_pages": len(config["pages"]),
                    "pages_fetched": found,
                    "complete": False,
                    "reason": "Not a complete funding-program catalog.",
                }

                run.save()

            except Exception as exc:
                run.status = "failed"
                run.finished_at = timezone.now()
                run.error_message = str(exc)
                run.save()
                raise CommandError(str(exc)) from exc

            total_errors += len(errors)

            self.stdout.write(
                f"{config['name']}: {found} pages fetched, "
                f"{created_count} created, "
                f"{updated_count} updated, "
                f"{len(errors)} errors."
            )

        if total_errors:
            raise CommandError(
                f"{total_errors} pages could not be imported."
            )
