"""Folder hydration remains one bounded query for a complete returned page."""

from contextlib import contextmanager
from test_collection_retrieval import add_video


def test_lexical_and_dense_folder_hydration_is_batched(retrieval, monkeypatch):
    db, _, lexical, dense = retrieval
    for i in range(1, 4):
        add_video(retrieval, index=i, text="数据库事务与连接池")
    dense.rebuild()
    original = db.connect
    calls = []

    class Counted:
        def __init__(self, c):
            self.c = c

        def __getattr__(self, k):
            return getattr(self.c, k)

        def execute(self, query, *args, **kwargs):
            if "FROM retrieval_unit_folders" in str(query):
                calls.append(str(query))
            return self.c.execute(query, *args, **kwargs)

    @contextmanager
    def counted(*args, **kwargs):
        with original(*args, **kwargs) as c:
            yield Counted(c)

    monkeypatch.setattr(db, "connect", counted)
    for index in (lexical, dense):
        calls.clear()
        hits = index.search("Claude", level="video", top_k=3)
        assert len(hits) == 3 and all(hit.folders for hit in hits)
        assert len(calls) == 1
