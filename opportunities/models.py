from django.db import models

from opportunities.profile_models import (
    ResearchProfile,
    ResearchProfileWeight,
)

class Sponsor(models.Model):
    SPONSOR_TYPES = [
        ("federal", "Federal Agency"),
        ("state", "State / Local Government"),
        ("foundation", "Foundation"),
        ("society", "Professional Society"),
        ("industry", "Industry / Company"),
        ("university", "University / Internal"),
        ("nonprofit", "Nonprofit Organization"),
        ("other", "Other"),
    ]

    name = models.CharField(max_length=200)

    sponsor_type = models.CharField(
        max_length=30,
        choices=SPONSOR_TYPES,
        default="other",
    )

    website = models.URLField(blank=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name
 
class Source(models.Model):
    SOURCE_TYPES = [
        ("api", "API"),
        ("website", "Website"),
        ("feed", "RSS / Data Feed"),
        ("manual", "Manual Entry"),
    ]

    name = models.CharField(max_length=200)
    url = models.URLField(blank=True)
    source_type = models.CharField(
        max_length=20,
        choices=SOURCE_TYPES,
        default="website",
    )
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Tag(models.Model):
    TAG_CATEGORIES = [
        ("domain", "Research Domain"),
        ("method", "Method / Technology"),
        ("purpose", "Purpose"),
        ("career", "Career Stage"),
        ("other", "Other"),
    ]

    name = models.CharField(max_length=100)
    category = models.CharField(
        max_length=20,
        choices=TAG_CATEGORIES,
        default="domain",
    )

    def __str__(self):
        return self.name

class EligibilityCriterion(models.Model):
    CRITERION_TYPES = [
        ("applicant", "Applicant Type"),
        ("career", "Career Stage"),
        ("organization", "Organization Type"),
        ("citizenship", "Citizenship / Residency"),
        ("geography", "Geographic Eligibility"),
        ("institution", "Institution Requirement"),
        ("other", "Other"),
    ]

    name = models.CharField(max_length=150)

    criterion_type = models.CharField(
        max_length=30,
        choices=CRITERION_TYPES,
    )

    description = models.TextField(blank=True)

    class Meta:
        ordering = ("criterion_type", "name")
        constraints = [
            models.UniqueConstraint(
                fields=("criterion_type", "name"),
                name="unique_eligibility_criterion",
            )
        ]

    def __str__(self):
        return f"{self.get_criterion_type_display()}: {self.name}"

class Opportunity(models.Model):
    OPPORTUNITY_TYPES = [
        ("research", "Research Grant"),
        ("fellowship", "Fellowship"),
        ("education", "Education Grant"),
        ("equipment", "Equipment / Research Resources"),
        ("travel", "Travel Award"),
        ("training", "Training Program"),
        ("other", "Other"),
    ]

    STATUS_CHOICES = [
        ("forecasted", "Forecasted"),
        ("open", "Open"),
        ("closed", "Closed"),
        ("unknown", "Unknown"),
    ]

    title = models.CharField(max_length=300)

    sponsor = models.ForeignKey(
        Sponsor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="opportunities",
    )

    source = models.ForeignKey(
        Source,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="opportunities",
    )

    opportunity_type = models.CharField(
        max_length=30,
        choices=OPPORTUNITY_TYPES,
        default="research",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="unknown",
    )

    summary = models.TextField(blank=True)
    url = models.URLField(blank=True)

    open_date = models.DateField(null=True, blank=True)
    deadline = models.DateField(null=True, blank=True)

    recurring = models.BooleanField(default=False)

    recurrence_notes = models.CharField(
        max_length=300,
        blank=True,
        help_text="Example: Usually opens each spring.",
    )

    award_min = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    award_max = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    eligibility_notes = models.TextField(blank=True)

    eligibility_criteria = models.ManyToManyField(
        EligibilityCriterion,
        blank=True,
        related_name="opportunities",
    )

    tags = models.ManyToManyField(
        Tag,
        blank=True,
        related_name="opportunities",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Opportunity"
        verbose_name_plural = "Opportunities"

    def __str__(self):
        return self.title


class OpportunityCycle(models.Model):
    STATUS_CHOICES = [
        ("forecasted", "Forecasted"),
        ("open", "Open"),
        ("closed", "Closed"),
        ("unknown", "Unknown"),
    ]

    opportunity = models.ForeignKey(
        Opportunity,
        on_delete=models.CASCADE,
        related_name="cycles",
    )

    cycle_name = models.CharField(
        max_length=100,
        help_text="Example: 2027, Fall 2027, FY2028",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="unknown",
    )

    open_date = models.DateField(null=True, blank=True)

    award_min = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    award_max = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    award_duration_months = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum project duration in months.",
    )

    cost_share_required = models.BooleanField(
        null=True,
        blank=True,
        help_text="Leave unknown if the solicitation is unclear.",
    )

    external_id = models.CharField(
        max_length=150,
        blank=True,
        help_text="Agency or source identifier, such as a Grants.gov Opportunity Number.",
    )

    source_url = models.URLField(blank=True)
    notes = models.TextField(blank=True)

    last_verified = models.DateField(
        null=True,
        blank=True,
    )

    def __str__(self):
        return f"{self.opportunity.title} — {self.cycle_name}"


class Deadline(models.Model):
    DEADLINE_TYPES = [
        ("loi", "Letter of Intent"),
        ("preproposal", "Preproposal"),
        ("application", "Full Application"),
        ("nomination", "Nomination"),
        ("rolling", "Rolling Deadline"),
        ("other", "Other"),
    ]

    cycle = models.ForeignKey(
        OpportunityCycle,
        on_delete=models.CASCADE,
        related_name="deadlines",
    )

    deadline_type = models.CharField(
        max_length=30,
        choices=DEADLINE_TYPES,
        default="application",
    )

    date = models.DateField(
        null=True,
        blank=True,
    )

    notes = models.CharField(
        max_length=300,
        blank=True,
    )

    def __str__(self):
        return f"{self.cycle} — {self.get_deadline_type_display()}"

class ImportRun(models.Model):
    STATUS_CHOICES = [
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    source = models.ForeignKey(
        Source,
        on_delete=models.CASCADE,
        related_name="import_runs",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="running",
    )

    started_at = models.DateTimeField(auto_now_add=True)

    finished_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    records_found = models.PositiveIntegerField(default=0)
    records_created = models.PositiveIntegerField(default=0)
    records_updated = models.PositiveIntegerField(default=0)

    error_message = models.TextField(blank=True)
    coverage = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.source.name} — {self.started_at:%Y-%m-%d %H:%M}"

class SourceRecord(models.Model):
    PROCESSING_STATUS = [
        ("new", "New"),
        ("processed", "Processed"),
        ("review", "Needs Review"),
        ("ignored", "Ignored"),
        ("error", "Error"),
    ]

    source = models.ForeignKey(
        Source,
        on_delete=models.CASCADE,
        related_name="records",
    )

    import_run = models.ForeignKey(
        ImportRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="records",
    )

    external_id = models.CharField(max_length=200)

    title = models.CharField(
        max_length=500,
        blank=True,
    )

    source_url = models.URLField(blank=True)

    raw_data = models.JSONField()

    processing_status = models.CharField(
        max_length=20,
        choices=PROCESSING_STATUS,
        default="new",
    )

    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)

    opportunity = models.ForeignKey(
        Opportunity,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_records",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("source", "external_id"),
                name="unique_source_external_record",
            )
        ]

    def __str__(self):
        return self.title or self.external_id

