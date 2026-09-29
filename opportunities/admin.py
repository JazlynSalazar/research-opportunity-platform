from django.contrib import admin

from .models import (
    ClassificationResult,
    Deadline,
    EligibilityCriterion,
    ImportRun,
    Opportunity,
    OpportunityCycle,
    Source,
    SourceRecord,
    Sponsor,
    Tag,
)

from django.utils import timezone
from .models import ClassificationReview

@admin.register(Sponsor)
class SponsorAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "sponsor_type",
        "website",
    )

    list_filter = ("sponsor_type",)
    search_fields = ("name",)


@admin.register(EligibilityCriterion)
class EligibilityCriterionAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "criterion_type",
    )

    list_filter = ("criterion_type",)
    search_fields = ("name", "description")


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ("name", "source_type", "active")
    list_filter = ("source_type", "active")
    search_fields = ("name",)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "category")
    list_filter = ("category",)
    search_fields = ("name",)


class OpportunityCycleInline(admin.TabularInline):
    model = OpportunityCycle
    extra = 0

    fields = (
        "cycle_name",
        "status",
        "open_date",
        "award_min",
        "award_max",
        "award_duration_months",
        "cost_share_required",
        "last_verified",
    )

    show_change_link = True


@admin.register(Opportunity)
class OpportunityAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "sponsor",
        "opportunity_type",
        "recurring",
    )

    list_filter = (
        "opportunity_type",
        "recurring",
        "sponsor",
        "tags",
    )

    search_fields = (
        "title",
        "summary",
        "eligibility_notes",
    )

    fields = (
        "title",
        "sponsor",
        "source",
        "opportunity_type",
        "summary",
        "url",
        "recurring",
        "recurrence_notes",
        "eligibility_notes",
        "tags",
        "eligibility_criteria",
    )

    filter_horizontal = (
        "tags",
        "eligibility_criteria",
    )

    inlines = [OpportunityCycleInline]


class DeadlineInline(admin.TabularInline):
    model = Deadline
    extra = 1


@admin.register(OpportunityCycle)
class OpportunityCycleAdmin(admin.ModelAdmin):
    list_display = (
        "opportunity",
        "cycle_name",
        "status",
        "open_date",
        "last_verified",
    )

    list_filter = (
        "status",
        "opportunity__sponsor",
    )

    search_fields = (
        "opportunity__title",
        "cycle_name",
    )

    inlines = [DeadlineInline]


@admin.register(Deadline)
class DeadlineAdmin(admin.ModelAdmin):
    list_display = (
        "cycle",
        "deadline_type",
        "date",
    )

    list_filter = ("deadline_type",)

    search_fields = (
        "cycle__opportunity__title",
        "cycle__cycle_name",
    )


class SourceRecordInline(admin.TabularInline):
    model = SourceRecord
    extra = 0

    fields = (
        "title",
        "external_id",
        "processing_status",
        "last_seen",
    )

    readonly_fields = (
        "title",
        "external_id",
        "processing_status",
        "last_seen",
    )

    can_delete = False
    show_change_link = True

@admin.register(ImportRun)
class ImportRunAdmin(admin.ModelAdmin):
    list_display = (
        "source",
        "status",
        "started_at",
        "finished_at",
        "records_found",
        "records_created",
        "records_updated",
    )

    list_filter = (
        "source",
        "status",
    )

    readonly_fields = (
        "started_at",
        "finished_at",
    )


    inlines = [SourceRecordInline]


@admin.register(SourceRecord)
class SourceRecordAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "source",
        "external_id",
        "processing_status",
        "last_seen",
    )

    list_filter = (
        "source",
        "processing_status",
    )

    search_fields = (
        "title",
        "external_id",
    )

    readonly_fields = (
        "raw_data",
        "first_seen",
        "last_seen",
    )

@admin.register(ClassificationResult)
class ClassificationResultAdmin(admin.ModelAdmin):
    list_display = (
        "source_record",
        "rules_version",
        "classified_at",
    )

    search_fields = (
        "source_record__title",
        "source_record__external_id",
    )

    readonly_fields = (
        "source_record",
        "rules_version",
        "source_hash",
        "suggestions",
        "classified_at",
    )

@admin.register(ClassificationReview)
class ClassificationReviewAdmin(admin.ModelAdmin):
    list_display = (
        "suggestion_name",
        "suggestion_category",
        "source_record",
        "decision",
        "is_current",
        "reviewed_by",
    )

    list_filter = (
        "decision",
        "is_current",
        "suggestion_category",
    )

    search_fields = (
        "suggestion_name",
        "source_record__title",
        "source_record__external_id",
    )

    readonly_fields = (
        "source_record",
        "suggestion_name",
        "suggestion_category",
        "evidence",
        "decision",
        "is_current",
        "reviewed_by",
        "reviewed_at",
    )

    actions = [
        "approve_selected",
        "reject_selected",
        "reset_selected",
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Approve selected current suggestions")
    def approve_selected(self, request, queryset):
        count = queryset.filter(is_current=True).update(
            decision=ClassificationReview.Decision.APPROVED,
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )
        self.message_user(request, f"Approved {count} suggestions.")

    @admin.action(description="Reject selected current suggestions")
    def reject_selected(self, request, queryset):
        count = queryset.filter(is_current=True).update(
            decision=ClassificationReview.Decision.REJECTED,
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )
        self.message_user(request, f"Rejected {count} suggestions.")

    @admin.action(description="Reset selected suggestions to pending")
    def reset_selected(self, request, queryset):
        count = queryset.update(
            decision=ClassificationReview.Decision.PENDING,
            reviewed_by=None,
            reviewed_at=None,
        )
        self.message_user(request, f"Reset {count} suggestions.")
