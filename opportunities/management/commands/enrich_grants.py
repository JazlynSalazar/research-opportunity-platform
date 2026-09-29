from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from opportunities.collectors.grants_gov import (
    GrantsGovError,
    fetch_opportunity,
)
from opportunities.models import SourceRecord


class Command(BaseCommand):
    help = "Fetch detailed Grants.gov data for staged SourceRecords."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=10,
            help="Maximum number of SourceRecords to enrich.",
        )

        parser.add_argument(
            "--stale-days",
            type=int,
            default=None,
            help="Refresh details last checked at least this many days ago.",
        )

        parser.add_argument(
            "--force",
            action="store_true",
            help="Refresh records that already have detailed data.",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        force = options["force"]
        stale_days = options["stale_days"]

        if limit < 1:
            raise CommandError("--limit must be at least 1.")
        if stale_days is not None and stale_days < 0:
            raise CommandError("--stale-days cannot be negative.")

        cutoff = (
            timezone.localdate() - timedelta(days=stale_days)
            if stale_days is not None
            else None
        )

        records = SourceRecord.objects.filter(
            source__name="Grants.gov API"
        ).order_by("id")

        missing = []
        refresh_candidates = []

        for source_record in records:
            raw_data = source_record.raw_data or {}
            detail_data = raw_data.get("detail")

            if not detail_data:
                missing.append(source_record)
                continue

            if not force and cutoff is None:
                continue

            try:
                checked = date.fromisoformat(
                    raw_data.get("detail_checked_on", "")
                )
            except (TypeError, ValueError):
                checked = date.min

            if force or (cutoff is not None and checked <= cutoff):
                refresh_candidates.append(
                    (checked, source_record.pk, source_record)
                )

        refresh_candidates.sort(key=lambda item: (item[0], item[1]))

        records_to_enrich = (
            missing + [item[2] for item in refresh_candidates]
        )[:limit]

        if not records_to_enrich:
            self.stdout.write(
                self.style.SUCCESS(
                    "No SourceRecords need enrichment."
                )
            )
            return

        enriched_count = 0
        error_count = 0

        self.stdout.write(
            f"Enriching {len(records_to_enrich)} Grants.gov records..."
        )

        for source_record in records_to_enrich:
            self.stdout.write(
                f"Fetching {source_record.external_id}: "
                f"{source_record.title}"
            )

            try:
                detail = fetch_opportunity(
                    source_record.external_id
                )

            except GrantsGovError as exc:
                error_count += 1

                self.stdout.write(
                    self.style.ERROR(
                        f"  Error: {exc}"
                    )
                )

                continue

            existing_raw = source_record.raw_data or {}

            if "search" in existing_raw or "detail" in existing_raw:
                search_data = existing_raw.get("search", {})
            else:
                search_data = existing_raw

            old_detail = existing_raw.get("detail")

            if (
                old_detail != detail
                and source_record.processing_status == "processed"
            ):
                source_record.processing_status = "review"

            source_record.raw_data = {
                "search": search_data,
                "detail": detail,
                "detail_checked_on": timezone.localdate().isoformat(),
            }

            source_record.save()

            enriched_count += 1

            self.stdout.write(
                self.style.SUCCESS(
                    "  Enriched successfully."
                )
            )

        self.stdout.write("")

        self.stdout.write(
            self.style.SUCCESS(
                f"Enrichment complete: "
                f"{enriched_count} enriched, "
                f"{error_count} errors."
            )
        )
