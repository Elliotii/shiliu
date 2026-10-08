"""Deep V2 bounded controller and wait-all executor."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
import time
from typing import Annotated, Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from langgraph.graph import START, END, StateGraph

from shiliu.ask.context import ContextBuildResult, _merge_spans, _same_lineage, _span_with_segments
from shiliu.ask.contracts import TranscriptEvidenceSpan
from shiliu.ask.deep.f1_tools import F1TranscriptTool
from shiliu.ask.deep.navigation import NavigationService
from shiliu.ask.deep.transcript import TranscriptWindowReader
from shiliu.retrieval.product_search import ProductSearchFilterRequest


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


NavigationSourceId = Annotated[str, StringConstraints(pattern=r"^nav:[1-9][0-9]*$")]


def navigation_source_id(video_id: int) -> str:
    return f"nav:{video_id}"


CONTROLLER_INSTRUCTIONS = (
    "You are Deep V2. Use one dynamic search loop. Based on the user's question and per-query findings "
    'with evidence refs, choose 1 to 4 independent fully parameterized actions, or finish immediately '
    'when the useful information is sufficient. A new entity, keyword, source, or interesting lead is not '
    "itself a reason to search. Search again only if a necessary part of the user's original question "
    'remains unanswered by the findings, and the proposed query can fill that specific gap, or if a '
    'necessary bridge fact must first be found. Do not chase optional precision or a direct comparison '
    'source when existing facts support a qualified answer. Use the fewest queries that naturally cover '
    'the necessary gaps; do not split a query merely to create parallel work. Parallel queries require '
    'distinct, already known, independent information needs. Do not search again merely to synthesize or '
    'compare facts already found; synthesis belongs to Final. Search has real latency cost. Aim to answer '
    'typical Deep questions in about 25 seconds over the whole run; this is a soft product goal, never a '
    'deadline or reason to omit a necessary search. After two research rounds, continue only when a '
    'further query is likely to resolve an important specific missing user requirement. Keep necessary '
    'dependent and parallel searches available. Later queries may depend on earlier findings, but no '
    'action may depend on another action in the same batch. Tool signatures: search_videos '
    '{query?:string,uploader?:string,uploader_contains?:string,folder_id?:int,favorite_time_from?:int,fav'
    'orite_time_to?:int,result_limit?:int}; search_transcripts '
    '{query:string,video_ids?:int[],result_limit?:int}; read_context '
    '{evidence_ref:string,before_seconds?:number,after_seconds?:number}. Use result_limit, never '
    'max_results. Only favorite_time is a supported date filter. Tool choice for source identity: '
    'transcript quotes establish what a video says; they do not establish that a discussion/reaction '
    "video is a work's original release. If the user requires a title, uploader, original publication, "
    'BVID or target source identity not yet established by navigation records, and a reasonable identity '
    'clue is known, use search_videos to locate that source before declaring that need supported. A '
    'discovered work name is such a clue when its release is requested. Keep that source-identity need '
    'open until the target is actually located; do not mark it supported with refs that merely discuss '
    'the work. Ordinary content questions should use search_transcripts directly; this is not a rule to '
    'start every question with search_videos. Video metadata establishes source identity only. Query '
    'findings are summaries, not new factual sources; their evidence refs point to exact transcript text '
    'for Final. Keep actual unresolved gaps. Use read_context only for valuable located evidence needing '
    'adjacent original text. Need and finish evidence refs must occur in the per-query retained evidence '
    'list. When a search_videos result is actually adopted to answer a source or uploader question, list '
    'only its source_record_id (nav: prefix) from navigation_sources in answer_source_ids on finish. '
    'Transcript video_id is never a navigation record ID, even if the video is useful. If '
    'navigation_sources is empty, answer_source_ids must be []. Do not include merely related navigation '
    'candidates. Keep the uploader, the people or work shown, and the speaker distinct. Return JSON '
    'matching schema: '
)

QUERY_REDUCE_INSTRUCTIONS = (
    'Digest one search query only. Form the smallest sufficient set of factual findings and original '
    "transcript evidence needed to answer this query within the user's actual question. Evidence support "
    'is necessary but not sufficient for retention. Retain a fact only if it helps answer this current '
    'query, narrows a current necessary gap, or supplies an evidence-established entity, relationship or '
    'condition needed for an explicitly necessary later dependent search. A bridge need not directly '
    'answer the current question, but its evidence and role in the necessary next search must be clear. '
    'Preserve concrete entity names, relationships, conditions, numbers, and technical terms needed for '
    'later dependent queries. Drop facts that are merely on the same topic, accurate but unable to '
    'advance this gap, or interesting leads without a necessary next step. Do not keep all candidates '
    'merely because they are related, and do not use a fixed number of chunks. For each finding, '
    'evidence_refs is its necessary support set: prefer the most direct, complete quote. After direct '
    'support is sufficient, retain another ref only if it adds a material fact, condition, number, '
    'relationship, source difference, conflict, or valuable independent corroboration needed for this '
    'query or its necessary bridge. Group chunks that support the same fact instead of describing every '
    'candidate. Stop adding findings and refs once the query can support a qualified answer and its '
    'necessary later-search bridges are preserved. This is a query-focused digest, not a catalog. Write '
    'concise but specific factual findings. Candidates are presented in video/time order. Read '
    'consecutive excerpts from the same video together to locate subject introductions and transitions '
    "before assigning attributes. Write subject first, then only that subject's facts in text. A "
    "finding's subject, relation, object, role, direction, quantity, condition and membership or "
    'containment must each be directly supported by its cited evidence. Verify the complete '
    'subject-to-relation-to-object statement, not just the subject name. Co-occurrence, similar behavior, '
    'shared topics or proximity do not establish identity, ownership, membership, containment or any '
    'other relationship between entities. Do not complete a relationship the evidence has not '
    'established; keep entities separate or preserve uncertainty. If two entities share an evidence_ref, '
    "produce separate subject-bound findings. A generic subject such as 'this item' cannot distinguish "
    "adjacent entities; use the source's name or a within-video position/description. A single video or "
    'candidate quote can describe several people, products, games, or works in sequence: label each by '
    'its distinguishing name or position and do not combine details across transitions. Resolve pronouns '
    'against the actual speaker and local antecedent; if ambiguous, omit that relation or say it is '
    'ambiguous. Treat source title and description only as clues to source identity, never as proof of '
    'transcript content or relationships between the described entities. Each finding must cite exact '
    'short candidate evidence_ref(s) such as c0 or c1. The system will bind them back to the original '
    'citation identities. Judge sufficiency for this current query, not a different query or an imagined '
    'exhaustive guide. Set sufficient=true when the current query has enough evidence and use '
    "unresolved=[]. If a fact essential to this query and the user's question remains missing, set "
    'sufficient=false and state that precise gap. Do not list optional details, absent cross-source '
    'comparisons, or facts assigned to another query as unresolved gaps. unresolved describes missing '
    'information, not candidate answers. Keep unknown slots unknown: do not fill them with a fact, '
    'entity, relationship, value, or candidate answer unsupported by evidence refs. You may name already '
    'evidenced entities whose attributes are missing. Model prior knowledge or search hypotheses may help '
    'formulate a later query, but must not enter findings or unresolved as factual state. A name '
    'suggested in the search query is not evidence: omit unsupported candidate names even in questions, '
    'parentheses, or examples within unresolved; describe only the missing attribute. Do not infer facts '
    'from titles alone, invent facts, or write the final answer. An unselected candidate remains in the '
    'audit Store. Return JSON matching schema: '
)

DEEP_ANSWER_INSTRUCTIONS = """Answer the user's actual question directly and coherently from the evidence provided.

