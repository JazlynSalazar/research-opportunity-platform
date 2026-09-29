from opportunities.models import (
    ClassificationReview,
    ResearchProfile,
)


def rank_opportunities(profile):
    """
    Rank opportunities against a ResearchProfile.

    Approved classifications and pending classifications
    are scored separately.

    Scores are relevance points only. They do not represent
    eligibility, probability of funding, or application quality.
    """

    if not isinstance(
        profile,
        ResearchProfile,
    ):
        raise TypeError(
            "profile must be a ResearchProfile."
        )

    weights = {
        (
            weight.category,
            weight.name,
        ): weight.weight
        for weight in profile.weights.all()
    }

    reviews = (
        ClassificationReview.objects
        .filter(
            decision__in=[
                ClassificationReview.Decision.APPROVED,
                ClassificationReview.Decision.PENDING,
            ],
            is_current=True,
            source_record__opportunity__isnull=False,
        )
        .select_related(
            "source_record__opportunity"
        )
    )

    results = {}

    for review in reviews:
        opportunity = (
            review
            .source_record
            .opportunity
        )

        tag_key = (
            review.suggestion_category,
            review.suggestion_name,
        )

        weight = weights.get(
            tag_key,
            0,
        )

        if weight == 0:
            continue

        if opportunity.pk not in results:
            results[opportunity.pk] = {
                "opportunity": opportunity,
                "approved": {},
                "provisional": {},
            }

        result = results[
            opportunity.pk
        ]

        if (
            review.decision
            == ClassificationReview.Decision.APPROVED
        ):
            result[
                "approved"
            ][tag_key] = (
                review.suggestion_name
            )

            # Approved evidence takes precedence over
            # provisional evidence for the same signal.
            result[
                "provisional"
            ].pop(
                tag_key,
                None,
            )

        elif (
            tag_key
            not in result["approved"]
        ):
            result[
                "provisional"
            ][tag_key] = (
                review.suggestion_name
            )

    ranked = []

    for result in results.values():
        approved_score = sum(
            weights[tag_key]
            for tag_key
            in result[
                "approved"
            ]
        )

        provisional_score = sum(
            weights[tag_key]
            for tag_key
            in result[
                "provisional"
            ]
        )

        ranked.append(
            {
                "opportunity": (
                    result[
                        "opportunity"
                    ]
                ),
                "approved_score": (
                    approved_score
                ),
                "provisional_score": (
                    provisional_score
                ),
                "approved_matches": sorted(
                    result[
                        "approved"
                    ].values()
                ),
                "provisional_matches": sorted(
                    result[
                        "provisional"
                    ].values()
                ),
            }
        )

    # Human-reviewed evidence ranks first.
    # Provisional evidence breaks ties and makes
    # newly collected opportunities discoverable.
    ranked.sort(
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

    return ranked
