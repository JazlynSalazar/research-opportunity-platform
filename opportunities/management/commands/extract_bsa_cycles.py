import re
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from opportunities.models import SourceRecord


SOURCE_NAME = "BSA Funding Pages"


MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


MONTH_PATTERN = "|".join(
    month.title()
    for month in MONTHS
)


EXPLICIT_DATE_RE = re.compile(
    rf"\b({MONTH_PATTERN})\s+"
    r"(\d{1,2})(?:st|nd|rd|th)?"
    r"(?:,\s*|\s+)"
    r"((?:19|20)\d{2})\b",
    re.IGNORECASE,
)


NO_YEAR_DATE_RE = re.compile(
    rf"\b({MONTH_PATTERN})\s+"
    r"(\d{1,2})(?:st|nd|rd|th)?\b",
    re.IGNORECASE,
)


MONEY_RE = re.compile(
    r"\$\s*"
    r"(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?"
    r"|\d+(?:\.\d{1,2})?)"
)


YEAR_RE = re.compile(
    r"\b((?:19|20)\d{2})\b"
)


DEADLINE_WORDS = (
    "deadline",
    "due",
    "applications close",
    "applications are due",
    "application deadline",
    "proposal deadline",
    "proposals due",
    "submit by",
    "submissions due",
)


EXCLUDED_DEADLINE_CONTEXT = (
    "fundraiser",
    "fundraising",
    "donation",
    "donate",
    "giving",
    "pledge",
)


ELIGIBILITY_WORDS = (
    "eligible",
    "eligibility",
    "applicants must",
    "applicant must",
    "applicants should",
    "must be",
    "open to",
)


CLOSED_PHRASES = (
    "call for applications is now closed",
    "applications are now closed",
    "application is now closed",
    "applications are closed",
    "application period is closed",
    "submissions are closed",
)


OPEN_PHRASES = (
    "applications are now open",
    "application is now open",
    "open for applications",
    "accepting applications",
)


def clean_text(value):
    return " ".join(
        (value or "").split()
    )


def split_sentences(text):
    text = clean_text(text)

    if not text:
        return []

    return [
        sentence.strip()
        for sentence in re.split(
            r"(?<=[.!?])\s+",
            text,
        )
        if sentence.strip()
    ]


def money_values(text):
    values = []

    for match in MONEY_RE.finditer(text):
        raw = match.group(1).replace(",", "")

        try:
            amount = Decimal(raw)
        except InvalidOperation:
            continue

        values.append(
            {
                "amount": str(amount),
                "evidence": match.group(0),
            }
        )

    return values


def deadline_candidates(text):
    candidates = []

    for sentence in split_sentences(text):
        sentence_lower = sentence.lower()

        if any(
            term in sentence_lower
            for term in EXCLUDED_DEADLINE_CONTEXT
        ):
            continue

        if not any(
            term in sentence_lower
            for term in DEADLINE_WORDS
        ):
            continue

        explicit = EXPLICIT_DATE_RE.search(
            sentence
        )

        if explicit:
            month_name = explicit.group(1).lower()
            day = int(explicit.group(2))
            year = int(explicit.group(3))

            try:
                parsed = date(
                    year,
                    MONTHS[month_name],
                    day,
                )
            except ValueError:
                parsed = None

            candidates.append(
                {
                    "text": sentence,
                    "date": (
                        parsed.isoformat()
                        if parsed
                        else None
                    ),
                    "year_explicit": True,
                }
            )

            continue

        no_year = NO_YEAR_DATE_RE.search(
            sentence
        )

        if no_year:
            candidates.append(
                {
                    "text": sentence,
                    "date": None,
                    "month": no_year.group(1).lower(),
                    "day": int(no_year.group(2)),
                    "year_explicit": False,
                }
            )

    return candidates


def eligibility_evidence(text):
    results = []

    for sentence in split_sentences(text):
        lower = sentence.lower()

        if any(
            term in lower
            for term in ELIGIBILITY_WORDS
        ):
            results.append(
                sentence
            )

    return results[:10]


def determine_status(text, deadlines):
    lower = text.lower()

    closed_evidence = [
        phrase
        for phrase in CLOSED_PHRASES
        if phrase in lower
    ]

    if closed_evidence:
        return {
            "status": "closed",
            "basis": "explicit_source_text",
            "evidence": closed_evidence,
        }

    today = timezone.localdate()

    current_cycle_deadlines = []

    for item in deadlines:
        value = item.get("date")

        if not value:
            continue

        try:
            parsed = date.fromisoformat(
                value
            )
        except ValueError:
            continue

        if parsed.year < today.year:
            continue

        current_cycle_deadlines.append(
            parsed
        )

    if current_cycle_deadlines:
        latest = max(
            current_cycle_deadlines
        )

        if latest < today:
            return {
                "status": "closed",
                "basis": "current_cycle_deadline_in_past",
                "evidence": [
                    latest.isoformat()
                ],
            }

    open_evidence = [
        phrase
        for phrase in OPEN_PHRASES
        if phrase in lower
    ]

    if open_evidence:
        return {
            "status": "open",
            "basis": "explicit_source_text",
            "evidence": open_evidence,
        }

    return {
        "status": "unknown",
        "basis": "insufficient_evidence",
        "evidence": [],
    }


