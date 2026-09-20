from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "src/shiliu/static/research.js").read_text(encoding="utf-8")
EVIDENCE_SCRIPT = (ROOT / "src/shiliu/static/evidence-ui.js").read_text(
    encoding="utf-8"
)


def test_stage2_citation_identity_mapping_and_keyboard_focus_are_preserved() -> None:
    assert "new Map(product.citations.map((item, index)" in SCRIPT
    assert "numbering.get(id)" in SCRIPT
    assert "targetId = `research-citation-${number}`" in SCRIPT
    assert "marker.setAttribute('aria-controls', targetId)" in SCRIPT
    assert "target.scrollIntoView({behavior: 'smooth', block: 'start'})" in SCRIPT
    assert "target.focus({preventScroll: true})" in SCRIPT
    assert "target.classList.add('is-citation-target')" in SCRIPT
    assert "history.pushState" not in SCRIPT.split("const renderAnswer", 1)[1].split(
        "const renderPersonalization", 1
    )[0]


def test_stage2_evidence_and_time_behavior_is_frontend_only() -> None:
    assert "EVIDENCE_PREVIEW_LENGTH = 240" in EVIDENCE_SCRIPT
    assert "expandButton.type = 'button'" in EVIDENCE_SCRIPT
    assert "aria-expanded" in EVIDENCE_SCRIPT
    assert "quote.textContent = expanded ? preview.text : quoteText" in EVIDENCE_SCRIPT
    assert "formatLocalDateTime(task.updated_at)" in SCRIPT
    assert "fetch(" not in EVIDENCE_SCRIPT


def test_stage1_answer_limitations_evidence_order_and_unknown_safety_remain() -> None:
    answer = SCRIPT.index("renderAnswer(product);")
    evidence = SCRIPT.index("renderEvidence(product);")
    assert answer < evidence
    assert "answerSection.append(limitations)" in SCRIPT
    assert "operation === 'retry' && category === 'failed'" in SCRIPT
    assert "if (category === 'unknown')" in SCRIPT
