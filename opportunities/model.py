from django.db import models


class Sponsor(models.Model):
    name = models.CharField(max_length=200)
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
