import requests


SEARCH_URL = "https://api.grants.gov/v1/api/search2"
FETCH_URL = "https://api.grants.gov/v1/api/fetchOpportunity"

class GrantsGovError(Exception):
    """Raised when the Grants.gov API cannot be queried successfully."""
    pass


def search_opportunities(
    limit=10,
    start_record=0,
    statuses="forecasted|posted",
    keyword="",
    return_data=False,
):
    """
    Search Grants.gov and return a list of opportunity records.

    This function ONLY retrieves information.
    It does not write anything to our Django database.
    """

    payload = {
        "rows": limit,
        "startRecordNum": start_record,
        "oppStatuses": statuses,
        "keyword": keyword,
    }

    try:
        response = requests.post(
            SEARCH_URL,
            json=payload,
            timeout=30,
        )

        response.raise_for_status()

    except requests.RequestException as exc:
        raise GrantsGovError(
            f"Could not connect to Grants.gov: {exc}"
        ) from exc

    result = response.json()

    if result.get("errorcode") != 0:
        raise GrantsGovError(
            result.get("msg", "Unknown Grants.gov API error")
        )

    data = result.get("data", {})

    if return_data:
        return data

    return data.get("oppHits", [])


DISCOVERY_KEYWORDS = [
    "agriculture",
    "horticulture",
    '"plant science"',
    "genomics",
    '"plant pathology"',
    '"plant breeding"',
    "phenotyping",
    "robotics",
    "automation",
    '"STEM education"',
    '"workforce development"',
    "fellowship",
]


def search_discovery_profile(
    limit_per_query=5,
    statuses="forecasted|posted",
):
    """
    Run several broad Grants.gov searches and merge the results.

    Duplicate opportunities are removed using their Grants.gov ID.
    """

    merged_records = {}

    for keyword in DISCOVERY_KEYWORDS:
        records = search_opportunities(
            limit=limit_per_query,
            statuses=statuses,
            keyword=keyword,
        )

        for record in records:
            external_id = str(record.get("id") or "").strip()

            if external_id:
                merged_records[external_id] = record

    return list(merged_records.values())

def fetch_opportunity(opportunity_id):
    """
    Retrieve the full Grants.gov detail record for one opportunity.

    This function only retrieves data.
    It does not modify the Django database.
    """

    payload = {
        "opportunityId": int(opportunity_id),
    }

    try:
        response = requests.post(
            FETCH_URL,
            json=payload,
            timeout=30,
        )

        response.raise_for_status()

    except requests.RequestException as exc:
        raise GrantsGovError(
            f"Could not fetch Grants.gov opportunity {opportunity_id}: {exc}"
        ) from exc

    result = response.json()

    if result.get("errorcode") != 0:
        raise GrantsGovError(
            result.get(
                "msg",
                f"Unknown Grants.gov error for opportunity {opportunity_id}",
            )
        )

    return result.get("data", {})



def search_paginated(
    keyword,
    statuses="forecasted|posted",
    page_size=100,
    max_pages=5,
):
    """
    Fetch a bounded set of search pages.

    Returns records and coverage information.
    Does not write to the database.
    """
    if page_size < 1 or max_pages < 1:
        raise ValueError("page_size and max_pages must be positive.")

    merged = {}
    seen_pages = set()
    offset = 0
    reported_total = None
    total_changed = False
    pages_fetched = 0
    reason = "page limit reached"

    for _ in range(max_pages):
        data = search_opportunities(
            limit=page_size,
            start_record=offset,
            statuses=statuses,
            keyword=keyword,
            return_data=True,
        )

        hits = data.get("oppHits", [])
        if not isinstance(hits, list):
            raise GrantsGovError("Invalid search results from Grants.gov.")

        try:
            total = int(data["hitCount"])
        except (KeyError, TypeError, ValueError) as exc:
            raise GrantsGovError(
                "Grants.gov did not return a valid hitCount."
            ) from exc

        if total < 0:
            raise GrantsGovError("Grants.gov returned a negative hitCount.")

        if reported_total is None:
            reported_total = total
        elif total != reported_total:
            total_changed = True

        page_ids = []
        for record in hits:
            external_id = str(record.get("id") or "").strip()
            if not external_id:
                raise GrantsGovError(
                    "A search result has no Grants.gov ID."
                )
            page_ids.append(external_id)

        signature = tuple(page_ids)
        if signature in seen_pages and signature:
            reason = "repeated page"
            break

        seen_pages.add(signature)
        pages_fetched += 1

        for external_id, record in zip(page_ids, hits):
            merged[external_id] = record

        offset += len(hits)

        if offset >= total:
            reason = "reported total reached"
            break

        if not hits:
            reason = "empty page before reported total"
            break

    complete = (
        reported_total is not None
        and not total_changed
        and offset >= reported_total
        and len(merged) == reported_total
    )

    return {
        "records": list(merged.values()),
        "coverage": {
            "keyword": keyword,
            "statuses": statuses,
            "reported_total": reported_total,
            "rows_fetched": offset,
            "unique_records": len(merged),
            "pages_fetched": pages_fetched,
            "next_start_record": offset,
            "complete": complete,
            "reason": reason,
        },
    }
