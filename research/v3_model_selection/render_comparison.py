from __future__ import annotations

import json
from pathlib import Path


INPUT = Path(
    "/Users/elliot/Library/Caches/Shiliu/model-selection/experiments/qwen_comparison.json"
)
OUTPUT = Path(__file__).with_name("qwen_retrieval_comparison.md")


def judgment(query: str, result: dict[str, object]) -> str:
    text = f"{result.get('title', '')} {result.get('excerpt', '')}".casefold()
    direct: dict[str, tuple[str, ...]] = {
        "mcp": ("mcp", "ncp协议"),
        "langgraph": ("langgraph", "long graph", "任grave"),
        "rag": ("rag", "retrieval augmented generation", "检索增强生成"),
        "faiss": ("faiss", "facebook提出来", "fices"),
        "claude code": ("claude code",),
        "codex": ("codex",),
        "openai agents sdk": ("openai agents sdk",),
    }
    normalized = query.casefold()
    for key, terms in direct.items():
        if key in normalized:
            if any(term in text for term in terms):
                return "Relevant"
            broad = {
                "mcp": ("协议", "tool", "工具"),
                "langgraph": ("workflow", "工作流", "状态", "流程"),
                "rag": ("检索", "向量", "知识库"),
                "faiss": ("向量", "索引", "embedding"),
                "claude code": ("claude", "coding agent", "编程"),
                "codex": ("coding agent", "编程", "agent"),
                "openai agents sdk": ("agent", "智能体", "harness"),
            }[key]
            return "Partially Relevant" if any(term in text for term in broad) else "Not Relevant"
    semantic_terms = {
        "上下文": ("上下文", "压缩", "context", "token"),
        "失败": ("失败", "出错", "错误", "工具", "重试", "循环"),
        "外部资料": ("检索", "rag", "资料", "知识库", "参考信息"),
        "可恢复": ("workflow", "工作流", "dag", "编排", "恢复", "多阶段", "检查点"),
    }
    for marker, terms in semantic_terms.items():
        if marker in query:
            if any(term in text for term in terms):
                return "Relevant"
            return "Partially Relevant" if any(term in text for term in ("agent", "智能体", "模型")) else "Not Relevant"
    return "Unclear"


def compact(value: object, limit: int) -> str:
    text = " ".join(str(value or "").split()).replace("|", "\\|")
    return text[:limit]


def render() -> str:
    payload = json.loads(INPUT.read_text(encoding="utf-8"))
    lines = [
        "# Qwen Retrieval Comparison Evidence",
        "",
        "Judged by: Codex Repository Executor. Basis: direct entity/topic match in the title and short excerpt is `Relevant`; same retrieval domain but not the requested entity is `Partially Relevant`; unrelated evidence is `Not Relevant`; insufficient evidence is `Unclear`.",
        "",
        "All excerpts are whitespace-normalized and limited to 72 characters. Chunk timestamps and unit identities are copied unchanged from formal `retrieval_units`.",
    ]
    labels = {"baseline_dense": "Baseline Dense", "qwen_dense": "Qwen Dense", "lexical": "Current Lexical"}
    for comparison in payload["comparisons"]:
        query = str(comparison["query"])
        lines.extend(["", f"## `{query}`"])
        for key, label in labels.items():
            lines.extend([
                "", f"### {label}", "",
                "| Rank | Unit ID | Type | Title | Timestamp | Score | Excerpt | Judgment |",
                "| ---: | --- | --- | --- | --- | ---: | --- | --- |",
            ])
            results = comparison[key]
            if not results:
                lines.append("| — | — | — | No result | — | — | — | Unclear |")
                continue
            for rank, result in enumerate(results, 1):
                start, end = result.get("start_time"), result.get("end_time")
                timestamp = "—" if start is None else f"{float(start):.3f}–{float(end):.3f}s"
                lines.append(
                    f"| {rank} | `{compact(result['unit_id'], 72)}` | {result['unit_type']} | "
                    f"{compact(result.get('title'), 52)} | {timestamp} | {float(result['score']):.6f} | "
                    f"{compact(result.get('excerpt'), 72)} | {judgment(query, result)} |"
                )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    OUTPUT.write_text(render(), encoding="utf-8")
    print(OUTPUT)
