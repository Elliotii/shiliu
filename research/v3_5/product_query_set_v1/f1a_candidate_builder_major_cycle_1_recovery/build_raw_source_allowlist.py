from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3


ROOT = Path("/Users/elliot/new-systems/agent-job-prep/Shiliu")
OUTPUT = ROOT / (
    "research/v3_5/product_query_set_v1/"
    "f1a_candidate_builder_major_cycle_1_recovery/f1a_raw_source_allowlist.json"
)
ARTIFACT_MANIFEST = ROOT / "research/v3_eval/artifact_manifest.jsonl"
SNAPSHOT_DB = Path(
    "/Users/elliot/Documents/Shiliu/eval/v3_stage6/"
    "20260720T094346Z_c7663365/shiliu_eval.db"
)
P8_QUERY_IDS = (
    "PQS_V1_Q003", "PQS_V1_Q004", "PQS_V1_Q005", "PQS_V1_Q006",
    "PQS_V1_Q007", "PQS_V1_Q008", "PQS_V1_Q011", "PQS_V1_Q012",
    "PQS_V1_Q013", "PQS_V1_Q014", "PQS_V1_Q015", "PQS_V1_Q017",
    "PQS_V1_Q018", "PQS_V1_Q019",
)
FORBIDDEN_FRAGMENTS = (
    "frozen_guarded", "internal_protected", "reviewed_gold_candidate",
    "frozen_gold",
)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


origins: dict[int, set[str]] = {}
identities: dict[int, dict] = {}
source_terminals: dict[int, dict] = {}


def ingest(search: dict, origin: str, input_id: str, candidate_set: dict | None) -> None:
    videos = {
        int(value["video_id"]): value
        for value in search.get("video_candidates", [])
        if value.get("video_id") is not None
    }
    chunk_video_ids: set[int] = set()
    for raw in search.get("raw_unit_candidates", []):
        video_id = int(raw["video_id"])
        if (
            video_id not in videos
            or raw.get("unit_type") != "transcript_chunk"
            or not raw.get("candidate_eligibility")
        ):
            continue
        source_artifact_id = raw.get("source_artifact_id")
        source_version = raw.get("source_version")
        if not source_artifact_id or not source_version:
            raise RuntimeError(f"eligible raw source identity missing: {origin}:{input_id}:{video_id}")
        chunk_video_ids.add(video_id)
        origins.setdefault(video_id, set()).add(origin)
        identity = identities.setdefault(video_id, {"timeline_run_ids": set()})
        identity["source_artifact_id"] = source_artifact_id
        identity["source_version"] = source_version
        if raw.get("timeline_run_id"):
            identity["timeline_run_ids"].add(raw["timeline_run_id"])
    for video_id, video in videos.items():
        if video_id in chunk_video_ids or not video.get("video_level_hit_present"):
            continue
        origins.setdefault(video_id, set()).add(origin)
        if candidate_set:
            candidates = [
                value for value in candidate_set.get("candidates", [])
                if int(value["video_id"]) == video_id
            ]
        else:
            candidates = []
        if not candidates:
            source_terminals[video_id] = {
                "video_id": video_id,
                "source_id": video.get("source_id"),
                "authorized_input_origin": origin,
                "authorized_input_id": input_id,
                "terminal_code": "no_supported_subtitle",
                "raw_source_identity_present": False,
                "admitted_to_raw_allowlist": False,
            }
            origins.pop(video_id, None)
            continue
        first = candidates[0]
        identity = identities.setdefault(video_id, {"timeline_run_ids": set()})
        identity["source_artifact_id"] = first["source_artifact_id"]
        identity["source_version"] = first["source_version"]
        identity["timeline_run_ids"].update(
            value["timeline_run_id"] for value in candidates if value.get("timeline_run_id")
        )
    if candidate_set:
        for candidate in candidate_set.get("candidates", []):
            video_id = int(candidate["video_id"])
            if video_id not in origins:
                continue
            identity = identities.setdefault(video_id, {"timeline_run_ids": set()})
            identity["source_artifact_id"] = candidate["source_artifact_id"]
            identity["source_version"] = candidate["source_version"]
            if candidate.get("timeline_run_id"):
                identity["timeline_run_ids"].add(candidate["timeline_run_id"])


