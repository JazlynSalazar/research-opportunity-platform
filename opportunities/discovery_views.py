from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render

from opportunities.matching import (
    rank_opportunities,
)
from opportunities.models import (
    Opportunity,
    OpportunityCycle,
    ResearchProfile,
    Source,
)


@login_required
def discover(request):
    profiles = (
        ResearchProfile.objects
        .filter(
            owner=request.user,
            is_template=False,
            active=True,
        )
        .prefetch_related(
            "weights"
        )
        .order_by(
            "-is_default",
            "name",
        )
    )

    requested_profile = (
        request.GET
        .get("profile", "")
        .strip()
    )

    selected_profile = None

    if requested_profile.isdigit():
        selected_profile = (
            profiles
            .filter(
                pk=int(
                    requested_profile
                )
            )
            .first()
        )

    if selected_profile is None:
        selected_profile = (
            profiles
            .filter(
                is_default=True
            )
            .first()
        )

    if selected_profile is None:
        selected_profile = (
            profiles.first()
        )

    ranked = {}

    if selected_profile:
        ranked = {
            item[
                "opportunity"
            ].pk: item
            for item
            in rank_opportunities(
                selected_profile
            )
        }

    query = (
        request.GET
        .get("q", "")
        .strip()
    )

    source_name = (
        request.GET
        .get("source", "")
        .strip()
    )

    opportunity_type = (
        request.GET
        .get("type", "")
        .strip()
    )

    cycle_status = (
        request.GET
        .get("status", "")
        .strip()
    )

    mode = (
        request.GET
        .get("mode", "all")
        .strip()
    )

    if mode not in {
        "all",
        "relevant",
    }:
        mode = "all"

    if selected_profile is None:
        mode = "all"

    opportunities = (
        Opportunity.objects
        .select_related(
            "sponsor",
            "source",
        )
        .prefetch_related(
            "tags",
            "cycles__deadlines",
            "source_records__classification_reviews",
        )
    )

    if source_name:
        opportunities = (
            opportunities.filter(
                source__name=source_name
            )
        )

    if opportunity_type:
        opportunities = (
            opportunities.filter(
                opportunity_type=(
                    opportunity_type
                )
            )
        )

    if cycle_status:
        if cycle_status == "unknown":
            opportunities = (
                opportunities.filter(
                    Q(
                        cycles__status="unknown"
                    )
                    | Q(
                        cycles__isnull=True
                    )
                )
            )

        else:
            opportunities = (
                opportunities.filter(
                    cycles__status=(
                        cycle_status
                    )
                )
            )

    opportunities = (
        opportunities
        .distinct()
        .order_by("title")
    )

    results = []

    query_lower = (
        query.lower()
    )

    for opportunity in opportunities:
        ranking = ranked.get(
            opportunity.pk,
            {},
        )

        approved_score = (
            ranking.get(
                "approved_score",
                0,
            )
        )

        provisional_score = (
            ranking.get(
                "provisional_score",
                0,
            )
        )

        approved_matches = (
            ranking.get(
                "approved_matches",
                [],
            )
        )

        provisional_matches = (
            ranking.get(
                "provisional_matches",
                [],
            )
        )

        has_relevance = (
            approved_score > 0
            or provisional_score > 0
        )

        if (
            mode == "relevant"
            and not has_relevance
        ):
            continue

        source_tags = sorted({
            tag.name
            for tag
            in opportunity.tags.all()
        })

        pending_tags = set()

        for source_record in (
            opportunity
            .source_records
            .all()
        ):
            for review in (
                source_record
                .classification_reviews
                .all()
            ):
                if (
                    review.is_current
                    and review.decision
                    == "pending"
                ):
                    pending_tags.add(
                        review.suggestion_name
                    )

        cycle_text = []

        for cycle in (
            opportunity.cycles.all()
        ):
            cycle_text.extend(
                [
                    cycle.cycle_name
                    or "",
                    cycle.status
                    or "",
                ]
            )

            for deadline in (
                cycle.deadlines.all()
            ):
                if deadline.date:
                    cycle_text.append(
                        str(
                            deadline.date
                        )
                    )

        search_text = " ".join(
            [
                opportunity.title,
                opportunity.summary
                or "",
                (
                    opportunity
                    .sponsor.name
                    if opportunity.sponsor
                    else ""
                ),
                (
                    opportunity
                    .source.name
                    if opportunity.source
                    else ""
                ),
                (
                    opportunity
                    .opportunity_type
                    or ""
                ),
                (
                    opportunity
                    .eligibility_notes
                    or ""
                ),
                " ".join(
                    source_tags
                ),
                " ".join(
                    pending_tags
                ),
                " ".join(
                    approved_matches
                ),
                " ".join(
                    provisional_matches
                ),
                " ".join(
                    cycle_text
                ),
            ]
        ).lower()

        if (
            query_lower
            and query_lower
            not in search_text
        ):
            continue

        results.append(
            {
                "opportunity": (
                    opportunity
                ),
                "approved_score": (
                    approved_score
                ),
                "provisional_score": (
                    provisional_score
                ),
                "approved_matches": (
                    approved_matches
                ),
                "provisional_matches": (
                    provisional_matches
                ),
                "source_tags": (
                    source_tags
                ),
                "pending_tags": sorted(
                    pending_tags
                ),
            }
        )

    results.sort(
        key=lambda item: (
            -item[
                "approved_score"
            ],
            -item[
                "provisional_score"
            ],
            item[
                "opportunity"
            ].title.lower(),
        )
    )

    source_options = (
        Source.objects
        .filter(
            opportunities__isnull=False
        )
        .distinct()
        .order_by("name")
    )

    type_options = (
        Opportunity._meta
        .get_field(
            "opportunity_type"
        )
        .choices
    )

    status_options = (
        OpportunityCycle._meta
        .get_field(
            "status"
        )
        .choices
    )

    return render(
        request,
        "opportunities/discover.html",
        {
            "profiles": profiles,
            "selected_profile": (
                selected_profile
            ),
            "selected_profile_id": (
                selected_profile.pk
                if selected_profile
                else None
            ),
            "results": results,
            "query": query,
            "source_name": (
                source_name
            ),
            "opportunity_type": (
                opportunity_type
            ),
            "cycle_status": (
                cycle_status
            ),
            "mode": mode,
            "source_options": (
                source_options
            ),
            "type_options": (
                type_options
            ),
            "status_options": (
                status_options
            ),
        },
    )
