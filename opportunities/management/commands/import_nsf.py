import hashlib
import xml.etree.ElementTree as ET

import requests

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from opportunities.models import ImportRun, Source, SourceRecord


RSS_URL = "https://www.nsf.gov/rss/rss_www_funding_pgm_annc_inf.xml"


def item_text(item, name):
    return (item.findtext(name) or "").strip()


class Command(BaseCommand):
    help = "Import official NSF funding RSS entries into staging."

    def handle(self, *args, **options):
        source, _ = Source.objects.get_or_create(
            name="NSF Funding RSS",
            defaults={
                "url": RSS_URL,
                "source_type": "feed",
                "active": True,
            },
        )

        run = ImportRun.objects.create(
            source=source,
            status="running",
        )

        try:
            response = requests.get(
                RSS_URL,
                timeout=30,
                headers={
                    "User-Agent": "ResearchOpportunityPlatform/0.1"
                },
            )
            response.raise_for_status()

            root = ET.fromstring(response.content)
            items = root.findall("./channel/item")

            # Also support RSS 1.0 / RDF feeds.
            if not items:
                items = root.findall(
                    "{http://purl.org/rss/1.0/}item"
                )

            created_count = 0
            updated_count = 0

            with transaction.atomic():
                for item in items:
                    title = item_text(item, "title")
                    link = item_text(item, "link")
                    guid = item_text(item, "guid")

                    if not title or not link:
                        raise ValueError(
                            "An NSF RSS item is missing a title or link."
                        )

                    # Stable identity within this source.
                    external_id = hashlib.sha256(
                        (guid or link).encode("utf-8")
                    ).hexdigest()

                    feed_data = {
                        "title": title,
                        "link": link,
                        "guid": guid,
                        "description": item_text(item, "description"),
                        "published": item_text(item, "pubDate"),
                    }

                    record, created = SourceRecord.objects.get_or_create(
                        source=source,
                        external_id=external_id,
                        defaults={
                            "import_run": run,
                            "title": title[:500],
                            "source_url": link,
                            "raw_data": {
                                "feed": feed_data,
                            },
                            "processing_status": "new",
                        },
                    )

                    if created:
                        created_count += 1
                    else:
                        old = record.raw_data or {}
                        changed = old.get("feed") != feed_data

                        record.import_run = run
                        record.title = title[:500]
                        record.source_url = link
                        record.raw_data = {
                            **old,
                            "feed": feed_data,
                        }

                        if changed:
                            updated_count += 1
                            if record.processing_status == "processed":
                                record.processing_status = "review"

                        record.save()

                run.status = "completed"
                run.finished_at = timezone.now()
                run.records_found = len(items)
                run.records_created = created_count
                run.records_updated = updated_count
                run.coverage = {
                    "feed_url": RSS_URL,
                    "entries_returned": len(items),
                    "complete": False,
                    "reason": (
                        "RSS is a recent-items feed, "
                        "not a complete funding catalog."
                    ),
                }
                run.save()

        except Exception as exc:
            run.status = "failed"
            run.finished_at = timezone.now()
            run.error_message = str(exc)
            run.save()
            raise CommandError(f"NSF import failed: {exc}") from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"NSF import complete: {len(items)} entries, "
                f"{created_count} created, "
                f"{updated_count} updated."
            )
        )

