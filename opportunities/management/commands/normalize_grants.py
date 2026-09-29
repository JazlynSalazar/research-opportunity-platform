from django.core.management.base import BaseCommand

from opportunities.models import SourceRecord
from opportunities.normalizers.grants_gov import (
    normalize_source_record,
)


class Command(BaseCommand):
    help = (
        "Normalize enriched Grants.gov SourceRecords "
        "into Opportunities."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=10,
            help="Maximum number of records to normalize.",
        )

        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-normalize records already marked processed.",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        force = options["force"]

        source_records = SourceRecord.objects.filter(
            source__name="Grants.gov API"
        ).order_by("id")

        records_to_normalize = []

        for source_record in source_records:
            raw_data = source_record.raw_data or {}

            detail = (
                raw_data.get("detail")
                if "detail" in raw_data
                else None
            )

            if not detail:
                continue

            if (
                source_record.processing_status != "ignored"
                and (
                    force
                    or source_record.opportunity_id is None
                    or source_record.processing_status in (
                        "new", "review", "error"
                    )
                )
            ):
                records_to_normalize.append(
                    source_record
                )

            if len(records_to_normalize) >= limit:
                break

        if not records_to_normalize:
            self.stdout.write(
                self.style.SUCCESS(
                    "No enriched SourceRecords need normalization."
                )
            )
            return

        normalized_count = 0
        error_count = 0

        self.stdout.write(
            f"Normalizing {len(records_to_normalize)} records..."
        )

        for source_record in records_to_normalize:
            self.stdout.write(
                f"Normalizing {source_record.external_id}: "
                f"{source_record.title}"
            )

            try:
                opportunity, cycle = normalize_source_record(
                    source_record
                )

            except Exception as exc:
                error_count += 1

                source_record.processing_status = "review"
                source_record.save(
                    update_fields=["processing_status"]
                )

                self.stdout.write(
                    self.style.ERROR(
                        f"  Error: {exc}"
                    )
                )

                continue

            normalized_count += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f"  Created/updated: "
                    f"{opportunity.title} "
                    f"[{cycle.cycle_name}]"
                )
            )

        self.stdout.write("")

        self.stdout.write(
            self.style.SUCCESS(
                f"Normalization complete: "
                f"{normalized_count} normalized, "
                f"{error_count} errors."
            )
        )
