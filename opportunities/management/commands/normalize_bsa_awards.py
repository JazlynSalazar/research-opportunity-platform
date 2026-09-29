from urllib.parse import urlsplit

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from opportunities.models import Opportunity, SourceRecord, Sponsor


SOURCE_NAME = "BSA Funding Pages"
SPONSOR_NAME = "Botanical Society of America"


def official_bsa_url(url):
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()

    allowed = (
        host == "botany.org"
        or host.endswith(".botany.org")
    )

    if (
        parsed.scheme != "https"
        or not allowed
        or parsed.username
        or parsed.password
    ):
        raise ValueError(
            "The saved URL is not an approved BSA source."
        )

    return url


def infer_opportunity_type(title):
    text = (title or "").lower()

    if "travel" in text:
        return "travel"

    if "fellowship" in text or "scholarship" in text:
        return "fellowship"

    if (
        "research" in text
        or "dissertation" in text
        or "grant" in text
    ):
        return "research"

    return "other"


@transaction.atomic
def normalize_bsa_award(record, sponsor):
    raw = record.raw_data or {}

    verification = raw.get("verification") or {}

    if verification.get("kind") != "award_program":
        raise ValueError(
            "Record is not a verified BSA award program."
        )

    if verification.get("confidence") != "high":
        raise ValueError(
            "BSA award is not high-confidence."
        )

    program = raw.get("program") or {}
    page = raw.get("candidate_page") or {}

    title = (
        program.get("title")
        or record.title
        or ""
    ).strip()

    source_url = official_bsa_url(
        (
            page.get("url")
            or program.get("url")
            or record.source_url
            or ""
        ).strip()
    )

    if not title:
        raise ValueError(
            "Verified BSA award has no title."
        )

    opportunity = record.opportunity
    created = False

    if opportunity is None:
        matches = list(
            Opportunity.objects.filter(
                source=record.source,
                sponsor=sponsor,
                url=source_url,
            ).order_by("pk")[:2]
        )

        if len(matches) > 1:
            raise ValueError(
                "Multiple Opportunities use this BSA URL."
            )

        if matches:
            opportunity = matches[0]

        else:
            opportunity = Opportunity.objects.create(
                title=title[:300],
                sponsor=sponsor,
                source=record.source,
                opportunity_type=infer_opportunity_type(
                    title
                ),
                summary=(
                    "Official Botanical Society of America "
                    "award or funding program. Review the "
                    "source page for current eligibility, "
                    "application requirements, funding, and "
                    "deadlines."
                ),
                url=source_url,
            )

            created = True

    record.opportunity = opportunity
    record.processing_status = "processed"

    record.save(
        update_fields=[
            "opportunity",
            "processing_status",
        ]
    )

    return opportunity, created


class Command(BaseCommand):
    help = (
        "Normalize verified Botanical Society of America "
        "award programs."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
        )

        parser.add_argument(
            "--force",
            action="store_true",
        )

    def handle(self, *args, **options):
        if options["limit"] < 1:
            raise CommandError(
                "--limit must be positive."
            )

        records = (
            SourceRecord.objects
            .filter(
                source__name=SOURCE_NAME,
                raw_data__program__kind="candidate",
                raw_data__verification__kind="award_program",
                raw_data__verification__confidence="high",
            )
            .select_related(
                "source",
                "opportunity",
            )
            .order_by("pk")
        )

        if not options["force"]:
            records = records.exclude(
                processing_status="processed",
                opportunity__isnull=False,
            )

        records = list(
            records[:options["limit"]]
        )

        if not records:
            self.stdout.write(
                "No verified BSA awards need normalization."
            )
            return

        sponsor, _ = Sponsor.objects.get_or_create(
            name=SPONSOR_NAME,
            defaults={
                "website": "https://botany.org/",
                "sponsor_type": "society",
            },
        )

        created_count = 0
        linked_count = 0
        error_count = 0

        for record in records:
            try:
                opportunity, created = (
                    normalize_bsa_award(
                        record,
                        sponsor,
                    )
                )

            except Exception as exc:
                error_count += 1

                record.processing_status = "review"
                record.save(
                    update_fields=[
                        "processing_status"
                    ]
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
            f"BSA normalization complete: "
            f"{created_count} created, "
            f"{linked_count} linked, "
            f"{error_count} errors."
        )

        if error_count:
            raise CommandError(
                "Some verified BSA awards need review."
            )
