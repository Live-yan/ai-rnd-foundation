"""Cross-process artifact lock for the Linux/WSL worker. Not used by generated products."""
from contextlib import contextmanager
from pathlib import Path
import fcntl


@contextmanager
def artifact_lock(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / '.factory.lock').open('a') as file:
        fcntl.flock(file, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(file, fcntl.LOCK_UN)
