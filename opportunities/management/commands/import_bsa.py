import requests

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from opportunities.management.commands.import_horticulture import fetch_page
from opportunities.models import ImportRun, Source, SourceRecord


BSA_PAGES = {
    "awards-directory": {
        "title": "Botanical Society of America Awards",
        "url": "https://botany.org/home/awards",
        "kind": "directory",
    },
}


class Command(BaseCommand):
    help = "Stage official Botanical Society of America funding pages."

    def handle(self, *args, **options):
        source, _ = Source.objects.get_or_create(
            name="BSA Funding Pages",
            defaults={
                "url": "https://botany.org/home/awards",
                "source_type": "website",
                "active": True,
            },
        )

        run = ImportRun.objects.create(
            source=source,
            status="running",
        )

        created_count = 0
        updated_count = 0
        errors = []

        for key, program in BSA_PAGES.items():
            try:
                page = fetch_page(
                    program["url"],
                    host="botany.org",
                )

            except (requests.RequestException, ValueError) as exc:
                errors.append(f"{key}: {exc}")
                self.stderr.write(
                    f"Error on {program['title']}: {exc}"
                )
                continue

            record, created = SourceRecord.objects.get_or_create(
                source=source,
                external_id=key,
                defaults={
                    "import_run": run,
                    "title": program["title"],
                    "source_url": page["url"],
                    "raw_data": {
                        "program": {
                            "key": key,
                            **program,
                        },
                        "page": page,
                    },
                    "processing_status": "new",
                },
            )

            if created:
                created_count += 1

            else:
                raw = dict(record.raw_data or {})
                old_page = raw.get("page") or {}

                changed = (
                    old_page.get("text") != page["text"]
                    or old_page.get("url") != page["url"]
                )

                raw["program"] = {
                    "key": key,
                    **program,
                }
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

            self.stdout.write(
                f"Staged: {program['title']}"
            )

        run.status = "failed" if errors else "completed"
        run.finished_at = timezone.now()
        run.records_found = len(BSA_PAGES) - len(errors)
        run.records_created = created_count
        run.records_updated = updated_count
        run.error_message = "\n".join(errors)
        run.coverage = {
            "scope": "BSA official awards directory",
            "pages_requested": len(BSA_PAGES),
            "pages_fetched": len(BSA_PAGES) - len(errors),
            "complete": False,
            "reason": (
                "Awards landing page only; individual awards "
                "must be discovered and verified separately."
            ),
        }

        run.save()

        self.stdout.write(
            f"BSA import: "
            f"{run.records_found} pages fetched, "
            f"{created_count} created, "
            f"{updated_count} updated, "
            f"{len(errors)} errors."
        )

        if errors:
            raise CommandError(
                "Some BSA pages could not be imported."
            )
