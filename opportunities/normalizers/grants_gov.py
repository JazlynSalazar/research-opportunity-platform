from datetime import datetime
from decimal import Decimal, InvalidOperation
from html import unescape

from django.db import transaction
from django.utils import timezone
from django.utils.html import strip_tags

from opportunities.models import (
    Deadline,
    EligibilityCriterion,
    Opportunity,
    OpportunityCycle,
    Sponsor,
    Tag,
)


def clean_text(value):
    """
    Remove HTML from Grants.gov text and convert HTML entities
    such as &nbsp; into normal characters.
    """
    if not value:
        return ""

    return unescape(strip_tags(str(value))).strip()


def parse_money(value):
    """
    Convert Grants.gov money values into Decimal values.

    Examples:
    "650000" -> Decimal("650000")
    "$650,000" -> Decimal("650000")
    """
    if value in (None, ""):
        return None

    cleaned = str(value).replace("$", "").replace(",", "").strip()

    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def parse_grants_date(value):
    """
    Convert several Grants.gov date formats into a Python date.
    """
    if not value:
        return None

    value = str(value).strip()

    formats = [
        "%b %d, %Y %I:%M:%S %p %Z",
        "%b %d, %Y %I:%M:%S %p",
        "%m/%d/%Y",
        "%Y-%m-%d",
    ]

    for date_format in formats:
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            continue

    # Some Grants.gov values end in timezone abbreviations
    # that Python may not recognize. Remove the final token
    # and try again.
    parts = value.rsplit(" ", 1)

    if len(parts) == 2:
        without_timezone = parts[0]

        try:
            return datetime.strptime(
                without_timezone,
                "%b %d, %Y %I:%M:%S %p",
            ).date()
        except ValueError:
            pass

    return None


def normalize_status(value):
    """
    Convert Grants.gov statuses to our OpportunityCycle choices.
    """
    mapping = {
        "posted": "open",
        "forecasted": "forecasted",
        "closed": "closed",
        "archived": "closed",
    }

    return mapping.get(
        str(value or "").lower(),
        "unknown",
    )


def infer_opportunity_type(title, synopsis):
    """
    Make a conservative first-pass classification.

    Later, our classifier can improve this.
    """
    text = f"{title} {synopsis}".lower()

    if "fellowship" in text or "scholarship" in text:
        return "fellowship"

    if "travel" in text:
        return "travel"

    if "equipment" in text or "instrumentation" in text:
        return "equipment"

    if (
        "education" in text
        or "workforce development" in text
        or "teaching" in text
    ):
        return "education"

    if "training" in text or "workshop" in text:
        return "training"

    return "research"


def build_cycle_notes(synopsis):
    """
    Preserve useful Grants.gov information that does not yet
    have its own structured database field.
    """
    notes = []

    estimated_funding = synopsis.get("estimatedFundingFormatted")
    number_of_awards = synopsis.get("numberOfAwards")

    if estimated_funding:
        notes.append(
            f"Estimated total funding: {estimated_funding}"
        )

    if number_of_awards:
        notes.append(
            f"Estimated number of awards: {number_of_awards}"
        )

    return "\n".join(notes)


