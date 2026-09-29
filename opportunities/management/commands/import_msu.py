from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
import requests

from opportunities.management.commands.import_horticulture import fetch_page
from opportunities.models import ImportRun, Source, SourceRecord


PROGRAMS = {
    "greeen": {
        "title": "Project GREEEN",
        "url": "https://www.canr.msu.edu/project-greeen/rfps_and_forms",
        "kind": "program",
        "opportunity_type": "research",
    },
    "research-enhancement": {
        "title": "Research Enhancement Award",
        "url": "https://grad.msu.edu/funding/research-enhancement-award",
        "kind": "program",
        "opportunity_type": "fellowship",
    },
    "travel": {
        "title": "Graduate School Travel Funding",
        "url": "https://grad.msu.edu/funding/travel-funding",
        "kind": "program",
        "opportunity_type": "travel",
    },
    "dissertation": {
        "title": "Dissertation Completion Fellowships",
        "url": "https://grad.msu.edu/funding/dissertation-completion-fellowships",
        "kind": "program",
        "opportunity_type": "fellowship",
    },
    "graduate-fellowships": {
        "title": "Graduate School Fellowship Directory",
        "url": "https://grad.msu.edu/funding/funding-list",
        "kind": "directory",
    },
    "horticulture-scholarships": {
        "title": "Horticulture Scholarships and Other Funding",
        "url": "https://www.canr.msu.edu/hrt/students/scholarships/",
        "kind": "directory",
    },
    "msu-scholarships": {
        "title": "MSU Scholarships Catalog",
        "url": "https://msu.academicworks.com/",
        "kind": "directory",
    },
    "limited-proposals": {
        "title": "Institutionally Limited Proposals",
        "url": "https://research.msu.edu/ilp",
        "kind": "directory",
    },
}


class Command(BaseCommand):
    help = "Stage official MSU funding programs and directories."

    def add_arguments(self, parser):
        parser.add_argument(
            "--program",
            choices=list(PROGRAMS),
            help="Import one configured page; omit for all.",
        )

    def handle(self, *args, **options):
        selected = (
            [options["program"]]
            if options["program"]
            else list(PROGRAMS)
        )

        source, _ = Source.objects.get_or_create(
            name="MSU Funding Pages",
            defaults={
                "url": "https://grad.msu.edu/funding",
                "source_type": "website",
                "active": True,
            },
        )

        run = ImportRun.objects.create(
            source=source,
            status="running",
        )

        found = 0
        created_count = 0
        updated_count = 0
        errors = []

        try:
            for key in selected:
                program = PROGRAMS[key]
                url = program["url"]

                try:
                    page = fetch_page(
                        url,
                        host=__import__("urllib.parse", fromlist=["urlsplit"])
                            .urlsplit(url).hostname,
                    )
                except (requests.RequestException, ValueError) as exc:
                    errors.append(f"{key}: {exc}")
                    self.stderr.write(f"Error on {key}: {exc}")
                    continue

                # The configured key is the stable identity.
                record, created = SourceRecord.objects.get_or_create(
                    source=source,
                    external_id=key,
                    defaults={
                        "import_run": run,
                        "title": program["title"],
                        "source_url": page["url"],
                        "raw_data": {
                            "program": {"key": key, **program},
                            "page": page,
                        },
                        "processing_status": "new",
                    },
                )

                found += 1

                if created:
                    created_count += 1
                else:
                    raw = dict(record.raw_data or {})
                    old_page = raw.get("page") or {}

                    changed = (
                        old_page.get("text") != page["text"]
                        or old_page.get("url") != page["url"]
                    )

                    raw["program"] = {"key": key, **program}
                    raw["page"] = page

                    record.import_run = run
                    record.title = program["title"]
                    record.source_url = page["url"]
                    record.raw_data = raw

                    if changed:
                        updated_count += 1
                        if record.processing_status == "processed":
                            record.processing_status = "review"

                    record.save()

                self.stdout.write(f"Staged: {program['title']}")

        except Exception as exc:
            errors.append(f"Import stopped: {exc}")

        run.status = "failed" if errors else "completed"
        run.finished_at = timezone.now()
        run.records_found = found
        run.records_created = created_count
        run.records_updated = updated_count
        run.error_message = "\n".join(errors)
        run.coverage = {
            "scope": "Configured MSU funding pages",
            "pages_requested": len(selected),
            "pages_fetched": found,
            "complete": False,
            "reason": "Not a complete funding or scholarship catalog.",
        }
        run.save()

        self.stdout.write(
            f"MSU import: {found} pages fetched, "
            f"{created_count} created, "
            f"{updated_count} updated, "
            f"{len(errors)} errors."
        )

        if errors:
            raise CommandError(
                "Some MSU pages could not be imported. "
                "Review the errors above."
            )
