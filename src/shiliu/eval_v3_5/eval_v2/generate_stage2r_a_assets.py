from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .contracts import AnnotationAgreementV2, AnnotationPacketV2, AnnotationReviewV2, MasterCaseV2, TranscriptSegment
from .packets import build_packet

ROOT = Path(__file__).resolve().parents[4]
ASSETS = ROOT / "research/v3_5/eval_v2/stage2r_a"


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def main() -> None:
    schemas = {
        "master_case.v2.schema.json": MasterCaseV2.model_json_schema(),
        "annotation_packet.v2.schema.json": AnnotationPacketV2.model_json_schema(),
        "annotation_review.v2.schema.json": AnnotationReviewV2.model_json_schema(),
        "annotation_agreement.v2.schema.json": AnnotationAgreementV2.model_json_schema(),
    }
    for name, schema in schemas.items():
        _write(ASSETS / "schemas" / name, schema)
    fixture = json.loads((ASSETS / "fixtures/synthetic_transcript.v2.json").read_text())
    packet = build_packet(case_id=fixture["case_id"], query=fixture["query"], query_language=fixture["query_language"],
                          transcript=[TranscriptSegment.model_validate(x) for x in fixture["segments"]],
                          source_metadata={"video_id": "video_fixture", "synthetic_fixture": True})
    _write(ASSETS / "fixtures/annotation_packet.synthetic.v2.json", packet.model_dump(mode="json"))
    included = sorted(path for path in ASSETS.rglob("*") if path.is_file() and path.name != "stage2r_a_manifest.json")
    manifest = {"manifest_version": "v3.5-stage2r-a-manifest-v2", "stage": "stage2r_a",
                "formal_annotation_cases": 0, "formal_gold_records": 0, "real_codex_reviewer_calls": 0,
                "real_deepseek_api_calls": 0, "files": [{"path": x.relative_to(ROOT).as_posix(),
                "sha256": hashlib.sha256(x.read_bytes()).hexdigest()} for x in included]}
    _write(ASSETS / "manifests/stage2r_a_manifest.json", manifest)


if __name__ == "__main__":
    main()
