from django.core.management.base import BaseCommand

from opportunities.models import (
    ResearchProfile,
    ResearchProfileWeight,
)


PROFILES = {
    "plant-tech": {
        "name": (
            "Plant Science and Agricultural Technology"
        ),
        "description": (
            "General profile combining plant science, "
            "genomics, agricultural technology, "
            "phenotyping, education, and automation."
        ),
        "weights": {
            ("domain", "Plant Science"): 5,
            ("domain", "Agriculture"): 2,

            ("method", "Genomics"): 4,
            ("method", "Robotics"): 4,
            ("method", "Automation"): 3,
            ("method", "Phenotyping"): 4,
            ("method", "Imaging"): 2,
            ("method", "Bioinformatics"): 3,

            ("purpose", "Education"): 2,
            (
                "purpose",
                "Workforce Development",
            ): 2,
            ("purpose", "Extension"): 1,
            (
                "purpose",
                "Fellowship Support",
            ): 1,
        },
    },

    "plant-genomics-pathology": {
        "name": (
            "Plant Genomics and Pathology"
        ),
        "description": (
            "Plant genomics, pathology, breeding, "
            "phenotyping, imaging, and "
            "bioinformatics opportunities."
        ),
        "weights": {
            ("domain", "Plant Science"): 5,
            ("domain", "Agriculture"): 2,

            ("method", "Genomics"): 5,
            ("method", "Bioinformatics"): 4,
            ("method", "Phenotyping"): 4,
            ("method", "Imaging"): 2,

            ("purpose", "Extension"): 1,
        },
    },

    "ag-tech-robotics": {
        "name": (
            "Agricultural Robotics and Technology"
        ),
        "description": (
            "Agricultural robotics, automation, "
            "imaging, phenotyping, and research "
            "technology opportunities."
        ),
        "weights": {
            ("domain", "Agriculture"): 4,
            ("domain", "Plant Science"): 3,

            ("method", "Robotics"): 5,
            ("method", "Automation"): 5,
            ("method", "Phenotyping"): 4,
            ("method", "Imaging"): 3,

            ("purpose", "Education"): 2,
            (
                "purpose",
                "Workforce Development",
            ): 3,
        },
    },

    "education-workforce": {
        "name": (
            "Education and Workforce Development"
        ),
        "description": (
            "Science education, extension, "
            "workforce development, and "
            "technology-training opportunities."
        ),
        "weights": {
            ("domain", "Agriculture"): 2,
            ("domain", "Plant Science"): 2,

            ("method", "Robotics"): 2,
            ("method", "Automation"): 2,

            ("purpose", "Education"): 5,
            (
                "purpose",
                "Workforce Development",
            ): 5,
            ("purpose", "Extension"): 4,
        },
    },

    "graduate-fellowships": {
        "name": (
            "Graduate Fellowships and Awards"
        ),
        "description": (
            "Graduate fellowships, scholarships, "
            "student awards, and related support."
        ),
        "weights": {
            (
                "purpose",
                "Fellowship Support",
            ): 5,
            ("purpose", "Education"): 1,
        },
    },
}


class Command(BaseCommand):
    help = (
        "Create or update starter research "
        "profile templates."
    )

    def handle(
        self,
        *args,
        **options,
    ):
        profile_count = 0
        created_count = 0
        weight_count = 0

        for key, settings in PROFILES.items():

            # Look for the original seeded profile first.
            # This lets us convert the existing proof-of-concept
            # records into templates instead of creating duplicates.
            profile = (
                ResearchProfile.objects
                .filter(
                    key=key,
                    owner__isnull=True,
                )
                .order_by("pk")
                .first()
            )

            if profile is None:
                profile = (
                    ResearchProfile.objects.create(
                        key=key,
                        name=settings["name"],
                        description=settings[
                            "description"
                        ],
                        active=True,
                        is_default=False,
                        is_template=True,
                        owner=None,
                    )
                )

                created_count += 1

            else:
                profile.name = settings[
                    "name"
                ]

                profile.description = settings[
                    "description"
                ]

                profile.active = True
                profile.is_default = False
                profile.is_template = True
                profile.owner = None

                profile.save(
                    update_fields=[
                        "name",
                        "description",
                        "active",
                        "is_default",
                        "is_template",
                        "owner",
                    ]
                )

            profile_count += 1

            self.stdout.write(
                f"Template ready: "
                f"{profile.name}"
            )

            for (
                category,
                name,
            ), weight in settings[
                "weights"
            ].items():

                _, created = (
                    ResearchProfileWeight.objects
                    .update_or_create(
                        profile=profile,
                        category=category,
                        name=name,
                        defaults={
                            "weight": weight,
                        },
                    )
                )

                if created:
                    weight_count += 1

        self.stdout.write("")

        self.stdout.write(
            self.style.SUCCESS(
                f"Starter templates ready: "
                f"{profile_count} processed, "
                f"{created_count} new profiles, "
                f"{weight_count} new weights."
            )
        )
