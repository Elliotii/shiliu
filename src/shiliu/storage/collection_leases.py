"""Renew short Collection claims while external work runs outside transactions."""

from __future__ import annotations

from contextlib import contextmanager
from threading import Event, Thread
from uuid import uuid4

from shiliu.storage.fences import CoordinationConflict


@contextmanager
def renewing_lease(db, table, claim, *, seconds=120):
    stop = Event()
    errors = []

    def renew():
        while not stop.wait(seconds / 3):
            try:
                db.heartbeat(table, claim, seconds=seconds)
            except Exception as error:
                errors.append(error)
                return

    worker = Thread(target=renew, name="collection-lease", daemon=True)
    worker.start()
    try:
        yield claim
        if errors:
            raise CoordinationConflict("lease_renewal_failed") from errors[0]
    finally:
        stop.set()
        worker.join(timeout=6)
        try:
            db.release(table, claim)
        except CoordinationConflict:
            # The caller's publication always checks epoch again. A late cleanup
            # must never release another worker or hide its original failure.
            pass


def worker_id():
    return "collection_" + uuid4().hex
