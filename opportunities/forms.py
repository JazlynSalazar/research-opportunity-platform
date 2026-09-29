from django import forms

from opportunities.models import (
    ResearchProfile,
    ResearchProfileWeight,
)


class ResearchProfileForm(forms.ModelForm):
    class Meta:
        model = ResearchProfile

        fields = (
            "name",
            "description",
        )

        widgets = {
            "name": forms.TextInput(
                attrs={
                    "placeholder": (
                        "Example: Plant Disease Genomics"
                    ),
                }
            ),

            "description": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": (
                        "Describe the research areas and "
                        "funding goals this profile represents."
                    ),
                }
            ),
        }


class ResearchProfileWeightForm(forms.ModelForm):
    IMPORTANCE_CHOICES = [
        (1, "Low"),
        (3, "Medium"),
        (5, "High"),
    ]

    weight = forms.TypedChoiceField(
        choices=IMPORTANCE_CHOICES,
        coerce=int,
        initial=3,
        label="Importance",
    )

    class Meta:
        model = ResearchProfileWeight

        fields = (
            "category",
            "name",
            "weight",
        )

        widgets = {
            "name": forms.TextInput(
                attrs={
                    "list": "signal-suggestions",
                    "placeholder": (
                        "Example: Genomics"
                    ),
                }
            ),
        }

    def clean_name(self):
        return self.cleaned_data[
            "name"
        ].strip()
