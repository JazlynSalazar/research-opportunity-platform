import re
from html import unescape

from django.utils.html import strip_tags


# These are temporary, explainable classification rules.
# Later, each lab will have its own matching profile.

RULES_VERSION = "rules-v1"

RULES = {
    "domain": {
        "Agriculture": [
            r"\bagricultur\w*\b",
            r"\bagronom\w*\b",
        ],
        "Plant Science": [
            r"\bplants?\b",
            r"\bcrops?\b",
            r"\bhorticultur\w*\b",
            r"\bfloricultur\w*\b",
            r"\bplant breeding\b",
            r"\bplant pathology\b",
        ],
        "Health / Clinical": [
            r"\bclinical\b",
            r"\bhealthcare\b",
            r"\bpublic health\b",
            r"\bhuman health\b",
            r"\bpatients?\b",
            r"\bdementia\b",
        ],
    },

    "method": {
        "Genomics": [
            r"\bgenom\w*\b",
            r"\bmetagenom\w*\b",
            r"\bDNA sequencing\b",
            r"\bRNA[- ]seq\b",
            r"\btranscriptom\w*\b",
        ],
        "Robotics": [
            r"\brobot\w*\b",
            r"\bautonomous systems?\b",
        ],
        "Automation": [
            r"\bautomat\w*\b",
        ],
        "Phenotyping": [
            r"\bphenotyp\w*\b",
        ],
        "Imaging": [
            r"\bimag(?:e|es|ing)\b",
            r"\bhyperspectral\b",
        ],
        "Bioinformatics": [
            r"\bbioinformatic\w*\b",
        ],
    },

    "purpose": {
        "Education": [
            r"\beducation\w*\b",
            r"\bteaching\b",
        ],
        "Workforce Development": [
            r"\bworkforce development\b",
            r"\bworkforce training\b",
        ],
        "Extension": [
            r"\bextension\b",
        ],
        "Fellowship Support": [
            r"\bfellowships?\b",
            r"\bscholarships?\b",
        ],
        "Research Infrastructure": [
            r"\bresearch infrastructure\b",
            r"\bresearch instrumentation\b",
            r"\bequipment grants?\b",
        ],
    },
}


def classify_text(text):
    """
    Return suggested tags and the words that triggered them.
    This function does not change the database.
    """

    clean = " ".join(
        unescape(strip_tags(text or "")).split()
    )

    suggestions = []

    for category, tags in RULES.items():
        for name, patterns in tags.items():
            evidence = []

            for pattern in patterns:
                match = re.search(
                    pattern,
                    clean,
                    flags=re.IGNORECASE,
                )

                if match:
                    evidence.append(match.group(0))

            if evidence:
                suggestions.append({
                    "name": name,
                    "category": category,
                    "evidence": evidence,
                })

    return suggestions


def classify_source_record(source_record):
    """
    Read an enriched SourceRecord and suggest tags.
    Supports both posted and forecasted Grants.gov records.
    """

    raw = source_record.raw_data or {}
    search = raw.get("search") or {}
    detail = raw.get("detail") or {}

    if not detail:
        raise ValueError(
            "This SourceRecord needs detail enrichment first."
        )

    if detail.get("docType") == "forecast":
        info = detail.get("forecast") or {}
        description = info.get("forecastDesc") or ""
    else:
        info = detail.get("synopsis") or {}
        description = info.get("synopsisDesc") or ""

    categories = info.get("fundingActivityCategories") or []

    category_text = " ".join(
        item.get("description", "")
        for item in categories
    )

    text = " ".join([
        detail.get("opportunityTitle") or search.get("title") or "",
        category_text,
        description,
    ])

    return classify_text(text)