Organize the answer around the user's requested conclusions or themes. When several sources address the same point, synthesize them rather than listing videos one by one. Preserve source attribution when it materially affects a definition, judgment, comparison, disagreement, or conclusion.

There are two supported evidence domains:

- `transcript_evidence` supports claims about what a video says, describes, recommends, compares, or reports.
- `adopted_video_sources` supports video identity facts such as title, uploader, BVID, URL, and whether a located video is the adopted publication/source record.

Use the source labels in transcript_evidence to identify the quoted video, without treating them as spoken-content evidence. Use adopted_video_sources for a separately located target source identity.

`subject_bindings_not_new_evidence` is an aid for keeping subjects and their facts associated with the correct transcript refs. Verify material content claims against the corresponding transcript evidence; the bindings are not an additional factual source.

Keep subjects and relationships precise. A long quote may discuss several people, products, games, or works. Preserve which action, attribute, price, condition, or relationship belongs to which subject. Keep uploaders distinct from speakers, featured people, creators, and owners of other works or channels. A video discussing or criticizing a work is not thereby that work's original publication. Identify an original publication only when the adopted metadata establishes that it matches the requested original release; adopting a record alone does not establish this.

Match claim strength to evidence strength. A limited example supports that observed case, not automatically a general property. Comparative conclusions require evidence for the actual subjects, direction, and dimension being compared. Preserve material conditions and uncertainty rather than broadening a supported observation.

Treat the user's terminology and assumptions as the question to investigate, not as evidence. When sources use different terminology or disagree, describe what the evidence supports and preserve the relevant attribution or disagreement.

Use only `citation_id` values present in `transcript_evidence` for transcript-derived claims. Each material transcript-derived claim in an answer block must be supported by the citations attached to that block. Source-identity facts may come from `adopted_video_sources`; do not imply that a transcript citation proves those metadata facts. In this output contract, include source-identity details within blocks that also contain supported transcript-derived content. Do not attach unrelated transcript citations to support metadata-only claims or use navigation IDs or BVIDs as transcript citations.

Return:
- `complete` when the important requested aspects are supported;
- `partial` when a substantive answer is possible but an important requested aspect remains unsupported;
- `insufficient` when the available evidence cannot support a substantive answer.

Limitations should describe real remaining gaps or execution boundaries and must remain consistent with the answer.

