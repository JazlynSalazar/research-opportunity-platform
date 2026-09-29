from html import unescape

from django.utils.html import strip_tags


def clean_text(value):
    return " ".join(
        unescape(strip_tags(str(value or ""))).split()
    )


def get_classification_text(source_record):
    """
    Return text for classification from a supported source.
    This does not change the database.
    """
    raw = source_record.raw_data or {}
    source_name = source_record.source.name

    if source_name == "Grants.gov API":
        detail = raw.get("detail") or {}

        if not detail:
            raise ValueError("Grants.gov details are missing.")

        if str(detail.get("docType") or "").lower() == "forecast":
            info = detail.get("forecast") or {}
            description = info.get("forecastDesc") or ""
        else:
            info = detail.get("synopsis") or {}
            description = info.get("synopsisDesc") or ""

        search = raw.get("search") or {}

        title = (
            detail.get("opportunityTitle")
            or search.get("title")
            or source_record.title
        )

        categories = info.get("fundingActivityCategories") or []
        category_text = " ".join(
            item.get("description", "")
            for item in categories
            if isinstance(item, dict)
        )

        parts = [title, category_text, description]

    elif source_name == "NSF Funding RSS":
        feed = raw.get("feed") or {}

        if not feed:
            raise ValueError("NSF feed data is missing.")

        page = raw.get("candidate_page") or raw.get("page") or {}

        parts = [
            feed.get("title") or source_record.title,
            feed.get("description") or "",
            page.get("text") or "",
        ]

    elif source_name in (
        "AFE Funding Pages",
        "HRI Funding Pages",
        "MSU Funding Pages",
        "BSA Funding Pages",
    ):
        program = raw.get("program") or {}
        page = raw.get("candidate page") or raw.get("page") or  {}

        # Directories are discovery sources, not individual awards.
        if program.get("kind") == "directory":
            raise ValueError("Funding directories are not classified.")

        if not page.get("text"):
            raise ValueError("Official page text is missing.")

        parts = [
            program.get("title") or source_record.title,
            page.get("text") or "",
        ]

    else:
        raise ValueError(
            f"No classification extractor for {source_name}."
        )

    text = " ".join(clean_text(part) for part in parts)

    if not text.strip():
        raise ValueError("No classification text is available.")

    return text
