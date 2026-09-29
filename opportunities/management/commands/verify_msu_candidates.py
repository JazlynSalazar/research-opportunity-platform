import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import requests

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from opportunities.models import SourceRecord


MAX_BYTES = 2_000_000


class TextParser(HTMLParser):
    SKIP = {
        "script", "style", "nav", "header", "footer",
        "aside", "form", "noscript", "svg",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip_depth += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data):
        if not self.skip_depth:
            self.parts.append(data)

    def text(self):
        return " ".join(
            " ".join(self.parts).split()
        )


def official_msu_url(url):
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()

    allowed = (
        host == "msu.edu"
        or host.endswith(".msu.edu")
        or host == "msu.academicworks.com"
    )

    if (
        parsed.scheme != "https"
        or not allowed
        or parsed.username
        or parsed.password
    ):
        raise ValueError("URL is not an approved MSU source.")

    return url


def fetch_candidate_page(url):
    for _ in range(5):
        url = official_msu_url(url)

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

        content_type = response.headers.get(
            "Content-Type", ""
        ).lower()

        if "text/html" not in content_type:
            raise ValueError("Page did not return HTML.")

        if len(response.content) > MAX_BYTES:
            raise ValueError("Page exceeds size limit.")

        parser = TextParser()
        parser.feed(response.text)
        text = parser.text()

        if len(text) < 40:
            raise ValueError("No usable page text was found.")

        return {
            "url": url,
            "text": text,
            "fetched_at": timezone.now().isoformat(),
        }

    raise ValueError("Too many redirects.")


def verify_candidate(title, url, text):
    parsed = urlsplit(url)

    host = (parsed.hostname or "").lower()
    path = parsed.path.lower().rstrip("/")
    title_lower = (title or "").lower()

    evidence = []

    # AcademicWorks opportunity URLs are strong evidence that
    # this is one individual scholarship/award listing.
    if (
        host == "msu.academicworks.com"
        and re.fullmatch(r"/opportunities/\d+", path)
    ):
        evidence.append(
            "Individual MSU AcademicWorks opportunity URL."
        )

        return {
            "kind": "individual_award",
            "confidence": "high",
            "evidence": evidence,
        }

    generic_titles = {
        "funding",
        "fellowships",
        "funding resources",
        "assistantship resources",
        "research integrity",
        "msu scholarships catalog",
        "graduate school fellowship directory",
    }

    if title_lower in generic_titles:
        evidence.append(
            "Generic directory or navigation title."
        )

        return {
            "kind": "directory_or_navigation",
            "confidence": "high",
            "evidence": evidence,
        }

    # These words suggest a real program, but are not enough
    # for automatic normalization.
    award_terms = (
        "scholarship",
        "fellowship",
        "award",
        "grant",
        "travel funding",
        "research funding",
    )

    matching_terms = [
        term
        for term in award_terms
        if term in title_lower
    ]

    if matching_terms:
        evidence.append(
            "Funding terms in title: "
            + ", ".join(matching_terms)
        )

        return {
            "kind": "possible_program",
            "confidence": "medium",
            "evidence": evidence,
        }

    text_lower = text.lower()

    text_signals = [
        term
        for term in (
            "eligibility",
            "application deadline",
            "apply for",
            "scholarship",
            "fellowship",
            "award amount",
        )
        if term in text_lower
    ]

    if len(text_signals) >= 2:
        evidence.append(
            "Funding-page signals: "
            + ", ".join(text_signals)
        )

        return {
            "kind": "possible_program",
            "confidence": "medium",
            "evidence": evidence,
        }

    return {
        "kind": "needs_review",
        "confidence": "low",
        "evidence": [
            "No strong individual-award signal was found."
        ],
    }


class Command(BaseCommand):
    help = "Fetch and verify staged MSU funding candidates."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=25,
        )

        parser.add_argument(
            "--force",
            action="store_true",
        )

    def handle(self, *args, **options):
        if options["limit"] < 1:
            raise CommandError("--limit must be positive.")

        records = (
            SourceRecord.objects
            .filter(
                source__name="MSU Funding Pages",
                raw_data__program__kind="candidate",
            )
            .order_by("pk")
        )

        checked = 0
        errors = 0

        counts = {
            "individual_award": 0,
            "possible_program": 0,
            "directory_or_navigation": 0,
            "needs_review": 0,
        }

        for record in records:
            raw = dict(record.raw_data or {})

            if (
                not options["force"]
                and raw.get("verification")
            ):
                continue

            if checked >= options["limit"]:
                break

            checked += 1

            url = (
                (raw.get("program") or {}).get("url")
                or record.source_url
            )

            try:
                page = fetch_candidate_page(url)

                verification = verify_candidate(
                    record.title,
                    page["url"],
                    page["text"],
                )

                verification["checked_at"] = (
                    timezone.now().isoformat()
                )

                raw["candidate_page"] = page
                raw["verification"] = verification

                record.raw_data = raw
                record.save(update_fields=["raw_data"])

                kind = verification["kind"]
                counts[kind] += 1

                self.stdout.write(
                    f"{kind}: {record.title}"
                )

            except (
                requests.RequestException,
                ValueError,
            ) as exc:
                errors += 1

                raw["verification"] = {
                    "kind": "fetch_error",
                    "confidence": "none",
                    "evidence": [str(exc)],
                    "checked_at": timezone.now().isoformat(),
                }

                record.raw_data = raw
                record.save(update_fields=["raw_data"])

                self.stderr.write(
                    f"Error on {record.title}: {exc}"
                )

        self.stdout.write("")
        self.stdout.write(
            f"Verified {checked} candidates."
        )

        self.stdout.write(
            f"Individual awards: "
            f"{counts['individual_award']}"
        )

        self.stdout.write(
            f"Possible programs: "
            f"{counts['possible_program']}"
        )

        self.stdout.write(
            f"Directory/navigation: "
            f"{counts['directory_or_navigation']}"
        )

        self.stdout.write(
            f"Needs review: "
            f"{counts['needs_review']}"
        )

        self.stdout.write(
            f"Fetch errors: {errors}"
        )
