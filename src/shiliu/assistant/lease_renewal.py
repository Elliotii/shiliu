"""Lifetime-scoped renewal for P3's four existing consumers, not a scheduler.

Each heartbeat owns one short connection. The caller must still fence every
publication under the real owner/epoch/lease and business resource locks.
"""

from __future__ import annotations
from contextvars import ContextVar
from threading import Event, Thread
from shiliu.storage.fences import CoordinationConflict
from shiliu.storage.scheduler import job_transition

_current = ContextVar("p3_lease_renewal", default=None)


def renewal_period(lease_seconds=120, interval=None):
    interval = lease_seconds / 3 if interval is None else interval
    if not 0 < lease_seconds <= 120 or not 0 < interval <= lease_seconds / 3:
        raise ValueError("invalid_renewal_interval")
    return interval


class LeaseRenewal:
    def __init__(self, heartbeat, *, interval, fenced=CoordinationConflict):
        self.heartbeat = heartbeat
        self.interval = interval
        self.fenced = fenced
        self.stopped = Event()
        self.error = None
        self.thread = Thread(
            target=self._loop, name=f"shiliu-p3-renewal-{id(self)}", daemon=False
        )

    def _loop(self):
        while not self.stopped.wait(self.interval):
            try:
                self.heartbeat()
            except Exception as exc:
                # Never replay a heartbeat after uncertainty, revive an expired
                # owner or release another worker's lane. Publication fails shut.
                self.error = exc
                return

    def check(self):
        if self.error is not None:
            raise self.fenced("maintenance_renewal_failed") from self.error

    def __enter__(self):
        self.token = _current.set(self)
        try:
            self.thread.start()
        except BaseException:
            _current.reset(self.token)
            raise
        return self

    def __exit__(self, *exc):
        self.stopped.set()
        self.thread.join()  # DB lock/statement/acquisition limits bound this wait.
        _current.reset(self.token)


def check_renewal():
    renewal = _current.get()
    if renewal is not None:
        renewal.check()


def job_renewal(db, job, *, lease_seconds=120, interval=None):
    interval = renewal_period(lease_seconds, interval)

    def heartbeat():
        with db.connect() as c:
            job_transition(
                c,
                db.context,
                job["id"],
                job["lease_owner"],
                job["lease_epoch"],
                action="heartbeat",
                lease_seconds=lease_seconds,
            )

    return LeaseRenewal(heartbeat, interval=interval)
