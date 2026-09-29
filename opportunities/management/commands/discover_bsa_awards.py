import hashlib
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit, urldefrag

import requests

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from opportunities.models import ImportRun, Source, SourceRecord


SOURCE_NAME = "BSA Funding Pages"

AWARD_TERMS = re.compile(
    r"\b(?:award|awards|grant|grants|prize|fellowship|"
    r"research|travel|dissertation|student|postdoc)\b",
    re.IGNORECASE,
)

MAX_BYTES = 2_000_000


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.href = None
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.href = dict(attrs).get("href")
            self.parts = []

    def handle_data(self, data):
        if self.href:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.href:
            text = " ".join("".join(self.parts).split())

            self.links.append(
                {
                    "text": text,
                    "href": self.href,
                }
            )

            self.href = None
            self.parts = []


def official_bsa_url(value):
    parsed = urlsplit(value)

    host = (parsed.hostname or "").lower()

    allowed = (
        host == "botany.org"
        or host.endswith(".botany.org")
    )

    if (
        parsed.scheme != "https"
        or not allowed
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Not an approved BSA URL.")

    return urlunsplit((
        "https",
        host,
        parsed.path.rstrip("/") or "/",
        parsed.query,
        "",
    ))


def fetch_links(url):
    for _ in range(5):
        url = official_bsa_url(url)

        response = requests.get(
            url,
            timeout=(10, 30),
            allow_redirects=False,
            headers={
                "User-Agent": "ResearchOpportunityPlatform/0.1"
            },
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
            raise ValueError("BSA awards page did not return HTML.")

        if len(response.content) > MAX_BYTES:
            raise ValueError("BSA awards page exceeds size limit.")

        parser = LinkParser()
        parser.feed(response.text)

        return url, parser.links

    raise ValueError("Too many redirects.")


def candidate_links(page_url, links):
    candidates = {}

    for item in links:
        href = item.get("href") or ""
        title = (item.get("text") or "").strip()

        url, _ = urldefrag(
            urljoin(page_url, href)
        )

        try:
            url = official_bsa_url(url)
        except ValueError:
            continue

        if url == page_url:
            continue

        parsed = urlsplit(url)

        searchable = " ".join([
            title,
            parsed.path.replace("-", " "),
        ])

        if not AWARD_TERMS.search(searchable):
            continue

        # Skip obvious category/landing links when possible.
        generic = title.lower().strip()

        if generic in {
            "awards",
            "student awards",
            "travel awards",
            "society awards",
            "awards for students",
            "awards for established scientists",
            "awards for early career scientists",
        }:
            continue

        candidates[url] = {
            "title": title or parsed.path.rstrip("/").split("/")[-1],
            "url": url,
        }

    return sorted(
        candidates.values(),
        key=lambda item: item["title"].lower(),
    )


def candidate_id(url):
    return "bsa-link:" + hashlib.sha256(
        url.encode("utf-8")
    ).hexdigest()


class Command(BaseCommand):
    help = "Discover and stage candidate BSA award pages."

    def add_arguments(self, parser):
        parser.add_argument(
            "--save",
            action="store_true",
            help="Save candidates. Without this, only preview them.",
        )

    def handle(self, *args, **options):
        source = Source.objects.filter(
            name=SOURCE_NAME
        ).first()

        if source is None:
            raise CommandError(
                "BSA Funding Pages is not staged. "
                "Run import_bsa first."
            )

        directory = SourceRecord.objects.filter(
            source=source,
            external_id="awards-directory",
        ).first()

        if directory is None:
            raise CommandError(
                "The BSA awards directory record was not found."
            )

        raw = directory.raw_data or {}

        page_url = (
            (raw.get("page") or {}).get("url")
            or directory.source_url
        )

        if not page_url:
            raise CommandError(
                "The BSA directory has no source URL."
            )

        try:
            final_url, links = fetch_links(page_url)
            candidates = candidate_links(
                final_url,
                links,
            )

        except (
            requests.RequestException,
            ValueError,
        ) as exc:
            raise CommandError(
                f"BSA award discovery failed: {exc}"
            ) from exc

        self.stdout.write(
            f"Found {len(candidates)} candidate BSA award links."
        )

        for item in candidates[:25]:
            self.stdout.write(
                f"  {item['title']}\n"
                f"  {item['url']}"
            )

        if len(candidates) > 25:
            self.stdout.write(
                f"  ...and {len(candidates) - 25} more."
            )

        if not options["save"]:
            self.stdout.write(
                "\nPreview only. Use --save to stage candidates."
            )
            return

        run = ImportRun.objects.create(
            source=source,
            status="running",
        )

        created_count = 0
        updated_count = 0

        try:
            with transaction.atomic():

                for item in candidates:
                    url = item["url"]
                    title = item["title"]

                    record, created = (
                        SourceRecord.objects.get_or_create(
                            source=source,
                            external_id=candidate_id(url),
                            defaults={
                                "import_run": run,
                                "title": title[:500],
                                "source_url": url,
                                "raw_data": {
                                    "program": {
                                        "kind": "candidate",
                                        "title": title,
                                        "url": url,
                                    },
                                    "discovered_from": {
                                        "title": directory.title,
                                        "url": final_url,
                                    },
                                },
                                "processing_status": "new",
                            },
                        )
                    )

                    if created:
                        created_count += 1
                        continue

                    record_raw = dict(
                        record.raw_data or {}
                    )

                    old_raw = dict(record_raw)

                    record_raw["program"] = {
                        **record_raw.get("program", {}),
                        "kind": "candidate",
                        "title": (
                            record_raw.get("program", {})
                            .get("title")
                            or title
                        ),
                        "url": url,
                    }

                    record_raw["discovered_from"] = {
                        "title": directory.title,
                        "url": final_url,
                    }

                    record.import_run = run
                    record.raw_data = record_raw

                    if old_raw != record_raw:
                        updated_count += 1

                    record.save(
                        update_fields=[
                            "import_run",
                            "raw_data",
                        ]
                    )

                directory_raw = dict(
                    directory.raw_data or {}
                )

                directory_raw["directory_discovery"] = {
                    "checked_at": timezone.now().isoformat(),
                    "candidate_count": len(candidates),
                    "candidates": candidates,
                    "complete": False,
                    "reason": (
                        "Links discovered from the BSA awards index; "
                        "each candidate still requires verification."
                    ),
                }

                directory.raw_data = directory_raw
                directory.save(
                    update_fields=["raw_data"]
                )

                run.status = "completed"
                run.finished_at = timezone.now()
                run.records_found = len(candidates)
                run.records_created = created_count
                run.records_updated = updated_count

                run.coverage = {
                    "scope": "BSA awards-index links",
                    "candidate_count": len(candidates),
                    "complete": False,
                    "reason": (
                        "Candidate award links only; "
                        "not yet verified individual programs."
                    ),
                }

                run.save()

        except Exception as exc:
            run.status = "failed"
            run.finished_at = timezone.now()
            run.error_message = str(exc)
            run.save()

            raise CommandError(
                f"BSA candidate staging failed: {exc}"
            ) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"BSA staging complete: "
                f"{created_count} created, "
                f"{updated_count} updated."
            )
        )
