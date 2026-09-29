from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from opportunities.collectors.grants_gov import (
    GrantsGovError,
    search_discovery_profile,
    search_opportunities,
    search_paginated,
)

from opportunities.models import ImportRun, Source, SourceRecord


class Command(BaseCommand):
    help = "Collect opportunity records from Grants.gov into the staging database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=10,
            help="Maximum number of records to retrieve.",
        )

        parser.add_argument(
            "--keyword",
            type=str,
            default="",
            help="Optional Grants.gov keyword search.",
        )

        parser.add_argument(
            "--statuses",
            type=str,
            default="forecasted|posted",
            help="Opportunity statuses to retrieve.",
        )
        parser.add_argument(
            "--discovery",
            action="store_true",
            help="Run the default multi-topic research discovery profile.",
        )

        parser.add_argument(
            "--paginated",
            action="store_true",
            help="Use paginated discovery for one keyword.",
        )
        parser.add_argument(
            "--page-size",
            type=int,
            default=100,
        )
        parser.add_argument(
            "--max-pages",
            type=int,
            default=5,
        )

        parser.add_argument(
            "--per-query",
            type=int,
            default=5,
            help="Maximum number of records retrieved for each discovery search.",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        keyword = options["keyword"]
        statuses = options["statuses"]
        discovery = options["discovery"]
        per_query = options["per_query"]
        paginated = options["paginated"]
        page_size = options["page_size"]
        max_pages = options["max_pages"]

        if limit < 1 or per_query < 1:
            raise CommandError("Limits must be positive.")
        if page_size < 1 or max_pages < 1:
            raise CommandError("Page size and max pages must be positive.")
        if paginated and (discovery or not keyword.strip()):
            raise CommandError(
                "--paginated requires --keyword and cannot use --discovery."
            )

        coverage = None

        source, _ = Source.objects.get_or_create(
            name="Grants.gov API",
            defaults={
                "url": "https://www.grants.gov/",
                "source_type": "api",
                "active": True,
            },
        )

        import_run = ImportRun.objects.create(
            source=source,
            status="running",
        )

        self.stdout.write(
            f"Starting Grants.gov import run {import_run.id}..."
        )

        try:
            if paginated:
                result = search_paginated(
                    keyword=keyword,
                    statuses=statuses,
                    page_size=page_size,
                    max_pages=max_pages,
                )
                records = result["records"]
                coverage = result["coverage"]

            elif discovery:
                self.stdout.write(
                    "Running default research discovery profile..."
                )

                records = search_discovery_profile(
                    limit_per_query=per_query,
                    statuses=statuses,
                )

            else:
                records = search_opportunities(
                    limit=limit,
                    keyword=keyword,
                    statuses=statuses,
                )

        except GrantsGovError as exc:
            import_run.status = "failed"
            import_run.finished_at = timezone.now()
            import_run.error_message = str(exc)
            import_run.save()

            raise CommandError(str(exc))

        created_count = 0
        updated_count = 0

        for record in records:
            external_id = str(record.get("id") or "").strip()

            if not external_id:
                self.stdout.write(
                    self.style.WARNING(
                        "Skipped a record because it had no Grants.gov ID."
                    )
                )
                continue

            title = (record.get("title") or "").strip()

            source_record, created = SourceRecord.objects.get_or_create(
                source=source,
                external_id=external_id,
                defaults={
                    "import_run": import_run,
                    "title": title,
                    "raw_data": {
                        "search": record,
                        "detail": None,
                    },
                    "processing_status": "new",
                },
            )

            if created:
                created_count += 1
                marker = "+"

            else:
                existing_raw = source_record.raw_data or {}

                if "search" in existing_raw or "detail" in existing_raw:
                    old_search = existing_raw.get("search", {})
                    detail_data = existing_raw.get("detail")
                else:
                    # Support records created before the
                    # search/detail structure was introduced.
                    old_search = existing_raw
                    detail_data = None

                record_changed = old_search != record

                source_record.import_run = import_run
                source_record.title = title

                metadata = {}
                if "search" in existing_raw or "detail" in existing_raw:
                    metadata = {
                        key: value
                        for key, value in existing_raw.items()
                        if key not in ("search", "detail")
                    }

                source_record.raw_data = {
                    **metadata,
                    "search": record,
                    "detail": detail_data,
                }

                if record_changed:
                    updated_count += 1

                    if source_record.processing_status == "processed":
                        source_record.processing_status = "review"

                    marker = "~"

                else:
                    marker = "="

                source_record.save()

        import_run.status = "completed"
        import_run.finished_at = timezone.now()
        import_run.records_found = len(records)
        import_run.records_created = created_count
        import_run.records_updated = updated_count
        import_run.coverage = coverage or {}
        import_run.save()

        if coverage is not None:
            self.stdout.write(f"Search coverage: {coverage}")
            if not coverage["complete"]:
                self.stdout.write(
                    self.style.WARNING(
                        "This search did not reach its reported total."
                    )
                )

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "Import completed successfully."
            )
        )

        self.stdout.write(
            f"Records found:   {len(records)}"
        )

        self.stdout.write(
            f"Records created: {created_count}"
        )

        self.stdout.write(
            f"Records updated: {updated_count}"
        )


