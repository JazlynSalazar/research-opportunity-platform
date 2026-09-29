import re
import traceback
from io import StringIO

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from opportunities.models import ImportRun, PipelineRun
from opportunities.management.commands.harvest_grants import Command as HarvestCommand
from opportunities.pipeline_lock import exclusive_pipeline_lock

SUMMARY_PATTERNS = {
    "enrichment": (
        r"Enrichment complete:\s*(\d+) enriched,\s*(\d+) errors\.",
        ("enriched", "errors"),
        "No SourceRecords need enrichment.",
        "enriched",
    ),
    "normalization": (
        r"Normalization complete:\s*(\d+) normalized,\s*(\d+) errors\.",
        ("normalized", "errors"),
        "No enriched SourceRecords need normalization.",
        "normalized",
    ),
    "classification": (
        r"Done\.\s*Saved (\d+) classifications;\s*"
        r"reused (\d+) unchanged;\s*"
        r"created (\d+) reviews;\s*errors (\d+)\.",
        ("saved", "reused", "reviews_created", "errors"),
        None,
        None,
    ),
}


def read_summary(stage_name, output):
    pattern, keys, empty_message, empty_key = SUMMARY_PATTERNS[stage_name]

    match = re.search(pattern, output, flags=re.IGNORECASE)
    if match:
        return dict(zip(keys, (int(value) for value in match.groups())))

    if empty_message and empty_message in output:
        return {empty_key: 0, "errors": 0}

    return None


