from contextlib import contextmanager
from fastapi import HTTPException


@contextmanager
def session_write(entry):
    """An active chat must not leave pointer actions waiting indefinitely."""
    if not entry['lock'].acquire(timeout=5):
        raise HTTPException(409,'Another request is still running. Stop it or wait, then retry this action.')
    try:yield
    finally:entry['lock'].release()
