import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urldefrag

import requests

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from opportunities.management.commands.import_msu import PROGRAMS
from opportunities.models import SourceRecord


FUNDING_TERMS = re.compile(
    r"\b(?:scholarships?|fellowships?|grants?|awards?|"
    r"funding|assistantships?|research|travel support|"
    r"financial aid|greeen)\b",
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
            title = " ".join("".join(self.parts).split())
            self.links.append((title, self.href))
            self.href = None
            self.parts = []


def official_source_url(url):
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()

    allowed = (
        host == "msu.edu"
        or host.endswith(".msu.edu")
        or host == "msu.academicworks.com"
    )

    if parsed.scheme != "https" or not allowed:
        raise ValueError("The directory URL is not an approved MSU source.")

    return url


def fetch_directory(url):
    """Fetch an official directory, with bounded redirects and size."""
    for _ in range(5):
        url = official_source_url(url)

        with requests.get(
            url,
            timeout=(10, 30),
            allow_redirects=False,
            stream=True,
            headers={"User-Agent": "ResearchOpportunityPlatform/0.1"},
        ) as response:
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
                raise ValueError("The directory did not return HTML.")

            chunks = []
            size = 0

            for chunk in response.iter_content(chunk_size=65536):
                size += len(chunk)

                if size > MAX_BYTES:
                    raise ValueError("The directory exceeds the size limit.")

                chunks.append(chunk)

            html = b"".join(chunks).decode(
                response.encoding or "utf-8",
                errors="replace",
            )

        parser = LinkParser()
        parser.feed(html)
        return url, parser.links

    raise ValueError("Too many redirects.")


def funding_links(page_url, links):
    """Return funding-related hyperlinks, not verified awards."""
    candidates = {}

    for title, href in links:
        url, _ = urldefrag(urljoin(page_url, href))
        parsed = urlsplit(url)

        if parsed.scheme not in ("http", "https"):
            continue

        if not parsed.hostname or parsed.username or parsed.password:
            continue

        if url == page_url:
            continue

        label = title or parsed.path.rstrip("/").split("/")[-1]
        searchable = f"{label} {parsed.path}"

        if not FUNDING_TERMS.search(searchable):
            continue

        candidates[url] = {
            "title": label,
            "url": url,
            "host": parsed.hostname,
        }

    return sorted(
        candidates.values(),
        key=lambda item: item["title"].lower(),
    )


class Command(BaseCommand):
    help = "Discover candidate funding links from staged MSU directories."

    def add_arguments(self, parser):
        parser.add_argument(
            "--program",
            choices=[
                key for key, value in PROGRAMS.items()
                if value.get("kind") == "directory"
            ],
            help="Scan one directory; omit to scan all.",
        )

    def handle(self, *args, **options):
        directories = {
            key: value
            for key, value in PROGRAMS.items()
            if value.get("kind") == "directory"
        }

        selected = (
            [options["program"]]
            if options["program"]
            else list(directories)
        )

        errors = 0

        for key in selected:
            record = SourceRecord.objects.filter(
                source__name="MSU Funding Pages",
                external_id=key,
            ).first()

            if record is None:
                errors += 1
                self.stderr.write(
                    f"{key}: not staged. Run import_msu first."
                )
                continue

            raw = dict(record.raw_data or {})
            program = directories[key]
            url = (
                (raw.get("page") or {}).get("url")
                or record.source_url
                or program["url"]
            )

            try:
                page_url, links = fetch_directory(url)
                candidates = funding_links(page_url, links)

            except (requests.RequestException, ValueError) as exc:
                errors += 1
                self.stderr.write(f"{key}: {exc}")
                continue

            raw["directory_discovery"] = {
                "checked_at": timezone.now().isoformat(),
                "source_url": page_url,
                "candidates": candidates,
                "candidate_count": len(candidates),
                "complete": False,
                "reason": (
                    "Funding-related links from one directory page; "
                    "not a verified or complete award catalog."
                ),
            }

            record.raw_data = raw
            record.save(update_fields=["raw_data"])

            self.stdout.write(
                f"\n{program['title']}: "
                f"{len(candidates)} candidate links saved."
            )

            for item in candidates[:15]:
                self.stdout.write(
                    f"  {item['title']}\n  {item['url']}"
                )

            if len(candidates) > 15:
                self.stdout.write(
                    f"  ...and {len(candidates) - 15} more."
                )

        if errors:
            raise CommandError(
                f"{errors} directories could not be scanned."
            )