class Command(BaseCommand):
    help = "Run the opportunity pipeline and record its history."

    def add_arguments(self, parser):
        parser.add_argument(
            "--paginated-discovery",
            action="store_true",
            help="Use the broader paginated research harvest.",
        )
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
            help="Restrict paginated discovery to one keyword; repeat as needed.",
        )

        parser.add_argument(
            "--limit",
            type=int,
            default=20,
            help="Maximum records to process per stage.",
        )
        parser.add_argument(
            "--stale-days",
            type=int,
            default=7,
            help="Refresh details last checked at least this many days ago.",
        )

    @exclusive_pipeline_lock
    def handle(self, *args, **options):
        limit = options["limit"]
        stale_days = options["stale_days"]
        page_size = options["page_size"]
        max_pages = options["max_pages"]

        if page_size < 1 or max_pages < 1:
            raise CommandError("Page size and max pages must be positive.")
        if options["keyword"] and not options["paginated_discovery"]:
            raise CommandError(
                "--keyword requires --paginated-discovery."
            )

        if limit < 1:
            raise CommandError("--limit must be at least 1.")
        if stale_days < 0:
            raise CommandError("--stale-days cannot be negative.")

        stages = [
            (
                "discovery",
                "import_grants",
                {"discovery": True, "per_query": 5, "limit": limit},
            ),
            (
                "enrichment",
                "enrich_grants",
                {"limit": limit, "stale_days": stale_days},
            ),
            (
                "normalization",
                "normalize_grants",
                {"limit": limit},
            ),
            (
                "classification",
                "classify_grants",
                {"limit": limit},
            ),
        ]

        if options["paginated_discovery"]:
            stages[0] = (
                "discovery",
                "harvest_grants",
                {
                    "page_size": page_size,
                    "max_pages": max_pages,
                    "keyword": options["keyword"],
                },
            )

        run = PipelineRun.objects.create()
        history = []
        issues = []

        self.stdout.write(f"Starting pipeline run {run.pk}...")

        try:
            for stage_name, command_name, kwargs in stages:
                self.stdout.write(f"\nRunning {stage_name}...")

                started = timezone.now().isoformat()
                output_buffer = StringIO()
                error_buffer = StringIO()
                exception_message = ""
                exception_traceback = ""
                fatal = False
                problems = []
                counts = {}
                coverage = []

                # Discovery already has its own ImportRun table.
                before_import_id = 0
                if stage_name == "discovery":
                    before_import_id = (
                        ImportRun.objects.filter(
                            source__name="Grants.gov API"
                        )
                        .order_by("-pk")
                        .values_list("pk", flat=True)
                        .first()
                        or 0
                    )

                try:
                    if (
                        stage_name == "discovery"
                        and options["paginated_discovery"]
                    ):
                        harvester = HarvestCommand(
                            stdout=output_buffer,
                            stderr=error_buffer,
                            no_color=True,
                        )
                        harvester.run_harvest(**kwargs)
                    else:
                        call_command(
                            command_name,
                            stdout=output_buffer,
                            stderr=error_buffer,
                            no_color=True,
                            **kwargs,
                        )
                except Exception as exc:
                    fatal = True
                    exception_message = str(exc)
                    exception_traceback = traceback.format_exc()
                    problems.append(exception_message)

                output = output_buffer.getvalue()
                stderr = error_buffer.getvalue()

                if output:
                    self.stdout.write(output, ending="")
                if stderr:
                    self.stderr.write(stderr, ending="")

                if stage_name == "discovery":
                    import_runs = list(
                        ImportRun.objects.filter(
                            source__name="Grants.gov API",
                            pk__gt=before_import_id,
                        ).order_by("pk")
                    )

                    counts = {
                        "searches": len(import_runs),
                        "found": 0,
                        "created": 0,
                        "updated": 0,
                        "complete_searches": 0,
                        "partial_searches": 0,
                        "errors": 0,
                    }

                    if not import_runs:
                        fatal = True
                        counts["errors"] = 1
                        problems.append(
                            "No discovery ImportRun was recorded."
                        )

                    for receipt in import_runs:
                        counts["found"] += receipt.records_found
                        counts["created"] += receipt.records_created
                        counts["updated"] += receipt.records_updated

                        if receipt.status != "completed":
                            fatal = True
                            counts["errors"] += 1
                            problems.append(
                                f"ImportRun {receipt.pk}: "
                                f"{receipt.status}"
                            )

                        if receipt.error_message:
                            problems.append(receipt.error_message)

                        if options["paginated_discovery"]:
                            item = dict(receipt.coverage or {})
                            item["import_run_id"] = receipt.pk
                            coverage.append(item)

                            if item.get("complete") is True:
                                counts["complete_searches"] += 1
                            else:
                                counts["partial_searches"] += 1
                                if receipt.status == "completed":
                                    problems.append(
                                        f"ImportRun {receipt.pk}: "
                                        "search coverage incomplete."
                                    )

                else:
                    parsed = read_summary(stage_name, output)

                    if parsed is None:
                        problems.append(
                            "No recognized completion summary was found."
                        )
                    else:
                        counts = parsed
                        if counts.get("errors", 0) > 0:
                            problems.append(
                                f"{counts['errors']} errors reported."
                            )

                if stderr.strip():
                    problems.append("Stage wrote to stderr; review its log.")

                if fatal:
                    stage_status = "failed"
                elif problems:
                    stage_status = "partial"
                else:
                    stage_status = "completed"

                entry = {
                    "name": stage_name,
                    "status": stage_status,
                    "started_at": started,
                    "finished_at": timezone.now().isoformat(),
                    "options": kwargs,
                    "counts": counts,
                    "coverage": coverage,
                    "output": output,
                    "stderr": stderr,
                    "error_message": "; ".join(problems),
                }

                if exception_traceback:
                    entry["traceback"] = exception_traceback

                history.append(entry)

                # Save progress after every stage.
                run.stages = history
                run.save(update_fields=["stages"])

                if problems:
                    issues.append(
                        f"{stage_name}: " + "; ".join(problems)
                    )

                self.stdout.write(
                    f"Stage result: {stage_status} | {counts}"
                )

            if any(item["status"] == "failed" for item in history):
                run.status = PipelineRun.Status.FAILED
            elif any(item["status"] == "partial" for item in history):
                run.status = PipelineRun.Status.PARTIAL
            else:
                run.status = PipelineRun.Status.COMPLETED

        finally:
            # Also record an interrupted run rather than leaving it running.
            if run.status == PipelineRun.Status.RUNNING:
                run.status = PipelineRun.Status.FAILED
                issues.append("Update interrupted before completion.")

            run.stages = history
            run.error_message = "\n".join(issues)
            run.finished_at = timezone.now()
            run.save(
                update_fields=[
                    "status",
                    "stages",
                    "error_message",
                    "finished_at",
                ]
            )

        self.stdout.write(
            f"\nPipeline run {run.pk}: {run.get_status_display()}"
        )

        if run.status != PipelineRun.Status.COMPLETED:
            raise CommandError(
                f"Update {run.pk} was not fully successful. "
                "Review its recorded stage errors."
            )
