from django.core.management.base import BaseCommand

from opportunities.models import (
    ClassificationResult,
    ClassificationReview,
    ImportRun,
    Opportunity,
    SourceRecord,
)


class Command(BaseCommand):
    help = "Show Grants.gov pipeline coverage and recent import runs."

    def handle(self, *args, **options):
        records = SourceRecord.objects.filter(
            source__name="Grants.gov API"
        )

        total = 0
        enriched = 0
        linked = 0
        needs_normalization = 0

        for record in records.only(
            "raw_data",
            "processing_status",
            "opportunity_id",
        ).iterator():
            total += 1

            has_detail = bool(
                (record.raw_data or {}).get("detail")
            )

            if has_detail:
                enriched += 1

            if record.opportunity_id is not None:
                linked += 1

            if (
                has_detail
                and record.processing_status != "ignored"
                and (
                    record.opportunity_id is None
                    or record.processing_status in (
                        "new", "review", "error"
                    )
                )
            ):
                needs_normalization += 1

        classified = ClassificationResult.objects.filter(
            source_record__source__name="Grants.gov API"
        ).count()

        pending = ClassificationReview.objects.filter(
            source_record__source__name="Grants.gov API",
            decision="pending",
            is_current=True,
        ).count()

        approved = ClassificationReview.objects.filter(
            source_record__source__name="Grants.gov API",
            decision="approved",
            is_current=True,
        ).count()

        self.stdout.write("\nGrants.gov pipeline coverage")
        self.stdout.write(f"Staged records: {total}")
        self.stdout.write(f"With detailed data: {enriched}")
        self.stdout.write(f"Linked to Opportunities: {linked}")
        self.stdout.write(
            f"Needing normalization: {needs_normalization}"
        )
        self.stdout.write(
            f"Saved classifications: {classified}"
        )
        self.stdout.write(
            f"Current pending reviews: {pending}"
        )
        self.stdout.write(
            f"Current approved reviews: {approved}"
        )
        self.stdout.write(
            f"Total canonical Opportunities: "
            f"{Opportunity.objects.count()}"
        )

        self.stdout.write("\nRecent discovery import runs")

        runs = ImportRun.objects.filter(
            source__name="Grants.gov API"
        ).order_by("-started_at")[:3]

        if not runs:
            self.stdout.write("No import runs recorded.")

        for run in runs:
            self.stdout.write(
                f"{run.started_at:%Y-%m-%d %H:%M} | "
                f"{run.status} | "
                f"found {run.records_found}, "
                f"created {run.records_created}, "
                f"updated {run.records_updated}"
            )

            if run.error_message:
                self.stdout.write(
                    f"  Error: {run.error_message}"
                )