def historical_signals(text):
    current_year = timezone.localdate().year

    meaningful_text = re.split(
        r"Copyright\s*(?:©|\(c\))?",
        text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]

    years = sorted(
        {
            int(value)
            for value in YEAR_RE.findall(
                meaningful_text
            )
        }
    )

    signals = []

    conference_years = re.findall(
        r"\bBOTANY\s+((?:19|20)\d{2})\b",
        meaningful_text,
        flags=re.IGNORECASE,
    )

    for value in conference_years:
        year = int(value)

        if year < current_year:
            signals.append(
                f"Page refers to BOTANY {year}."
            )

    if (
        years
        and max(years) < current_year
    ):
        signals.append(
            "Page contains no current-year content."
        )

    likely_historical = (
        bool(signals)
        and current_year not in years
    )

    return {
        "years_found": years,
        "signals": sorted(
            set(signals)
        ),
        "likely_historical": likely_historical,
    }


def extract_record(record):
    raw = dict(
        record.raw_data or {}
    )

    page = (
        raw.get("candidate_page")
        or raw.get("page")
        or {}
    )

    text = clean_text(
        page.get("text")
    )

    if not text:
        raise ValueError(
            "No saved BSA page text."
        )

    deadlines = deadline_candidates(
        text
    )

    history = historical_signals(
        text
    )

    extraction = {
        "extracted_at": timezone.now().isoformat(),
        "source_url": (
            page.get("url")
            or record.source_url
        ),
        "status": determine_status(
            text,
            deadlines,
        ),
        "deadline_candidates": deadlines,
        "money_mentions": money_values(
            text
        )[:20],
        "eligibility_evidence": (
            eligibility_evidence(
                text
            )
        ),
        "historical": history,
        "safe_to_promote_deadline": False,
        "notes": [],
    }

    explicit_deadlines = [
        item
        for item in deadlines
        if item.get("date")
        and item.get(
            "year_explicit"
        )
    ]

    current_year = (
        timezone.localdate().year
    )

    safe_years = {
        current_year,
        current_year + 1,
    }

    if (
        len(explicit_deadlines) == 1
        and not history[
            "likely_historical"
        ]
    ):
        deadline_year = int(
            explicit_deadlines[0][
                "date"
            ][:4]
        )

        if deadline_year in safe_years:
            extraction[
                "safe_to_promote_deadline"
            ] = True

    if any(
        not item.get(
            "year_explicit"
        )
        for item in deadlines
    ):
        extraction["notes"].append(
            "At least one deadline lacks an explicit year; "
            "no year was inferred."
        )

    if history[
        "likely_historical"
    ]:
        extraction["notes"].append(
            "Historical/stale content detected; "
            "dates should not be promoted automatically."
        )

    if len(
        explicit_deadlines
    ) > 1:
        extraction["notes"].append(
            "Multiple explicit deadline-like dates found; "
            "manual or stronger parsing is required."
        )

    raw[
        "cycle_extraction"
    ] = extraction

    record.raw_data = raw

    record.save(
        update_fields=[
            "raw_data"
        ]
    )

    return extraction


class Command(BaseCommand):
    help = (
        "Conservatively extract current-cycle "
        "information from verified BSA awards."
    )

    def add_arguments(
        self,
        parser,
    ):
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
        )

        parser.add_argument(
            "--force",
            action="store_true",
        )

    def handle(
        self,
        *args,
        **options,
    ):
        limit = options[
            "limit"
        ]

        if limit < 1:
            raise CommandError(
                "--limit must be positive."
            )

        records = (
            SourceRecord.objects
            .filter(
                source__name=SOURCE_NAME,
                raw_data__verification__kind="award_program",
                opportunity__isnull=False,
            )
            .order_by("title")
        )

        processed = 0
        skipped = 0
        errors = 0

        for record in records:
            raw = (
                record.raw_data
                or {}
            )

            if (
                not options["force"]
                and raw.get(
                    "cycle_extraction"
                )
            ):
                skipped += 1
                continue

            if processed >= limit:
                break

            try:
                extraction = (
                    extract_record(
                        record
                    )
                )

            except ValueError as exc:
                errors += 1

                self.stderr.write(
                    f"Error: "
                    f"{record.title}: "
                    f"{exc}"
                )

                continue

            processed += 1

            status = extraction[
                "status"
            ][
                "status"
            ]

            deadline_count = len(
                extraction[
                    "deadline_candidates"
                ]
            )

            historical = extraction[
                "historical"
            ][
                "likely_historical"
            ]

            safe = extraction[
                "safe_to_promote_deadline"
            ]

            self.stdout.write(
                f"{record.title} | "
                f"status={status} | "
                f"deadlines={deadline_count} | "
                f"historical={historical} | "
                f"safe_deadline={safe}"
            )

        self.stdout.write("")

        self.stdout.write(
            f"BSA cycle extraction complete: "
            f"{processed} processed, "
            f"{skipped} already extracted, "
            f"{errors} errors."
        )