for query_id in P8_QUERY_IDS:
    trace = load(
        ROOT / (
            "research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3/"
            f"blind_run/product_initial_baseline.traces/{query_id}.trace.json"
        )
    )
    ingest(
        trace["search_candidate_set"], "p8_attempt_3", query_id,
        trace.get("evidence_candidate_set"),
    )

stress_root = ROOT / "research/v3_5/stage3r_qc/track_a_auto_refresh"
case_ids = load(stress_root / "input_freeze/evidence_bearing_case_ids.json")["case_ids"]
for case_id in case_ids:
    case_root = stress_root / f"execution/cases/{case_id}"
    ingest(
        load(case_root / "search_candidate_set.json"), "corrected_stress", case_id,
        load(case_root / "candidate_set.json"),
    )

manifest_records = {}
for line in ARTIFACT_MANIFEST.read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    record = json.loads(line)
    if (
        record.get("artifact_type") == "raw_subtitle"
        and record.get("video_id") is not None
        and int(record["video_id"]) in origins
    ):
        manifest_records[int(record["video_id"])] = record

database_rows = {}
with sqlite3.connect(f"file:{SNAPSHOT_DB}?mode=ro", uri=True) as connection:
    for video_id in origins:
        database_rows[video_id] = connection.execute(
            "SELECT source_id, part, subtitle_source, subtitle_language "
            "FROM videos WHERE id=?",
            (video_id,),
        ).fetchone()

records = []
unresolved = []
hash_mismatches = []
forbidden = []
for video_id in sorted(origins):
    manifest = manifest_records.get(video_id)
    database = database_rows.get(video_id)
    if (
        not manifest or not database or manifest.get("status") != "ok"
        or not manifest.get("snapshot_path")
    ):
        unresolved.append(video_id)
        continue
    path = Path(manifest["snapshot_path"])
    observed = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    expected = manifest.get("sha256")
    if observed != expected:
        hash_mismatches.append(video_id)
    if any(fragment in str(path).casefold() for fragment in FORBIDDEN_FRAGMENTS):
        forbidden.append(video_id)
    identity = identities[video_id]
    records.append({
        "source_artifact_id": identity["source_artifact_id"],
        "source_version": identity["source_version"],
        "timeline_run_ids": sorted(identity["timeline_run_ids"]),
        "video_identity": {
            "video_id": video_id,
            "source_id": str(database[0]),
            "part": int(database[1]),
        },
        "resolved_exact_path": str(path),
        "expected_sha256": expected,
        "observed_sha256": observed,
        "resolution_method": "existing_raw_source_resolver",
        "authorized_input_origin": sorted(origins[video_id]),
        "path_is_frozen_evaluation_gold": False,
        "hash_matches": observed == expected,
    })

identity_count = len({
    (record["source_artifact_id"], record["source_version"]) for record in records
})
payload = {
    "schema_version": "v3.5-b-f1a-raw-source-allowlist-v1",
    "execution_id": "F1A_MAJOR_CYCLE_1_RECOVERY_EXECUTION",
    "status": "complete" if not (unresolved or hash_mismatches or forbidden) else "blocked",
    "artifact_manifest": {
        "path": str(ARTIFACT_MANIFEST),
        "expected_sha256": "36e63e3a510e840f688b7ce5075fef2a0b1f65086c039960632a9ec726dfd08f",
        "observed_sha256": hashlib.sha256(ARTIFACT_MANIFEST.read_bytes()).hexdigest(),
    },
    "snapshot_database": {
        "path": str(SNAPSHOT_DB),
        "expected_sha256": "61589a5b64e9c9e6e5356d33baa6054aa435722e186066501a3213e8e9a6c4e1",
    },
    "records": records,
    "recognized_source_terminals": [
        source_terminals[key] for key in sorted(source_terminals)
    ],
    "raw_source_count": len(records),
    "duplicate_source_identity_count": len(records) - identity_count,
    "unresolved_source_count": len(unresolved),
    "unresolved_video_ids": unresolved,
    "hash_mismatch_count": len(hash_mismatches),
    "hash_mismatch_video_ids": hash_mismatches,
    "forbidden_path_count": len(forbidden),
    "forbidden_video_ids": forbidden,
    "repository_search_count": 0,
}
OUTPUT.write_text(
    json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    encoding="utf-8",
)
