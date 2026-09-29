import hashlib
import json
from urllib.parse import urlsplit, urlunsplit

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from opportunities.management.commands.import_msu import PROGRAMS
from opportunities.models import ImportRun, Source, SourceRecord


SOURCE_NAME = "MSU Funding Pages"


def official_url(value):
    """Normalize an official MSU URL without discarding its query."""
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower()

    allowed = (
        host == "msu.edu"
        or host.endswith(".msu.edu")
        or host == "msu.academicworks.com"
    )

    if (
        parsed.scheme != "https"
        or not allowed
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise ValueError("Not an approved HTTPS MSU URL.")

    return urlunsplit((
        "https",
        host,
        parsed.path.rstrip("/") or "/",
        parsed.query,
        "",
    ))


def candidate_id(url):
    return "msu-link:" + hashlib.sha256(
        url.encode("utf-8")
    ).hexdigest()


class Command(BaseCommand):
    help = "Stage discovered MSU funding links as unverified candidates."

    def add_arguments(self, parser):
        parser.add_argument(
            "--directory",
            choices=[
                key for key, value in PROGRAMS.items()
                if value.get("kind") == "directory"
            ],
            help="Use one directory; omit to use all saved scans.",
        )
        parser.add_argument(
            "--save",
            action="store_true",
            help="Save the candidates. Without this, only preview them.",
        )

    def handle(self, *args, **options):
        source = Source.objects.filter(name=SOURCE_NAME).first()

        if source is None:
            raise CommandError(
                "MSU Funding Pages is not staged. Run import_msu first."
            )

        existing_records = list(
            SourceRecord.objects.filter(source=source).order_by("pk")
        )

        # Recognize existing programs, directories, and candidates
        # by URL so we do not create duplicate records.
        existing_by_url = {}

        for record in existing_records:
            raw = record.raw_data or {}
            program = raw.get("program") or {}

            for value in (
                record.source_url,
                program.get("url"),
                (raw.get("page") or {}).get("url"),
            ):
                if value:
                    try:
                        existing_by_url[official_url(value)] = record
                    except ValueError:
                        pass

        configured_urls = {
            official_url(program["url"])
            for program in PROGRAMS.values()
        }

        directory_keys = [
            key for key, value in PROGRAMS.items()
            if value.get("kind") == "directory"
        ]

        if options["directory"]:
            directory_keys = [options["directory"]]

        candidates = {}
        scanned = 0
        skipped_external = 0
        skipped_known = 0

        for key in directory_keys:
            record = SourceRecord.objects.filter(
                source=source,
                external_id=key,
            ).first()

            if record is None:
                continue

            raw = record.raw_data or {}
            discovery = raw.get("directory_discovery")

            if not discovery:
                continue

            scanned += 1

            for item in discovery.get("candidates", []):
                try:
                    url = official_url(item.get("url") or "")
                except ValueError:
                    skipped_external += 1
                    continue

                if url in configured_urls:
                    skipped_known += 1
                    continue

                existing = existing_by_url.get(url)

                # Never turn an existing program or directory
                # back into an unverified candidate.
                if existing is not None:
                    existing_kind = (
                        (existing.raw_data or {})
                        .get("program", {})
                        .get("kind")
                    )

                    if existing_kind != "candidate":
                        skipped_known += 1
                        continue

                title = (item.get("title") or "").strip() or url

                entry = candidates.setdefault(
                    url,
                    {
                        "title": title,
                        "url": url,
                        "discovered_from": [],
                    },
                )

                entry["discovered_from"].append({
                    "directory_key": key,
                    "directory_title": PROGRAMS[key]["title"],
                    "directory_url": discovery.get("source_url"),
                    "link_text": title,
                })

        if scanned == 0:
            raise CommandError(
                "No saved MSU directory scans were found. "
                "Run discover_msu_funding first."
            )

        self.stdout.write(
            f"Found {len(candidates)} unique MSU-hosted candidate links."
        )
        self.stdout.write(
            f"Skipped {skipped_known} known-program links and "
            f"{skipped_external} external or unsupported links."
        )

        if not options["save"]:
            for item in list(candidates.values())[:20]:
                self.stdout.write(
                    f"  {item['title']}\n  {item['url']}"
                )

            if len(candidates) > 20:
                self.stdout.write(
                    f"  ...and {len(candidates) - 20} more."
                )

            self.stdout.write(
                "\nPreview only. Use --save to stage these candidates."
            )
            return

        run = ImportRun.objects.create(
            source=source,
            status="running",
        )

        created_count = 0
        updated_count = 0

        try:
            with transaction.atomic():
                for url, item in candidates.items():
                    existing = existing_by_url.get(url)

                    if existing is not None:
                        record = existing
                        created = False
                    else:
                        record, created = (
                            SourceRecord.objects.get_or_create(
                                source=source,
                                external_id=candidate_id(url),
                                defaults={
                                    "title": item["title"][:500],
                                    "source_url": url,
                                    "raw_data": {
                                        "program": {
                                            "kind": "candidate",
                                            "title": item["title"],
                                            "url": url,
                                        },
                                        "discovered_from": [],
                                    },
                                    "processing_status": "new",
                                },
                            )
                        )

                    raw = dict(record.raw_data or {})
                    program = raw.get("program") or {}

                    if program.get("kind") != "candidate":
                        continue

                    # Preserve any existing page text, review data,
                    # and other metadata.
                    old_raw = dict(raw)
                    raw["program"] = {
                        **program,
                        "kind": "candidate",
                        "title": program.get("title") or item["title"],
                        "url": url,
                    }

                    provenance = {
                        json.dumps(entry, sort_keys=True): entry
                        for entry in raw.get("discovered_from", [])
                    }

                    for entry in item["discovered_from"]:
                        provenance[json.dumps(
                            entry, sort_keys=True
                        )] = entry

                    raw["discovered_from"] = list(provenance.values())

                    changed = old_raw != raw

                    record.raw_data = raw
                    record.import_run = run
                    record.save(update_fields=["raw_data", "import_run"])

                    if created:
                        created_count += 1
                    elif changed:
                        updated_count += 1

                run.status = "completed"
                run.finished_at = timezone.now()
                run.records_found = len(candidates)
                run.records_created = created_count
                run.records_updated = updated_count
                run.coverage = {
                    "scope": "Saved MSU directory candidate links",
                    "directories_scanned": scanned,
                    "unique_candidates": len(candidates),
                    "skipped_known": skipped_known,
                    "skipped_external": skipped_external,
                    "complete": False,
                    "reason": (
                        "Candidate links only; not a verified or "
                        "complete award catalog."
                    ),
                }
                run.save()

        except Exception as exc:
            run.status = "failed"
            run.finished_at = timezone.now()
            run.error_message = str(exc)
            run.save()
            raise CommandError(
                f"Candidate staging failed: {exc}"
            ) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Staging complete: {created_count} created, "
                f"{updated_count} updated."
            )
        )
