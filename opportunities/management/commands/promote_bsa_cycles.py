from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from opportunities.models import (
    Deadline,
    OpportunityCycle,
    SourceRecord,
)


SOURCE_NAME = "BSA Funding Pages"


def cycle_external_id(record):
    return f"bsa-current:{record.external_id}"


def build_cycle_name(extraction):
    deadlines = [
        item
        for item in extraction.get(
            "deadline_candidates",
            [],
        )
        if item.get("date")
    ]

    years = sorted(
        {
            int(item["date"][:4])
            for item in deadlines
            if item.get("date")
        }
    )

    if len(years) == 1:
        return f"{years[0]} cycle"

    return "Current/most recently verified cycle"


@transaction.atomic
def promote_record(record):
    raw = record.raw_data or {}

    verification = (
        raw.get("verification")
        or {}
    )

    extraction = (
        raw.get("cycle_extraction")
        or {}
    )

    if (
        verification.get("kind")
        != "award_program"
    ):
        raise ValueError(
            "Record is not a verified BSA award program."
        )

    if (
        verification.get("confidence")
        != "high"
    ):
        raise ValueError(
            "Record is not high-confidence."
        )

    if record.opportunity is None:
        raise ValueError(
            "Record has no canonical Opportunity."
        )

    if not extraction:
        raise ValueError(
            "Record has no BSA cycle extraction."
        )

    historical = (
        extraction
        .get("historical", {})
        .get(
            "likely_historical",
            False,
        )
    )

    # Fully historical pages should stay in raw staging.
    # We do not create a current cycle from them.
    if historical:
        return {
            "result": "historical_skipped",
            "cycle": None,
            "deadline_created": False,
        }

    status = (
        extraction
        .get("status", {})
        .get(
            "status",
            "unknown",
        )
    )

    if status not in {
        "open",
        "closed",
        "forecasted",
        "unknown",
    }:
        status = "unknown"

    source_url = (
        extraction.get("source_url")
        or record.source_url
    )

    cycle, created = (
        OpportunityCycle.objects.get_or_create(
            opportunity=record.opportunity,
            external_id=cycle_external_id(
                record
            ),
            defaults={
                "cycle_name": build_cycle_name(
                    extraction
                ),
                "status": status,
                "source_url": source_url,
                "last_verified": (
                    timezone.localdate()
                ),
                "notes": (
                    "Structured from the official "
                    "Botanical Society of America "
                    "program page. Ambiguous dates "
                    "and award amounts are not "
                    "promoted automatically."
                ),
            },
        )
    )

    if not created:
        cycle.cycle_name = (
            build_cycle_name(
                extraction
            )
        )

        cycle.status = status
        cycle.source_url = source_url
        cycle.last_verified = (
            timezone.localdate()
        )

        cycle.notes = (
            "Structured from the official "
            "Botanical Society of America "
            "program page. Ambiguous dates "
            "and award amounts are not "
            "promoted automatically."
        )

        cycle.save(
            update_fields=[
                "cycle_name",
                "status",
                "source_url",
                "last_verified",
                "notes",
            ]
        )

    deadline_created = False

    if extraction.get(
        "safe_to_promote_deadline"
    ):
        safe_deadlines = [
            item
            for item in extraction.get(
                "deadline_candidates",
                []
            )
            if (
                item.get("date")
                and item.get(
                    "year_explicit"
                )
            )
        ]

        if len(safe_deadlines) == 1:
            item = safe_deadlines[0]

            deadline_date = (
                date.fromisoformat(
                    item["date"]
                )
            )

            deadline, deadline_created = (
                Deadline.objects.update_or_create(
                    cycle=cycle,
                    deadline_type="application",
                    defaults={
                        "date": deadline_date,
                        "notes": (
                            "Explicit deadline from "
                            "official BSA source text: "
                            + item.get(
                                "text",
                                "",
                            )
                        ),
                    },
                )
            )

    eligibility = extraction.get(
        "eligibility_evidence",
        [],
    )

    if eligibility:
        existing = (
            record.opportunity
            .eligibility_notes
            or ""
        ).strip()

        source_notes = "\n".join(
            eligibility
        )

        new_notes = (
            "BSA source eligibility evidence:\n"
            + source_notes
        )

        if new_notes not in existing:
            if existing:
                updated = (
                    existing
                    + "\n\n"
                    + new_notes
                )
            else:
                updated = new_notes

            record.opportunity.eligibility_notes = (
                updated
            )

            record.opportunity.save(
                update_fields=[
                    "eligibility_notes"
                ]
            )

    return {
        "result": (
            "created"
            if created
            else "updated"
        ),
        "cycle": cycle,
        "deadline_created": (
            deadline_created
        ),
    }


class Command(BaseCommand):
    help = (
        "Promote trustworthy BSA cycle "
        "extractions into structured cycles "
        "and deadlines."
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

    def handle(
        self,
        *args,
        **options,
    ):
        limit = options["limit"]

        if limit < 1:
            raise CommandError(
                "--limit must be positive."
            )

        records = (
            SourceRecord.objects
            .filter(
                source__name=SOURCE_NAME,
                raw_data__verification__kind=(
                    "award_program"
                ),
                raw_data__verification__confidence=(
                    "high"
                ),
                opportunity__isnull=False,
            )
            .select_related(
                "opportunity"
            )
            .order_by(
                "title"
            )
        )

        processed = 0
        created = 0
        updated = 0
        historical_skipped = 0
        deadline_count = 0
        errors = 0

        for record in records:
            if processed >= limit:
                break

            try:
                result = promote_record(
                    record
                )

            except (
                ValueError,
                TypeError,
            ) as exc:
                errors += 1

                self.stderr.write(
                    f"Error: "
                    f"{record.title}: "
                    f"{exc}"
                )

                continue

            processed += 1

            if (
                result["result"]
                == "historical_skipped"
            ):
                historical_skipped += 1

                self.stdout.write(
                    f"Historical skip: "
                    f"{record.title}"
                )

                continue

            if result["result"] == "created":
                created += 1
            else:
                updated += 1

            if result[
                "deadline_created"
            ]:
                deadline_count += 1

            cycle = result["cycle"]

            self.stdout.write(
                f"{result['result'].title()}: "
                f"{record.title} | "
                f"status={cycle.status}"
            )

        self.stdout.write("")

        self.stdout.write(
            f"BSA promotion complete: "
            f"{processed} processed, "
            f"{created} cycles created, "
            f"{updated} cycles updated, "
            f"{historical_skipped} "
            f"historical pages skipped, "
            f"{deadline_count} deadlines created, "
            f"{errors} errors."
        )