class ClassificationResult(models.Model):
    source_record = models.OneToOneField(
        SourceRecord,
        on_delete=models.CASCADE,
        related_name="classification_result",
    )

    rules_version = models.CharField(
        max_length=32,
        default="rules-v1",
    )

    source_hash = models.CharField(
        max_length=64,
        blank=True,
    )

    suggestions = models.JSONField(default=list)

    classified_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Classification: {self.source_record}"

class ClassificationReview(models.Model):
    class Decision(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    source_record = models.ForeignKey(
        SourceRecord,
        on_delete=models.CASCADE,
        related_name="classification_reviews",
    )

    suggestion_name = models.CharField(max_length=100)
    suggestion_category = models.CharField(max_length=50)
    evidence = models.JSONField(default=list)

    decision = models.CharField(
        max_length=20,
        choices=Decision.choices,
        default=Decision.PENDING,
    )

    is_current = models.BooleanField(default=True)

    reviewed_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "source_record",
                    "suggestion_name",
                    "suggestion_category",
                ],
                name="unique_classification_review",
            )
        ]

    def __str__(self):
        return (
            f"{self.suggestion_name} — "
            f"{self.source_record.external_id}"
        )


class PipelineRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        PARTIAL = "partial", "Completed with errors"
        FAILED = "failed", "Failed"

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.RUNNING,
    )

    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    # Each stage will record its outcome here.
    stages = models.JSONField(default=list)

    error_message = models.TextField(blank=True)

    def __str__(self):
        return f"Update {self.pk} — {self.status}"