Return one JSON object matching the supplied schema.
Required JSON Schema: """

def deep_answer_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """Select the Deep contract for initial and repair calls; shared Ask stays intact."""
    from shiliu.ask.answer import _ANSWER_PRODUCT_INSTRUCTIONS
    return [{**message, "content": message["content"].replace(
        _ANSWER_PRODUCT_INSTRUCTIONS, DEEP_ANSWER_INSTRUCTIONS)}
        if message["role"] == "system" else dict(message) for message in messages]


class NeedUpdate(_Strict):
    need_id: str
    text: str
    status: Literal["open", "supported", "conflicting"] = "open"
    evidence_refs: list[str] = Field(default_factory=list)
    gap: str = ""


class V2Action(_Strict):
    action_id: str
    kind: Literal["search_videos", "search_transcripts", "read_context"]
    arguments: dict[str, Any]
    need_ids: list[str] = Field(default_factory=list)
    purpose: str
    based_on_refs: list[str] = Field(default_factory=list)


class V2Decision(_Strict):
    type: Literal["continue", "finish"]
    need_updates: list[NeedUpdate] = Field(default_factory=list)
    actions: list[V2Action] = Field(default_factory=list)
    outcome: Literal["sufficient", "partial", "insufficient", "needs_clarification", "sources_found"] | None = None
    answer_evidence_refs: list[str] = Field(default_factory=list)
    answer_source_ids: list[NavigationSourceId] = Field(default_factory=list, description=
        "Adopted search_videos navigation record IDs, such as nav:7, copied from navigation_sources. "
        "Never transcript video_id integers. Use [] when no navigation record is adopted.")
    unresolved_items: list[str] = Field(default_factory=list)
    finish_reason: str = ""

    @model_validator(mode="after")
    def shape(self):
        if self.type == "continue" and not self.actions:
            raise ValueError("continue requires actions")
        if self.type == "finish" and (self.actions or self.outcome is None):
            raise ValueError("finish requires outcome and no actions")
        return self


class QueryFinding(_Strict):
    subject: str = Field(min_length=1, description=
        "One explicitly identified subject of this finding: name or distinguishing within-video "
        "position/description. Different adjacent people, products, games or works need distinct subjects.")
    text: str
    evidence_refs: list[str]


class QueryReduction(_Strict):
    findings: list[QueryFinding] = Field(default_factory=list)
    sufficient: bool
    unresolved: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class V2Budget:
    max_controller_calls: int = 8
    max_tool_calls: int = 24
    max_actions_per_decision: int = 4
    total_seconds: float = 240
    search_seconds: float = 180
    tool_result_chars: int = 16000
    controller_context_chars: int = 80000
    final_context_chars: int = 80000
    controller_output_tokens: int = 4096
    reduce_output_tokens: int = 6000
    answer_output_tokens: int = 8192
    no_progress_limit: int = 3

    def __post_init__(self):
        if min(self.max_controller_calls, self.max_tool_calls, self.max_actions_per_decision,
               self.tool_result_chars, self.controller_context_chars, self.final_context_chars) <= 0:
            raise ValueError("V2 limits must be positive")
        if not 0 < self.search_seconds < self.total_seconds:
            raise ValueError("invalid V2 time budget")


def canonical_material(spans):
    """Merge exact same-lineage contiguous segments once, preserving all hit lineage."""
    groups = []
    origins = []
    for span in spans:
        candidate = span
        refs = {span.citation_id}
        index = 0
        while index < len(groups):
            existing = groups[index]
            same = _same_lineage(existing, candidate)
            related = same and (max(existing.segment_ordinals) + 1 >= min(candidate.segment_ordinals)
                and max(candidate.segment_ordinals) + 1 >= min(existing.segment_ordinals))
            if not related:
                index += 1
                continue
            left = {segment.segment_id: segment for segment in existing.segments}
            for segment in candidate.segments:
                if segment.segment_id in left and segment != left[segment.segment_id]:
                    raise ValueError("same evidence segment identity has different original text")
            candidate = _merge_spans(existing, candidate)
            refs |= origins[index]
            groups.pop(index)
            origins.pop(index)
            index = 0
        groups.append(candidate)
        origins.append(refs)
    # Page only for actual text budget, on complete segment boundaries.
    pages = {}
    aliases = {}
    for span, refs in zip(groups, origins):
        partitions = []
        current = []
        characters = 0
        for segment in span.segments:
            if current and characters + len(segment.source_text) > 16000:
                partitions.append(current)
                current, characters = [], 0
            current.append(segment)
            characters += len(segment.source_text) + 1
        if current:
            partitions.append(current)
        page_refs = []
        for partition in partitions:
            page = span if len(partitions) == 1 else _span_with_segments(span, tuple(partition))
            pages[page.citation_id] = page
            page_refs.append(page.citation_id)
        for ref in refs:
            aliases[ref] = page_refs
    return pages, aliases


def _normalized_query(value: str) -> str:
    return " ".join(value.casefold().split())


class DeepV2ContextBuilder:
    """Keep complete spans, ordered by needs/actions, without fixed quote truncation."""
    def __init__(self, budget: int = 80000):
        self.budget = budget
        self.preferred_refs: list[str] = []
        self.candidate_refs: list[str] = []
        self.omitted: list[str] = []
        self.available_count = 0
        self.last_context: ContextBuildResult | None = None
        self.task_notes: dict[str, Any] = {}
        self.source_metadata: dict[int, dict[str, Any]] = {}
        self.adopted_sources: list[dict[str, Any]] = []
        self.subject_bindings: list[dict[str, Any]] = []

    def build(self, *, query: str, normalized_intent: str,
              spans: tuple[TranscriptEvidenceSpan, ...]) -> ContextBuildResult:
        # Select by Query-reduced references before any optional contiguous recovery.
        # Merging the complete audit Store here can recreate a whole-video quote
        # from unrelated raw search hits before relevance has been established.
        lookup = {span.citation_id: span for span in spans}
        self.available_count = len(lookup)
        ordered = list(dict.fromkeys(ref for ref in (*self.preferred_refs, *self.candidate_refs)
            if ref in lookup))
        selected: list[TranscriptEvidenceSpan] = []
        self.omitted = []
        for ref in ordered:
            span = lookup.get(ref)
            if span is None:
                continue
            candidate = selected + [span]
            payload = self._payload(query, candidate)
            from shiliu.ask.answer import _answer_messages
            provisional = ContextBuildResult(tuple(candidate), payload, (), False, 0)
            if sum(len(message["content"]) for message in deep_answer_messages(_answer_messages(query=query, context=provisional))) <= self.budget:
                selected.append(span)
            else:
                self.omitted.append(ref)
        # Omissions are also model metadata: check the completed payload after all
        # candidates have been considered, not only each provisional addition.
        from shiliu.ask.answer import _answer_messages
        while selected:
            payload = self._payload(query, selected)
            provisional = ContextBuildResult(tuple(selected), payload, (), bool(self.omitted), len(self.omitted))
            if sum(len(message["content"]) for message in deep_answer_messages(_answer_messages(query=query, context=provisional))) <= self.budget:
                break
            self.omitted.append(selected.pop().citation_id)
        self.last_context = ContextBuildResult(tuple(selected), self._payload(query, selected),
                                  tuple(span.citation_id for span in selected), bool(self.omitted), len(self.omitted))
        return self.last_context

    def _payload(self, query: str, spans: list[TranscriptEvidenceSpan]) -> str:
        selected_refs = {span.citation_id for span in spans}
        return json.dumps({"user_query": query,
            "research_state_only_not_factual_evidence": self.task_notes,
            "lower_priority_material_omitted_count": max(0, self.available_count - len(spans)),
            "adopted_video_sources": self.adopted_sources,
            "subject_bindings_not_new_evidence": [finding for finding in self.subject_bindings
                if finding.get("evidence_refs") and set(finding["evidence_refs"]) <= selected_refs],
            "transcript_evidence": [{"citation_id": span.citation_id, "video_id": span.video_id,
                "video_title": span.title, "source_uploader": self.source_metadata.get(span.video_id, {}).get("uploader"),
                "bvid": span.bvid, "start_time": span.start_time, "end_time": span.end_time,
                "quote": span.quote_text} for span in spans]}, ensure_ascii=False, separators=(",", ":"))


class DeepV2Graph:
    def __init__(self, *, provider_factory: Callable[[str], object], transcripts: F1TranscriptTool,
                 navigation: NavigationService, windows: TranscriptWindowReader,
                 budget: V2Budget | None = None, clock: Callable[[], float] = time.monotonic,
                 cancelled: Callable[[str], bool] | None = None):
        self.provider_factory, self.transcripts, self.navigation, self.windows = provider_factory, transcripts, navigation, windows
        self.budget, self.clock = budget or V2Budget(), clock
        self.cancelled = cancelled or (lambda _run_id: False)
        graph = StateGraph(dict)
        graph.add_node("research", self._run_loop)
        graph.add_edge(START, "research")
        graph.add_edge("research", END)
        self.compiled = graph.compile()

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        return self.compiled.invoke(state)

    def _run_loop(self, state: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("v2_needs", {})
        state.setdefault("v2_store", {span.citation_id: span for span in state.get("evidence_spans", [])})
        state.setdefault("v2_sources", {})
        state.setdefault("v2_cache", {})
        state.setdefault("v2_outcome", None)
        state.setdefault("v2_final_refs", [])
        state.setdefault("v2_final_source_ids", [])
        state.setdefault("v2_omitted", [])
        state.setdefault("v2_controller_calls", 0)
        state.setdefault("v2_unresolved", [])
        state.setdefault("v2_query_results", [])
        state.setdefault("v2_round_timings", [])
        no_progress = 0
        while self.clock() < state["search_deadline"] and state["v2_controller_calls"] < self.budget.max_controller_calls:
            if self.cancelled(state.get("run_id", "")):
                state["termination_reason"] = "cancelled"
                break
            decision = None
            error = None
            for attempt in range(2):
                if self.clock() >= state["search_deadline"] or state["v2_controller_calls"] >= self.budget.max_controller_calls:
                    break
                state["v2_controller_calls"] += 1
                try:
                    candidate, metadata, messages = self._decide(state, repair_error=error)
                    error = self._validate(candidate, state)
                    decision = candidate
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"[:1000]
                    if getattr(exc, "code", "") == "deadline_exhausted" or isinstance(exc, TimeoutError):
                        state["errors"].append(error)
                        state["termination_reason"] = "timeout"
                        break
                    if getattr(exc, "code", "") not in {"invalid_model_output", "provider_output_invalid", "output_budget_exhausted", "empty_model_output"} and not isinstance(exc, ValueError):
                        state["errors"].append(error)
                        state["termination_reason"] = "provider_error"
                        break
                if error is None:
                    break
            state["decision_rounds"] += 1
            if error or decision is None:
                if error:
                    state["errors"].append(error)
                if state["termination_reason"] is None:
                    if error == "batch exceeds remaining tool budget":
                        state["termination_reason"] = "tool_budget_exhausted"
                    elif error and (error.startswith(("PipelineError:", "ValueError:", "unknown answer navigation")) or "validation error" in error):
                        state["termination_reason"] = "invalid_structured_output"
                    else:
                        state["termination_reason"] = "provider_error" if error else "controller_budget_exhausted"
                break
            changed = self._update_needs(decision, state)
            if decision.type == "finish":
                state["v2_outcome"] = decision.outcome
                state["v2_final_refs"] = decision.answer_evidence_refs
                state["v2_final_source_ids"] = decision.answer_source_ids
                state["v2_unresolved"] = decision.unresolved_items
                state["termination_reason"] = "answer_ready" if decision.outcome in {"sufficient", "partial", "sources_found"} else "evidence_unavailable"
                break
            if self.clock() >= state["search_deadline"] or self.cancelled(state.get("run_id", "")):
                state["termination_reason"] = "timeout" if self.clock() >= state["search_deadline"] else "cancelled"
                break
            # Reserve the complete batch before dispatch; no partial dispatch or truncation.
            state["tool_calls"] += len(decision.actions)
            results = self._execute_batch(decision.actions, state)
            if self.cancelled(state.get("run_id", "")):
                state["termination_reason"] = "cancelled"
                break
            deadline = min(state["search_deadline"], state["total_deadline"])
            for result in results:
                if result["ended_at"] > deadline:
                    result.update(status="timeout", spans=(), sources=(), error="tool result arrived after deadline")
            before = self._effective_progress(state)
            for action, result in zip(decision.actions, results):
                self._reduce(action, result, state)
            after = self._effective_progress(state)
            repeated = [event for event in state["events"][-len(results):]
                if event.get("event_type") == "v2_tool_result" and event.get("no_new_result")]
            state["v2_repeated_query_advice"] = (
                "The same normalized query and scope already ran with no new result; choose a genuinely different direction or consider ending this need."
                if repeated else None)
            no_progress = 0 if changed or after != before else no_progress + 1
            state["v2_no_progress"] = no_progress
            if no_progress >= self.budget.no_progress_limit:
                state["termination_reason"] = "no_new_evidence"
                state["v2_outcome"] = "partial" if state["v2_store"] else "insufficient"
                break
        if state["termination_reason"] is None:
            state["termination_reason"] = ("timeout" if self.clock() >= state["search_deadline"]
                else "controller_budget_exhausted")
        if state["v2_outcome"] is None:
            state["v2_outcome"] = "partial" if state["v2_store"] else "insufficient"
        if state["termination_reason"] != "answer_ready" and not state["v2_unresolved"]:
            state["v2_unresolved"] = [f"{need['text']}: {need.get('gap') or '尚未确认'}"
                for need in state["v2_needs"].values() if need["status"] != "supported"]
        state["open_questions"] = [need["text"] for need in state["v2_needs"].values() if need["status"] != "supported"]
        state["resolved_questions"] = [need for need in state["v2_needs"].values() if need["status"] == "supported"]
        state["evidence_spans"] = list(state["v2_store"].values())
        state["navigation_result_count"] = len(state["v2_sources"])
        state["visited_video_ids"] = list(dict.fromkeys(span.video_id for span in state["evidence_spans"]))
        state["visited_segment_ids"] = list(dict.fromkeys(segment for span in state["evidence_spans"] for segment in span.segment_ids))
        return state

    @staticmethod
    def _effective_progress(state: dict) -> tuple:
        return (frozenset(ref for result in state.get("v2_query_results", [])
                for ref in result.get("retained_evidence_refs", [])),
            frozenset((finding.get("text"), tuple(finding.get("evidence_refs", [])))
                for result in state.get("v2_query_results", []) for finding in result.get("findings", [])),
            frozenset(state.get("v2_sources", {})))

    def _decide(self, state, repair_error: str | None = None):
        now = self.clock()
        recent_actions = [{"action_id": event.get("action_id"), "kind": event.get("kind"),
            "query": event.get("arguments", {}).get("query"), "status": event.get("status"),
            "no_new_result": event.get("no_new_result", False), "error": event.get("error")}
            for event in state["events"] if event.get("event_type") == "v2_tool_result"][-8:]
        payload = {"question": state["query"],
            "immutable_scope": state["filters"].model_dump(mode="json", exclude_none=True),
            "needs": list(state["v2_needs"].values()),
            "query_results": [{key: value for key, value in result.items() if key != "source_ids"}
                for result in state["v2_query_results"]],
            "research_round": len(state["v2_round_timings"]) + 1,
            "research_rounds_completed": len(state["v2_round_timings"]),
            "transcript_queries_executed": sum(event.get("kind") == "search_transcripts"
                for event in state["events"] if event.get("event_type") == "v2_tool_result"),
            "elapsed_wall_seconds": round(max(0, now - state.get("started_at", now)), 2),
            "navigation_sources": [{"source_record_id": navigation_source_id(value["video_id"]),
                "video_id": value["video_id"], "title": value.get("title"), "uploader": value.get("uploader"),
                "subtitle_available": value.get("subtitle_available")}
                for value in state["v2_sources"].values()],
            "recent_actions": recent_actions,
            "remaining": {"controller_calls": self.budget.max_controller_calls - state["v2_controller_calls"],
                "tool_calls": self.budget.max_tool_calls - state["tool_calls"],
                "search_seconds": max(0, state["search_deadline"] - now),
                "total_seconds": max(0, state["total_deadline"] - now),
                "max_actions_per_decision": self.budget.max_actions_per_decision},
            "repair_error": repair_error,
            "no_progress_advice": "Two decisions made no progress; change the investigation or finish honestly."
                if state.get("v2_no_progress", 0) >= 2 else None,
            "repeated_query_advice": state.get("v2_repeated_query_advice")}
        policy = CONTROLLER_INSTRUCTIONS.replace("choose 1 to 4 independent",
            f"choose 1 to {self.budget.max_actions_per_decision} independent")
        schema = V2Decision.model_json_schema()
        schema["properties"]["actions"]["maxItems"] = self.budget.max_actions_per_decision
        if state["v2_sources"]:
            schema["properties"]["answer_source_ids"]["items"]["enum"] = [
                navigation_source_id(video_id) for video_id in state["v2_sources"]]
        else:
            schema["properties"]["answer_source_ids"]["maxItems"] = 0
        messages = [{"role": "system", "content": policy + json.dumps(schema, ensure_ascii=False)},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]
        if sum(len(message["content"]) for message in messages) > self.budget.controller_context_chars:
            raise ValueError("Controller query summaries exceed character budget")
        provider = self.provider_factory("agent_action")
        try:
            response = provider.generate_structured(role="agent_action", messages=messages,
                response_schema=V2Decision, max_tokens=self.budget.controller_output_tokens,
                timeout_seconds=max(0.001, min(state["search_deadline"], state["total_deadline"]) - now))
        except Exception as exc:
            metadata = getattr(exc, "completion_metadata", {})
            state["usage"].append(metadata)
            state["events"].append({"event_type": "v2_controller_call", "messages": messages,
                "call": state["v2_controller_calls"], "repair_error": repair_error,
                "error": str(exc), "provider": metadata})
            raise
        decision = response.output if isinstance(response.output, V2Decision) else V2Decision.model_validate(response.output)
        metadata = {"model_requested": getattr(provider, "model", None),
            "model_response": getattr(response, "response_model", None),
            "usage": getattr(response, "usage", None), "latency_ms": getattr(response, "latency_ms", None),
            "retry_count": getattr(response, "retry_count", 0), "response_id": getattr(response, "response_id", None)}
        state["usage"].append(metadata)
        state["events"].append({"event_type": "v2_decision", "round": state["decision_rounds"] + 1,
            "call": state["v2_controller_calls"], "messages": messages,
            "decision": decision.model_dump(mode="json"), "repair_error": repair_error,
            "provider": metadata})
        return decision, metadata, messages

    def _validate(self, decision: V2Decision, state: dict) -> str | None:
        available = set(state["v2_store"])
        retained = ({ref for result in state.get("v2_query_results", [])
            for ref in result.get("retained_evidence_refs", [])}
            if state.get("v2_query_results") else available)
        for need in decision.need_updates:
            if not need.need_id.strip() or set(need.evidence_refs) - retained:
                return "need_updates requires stable ID and retained evidence refs"
        prior_ids = {event.get("action_id") for event in state["events"] if event.get("event_type") == "v2_tool_result"}
        known_needs = set(state.get("v2_needs", {})) | {need.need_id for need in decision.need_updates}
        if decision.type == "finish":
            missing = set(decision.answer_evidence_refs) - retained
            if missing:
                return f"unknown or unretained answer evidence refs: {sorted(missing)}"
            unknown_sources = set(decision.answer_source_ids) - {
                navigation_source_id(video_id) for video_id in state.get("v2_sources", {})}
            if unknown_sources:
                return f"unknown answer navigation source IDs: {sorted(unknown_sources)}"
            return None
        if len(decision.actions) > self.budget.max_actions_per_decision:
            return f"batch exceeds max_actions_per_decision={self.budget.max_actions_per_decision}"
        if state["tool_calls"] + len(decision.actions) > self.budget.max_tool_calls:
            return "batch exceeds remaining tool budget"
        ids = [action.action_id for action in decision.actions]
        if len(ids) != len(set(ids)) or set(ids) & prior_ids:
            return "duplicate action_id in batch"
        for action in decision.actions:
            if not action.action_id.strip() or not action.purpose.strip():
                return "action_id and purpose required"
            if set(action.based_on_refs) - available:
                return "based_on_refs contains unknown or same-batch evidence"
            if set(action.need_ids) - known_needs:
                return "action refers to unknown need_id"
            args = action.arguments
            try:
                limit = args.get("result_limit", 10)
                if type(limit) is not int:
                    return "result_limit must be an integer"
                if action.kind == "search_transcripts" and (not isinstance(args.get("video_ids", []), list) or any(type(value) is not int or value <= 0 for value in args.get("video_ids", []))):
                    return "video_ids must be a list of positive integers"
                if action.kind == "read_context" and any(type(args.get(key, 30)) not in (int, float) for key in ("before_seconds", "after_seconds")):
                    return "read_context window must be numeric"
                if action.kind == "search_videos":
                    ProductSearchFilterRequest.model_validate({key: value for key, value in args.items() if key not in {"query", "result_limit"}})
            except Exception as exc:
                return f"invalid tool arguments: {exc}"
            if action.kind == "search_transcripts":
                if set(args) - {"query", "video_ids", "result_limit"}:
                    return "unsupported search_transcripts argument; allowed query, video_ids, result_limit"
                if not isinstance(args.get("query"), str) or not args["query"].strip():
                    return "search_transcripts requires query"
                if not 1 <= args.get("result_limit", 10) <= 50:
                    return "result_limit outside 1..50"
                if any(not isinstance(value, int) or value <= 0 for value in args.get("video_ids", [])):
                    return "invalid video_ids"
            elif action.kind == "read_context":
                if set(args) - {"evidence_ref", "before_seconds", "after_seconds"}:
                    return "unsupported read_context argument; allowed evidence_ref, before_seconds, after_seconds"
                if args.get("evidence_ref") not in available:
                    return "read_context requires existing evidence_ref; same-batch dependency forbidden"
                if any(not 0 <= args.get(key, 30) <= 120 for key in ("before_seconds", "after_seconds")):
                    return "read_context window outside 0..120"
            else:
                if set(args) - {"query", "uploader", "uploader_contains", "folder_id",
                                "favorite_time_from", "favorite_time_to", "result_limit"}:
                    return "unsupported search_videos field or date type; allowed query, uploader, uploader_contains, folder_id, favorite_time_from, favorite_time_to, result_limit"
                if not isinstance(args.get("query", ""), str):
                    return "search_videos query must be text"
                if not 1 <= args.get("result_limit", 10) <= 20:
                    return "search_videos result_limit outside 1..20"
        return None

    def _update_needs(self, decision, state):
        changed = False
        for need in decision.need_updates:
            previous = state["v2_needs"].get(need.need_id)
            value = need.model_dump(mode="json")
            if previous is None or (previous["status"], previous["evidence_refs"]) != (value["status"], value["evidence_refs"]):
                changed = True
            state["v2_needs"][need.need_id] = value
        return changed

    def _execute_batch(self, actions: list[V2Action], state: dict) -> list[dict]:
        # Search all independent actions together, then digest each Query in parallel.
        # Only the state reducer below writes shared state, in action order.
        state["v2_last_batch_size"] = len(actions)
        snapshot = {"filters": state["filters"], "store": dict(state["v2_store"]), "cache": dict(state["v2_cache"])}
        search_started = self.clock()
        with ThreadPoolExecutor(max_workers=self.budget.max_actions_per_decision) as pool:
            futures = [pool.submit(self._execute_one, action, snapshot) for action in actions]
            results = [future.result() for future in futures]
        for result in results:
            if result.get("cache_hit") and result.get("query_reduction"):
                result["query_reduction"] = {**result["query_reduction"],
                    "called": False, "cache_reused": True, "latency_ms": 0, "provider": None}
        search_wall_ms = (self.clock() - search_started) * 1000
        reduce_started = self.clock()
        with ThreadPoolExecutor(max_workers=self.budget.max_actions_per_decision) as pool:
            futures = [pool.submit(self._query_reduce_one, action, result, state["query"],
                min(state["search_deadline"], state["total_deadline"]))
                if action.kind in {"search_transcripts", "read_context"}
                and result.get("status") == "ok" and not result.get("query_reduction") else None
                for action, result in zip(actions, results)]
            for result, future in zip(results, futures):
                if future is not None:
                    result["query_reduction"] = future.result()
        reduce_wall_ms = (self.clock() - reduce_started) * 1000
        state["v2_round_timings"].append({"round": state["decision_rounds"],
            "query_count": sum(action.kind in {"search_transcripts", "read_context"} for action in actions),
            "search_wall_ms": search_wall_ms, "query_reduce_wall_ms": reduce_wall_ms})
        return results

    def _query_reduce_one(self, action: V2Action, result: dict, user_query: str,
                          deadline: float) -> dict:
        spans = result.get("spans", ())
        candidate_chars = sum(len(span.quote_text) for span in spans)
        if not spans:
            return {"called": False, "findings": [], "unresolved": ["No transcript evidence found for this query."],
                "retained_evidence_refs": [], "candidate_count": 0, "candidate_chars": 0,
                "retained_evidence_chars": 0, "input_chars": 0, "latency_ms": 0}
        query = action.arguments.get("query") or action.purpose
        short_refs = {f"c{index}": span for index, span in enumerate(spans)}
        descriptions = {}
        if self.navigation is not None:
            video_ids = list(dict.fromkeys(span.video_id for span in spans))
            with self.navigation.db.connect() as connection:
                placeholders = ",".join("?" for _ in video_ids)
                descriptions = {row["id"]: (row["description"] or "")[:240]
                    for row in connection.execute(
                        f"SELECT id, description FROM videos WHERE id IN ({placeholders})", video_ids)}
        candidates = [{"evidence_ref": short_ref, "video_id": span.video_id,
            "title": span.title, "source_description_for_identity": descriptions.get(span.video_id, ""),
            "start_time": span.start_time, "end_time": span.end_time,
            "quote": span.quote_text} for short_ref, span in short_refs.items()]
        # Presentation only: retain retrieval identities/ranks, but read adjacent
        # excerpts in source order so transitions are not hidden by relevance rank.
        candidates.sort(key=lambda item: (item["video_id"], item["start_time"], item["end_time"]))
        policy = QUERY_REDUCE_INSTRUCTIONS + json.dumps(QueryReduction.model_json_schema(), ensure_ascii=False)
        messages = [{"role": "system", "content": policy}, {"role": "user", "content":
            json.dumps({"user_question": user_query, "current_query": query,
                "candidates": candidates}, ensure_ascii=False)}]
        input_chars = sum(len(message["content"]) for message in messages)
        base = {"called": False, "candidate_count": len(spans), "candidate_chars": candidate_chars,
            "input_chars": input_chars, "findings": [], "retained_evidence_refs": [],
            "retained_evidence_chars": 0, "unresolved": []}
        if input_chars > self.budget.controller_context_chars:
            return {**base, "error": "query candidate context exceeds safety budget",
                "unresolved": ["Query candidates need a narrower search scope."]}
        provider = self.provider_factory("query_reduce")
        started = self.clock()
        try:
            response = provider.generate_structured(role="query_reduce", messages=messages,
                response_schema=QueryReduction, max_tokens=self.budget.reduce_output_tokens,
                timeout_seconds=max(0.001, deadline - started))
            reduced = response.output if isinstance(response.output, QueryReduction) else QueryReduction.model_validate(response.output)
            known = short_refs
            if any(not finding.subject.strip() or not finding.text.strip() or not finding.evidence_refs
                or set(finding.evidence_refs) - set(known) for finding in reduced.findings):
                raise ValueError("query finding has empty text or unknown evidence reference")
            if not reduced.sufficient and not any(item.strip() for item in reduced.unresolved):
                raise ValueError("insufficient query reduction requires a precise unresolved gap")
            refs = list(dict.fromkeys(known[ref].citation_id
                for finding in reduced.findings for ref in finding.evidence_refs))
            findings = [{"subject": finding.subject, "text": finding.text,
                "evidence_refs": [known[ref].citation_id for ref in finding.evidence_refs]}
                for finding in reduced.findings]
            original = {span.citation_id: span for span in spans}
            return {**base, "called": True, "findings": findings,
                "sufficient": reduced.sufficient, "unresolved": reduced.unresolved,
                "retained_evidence_refs": refs,
                "retained_evidence_chars": sum(len(original[ref].quote_text) for ref in refs),
                "latency_ms": (self.clock() - started) * 1000,
                "provider": {"model_requested": getattr(provider, "model", None),
                    "model_response": getattr(response, "response_model", None),
                    "usage": getattr(response, "usage", None), "latency_ms": getattr(response, "latency_ms", None),
                    "retry_count": getattr(response, "retry_count", 0)}}
        except Exception as exc:
            return {**base, "called": True, "error": f"{type(exc).__name__}: {exc}"[:500],
                "unresolved": ["Query result selection failed; necessary evidence remains in the audit Store."],
                "latency_ms": (self.clock() - started) * 1000,
                "provider": getattr(exc, "completion_metadata", {})}

    def _execute_one(self, action, snapshot):
        started = self.clock()
        key_arguments = dict(action.arguments)
        if isinstance(key_arguments.get("query"), str):
            key_arguments["query"] = _normalized_query(key_arguments["query"])
        if action.kind == "search_transcripts":
            key_arguments.pop("result_limit", None)
        key = json.dumps([action.kind, key_arguments, snapshot["filters"].model_dump(mode="json", exclude_none=True)], sort_keys=True, ensure_ascii=False)
        try:
            if key in snapshot["cache"]:
                result = {**snapshot["cache"][key], "cache_hit": True}
                if action.kind == "search_transcripts":
                    result["delivered_limit"] = action.arguments.get("result_limit", 10)
            elif action.kind == "search_transcripts":
                args = action.arguments
                result = self.transcripts.search(args["query"], filters=snapshot["filters"],
                    video_ids=tuple(args.get("video_ids", [])))
                result["delivered_limit"] = args.get("result_limit", 10)
            elif action.kind == "read_context":
                args = action.arguments
                span = snapshot["store"][args["evidence_ref"]]
                read = self.windows.read_context(span, before_seconds=args.get("before_seconds", 30),
                    after_seconds=args.get("after_seconds", 30))
                result = {"spans": [read.span], "anchor_ref": args["evidence_ref"],
                          "before_boundary": read.before_boundary, "after_boundary": read.after_boundary}
            else:
                args = action.arguments
                scope = snapshot["filters"].model_dump(mode="python", exclude_none=True)
                if args.get("uploader_contains"):
                    hard = scope.get("uploader_contains")
                    if hard and hard.casefold() not in args["uploader_contains"].casefold():
                        raise ValueError("model uploader filter cannot override hard scope")
                    scope["uploader_contains"] = args["uploader_contains"]
                if args.get("uploader"):
                    if scope.get("uploader") and scope["uploader"].casefold() != args["uploader"].casefold():
                        raise ValueError("model uploader conflicts with hard scope")
                    scope["uploader"] = args["uploader"]
                if args.get("folder_id"):
                    if scope.get("folder_id") and scope["folder_id"] != args["folder_id"]:
                        result = {"sources": [], "query": args.get("query", ""), "empty_intersection": True}
                        result["status"] = "empty"
                        result["cache_key"] = key
                        result["started_at"] = started
                        result["ended_at"] = self.clock()
                        return result
                    scope["folder_id"] = args["folder_id"]
                if "favorite_time_from" in args:
                    scope["favorite_time_from"] = max(scope.get("favorite_time_from", args["favorite_time_from"]), args["favorite_time_from"])
                if "favorite_time_to" in args:
                    scope["favorite_time_to"] = min(scope.get("favorite_time_to", args["favorite_time_to"]), args["favorite_time_to"])
                if (scope.get("favorite_time_from") is not None and scope.get("favorite_time_to") is not None
                        and scope["favorite_time_from"] > scope["favorite_time_to"]):
                    result = {"sources": [], "query": args.get("query", ""), "empty_intersection": True}
                    result["status"] = "empty"
                    result["cache_key"] = key
                    result["started_at"] = started
                    result["ended_at"] = self.clock()
                    return result
                filters = ProductSearchFilterRequest.model_validate(scope)
                query = args.get("query", "").strip()
                if query:
                    documents = self.navigation.search(query, filters=filters, limit=args.get("result_limit", 10))
                else:
                    documents = self._field_only_videos(filters, args.get("result_limit", 10))
                result = {"sources": documents, "query": query}
            result["status"] = "empty" if not result.get("spans") and not result.get("sources") else "ok"
            result["cache_key"] = key
        except Exception as exc:
            code = str(getattr(exc, "code", ""))
            result = {"status": "stale" if "stale" in code or "version" in code else "error",
                      "error": f"{type(exc).__name__}: {exc}"[:500], "error_code": code, "cache_key": key}
        result["started_at"] = started
        result["ended_at"] = self.clock()
        return result

    def _field_only_videos(self, filters, limit):
        clauses = ["v.removed_at IS NULL", "v.is_ignored=0"]
        params = []
        for field, column in (("reading_state", "v.reading_state"), ("marked", "v.is_marked"),
                              ("archived", "v.archived_at"), ("uploader", "v.uploader")):
            value = getattr(filters, field)
            if value is None:
                continue
            if field == "archived":
                clauses.append(column + (" IS NOT NULL" if value else " IS NULL"))
            else:
                clauses.append(column + "=?")
                params.append(int(value) if isinstance(value, bool) else value)
        if filters.uploader_contains:
            clauses.append("instr(lower(v.uploader),lower(?))>0")
            params.append(filters.uploader_contains)
        favorite = []
        for field, column, operator in (("source_db_id", "s.id", "="), ("folder_id", "s.folder_id", "="),
                ("favorite_time_from", "m.favorite_time", ">="), ("favorite_time_to", "m.favorite_time", "<=")):
            value = getattr(filters, field)
            if value is not None:
                favorite.append(column + operator + "?")
                params.append(value)
        if favorite:
            clauses.append("EXISTS(SELECT 1 FROM video_source_memberships m JOIN favorite_sources s ON s.id=m.source_id "
                "WHERE m.video_id=v.id AND m.removed_at IS NULL AND " + " AND ".join(favorite) + ")")
        with self.navigation.db.connect() as connection:
            rows = connection.execute("SELECT v.id FROM videos v WHERE " + " AND ".join(clauses)
                + " ORDER BY COALESCE(v.display_favorite_time,0) DESC,v.id DESC LIMIT ?",
                [*params, min(20, max(1, limit))]).fetchall()
        return [self.navigation._project(row["id"], "field match") for row in rows]

    def _reduce(self, action, result, state):
        before_refs = set(state["v2_store"])
        before_sources = set(state["v2_sources"])
        state["v2_cache"][result["cache_key"]] = {key: value for key, value in result.items()
            if key not in {"started_at", "ended_at", "cache_hit"}}
        refs = []
        for span in result.get("spans", []):
            existing = state["v2_store"].get(span.citation_id)
            if existing is None:
                state["v2_store"][span.citation_id] = span
            else:
                provenance = tuple(dict.fromkeys(json.dumps(value, sort_keys=True, ensure_ascii=False)
                    for value in (*existing.retrieval_provenance, *span.retrieval_provenance)))
                state["v2_store"][span.citation_id] = existing.model_copy(update={
                    "retrieval_provenance": tuple(json.loads(value) for value in provenance),
                    "parent_chunk_ids": tuple(dict.fromkeys((*existing.parent_chunk_ids, *span.parent_chunk_ids))),
                })
            refs.append(span.citation_id)
        reduction = result.get("query_reduction") or {"called": False, "findings": [],
            "unresolved": ["No transcript evidence found for this query."] if action.kind == "search_transcripts" else [],
            "retained_evidence_refs": [], "candidate_count": len(refs),
            "candidate_chars": sum(len(state["v2_store"][ref].quote_text) for ref in refs),
            "retained_evidence_chars": 0, "input_chars": 0, "latency_ms": 0}
        retained = list(dict.fromkeys(reduction.get("retained_evidence_refs", [])))
        if reduction.get("provider"):
            state["usage"].append({"role": "query_reduce", **reduction["provider"]})
        if reduction.get("error"):
            state["errors"].append(reduction["error"])
        for source in result.get("sources", []):
            state["v2_sources"][source.video_id] = {"video_id": source.video_id, "title": source.title,
                "uploader": source.uploader, "bvid": source.bvid,
                "url": source.metadata.get("video_url"), "matched_excerpt": source.matched_excerpt,
                "subtitle_available": bool(source.metadata.get("subtitle_available")),
                "matched_fields": source.matched_sources, "description": source.description,
                "navigation_summary": source.summary_sections[:3]}
        if result.get("status") == "error":
            state["errors"].append(result["error"])
        if result.get("status") == "stale":
            state["stale_reasons"].append(result.get("error_code") or result.get("error"))
        query_result = {"action_id": action.action_id, "kind": action.kind,
            "query": action.arguments.get("query") or action.purpose, "need_ids": action.need_ids,
            "status": result["status"], "source_ids": [source.video_id for source in result.get("sources", [])],
            "source_record_ids": [navigation_source_id(source.video_id) for source in result.get("sources", [])],
            "findings": reduction.get("findings", []), "sufficient": reduction.get("sufficient", False),
            "unresolved": reduction.get("unresolved", []),
            "raw_candidate_count": reduction.get("candidate_count", len(refs)),
            "retained_evidence_refs": retained,
            "retained_evidence": [{"evidence_ref": ref, "video_id": state["v2_store"][ref].video_id,
                "title": state["v2_store"][ref].title, "start_time": state["v2_store"][ref].start_time,
                "end_time": state["v2_store"][ref].end_time} for ref in retained]}
        state["v2_query_results"].append(query_result)
        if action.kind in {"search_transcripts", "read_context"}:
            state["events"].append({"event_type": "v2_query_reduce", "round": state["decision_rounds"],
                "action_id": action.action_id, "query": query_result["query"],
                **reduction})
        display = [{"evidence_ref": ref, "quote": state["v2_store"][ref].quote_text,
                    "video_id": state["v2_store"][ref].video_id} for ref in refs]
        delivered = []
        count = 0
        for item in display[:result.get("delivered_limit", 50)]:
            if count + len(json.dumps(item, ensure_ascii=False)) > self.budget.tool_result_chars:
                break
            delivered.append(item)
            count += len(json.dumps(item, ensure_ascii=False))
        state["events"].append({"event_type": "v2_tool_result", "action_id": action.action_id,
            "kind": action.kind, "arguments": action.arguments, "purpose": action.purpose,
            "status": result["status"], "error": result.get("error"), "cache_hit": result.get("cache_hit", False),
            "no_new_result": bool(result.get("cache_hit") and not (set(refs) - before_refs)
                and not ({source.video_id for source in result.get("sources", [])} - before_sources)),
            "scope": result.get("scope"), "index_identity": result.get("index_identity"),
            "anchor_ref": result.get("anchor_ref"), "before_boundary": result.get("before_boundary"),
            "after_boundary": result.get("after_boundary"),
            "raw_count": result.get("raw_count"), "available": result.get("available"),
            "raw_hits": [hit.as_dict() for hit in result.get("hits", [])],
            "search_executions": result.get("search_executions", []),
            "need_ids": action.need_ids, "based_on_refs": action.based_on_refs,
            "batch_concurrency_capacity": self.budget.max_actions_per_decision,
            "evidence_refs": refs, "visible_evidence": delivered, "omitted_refs": [item["evidence_ref"] for item in display[len(delivered):]],
            "retained_evidence_refs": retained,
            "source_ids": [source.video_id for source in result.get("sources", [])],
            "started_at": result["started_at"], "ended_at": result["ended_at"],
            "latency_ms": (result["ended_at"] - result["started_at"]) * 1000})


class AuditedProvider:
    """Request-local records of actual Answer inputs, outputs, and provider identity."""
    def __init__(self, provider, calls: list[dict], output_limit: int | None = None):
        self.output_limit = output_limit
        self.provider = provider
        self.calls = calls

    def generate_structured(self, **kwargs):
        if self.output_limit is not None:
            kwargs["max_tokens"] = self.output_limit
        kwargs["messages"] = deep_answer_messages(kwargs["messages"])
        record = {"messages": kwargs["messages"], "role": kwargs["role"],
            "model_requested": getattr(self.provider, "model", None),
            "max_tokens": kwargs.get("max_tokens"), "thinking_enabled": getattr(self.provider, "thinking_enabled", None),
            "temperature": 0 if getattr(self.provider, "thinking_enabled", None) is False else None}
        self.calls.append(record)
        try:
            response = self.provider.generate_structured(**kwargs)
            record.update(model_response=getattr(response, "response_model", None),
                usage=getattr(response, "usage", None), latency_ms=getattr(response, "latency_ms", None),
                output=response.output.model_dump(mode="json"), retry_count=getattr(response, "retry_count", 0))
            return response
        except Exception as exc:
            record.update(error=str(exc), provider=getattr(exc, "completion_metadata", {}))
            raise
