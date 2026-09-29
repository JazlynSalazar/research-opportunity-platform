import re
from urllib.parse import urlsplit

import requests

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from opportunities.management.commands.import_horticulture import fetch_page
from opportunities.models import SourceRecord


SOURCE_NAME = "BSA Funding Pages"


YEAR_RECIPIENT_RE = re.compile(
    r"\b(?:19|20)\d{2}\b.*\b(?:award\s+)?recipients?\b",
    re.IGNORECASE,
)


def classify_candidate(title, url, text=""):
    title_lower = (title or "").lower()
    path = urlsplit(url).path.lower()

    evidence = []

    # Historical winner/recipient pages are not funding opportunities.
    if (
        "/annual-award-recipients/" in path
        or YEAR_RECIPIENT_RE.search(title or "")
    ):
        return {
            "kind": "historical_recipient_page",
            "confidence": "high",
            "evidence": [
                "Page appears to list historical award recipients."
            ],
        }

    generic_titles = {
        "awards",
        "award recipients",
        "annual award recipients",
        "student awards",
        "society awards",
    }

    if title_lower.strip() in generic_titles:
        return {
            "kind": "directory_or_navigation",
            "confidence": "high",
            "evidence": [
                "Generic awards directory/navigation title."
            ],
        }

    award_terms = (
        "award",
        "grant",
        "fellowship",
        "travel grant",
        "research award",
        "dissertation",
        "scholarship",
        "prize",
    )

    matching_title_terms = [
        term
        for term in award_terms
        if term in title_lower
    ]

    text_lower = (text or "").lower()

    application_signals = [
        term
        for term in (
            "eligibility",
            "eligible",
            "application",
            "apply",
            "deadline",
            "award amount",
            "funding",
            "proposal",
        )
        if term in text_lower
    ]

    # A dedicated award page with both an award-like title and
    # application/funding language is strong evidence.
    if matching_title_terms and len(application_signals) >= 2:
        evidence.append(
            "Award terms in title: "
            + ", ".join(matching_title_terms)
        )
        evidence.append(
            "Application/funding signals: "
            + ", ".join(application_signals)
        )

        return {
            "kind": "award_program",
            "confidence": "high",
            "evidence": evidence,
        }

    if matching_title_terms:
        return {
            "kind": "possible_award_program",
            "confidence": "medium",
            "evidence": [
                "Award-related terminology appears in the title."
            ],
        }

    return {
        "kind": "needs_review",
        "confidence": "low",
        "evidence": [
            "No strong award-program signal was found."
        ],
    }


class Command(BaseCommand):
    help = "Verify staged Botanical Society of America award candidates."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
        )

        parser.add_argument(
            "--force",
            action="store_true",
        )

    def handle(self, *args, **options):
        limit = options["limit"]

        if limit < 1:
            raise CommandError("--limit must be positive.")

        records = (
            SourceRecord.objects
            .filter(
                source__name=SOURCE_NAME,
                raw_data__program__kind="candidate",
            )
            .order_by("pk")
        )

        checked = 0
        errors = 0

        counts = {
            "award_program": 0,
            "possible_award_program": 0,
            "historical_recipient_page": 0,
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

            if checked >= limit:
                break

            checked += 1

            program = raw.get("program") or {}
            url = (
                program.get("url")
                or record.source_url
                or ""
            )

            # Historical-recipient pages can be classified
            # without downloading them again.
            preliminary = classify_candidate(
                record.title,
                url,
                "",
            )

            if (
                preliminary["kind"]
                == "historical_recipient_page"
            ):
                verification = preliminary
                verification["checked_at"] = (
                    timezone.now().isoformat()
                )

                raw["verification"] = verification
                record.raw_data = raw
                record.save(update_fields=["raw_data"])

                counts["historical_recipient_page"] += 1

                self.stdout.write(
                    f"historical_recipient_page: "
                    f"{record.title}"
                )
                continue

            try:
                page = fetch_page(
                    url,
                    host="botany.org",
                )

                verification = classify_candidate(
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
            f"Verified {checked} BSA candidates."
        )
        self.stdout.write(
            f"Award programs: {counts['award_program']}"
        )
        self.stdout.write(
            f"Possible award programs: "
            f"{counts['possible_award_program']}"
        )
        self.stdout.write(
            f"Historical recipient pages: "
            f"{counts['historical_recipient_page']}"
        )
        self.stdout.write(
            f"Directory/navigation: "
            f"{counts['directory_or_navigation']}"
        )
        self.stdout.write(
            f"Needs review: {counts['needs_review']}"
        )
        self.stdout.write(
            f"Fetch errors: {errors}"
        )
