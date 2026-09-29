from django.conf import settings
from django.db import models


class ResearchProfile(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="research_profiles",
        null=True,
        blank=True,
        help_text=(
            "User who owns this profile. "
            "Starter templates do not have an owner."
        ),
    )

    key = models.SlugField(
        max_length=100,
        help_text=(
            "Internal identifier such as "
            "plant-genomics-pathology."
        ),
    )

    name = models.CharField(
        max_length=200,
    )

    description = models.TextField(
        blank=True,
    )

    active = models.BooleanField(
        default=True,
    )

    is_default = models.BooleanField(
        default=False,
        help_text=(
            "For user-owned profiles, indicates "
            "the user's default research profile."
        ),
    )

    is_template = models.BooleanField(
        default=False,
        help_text=(
            "Starter profile available for users "
            "to copy into their own account."
        ),
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = (
            "name",
        )

        constraints = [
            models.UniqueConstraint(
                fields=(
                    "key",
                ),
                condition=models.Q(
                    is_template=True,
                ),
                name=(
                    "unique_research_profile_template_key"
                ),
            ),

            models.UniqueConstraint(
                fields=(
                    "owner",
                    "key",
                ),
                condition=models.Q(
                    is_template=False,
                    owner__isnull=False,
                ),
                name=(
                    "unique_user_research_profile_key"
                ),
            ),
        ]

    def __str__(self):
        if self.is_template:
            return f"{self.name} (Template)"

        if self.owner:
            return (
                f"{self.name} "
                f"({self.owner.get_username()})"
            )

        return self.name


class ResearchProfileWeight(models.Model):
    CATEGORY_CHOICES = [
        (
            "domain",
            "Research Domain",
        ),
        (
            "method",
            "Method / Technology",
        ),
        (
            "purpose",
            "Purpose",
        ),
        (
            "career",
            "Career Stage",
        ),
        (
            "other",
            "Other",
        ),
    ]

    profile = models.ForeignKey(
        ResearchProfile,
        on_delete=models.CASCADE,
        related_name="weights",
    )

    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
    )

    name = models.CharField(
        max_length=100,
    )

    weight = models.PositiveSmallIntegerField(
        default=1,
        help_text=(
            "Higher numbers mean a stronger "
            "relevance signal. These are ranking "
            "points, not probabilities."
        ),
    )

    class Meta:
        ordering = (
            "profile",
            "category",
            "name",
        )

        constraints = [
            models.UniqueConstraint(
                fields=(
                    "profile",
                    "category",
                    "name",
                ),
                name=(
                    "unique_research_profile_weight"
                ),
            ),
        ]

    def __str__(self):
        return (
            f"{self.profile.name}: "
            f"{self.category} / "
            f"{self.name} "
            f"({self.weight})"
        )
