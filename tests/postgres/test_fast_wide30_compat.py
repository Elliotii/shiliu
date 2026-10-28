"""Reuse one original Assistant build/freeze contract with current PG fixtures."""
from ask_product_fixture import pg_formal


def test_original_assistant_prepare_freeze_contract(pg_formal, app_paths, monkeypatch):
    import test_assistant_context_c2 as original
    from shiliu.assistant.sources import CollectionSourceService
    from shiliu.assistant.snapshots import SourceSnapshotStore
    from shiliu.assistant.store import AssistantRunStore
    from shiliu.assistant.wiki import WikiService
    from shiliu.domain import FavoriteItem

    core, _, _ = pg_formal
    db, artifacts = core.db, core.artifacts
    sources = CollectionSourceService(db=db, artifacts=artifacts,
        snapshots=SourceSnapshotStore(db, artifacts))
    store = AssistantRunStore(db)
    wiki = WikiService(db=db, store=store, sources=sources)
    monkeypatch.setattr(original, '_services', lambda _: (db, artifacts, sources, store, wiki))

    def add_material(db, artifacts, source_id, *, bvid, title, text):
        db.record_source_snapshot(source_id, [FavoriteItem(bvid=bvid, title=title,
            uploader='公开作者', favorite_time=1700000000)], processing_profile='fast', authoritative=False)
        vid = db.get_video_by_source(bvid)['id']
        batch = artifacts.batch(vid)
        ref = batch._save('summary.md', text.encode(), media_type='text/markdown')
        batch.commit(lambda conn: db.update_video(vid, summary_path=ref, status='completed', conn=conn))
        return vid

    monkeypatch.setattr(original, '_add_material', add_material)
    c2 = original.c2.__wrapped__(app_paths, monkeypatch)
    original.test_full_focus_suffix_and_memory_invalidation_are_not_json_slices(c2)
