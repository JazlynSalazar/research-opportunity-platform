from urllib.parse import urlsplit

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from opportunities.management.commands.import_msu import PROGRAMS
from opportunities.models import Opportunity, SourceRecord, Sponsor


SOURCE_NAME = "MSU Funding Pages"
SPONSOR_NAME = "Michigan State University"


def official_msu_url(url):
    """Accept only official HTTPS MSU websites."""
    parsed = urlsplit(url)

    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not (
            parsed.hostname == "msu.edu"
            or parsed.hostname.endswith(".msu.edu")
        )
    ):
        raise ValueError("The saved URL is not an official MSU website.")

    return url


@transaction.atomic
def normalize_msu_record(record, program, sponsor):
    """Create or link one actual MSU funding program."""
    if program.get("kind") != "program":
        raise ValueError("Directories are not individual Opportunities.")

    raw = record.raw_data or {}
    page = raw.get("page") or {}

    if not page.get("text"):
        raise ValueError("The official program page has not been fetched.")

    title = program["title"]
    original_url = official_msu_url(program["url"])

    source_url = official_msu_url(
        (page.get("url") or record.source_url or original_url).strip()
    )

    opportunity = record.opportunity
    created = False

    if opportunity is None:
        # Match only an exact URL from this same source and sponsor.
        # Do not guess that two programs are identical from their titles.
        matches = list(
            Opportunity.objects.filter(
                source=record.source,
                sponsor=sponsor,
                url__in=[original_url, source_url],
            ).order_by("pk")[:2]
        )

        if len(matches) > 1:
            raise ValueError(
                "Multiple Opportunities match this URL. "
                "Review before linking."
            )

        if matches:
            opportunity = matches[0]
        else:
            opportunity = Opportunity.objects.create(
                title=title,
                sponsor=sponsor,
                source=record.source,
                opportunity_type=program["opportunity_type"],
                summary=(
                    "Official MSU funding program. Review the linked "
                    "source for current application requirements, "
                    "eligibility, and deadlines."
                ),
                url=source_url,
            )
            created = True

    # Preserve existing canonical information.
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
            opportunity.source = record.source
            update_fields.append("source")

        if not opportunity.url:
            opportunity.url = source_url
            update_fields.append("url")

        if update_fields:
            opportunity.save(update_fields=update_fields)

    record.opportunity = opportunity
    record.processing_status = "processed"
    record.save(
        update_fields=["opportunity", "processing_status"]
    )

    return opportunity, created


class Command(BaseCommand):
    help = "Normalize staged MSU funding programs into Opportunities."

    def add_arguments(self, parser):
        parser.add_argument(
            "--program",
            choices=list(PROGRAMS),
            help="Process one configured MSU program.",
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

        # Directories are intentionally excluded.
        program_keys = [
            key
            for key, program in PROGRAMS.items()
            if program.get("kind") == "program"
        ]

        if options["program"]:
            if options["program"] not in program_keys:
                raise CommandError(
                    "That page is a funding directory, not an "
                    "individual program."
                )
            program_keys = [options["program"]]

        records = (
            SourceRecord.objects
            .filter(
                source__name=SOURCE_NAME,
                external_id__in=program_keys,
            )
            .exclude(processing_status="ignored")
            .select_related("source", "opportunity")
            .order_by("pk")
        )

        if not options["force"]:
            records = records.exclude(
                processing_status="processed",
                opportunity__isnull=False,
            )

        records = list(records[:options["limit"]])

        if not records:
            self.stdout.write(
                "No staged MSU programs need normalization."
            )
            return

        sponsor, _ = Sponsor.objects.get_or_create(
            name=SPONSOR_NAME,
            defaults={
                "website": "https://msu.edu/",
                "sponsor_type": "university",
            },
        )

        created_count = 0
        linked_count = 0
        error_count = 0

        for record in records:
            try:
                opportunity, created = normalize_msu_record(
                    record,
                    PROGRAMS[record.external_id],
                    sponsor,
                )

            except Exception as exc:
                error_count += 1
                record.processing_status = "review"
                record.save(update_fields=["processing_status"])

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
            f"MSU normalization complete: "
            f"{created_count} created, "
            f"{linked_count} linked, "
            f"{error_count} errors."
        )

        if error_count:
            raise CommandError(
                "Some MSU programs need review."
            )
