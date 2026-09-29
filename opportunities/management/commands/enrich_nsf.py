from datetime import date, timedelta
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import requests

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from opportunities.models import SourceRecord


MAX_BYTES = 2_000_000
ALLOWED_HOSTS = {"nsf.gov", "www.nsf.gov"}


def validate_url(url):
    parsed = urlsplit(url)

    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError("Only official HTTPS NSF pages are allowed.")

    return url


class MainTextParser(HTMLParser):
    """Extract readable text from the page's main content."""

    SKIP = {"script", "style", "nav", "footer", "aside", "svg", "noscript"}
    BREAKS = {"p", "div", "section", "article", "h1", "h2", "h3", "h4", "li", "tr", "br"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.main_depth = 0
        self.skipped = []
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skipped.append(tag)

        if tag == "main" and not self.skipped:
            self.main_depth += 1

        if self.main_depth and not self.skipped and tag in self.BREAKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if self.skipped:
            if tag == self.skipped[-1]:
                self.skipped.pop()
            return

        if self.main_depth and tag in self.BREAKS:
            self.parts.append("\n")

        if tag == "main" and self.main_depth:
            self.main_depth -= 1

    def handle_data(self, data):
        if self.main_depth and not self.skipped:
            self.parts.append(data)

    def text(self):
        lines = [
            " ".join(line.split())
            for line in "".join(self.parts).splitlines()
        ]
        return "\n".join(line for line in lines if line)


def fetch_nsf_page(url):
    """Fetch an official NSF HTML page without following off-site redirects."""
    url = validate_url(url)

    for _ in range(5):
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
            url = validate_url(urljoin(url, location))
            continue

        response.raise_for_status()

        if "text/html" not in response.headers.get("Content-Type", "").lower():
            raise ValueError("The source is not an HTML page.")

        if len(response.content) > MAX_BYTES:
            raise ValueError("The page exceeds the size limit.")

        parser = MainTextParser()
        parser.feed(response.text)
        text = parser.text()

        if len(text) < 80:
            raise ValueError("No usable main-page text was found.")

        return {
            "url": url,
            "text": text,
            "fetched_at": timezone.now().isoformat(),
        }

    raise ValueError("Too many redirects.")


class Command(BaseCommand):
    help = "Fetch official NSF program-page text into staging."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=10)
        parser.add_argument("--stale-days", type=int, default=7)
        parser.add_argument("--force", action="store_true")

    def handle(self, *args, **options):
        limit = options["limit"]
        stale_days = options["stale_days"]

        if limit < 1 or stale_days < 0:
            raise CommandError("Limit must be positive and stale-days nonnegative.")

        cutoff = timezone.localdate() - timedelta(days=stale_days)
        candidates = []

        records = SourceRecord.objects.filter(
            source__name="NSF Funding RSS"
        ).exclude(processing_status="ignored").order_by("id")

        for record in records:
            raw = record.raw_data or {}
            feed = raw.get("feed") or {}
            url = feed.get("link") or record.source_url

            if not url:
                continue

            check = raw.get("page_check") or {}
            checked = check.get("checked_on")

            try:
                checked_date = date.fromisoformat(checked)
            except (TypeError, ValueError):
                checked_date = date.min

            if options["force"] or checked_date <= cutoff:
                candidates.append((checked_date, record.pk, record))

        candidates.sort(key=lambda item: (item[0], item[1]))

        saved = 0
        unchanged = 0
        errors = 0

        for _, _, record in candidates[:limit]:
            raw = record.raw_data or {}
            feed = raw.get("feed") or {}
            url = feed.get("link") or record.source_url

            try:
                page = fetch_nsf_page(url)
            except (requests.RequestException, ValueError) as exc:
                errors += 1
                raw["page_check"] = {
                    "checked_on": timezone.localdate().isoformat(),
                    "status": "error",
                    "error": str(exc),
                }
                record.raw_data = raw
                record.save(update_fields=["raw_data"])
                self.stderr.write(f"Error on {record.title}: {exc}")
                continue

            old_page = raw.get("page") or {}
            changed = (
                old_page.get("text") != page["text"]
                or old_page.get("url") != page["url"]
            )

            raw["page"] = page
            raw["page_check"] = {
                "checked_on": timezone.localdate().isoformat(),
                "status": "completed",
            }

            record.raw_data = raw

            if changed and record.processing_status == "processed":
                record.processing_status = "review"

            record.save(update_fields=["raw_data", "processing_status"])

            if changed:
                saved += 1
            else:
                unchanged += 1

            self.stdout.write(f"Fetched: {record.title}")

        self.stdout.write(
            f"NSF enrichment complete: {saved} changed, "
            f"{unchanged} unchanged, {errors} errors."
        )

        if errors:
            raise CommandError("Some NSF pages could not be enriched.")
