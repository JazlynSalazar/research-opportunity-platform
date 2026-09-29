import fcntl
from functools import wraps
from pathlib import Path

from django.conf import settings
from django.core.management.base import CommandError


def exclusive_pipeline_lock(handle):
    """Allow only one local pipeline update at a time."""

    @wraps(handle)
    def locked_handle(self, *args, **kwargs):
        lock_path = Path(settings.BASE_DIR) / ".pipeline-update.lock"

        with lock_path.open("a+") as lock_file:
            try:
                fcntl.flock(
                    lock_file.fileno(),
                    fcntl.LOCK_EX | fcntl.LOCK_NB,
                )
            except BlockingIOError as exc:
                raise CommandError(
                    "Another opportunity update is already running."
                ) from exc

            try:
                return handle(self, *args, **kwargs)
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    return locked_handle
