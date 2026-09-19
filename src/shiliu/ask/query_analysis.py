from __future__ import annotations

from dataclasses import dataclass
import unicodedata
from typing import Any, Callable

from shiliu.ask.contracts import QueryAnalysis


@dataclass(frozen=True)
class QueryPlan:
    analysis: QueryAnalysis
    queries: tuple[str, ...]
    usage: dict[str, Any] | None
    latency_ms: float | None
    finish_reason: str | None
    retry_count: int
    error: str | None


class QueryAnalyzer:
    def __init__(self, provider_factory: Callable[[str], object]) -> None:
        self.provider_factory = provider_factory

    def analyze(self, query: str) -> QueryPlan:
        try:
            provider = self.provider_factory("query_analysis")
            response = provider.generate_structured(  # type: ignore[attr-defined]
                role="query_analysis",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Analyze the user's search intent. Return JSON only with "
                            "normalized_intent, search_queries, entities, and language. "
                            "search_queries contains at most two retrieval rewrites. "
                            "Do not answer the question or judge evidence sufficiency."
                        ),
                    },
                    {"role": "user", "content": query},
                ],
                response_schema=QueryAnalysis,
                max_tokens=1200,
            )
            analysis = _structured_output(response, QueryAnalysis)
            usage = getattr(response, "usage", None)
            queries = bounded_distinct_queries(query, analysis.search_queries)
            return QueryPlan(
                analysis=analysis,
                queries=queries,
                usage=usage if isinstance(usage, dict) else None,
                latency_ms=_optional_float(getattr(response, "latency_ms", None)),
                finish_reason=_optional_string(
                    getattr(response, "finish_reason", None)
                ),
                retry_count=int(getattr(response, "retry_count", 0)),
                error=None,
            )
        except Exception as exc:
            return QueryPlan(
                analysis=QueryAnalysis(),
                queries=(query,),
                usage=None,
                latency_ms=None,
                finish_reason=None,
                retry_count=0,
                error=f"{type(exc).__name__}: {exc}"[:500],
            )


def bounded_distinct_queries(
    original_query: str, rewrites: list[str] | tuple[str, ...]
) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for candidate in (original_query, *rewrites[:2]):
        normalized = normalize_search_query(candidate)
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
        if len(result) == 3:
            break
    return tuple(result or [normalize_search_query(original_query)])


def normalize_search_query(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value)).split())


def _structured_output(value: object, schema: type[QueryAnalysis]) -> QueryAnalysis:
    output = getattr(value, "output", value)
    if isinstance(output, schema):
        return output
    return schema.model_validate(output)


def _optional_float(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _optional_string(value: object) -> str | None:
    return str(value) if value is not None else None