@transaction.atomic
def normalize_source_record(source_record):
    """
    Convert one enriched Grants.gov SourceRecord into our
    canonical Django models.
    """

    raw_data = source_record.raw_data or {}

    # Support both our newer search/detail structure
    # and older SourceRecords created during development.
    if "search" in raw_data or "detail" in raw_data:
        search = raw_data.get("search") or {}
        detail = raw_data.get("detail") or {}
    else:
        search = raw_data
        detail = {}

    doc_type = str(detail.get("docType") or "").lower()
    is_forecast = doc_type == "forecast"

    if is_forecast:
        synopsis = detail.get("forecast") or {}
    else:
        synopsis = detail.get("synopsis") or {}

    agency_details = (
        detail.get("agencyDetails")
        or synopsis.get("agencyDetails")
        or {}
    )

    title = (
        detail.get("opportunityTitle")
        or search.get("title")
        or source_record.title
        or ""
    ).strip()

    if not title:
        raise ValueError(
            f"SourceRecord {source_record.id} has no title."
        )

    # ---------------------------------------------------------
    # SPONSOR
    # ---------------------------------------------------------

    sponsor_name = (
        agency_details.get("agencyName")
        or synopsis.get("agencyName")
        or search.get("agencyName")
        or "Unknown Federal Agency"
    ).strip()

    sponsor, _ = Sponsor.objects.get_or_create(
        name=sponsor_name,
        defaults={
            "sponsor_type": "federal",
        },
    )

    if sponsor.sponsor_type != "federal":
        sponsor.sponsor_type = "federal"
        sponsor.save(update_fields=["sponsor_type"])

    # ---------------------------------------------------------
    # OPPORTUNITY
    # ---------------------------------------------------------

    if is_forecast:
        summary = clean_text(
            synopsis.get("forecastDesc")
        )
    else:
        summary = clean_text(
            synopsis.get("synopsisDesc")
        )

    eligibility_notes = clean_text(
        synopsis.get("applicantEligibilityDesc")
    )

    if is_forecast and not eligibility_notes:
        applicant_names = []

        for applicant_type in synopsis.get("applicantTypes") or []:
            applicant_name = clean_text(
                applicant_type.get("description")
            )

            if applicant_name:
                applicant_names.append(applicant_name)

        if applicant_names:
            eligibility_notes = (
                "Eligible applicant types listed by Grants.gov: "
                + "; ".join(applicant_names)
            )

    opportunity_type = infer_opportunity_type(
        title,
        summary,
    )

    grants_gov_url = (
        f"https://www.grants.gov/search-results-detail/"
        f"{source_record.external_id}"
    )

    source_url = (
        synopsis.get("fundingDescLinkUrl")
        or detail.get("assistURL")
        or grants_gov_url
    )

    opportunity = source_record.opportunity

    opportunity = source_record.opportunity

    if opportunity is None:
        opportunity = Opportunity.objects.filter(
            title=title,
            sponsor=sponsor,
            source=source_record.source,
        ).first()

    if opportunity is None:
        opportunity = Opportunity.objects.create(
            title=title,
            sponsor=sponsor,
            source=source_record.source,
            opportunity_type=opportunity_type,
            summary=summary,
            url=source_url,
            eligibility_notes=eligibility_notes,
        )

    else:
        opportunity.title = title
        opportunity.sponsor = sponsor
        opportunity.source = source_record.source
        opportunity.opportunity_type = opportunity_type

        if source_url:
            opportunity.url = source_url

        if summary:
            opportunity.summary = summary

        if eligibility_notes:
            opportunity.eligibility_notes = eligibility_notes

        opportunity.save()

    # ---------------------------------------------------------
    # AUTHORITATIVE TAGS
    # ---------------------------------------------------------

    funding_categories = (
        synopsis.get("fundingActivityCategories") or []
    )

    for category in funding_categories:
        name = clean_text(
            category.get("description")
        )

        if not name:
            continue

        tag, _ = Tag.objects.get_or_create(
            name=name,
            category="domain",
        )

        opportunity.tags.add(tag)

    funding_instruments = (
        synopsis.get("fundingInstruments") or []
    )

    for instrument in funding_instruments:
        name = clean_text(
            instrument.get("description")
        )

        if not name:
            continue

        tag, _ = Tag.objects.get_or_create(
            name=name,
            category="other",
        )

        opportunity.tags.add(tag)

    # ---------------------------------------------------------
    # ELIGIBILITY
    # ---------------------------------------------------------

    applicant_types = (
        synopsis.get("applicantTypes") or []
    )

    for applicant_type in applicant_types:
        name = clean_text(
            applicant_type.get("description")
        )

        if not name:
            continue

        criterion, _ = EligibilityCriterion.objects.get_or_create(
            name=name,
            criterion_type="applicant",
        )

        opportunity.eligibility_criteria.add(
            criterion
        )

    # ---------------------------------------------------------
    # OPPORTUNITY CYCLE
    # ---------------------------------------------------------

    external_id = str(
        detail.get("id")
        or search.get("id")
        or source_record.external_id
    )

    opportunity_number = (
        detail.get("opportunityNumber")
        or search.get("number")
        or external_id
    )

    status = normalize_status(
        search.get("oppStatus")
    )

    if is_forecast:
        open_date = (
            parse_grants_date(
                synopsis.get("estSynopsisPostingDate")
            )
            or parse_grants_date(
                synopsis.get("postingDate")
            )
            or parse_grants_date(
                search.get("openDate")
            )
        )
    else:
        open_date = (
            parse_grants_date(
                synopsis.get("postingDate")
            )
            or parse_grants_date(
                search.get("openDate")
            )
        )

    if is_forecast:
        deadline_date = (
            parse_grants_date(
                synopsis.get("estApplicationResponseDate")
            )
            or parse_grants_date(
                search.get("closeDate")
            )
        )
    else:
        deadline_date = (
            parse_grants_date(
                synopsis.get("responseDate")
            )
            or parse_grants_date(
                detail.get("originalDueDate")
            )
            or parse_grants_date(
                search.get("closeDate")
            )
        )

    award_min = parse_money(
        synopsis.get("awardFloor")
    )

    award_max = parse_money(
        synopsis.get("awardCeiling")
    )

    cycle, _ = OpportunityCycle.objects.update_or_create(
        opportunity=opportunity,
        external_id=external_id,
        defaults={
            "cycle_name": opportunity_number,
            "status": status,
            "open_date": open_date,
            "award_min": award_min,
            "award_max": award_max,
            "cost_share_required": synopsis.get("costSharing"),
            "source_url": source_url,
            "notes": build_cycle_notes(synopsis),
            "last_verified": timezone.localdate(),
        },
    )

    # ---------------------------------------------------------
    # DEADLINE
    # ---------------------------------------------------------

    if deadline_date:
        Deadline.objects.update_or_create(
            cycle=cycle,
            deadline_type="application",
            defaults={
                "date": deadline_date,
                "notes": clean_text(
                    synopsis.get("estApplicationResponseDateDesc")
                    if is_forecast
                    else synopsis.get("responseDateDesc")
                ),
            },
        )

    # ---------------------------------------------------------
    # CONNECT STAGING RECORD TO CANONICAL OPPORTUNITY
    # ---------------------------------------------------------

    source_record.opportunity = opportunity
    source_record.processing_status = "processed"

    source_record.save(
        update_fields=[
            "opportunity",
            "processing_status",
        ]
    )

    # If we have multiple imported cycles for the same program,
    # mark the program as recurring.
    if opportunity.cycles.count() > 1 and not opportunity.recurring:
        opportunity.recurring = True
        opportunity.save(
            update_fields=[
                "recurring",
                "updated_at",
            ]
        )

    return opportunity, cycle
