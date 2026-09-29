from urllib.parse import urlsplit

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from opportunities.models import Opportunity, SourceRecord, Sponsor


SOURCE_NAME = "MSU Funding Pages"
SPONSOR_NAME = "Michigan State University"


def official_msu_url(url):
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()

    allowed = (
        host == "msu.edu"
        or host.endswith(".msu.edu")
        or host == "msu.academicworks.com"
    )

    if (
        parsed.scheme != "https"
        or not allowed
        or parsed.username
        or parsed.password
    ):
        raise ValueError("The saved URL is not an approved MSU source.")

    return url


def infer_type(title):
    text = (title or "").lower()

    if "fellowship" in text or "scholarship" in text:
        return "fellowship"

    if "travel" in text:
        return "travel"

    if "research" in text:
        return "research"

    return "other"


@transaction.atomic
def normalize_award(record, sponsor):
    raw = record.raw_data or {}
    verification = raw.get("verification") or {}

    if verification.get("kind") != "individual_award":
        raise ValueError("Record is not a verified individual award.")

    if verification.get("confidence") != "high":
        raise ValueError("Individual award is not high-confidence.")

    page = raw.get("candidate_page") or {}
    program = raw.get("program") or {}

    title = (
        program.get("title")
        or record.title
        or ""
    ).strip()

    source_url = official_msu_url(
        (
            page.get("url")
            or program.get("url")
            or record.source_url
            or ""
        ).strip()
    )

    if not title:
        raise ValueError("Verified award has no title.")

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
                "Multiple Opportunities use this source URL."
            )

        if matches:
            opportunity = matches[0]
        else:
            opportunity = Opportunity.objects.create(
                title=title[:300],
                sponsor=sponsor,
                source=record.source,
                opportunity_type=infer_type(title),
                summary=(
                    "Official MSU individual funding award. "
                    "See the source page for current eligibility, "
                    "application requirements, and deadlines."
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
    help = "Normalize verified individual MSU awards."

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
            raise CommandError("--limit must be positive.")

        records = (
            SourceRecord.objects
            .filter(
                source__name=SOURCE_NAME,
                raw_data__program__kind="candidate",
                raw_data__verification__kind="individual_award",
                raw_data__verification__confidence="high",
            )
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
                "No verified MSU awards need normalization."
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
        errors = 0

        for record in records:
            try:
                opportunity, created = normalize_award(
                    record,
                    sponsor,
                )

            except Exception as exc:
                errors += 1
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
            f"MSU award normalization complete: "
            f"{created_count} created, "
            f"{linked_count} linked, "
            f"{errors} errors."
        )

        if errors:
            raise CommandError(
                "Some verified MSU awards need review."
            )
