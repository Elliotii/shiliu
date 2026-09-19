from __future__ import annotations

import numpy as np
import pytest

from shiliu.retrieval.adoption import DenseAdoptionManager, formal_dense_fingerprint
from shiliu.retrieval.dense import (
    DenseIndexRebuildRequiredError, DenseModelIdentity, SQLiteExactDenseIndex,
)
from tests.test_dense_retrieval import add_video, make_services


class IdentityProvider:
    def __init__(self, identity: DenseModelIdentity, *, fail=False, damaged=False):
        self.identity = identity
        self.model_id = identity.model_id
        self.dimension = identity.dimension
        self.fail = fail
        self.damaged = damaged

    def model_identity(self):
        return self.identity

    def embed_documents(self, texts):
        if self.fail:
            raise RuntimeError("controlled encode failure")
        return [self._vector(text) for text in texts]

    def embed_query(self, text):
        return self._vector(text)

    def count_tokens(self, text, *, add_special_tokens=True):
        return len(text) + (2 if add_special_tokens else 0)

    def truncate_text(self, text, max_content_tokens):
        return text[:max_content_tokens]

    def _vector(self, text):
        vector = np.zeros(self.dimension - (1 if self.damaged else 0), dtype=np.float32)
        for index, value in enumerate(text.encode()):
            vector[index % len(vector)] += value + 1
        vector[0] += 1
        return vector / np.linalg.norm(vector)


def identity(model, revision, provider, projection, instruction, dense):
    return DenseModelIdentity(
        model_id=model, model_revision=revision, provider_version=provider,
        dimension=8, embedding_mode="first-8-normalized",
        projection_version=projection, query_instruction_version=instruction,
        input_policy_version="input-v1", dense_index_version=dense,
    )


BGE = identity("bge", "bge-rev", "bge-provider", "projection-bge", "none", "dense-bge")
QWEN = identity("qwen", "qwen-rev", "qwen-provider", "projection-qwen", "qwen-i-v1", "dense-qwen")


def corpus(app_paths):
    bge = IdentityProvider(BGE)
    db, artifacts, lexical, dense = make_services(app_paths, bge)
    add_video(db, artifacts, bvid="BV4000000001", title="Adoption MCP", folder_id=401)
    lexical.rebuild()
    dense.rebuild()
    return db, dense


def test_same_dimension_different_identity_is_rejected(app_paths):
    db, _ = corpus(app_paths)
    for changed in (
        QWEN,
        identity("bge", "other", "bge-provider", "projection-bge", "none", "dense-bge"),
        identity("bge", "bge-rev", "other", "projection-bge", "none", "dense-bge"),
        identity("bge", "bge-rev", "bge-provider", "other", "none", "dense-bge"),
        identity("bge", "bge-rev", "bge-provider", "projection-bge", "other", "dense-bge"),
    ):
        with pytest.raises(DenseIndexRebuildRequiredError):
            SQLiteExactDenseIndex(db=db, provider=IdentityProvider(changed)).search("MCP")
    assert SQLiteExactDenseIndex(db=db, provider=IdentityProvider(BGE)).search("MCP")


def test_shadow_build_isolated_validated_and_stale_detected(app_paths):
    db, _ = corpus(app_paths)
    before = formal_dense_fingerprint(db)
    manager = DenseAdoptionManager(db=db, provider=IdentityProvider(QWEN))
    stats = manager.build_candidate(batch_size=1, build_id="candidate-one")
    assert stats.successful_vectors == stats.total_unit_count == 2
    assert formal_dense_fingerprint(db) == before
    validation = manager.validate_candidate("candidate-one")
    assert validation["valid"] and validation["missing_rows"] == 0
    with db.connect() as connection:
        connection.execute("UPDATE retrieval_units SET content_hash='changed' WHERE unit_type='video'")
    assert not manager.validate_candidate("candidate-one")["valid"]


@pytest.mark.parametrize("stage", ["after_vectors", "after_meta"])
def test_atomic_cutover_failure_rolls_back_vectors_and_meta(app_paths, stage):
    db, _ = corpus(app_paths)
    before = formal_dense_fingerprint(db)
    manager = DenseAdoptionManager(db=db, provider=IdentityProvider(QWEN))
    manager.build_candidate(build_id="candidate-rollback")
    with db.connect() as connection:
        meta_before = dict(connection.execute("SELECT * FROM retrieval_dense_index_meta").fetchone())

    def fail(current):
        if current == stage:
            raise RuntimeError("forced cutover failure")

    with pytest.raises(RuntimeError, match="forced"):
        manager.atomic_cutover(
            "candidate-rollback", expected_formal_fingerprint=before,
            expected_formal_identity=BGE, failure_hook=fail
        )
    with db.connect() as connection:
        meta_after = dict(connection.execute("SELECT * FROM retrieval_dense_index_meta").fetchone())
        status = connection.execute(
            "SELECT status FROM retrieval_dense_candidate_meta WHERE build_id='candidate-rollback'"
        ).fetchone()[0]
    assert formal_dense_fingerprint(db) == before
    assert meta_after == meta_before and status == "ready"


def test_atomic_cutover_switches_vectors_and_meta_together(app_paths):
    db, _ = corpus(app_paths)
    before = formal_dense_fingerprint(db)
    manager = DenseAdoptionManager(db=db, provider=IdentityProvider(QWEN))
    manager.build_candidate(build_id="candidate-ready")
    manager.atomic_cutover(
        "candidate-ready", expected_formal_fingerprint=before,
        expected_formal_identity=BGE,
    )
    with db.connect() as connection:
        meta = connection.execute("SELECT * FROM retrieval_dense_index_meta").fetchone()
        models = {row[0] for row in connection.execute("SELECT model_id FROM retrieval_dense_vectors")}
        status = connection.execute(
            "SELECT status FROM retrieval_dense_candidate_meta WHERE build_id='candidate-ready'"
        ).fetchone()[0]
    assert meta["model_id"] == "qwen" and meta["provider_version"] == "qwen-provider"
    assert models == {"qwen"} and status == "cutover"
    assert SQLiteExactDenseIndex(db=db, provider=IdentityProvider(QWEN)).search("MCP")


def test_atomic_cutover_rejects_formal_meta_drift(app_paths):
    db, _ = corpus(app_paths)
    before = formal_dense_fingerprint(db)
    manager = DenseAdoptionManager(db=db, provider=IdentityProvider(QWEN))
    manager.build_candidate(build_id="candidate-meta-guard")
    with db.connect() as connection:
        connection.execute(
            "UPDATE retrieval_dense_index_meta SET provider_version='unexpected'"
        )
    with pytest.raises(RuntimeError, match="identity changed"):
        manager.atomic_cutover(
            "candidate-meta-guard", expected_formal_fingerprint=before,
            expected_formal_identity=BGE,
        )


def test_failed_or_damaged_candidate_never_changes_formal_index(app_paths):
    db, _ = corpus(app_paths)
    before = formal_dense_fingerprint(db)
    with pytest.raises(RuntimeError, match="encode failure"):
        DenseAdoptionManager(db=db, provider=IdentityProvider(QWEN, fail=True)).build_candidate(
            build_id="candidate-failed"
        )
    with pytest.raises(ValueError, match="dimension mismatch"):
        DenseAdoptionManager(db=db, provider=IdentityProvider(QWEN, damaged=True)).build_candidate(
            build_id="candidate-damaged"
        )
    assert formal_dense_fingerprint(db) == before
