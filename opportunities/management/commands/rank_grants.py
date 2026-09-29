from django.core.management.base import BaseCommand, CommandError

from opportunities.matching import LAB_PROFILES, rank_opportunities


class Command(BaseCommand):
    help = "Rank opportunities using approved tags and a lab profile."

    def add_arguments(self, parser):
        parser.add_argument(
            "--profile",
            choices=list(LAB_PROFILES.keys()),
            default="plant-tech",
        )

        parser.add_argument(
            "--limit",
            type=int,
            default=10,
        )

    def handle(self, *args, **options):
        if options["limit"] < 1:
            raise CommandError("--limit must be at least 1.")

        profile_key = options["profile"]
        profile = LAB_PROFILES[profile_key]

        ranked = rank_opportunities(profile_key)

        self.stdout.write(
            f"\nProfile: {profile['name']}"
        )
        self.stdout.write(
            "Scores are relevance points, not eligibility decisions.\n"
        )

        if not ranked:
            self.stdout.write(
                "No matching approved tags found yet."
            )
            return

        for result in ranked[:options["limit"]]:
            self.stdout.write(
                f"[{result['score']} points] "
                f"{result['opportunity'].title}"
            )

            self.stdout.write(
                "  Matched: " + ", ".join(result["matches"])
            )

        self.stdout.write(
            f"\n{len(ranked)} opportunities have matching approved tags."
        )
