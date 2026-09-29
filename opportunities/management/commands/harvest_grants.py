from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from opportunities.collectors.grants_gov import DISCOVERY_KEYWORDS
from opportunities.models import ImportRun
from opportunities.pipeline_lock import exclusive_pipeline_lock


class Command(BaseCommand):
    help = "Harvest paginated Grants.gov searches and record coverage."

    def add_arguments(self, parser):
        parser.add_argument(
            "--page-size",
            type=int,
            default=100,
        )
        parser.add_argument(
            "--max-pages",
            type=int,
            default=3,
        )
        parser.add_argument(
            "--keyword",
            action="append",
            help="Search one keyword. Repeat for multiple keywords.",
        )

    @exclusive_pipeline_lock
    def handle(self, *args, **options):
        return self.run_harvest(*args, **options)

    def run_harvest(self, *args, **options):
        page_size = options["page_size"]
        max_pages = options["max_pages"]

        if page_size < 1 or max_pages < 1:
            raise CommandError("Page size and max pages must be positive.")

        keywords = options["keyword"] or DISCOVERY_KEYWORDS

        complete_count = 0
        partial_count = 0
        failed_count = 0
        created_count = 0

        for keyword in keywords:
            self.stdout.write(f"\nSearching: {keyword}")

            # Identify the ImportRun created by this search.
            before_id = (
                ImportRun.objects.order_by("-pk")
                .values_list("pk", flat=True)
                .first()
                or 0
            )

            error = None

            try:
                call_command(
                    "import_grants",
                    paginated=True,
                    keyword=keyword,
                    page_size=page_size,
                    max_pages=max_pages,
                    stdout=self.stdout,
                    stderr=self.stderr,
                )
            except CommandError as exc:
                error = str(exc)

            run = (
                ImportRun.objects.filter(
                    source__name="Grants.gov API",
                    pk__gt=before_id,
                )
                .order_by("-pk")
                .first()
            )

            if run is None:
                failed_count += 1
                self.stderr.write(
                    f"No import history was recorded for {keyword}."
                )
                continue

            if error or run.status != "completed":
                failed_count += 1
                self.stderr.write(
                    f"Search failed: "
                    f"{error or run.error_message or run.status}"
                )
                continue

            created_count += run.records_created
            coverage = run.coverage or {}

            if coverage.get("complete") is True:
                complete_count += 1
                self.stdout.write(
                    self.style.SUCCESS("Coverage: complete")
                )
            else:
                partial_count += 1
                self.stdout.write(
                    self.style.WARNING(
                        "Coverage: partial — "
                        + str(coverage.get("reason", "unknown reason"))
                    )
                )

        self.stdout.write(
            f"\nHarvest finished: "
            f"{complete_count} complete searches, "
            f"{partial_count} partial searches, "
            f"{failed_count} failed searches."
        )
        self.stdout.write(
            f"New staged records: {created_count}"
        )

        if failed_count:
            raise CommandError(
                f"{failed_count} searches failed. "
                "Review the ImportRun history."
            )
