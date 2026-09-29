from html import unescape

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.html import strip_tags

from opportunities.models import Opportunity, SourceRecord, Sponsor


def clean_text(value):
    return " ".join(unescape(strip_tags(value or "")).split())


@transaction.atomic
def normalize_nsf_record(source_record, sponsor):
    feed = (source_record.raw_data or {}).get("feed") or {}

    title = clean_text(feed.get("title") or source_record.title)
    link = (feed.get("link") or source_record.source_url or "").strip()
    summary = clean_text(feed.get("description"))

    if not title or not link:
        raise ValueError("NSF entry is missing a title or source URL.")

    opportunity = source_record.opportunity
    created = False

    if opportunity is None:
        # Reuse an existing canonical record only when its
        # exact source URL matches. Do not guess from titles.
        matches = list(
            Opportunity.objects.filter(url=link)[:2]
        )

        if len(matches) > 1:
            raise ValueError(
                "Multiple Opportunities use this URL; review manually."
            )

        if matches:
            opportunity = matches[0]

            if opportunity.sponsor_id not in (None, sponsor.pk):
                raise ValueError(
                    "This URL is linked to a different sponsor; "
                    "review manually."
                )

        else:
            opportunity = Opportunity.objects.create(
                title=title[:300],
                sponsor=sponsor,
                source=source_record.source,
                opportunity_type="research",
                summary=summary,
                url=link,
            )
            created = True

    # Preserve existing canonical information. RSS summaries
    # should not overwrite fuller program descriptions.
    if not created:
        update_fields = []

        if opportunity.sponsor_id is None:
            opportunity.sponsor = sponsor
            update_fields.append("sponsor")

        if opportunity.source_id is None:
            opportunity.source = source_record.source
            update_fields.append("source")

        if not opportunity.summary and summary:
            opportunity.summary = summary
            update_fields.append("summary")

        if not opportunity.url:
            opportunity.url = link
            update_fields.append("url")

        if update_fields:
            opportunity.save(update_fields=update_fields)

    source_record.opportunity = opportunity
    source_record.processing_status = "processed"
    source_record.save(
        update_fields=["opportunity", "processing_status"]
    )

    return opportunity, created


class Command(BaseCommand):
    help = "Normalize staged NSF RSS entries into Opportunities."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Reprocess already-normalized NSF entries.",
        )

    def handle(self, *args, **options):
        if options["limit"] < 1:
            raise CommandError("--limit must be at least 1.")

        sponsor, _ = Sponsor.objects.get_or_create(
            name="National Science Foundation",
            defaults={
                "website": "https://www.nsf.gov/",
                "sponsor_type": "federal",
            },
        )

        records = SourceRecord.objects.filter(
            source__name="NSF Funding RSS"
        ).exclude(
            processing_status="ignored"
        ).order_by("id")

        if not options["force"]:
            records = records.exclude(
                processing_status="processed",
                opportunity__isnull=False,
            )

        records = records[:options["limit"]]

        created_count = 0
        linked_count = 0
        error_count = 0

        for source_record in records:
            try:
                opportunity, created = normalize_nsf_record(
                    source_record,
                    sponsor,
                )

            except Exception as exc:
                error_count += 1
                source_record.processing_status = "review"
                source_record.save(
                    update_fields=["processing_status"]
                )
                self.stderr.write(
                    f"Error on {source_record.title}: {exc}"
                )
                continue

            if created:
                created_count += 1
            else:
                linked_count += 1

            self.stdout.write(
                f"{'Created' if created else 'Linked'}: "
                f"{opportunity.title}"
            )

        self.stdout.write(
            f"NSF normalization complete: "
            f"{created_count} created, "
            f"{linked_count} linked, "
            f"{error_count} errors."
        )

        if error_count:
            raise CommandError(
                "Some NSF entries need review."
            )
