import hashlib
import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from opportunities.classifiers.rules import (
    RULES_VERSION,
    classify_text,
)
from opportunities.classifiers.source_text import get_classification_text

CLASSIFICATION_VERSION = RULES_VERSION + "-sources-v4"
from opportunities.models import (
    ClassificationResult,
    ClassificationReview,
    SourceRecord,
)


class Command(BaseCommand):
    help = "Save classification suggestions and synchronize their reviews."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=10,
            help="Maximum number of enriched records to inspect.",
        )
        parser.add_argument(
            "--source",
            action="append",
            choices=[
                "Grants.gov API",
                "NSF Funding RSS",
                "AFE Funding Pages",
                "HRI Funding Pages",
                "MSU Funding Pages",
                "BSA Funding Pages",
            ],
            help="Source to classify; repeat for multiple sources.",
        )

        parser.add_argument(
            "--id",
            type=str,
            help="Classify one specific Grants.gov external ID.",
        )
        parser.add_argument(
            "--refresh",
            action="store_true",
            help="Reclassify even if the source data has not changed.",
        )

    def handle(self, *args, **options):
        limit = options["limit"]

        if limit < 1:
            raise CommandError("--limit must be at least 1.")

        source_names = options["source"] or ["Grants.gov API"]

        records = (
            SourceRecord.objects
            .filter(source__name__in=source_names)
            .select_related("source")
            .order_by("id")
        )

        if options["id"]:
            records = records.filter(
                external_id=options["id"]
            )

        inspected = 0
        saved_count = 0
        unchanged_count = 0
        created_reviews = 0
        error_count = 0

        for source_record in records:
            try:
                classification_text = get_classification_text(
                    source_record
                )
            except ValueError:
                continue

            source_hash = hashlib.sha256(
                json.dumps(
                    {
                        "source": source_record.source.name,
                        "text": classification_text,
                    },
                    sort_keys=True,
                    ensure_ascii=False,
                ).encode("utf-8")
            ).hexdigest()

            # Skip records that are already fully classified.
            # Still process records with missing or outdated reviews.
            if not options["refresh"]:
                previous = ClassificationResult.objects.filter(
                    source_record=source_record
                ).first()

                if (
                    previous
                    and previous.rules_version == CLASSIFICATION_VERSION
                    and previous.source_hash == source_hash
                ):
                    expected_keys = {
                        (item["category"], item["name"])
                        for item in previous.suggestions or []
                    }

                    current_keys = set(
                        ClassificationReview.objects.filter(
                            source_record=source_record,
                            is_current=True,
                        ).values_list(
                            "suggestion_category",
                            "suggestion_name",
                        )
                    )

                    if expected_keys == current_keys:
                        continue

            inspected += 1

            try:
                with transaction.atomic():
                    existing = ClassificationResult.objects.filter(
                        source_record=source_record
                    ).first()

                    unchanged = (
                        existing is not None
                        and not options["refresh"]
                        and existing.rules_version == CLASSIFICATION_VERSION
                        and existing.source_hash == source_hash
                    )

                    if unchanged:
                        # Reuse saved suggestions, but still synchronize
                        # their review rows.
                        suggestions = existing.suggestions or []
                        unchanged_count += 1
                    else:
                        suggestions = classify_text(
                            classification_text
                        )

                        ClassificationResult.objects.update_or_create(
                            source_record=source_record,
                            defaults={
                                "rules_version": CLASSIFICATION_VERSION,
                                "source_hash": source_hash,
                                "suggestions": suggestions,
                            },
                        )

                        saved_count += 1

                    # Mark old suggestions inactive. Matching suggestions
                    # will be made current again below.
                    reviews = ClassificationReview.objects.filter(
                        source_record=source_record
                    )

                    reviews.update(is_current=False)

                    new_for_record = 0

                    for item in suggestions:
                        review, created = (
                            ClassificationReview.objects.update_or_create(
                                source_record=source_record,
                                suggestion_name=item["name"],
                                suggestion_category=item["category"],
                                defaults={
                                    "evidence": item["evidence"],
                                    "is_current": True,
                                },
                            )
                        )

                        # Existing decision, reviewer, and review date
                        # are deliberately NOT overwritten.
                        if created:
                            new_for_record += 1

                    created_reviews += new_for_record

                self.stdout.write(
                    f"{source_record.external_id}: "
                    f"{len(suggestions)} suggestions; "
                    f"{new_for_record} new reviews."
                )

            except Exception as exc:
                error_count += 1
                self.stderr.write(
                    f"Error on {source_record.external_id}: {exc}"
                )

            if inspected >= limit:
                break

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Saved {saved_count} classifications; "
                f"reused {unchanged_count} unchanged; "
                f"created {created_reviews} reviews; "
                f"errors {error_count}."
            )
        )
