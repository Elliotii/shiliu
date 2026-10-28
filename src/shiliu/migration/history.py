"""Explicit PoC history reader; not an alternate long-lived product backend."""
from __future__ import annotations
import json
from pathlib import Path

from shiliu.storage.dto import row_dto
from shiliu.migration.values import MigrationRejected
from shiliu.migration.snapshot import sha
from shiliu.evidence.source import make_segment_id,make_timeline_run_id


def resolve_version(conn,root: Path,workspace: str,logical_key: str,source_version: str):
    row=conn.execute('SELECT o.relative_key,o.sha256,o.byte_size FROM shiliu.artifact_versions v '
        'JOIN shiliu.artifact_objects o ON o.workspace_id=v.workspace_id AND o.sha256=v.object_sha256 '
        'WHERE v.workspace_id=%s AND v.logical_key=%s AND v.source_version=%s',
        (workspace,logical_key,source_version)).fetchone()
    if row is None:raise MigrationRejected('historical_artifact_missing')
    key=Path(row['relative_key'])
    if key.is_absolute() or '..' in key.parts:raise MigrationRejected('unsafe_manifest_key')
    path=root/key
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
        raise MigrationRejected('unsafe_manifest_path')
    if sha(path)!=row['sha256'] or path.stat().st_size!=row['byte_size']:raise MigrationRejected('historical_artifact_corrupt')
    return path.read_bytes()


def old_ask_citation(conn,root: Path,run_id: str):
    row=conn.execute('SELECT * FROM shiliu.ask_runs WHERE run_id=%s',(run_id,)).fetchone()
    if row is None:raise MigrationRejected('historical_ask_missing')
    citation=row['citations_json'][0]
    raw=resolve_version(conn,root,row['workspace_id'],'subtitle:'+str(citation['video_id']),citation['source_version'])
    payload=json.loads(raw)
    if citation['segment_id']!=make_segment_id(citation['source_artifact_id'],citation['source_version'],0):
        raise MigrationRejected('historical_segment_identity_mismatch')
    if citation['timeline_run_id']!=make_timeline_run_id(citation['source_version'],0):
        raise MigrationRejected('historical_timeline_identity_mismatch')
    return row_dto(row,timestamps=('created_at','completed_at')),raw,payload
