"""Retired SQLite candidate writer. Historical data stays in offline snapshots.

Formal profile adoption uses PgExactDenseIndex.rebuild()/activate(); source
inspection classifies legacy candidate tables without running their writers.
"""


class DenseAdoptionManager:
    def __init__(self, *args, **kwargs):
        raise RuntimeError("legacy_candidate_writer_retired_use_pg_profiles")
