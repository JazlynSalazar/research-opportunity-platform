from hashlib import sha256
from urllib.parse import urlsplit

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from opportunities.management.commands.import_horticulture import SOURCES
from opportunities.models import Opportunity, Source, SourceRecord, Sponsor


SPONSOR_NAMES = {
    "afe": "American Floral Endowment",
    "hri": "Horticultural Research Institute",
}


def configured_programs(config):
    """Use the same program identities as the staging importer."""
    programs = {}

    for title, original_url in config["pages"]:
        external_id = sha256(original_url.encode("utf-8")).hexdigest()

        programs[external_id] = {
            "title": title,
            "original_url": original_url,
            "opportunity_type": (
                "education"
                if title == "Educational Grants"
                else "research"
            ),
        }

    return programs


@transaction.atomic
def normalize_horticulture_record(source_record, program, config):
    raw = source_record.raw_data or {}
    page = raw.get("page") or {}

    if not page.get("text"):
        raise ValueError("The official page has not been fetched.")

    title = program["title"]
    source_url = (
        page.get("url")
        or source_record.source_url
        or program["original_url"]
    ).strip()

    # Only accept the official source website.
    parsed = urlsplit(source_url)
    allowed_hosts = {
        config["host"],
        "www." + config["host"],
    }

    if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
        raise ValueError("The saved page URL is not an official source URL.")

    sponsor, _ = Sponsor.objects.get_or_create(
        name=SPONSOR_NAMES[
            "afe" if config["name"] == "AFE Funding Pages" else "hri"
        ],
        defaults={
            "website": config["website"],
            "sponsor_type": "nonprofit",
        },
    )

    opportunity = source_record.opportunity
    created = False

    if opportunity is None:
        # Reuse only a matching record from this same source.
        # Do not automatically merge AFE/HRI with another source.
        matches = list(
            Opportunity.objects.filter(
                source=source_record.source,
                sponsor=sponsor,
            ).filter(
                Q(url__in=[
                    source_url,
                    program["original_url"],
                ])
                | Q(title=title)
            ).order_by("pk")[:2]
        )

        if len(matches) > 1:
            raise ValueError(
                "Multiple possible Opportunities found. "
                "Review before linking."
            )

        if matches:
            opportunity = matches[0]
        else:
            opportunity = Opportunity.objects.create(
                title=title,
                sponsor=sponsor,
                source=source_record.source,
                opportunity_type=program["opportunity_type"],
                summary=(
                    "Official funding-program information. "
                    "Review the source for current application "
                    "requirements, funding amounts, and deadlines."
                ),
                url=source_url,
            )
            created = True

    # Do not overwrite an existing program's fuller information.
    if not created:
        if opportunity.sponsor_id not in (None, sponsor.pk):
            raise ValueError(
                "The linked Opportunity has a different sponsor."
            )

        update_fields = []

        if opportunity.sponsor_id is None:
            opportunity.sponsor = sponsor
            update_fields.append("sponsor")

        if opportunity.source_id is None:
            opportunity.source = source_record.source
            update_fields.append("source")

        if not opportunity.url:
            opportunity.url = source_url
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
    help = "Normalize staged AFE and HRI funding pages."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            choices=["afe", "hri"],
            help="Normalize one source; omit for both.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=20,
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Reprocess already-linked records.",
        )

    def handle(self, *args, **options):
        if options["limit"] < 1:
            raise CommandError("--limit must be positive.")

        selected = (
            [options["source"]]
            if options["source"]
            else list(SOURCES)
        )

        created_count = 0
        linked_count = 0
        error_count = 0

        for key in selected:
            config = SOURCES[key]
            programs = configured_programs(config)

            source = Source.objects.filter(
                name=config["name"]
            ).first()

            if source is None:
                error_count += 1
                self.stderr.write(
                    f"{config['name']} is not staged yet. "
                    f"Run import_horticulture --source {key}."
                )
                continue

            records = (
                SourceRecord.objects
                .filter(
                    source=source,
                    external_id__in=programs,
                )
                .exclude(processing_status="ignored")
                .order_by("id")
            )

            if not options["force"]:
                records = records.exclude(
                    processing_status="processed",
                    opportunity__isnull=False,
                )

            records = records[:options["limit"]]

            for record in records:
                try:
                    opportunity, created = (
                        normalize_horticulture_record(
                            record,
                            programs[record.external_id],
                            config,
                        )
                    )

                except Exception as exc:
                    error_count += 1
                    record.processing_status = "review"
                    record.save(
                        update_fields=["processing_status"]
                    )
                    self.stderr.write(
                        f"Error on {record.title}: {exc}"
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
            f"Horticulture normalization complete: "
            f"{created_count} created, "
            f"{linked_count} linked, "
            f"{error_count} errors."
        )

        if error_count:
            raise CommandError(
                "Some funding pages need review."
            )
