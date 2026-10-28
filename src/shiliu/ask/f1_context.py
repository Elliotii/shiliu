"""Frozen S5 F1 context packing, promoted verbatim from Cbase + S2Cbase.

Source: optimization/context.py and optimization/s2_k.py; S5 maps F1 to S4 H0.
No legacy fusion or quote-only budget may precede this builder.
"""
from shiliu.ask.context import ContextBuildResult, _span_with_segments, _same_lineage, _merge_spans


def serialize(query, intent, spans):
    import json
    return json.dumps({"user_query": query, "normalized_intent": intent,
        "citation_allowlist": [s.citation_id for s in spans],
        "transcript_evidence": [{"citation_id": s.citation_id, "video_id": s.video_id,
            "video_title": s.title, "start_time": s.start_time, "end_time": s.end_time,
            "quote": s.quote_text} for s in spans]}, ensure_ascii=False, separators=(",", ":"))


class Cbase:
    def __init__(self, total_character_budget=12000, per_span_character_budget=2500, max_spans=12):
        self.total_character_budget = total_character_budget
        self.per_span_character_budget = per_span_character_budget
        self.max_spans = max_spans
        self.decisions = []
        self.last = None

    def build(self, *, query, normalized_intent, spans):
        selected, seen = [], set()
        self.decisions = []
        if len(serialize(query, normalized_intent, [])) > self.total_character_budget:
            raise ValueError("query and metadata exceed payload budget")
        for rank, span in enumerate(spans, 1):
            # Materializer has already verified raw lineage/timeline. Keep complete segments.
            for segment in span.segments:
                key = (span.source_artifact_id, span.source_version, span.timeline_run_id, segment.original_ordinal)
                event = {"rank": rank, "segment_id": segment.segment_id}
                if key in seen:
                    self.decisions.append({**event, "action": "drop", "reason": "exact_raw_duplicate"})
                    continue
                single = _span_with_segments(span, (segment,))
                if len(single.quote_text) > self.per_span_character_budget:
                    self.decisions.append({**event, "action": "drop", "reason": "segment_over_quote_budget"})
                    continue
                proposal = None
                # Only append to the last span: never move later ranks ahead of earlier ones.
                if selected and _same_lineage(selected[-1], single) and selected[-1].segments[-1].run_local_ordinal + 1 == segment.run_local_ordinal:
                    merged = _merge_spans(selected[-1], single)
                    trial = [*selected[:-1], merged]
                    if len(merged.quote_text) <= self.per_span_character_budget and len(serialize(query, normalized_intent, trial)) <= self.total_character_budget:
                        proposal = trial
                if proposal is None:
                    trial = [*selected, single]
                    reason = "max_spans" if len(trial) > self.max_spans else "payload_budget"
                    if len(trial) <= self.max_spans and len(serialize(query, normalized_intent, trial)) <= self.total_character_budget:
                        proposal = trial
                if proposal is None:
                    self.decisions.append({**event, "action": "drop", "reason": reason})
                    continue
                selected = proposal
                seen.add(key)
                self.decisions.append({**event, "action": "select"})
        dropped = sum(x['action'] == 'drop' and x['reason'] != 'exact_raw_duplicate' for x in self.decisions)
        self.last = ContextBuildResult(tuple(selected), serialize(query, normalized_intent, selected),
            tuple(s.citation_id for s in selected), bool(dropped), len({x['rank'] for x in self.decisions if x['action']=='drop'}))
        return self.last


class S2Cbase(Cbase):
    """Adapt sparse nonempty raw positions to the unchanged contiguous Cbase.

    Blank coordinates stay in validated anchors but never consume D slots/text.
    Contiguous citation parts keep their candidate's packing rank.
    """
    def build(self,*,query,normalized_intent,spans):
        parts=[];original_ranks=[]
        for rank,span in enumerate(spans,1):
            group=[]
            for segment in span.segments:
                if not segment.source_text.strip():
                    if group: parts.append(_span_with_segments(span,tuple(group)));original_ranks.append(rank);group=[]
                    continue
                if group and segment.run_local_ordinal!=group[-1].run_local_ordinal+1:
                    parts.append(_span_with_segments(span,tuple(group)));original_ranks.append(rank);group=[]
                group.append(segment)
            if group: parts.append(_span_with_segments(span,tuple(group)));original_ranks.append(rank)
        result=super().build(query=query,normalized_intent=normalized_intent,spans=parts)
        for event in self.decisions: event['rank']=original_ranks[event['rank']-1]
        return result


F1ContextBuilder = S2Cbase


class FastWide30ContextBuilder:
    """Deliver complete original RRF rank <= 30 segments in input order."""

    def build(self, *, query, normalized_intent, spans):
        selected, seen = [], {}
        barrier = False
        for span in spans:
            if span.retrieval_provenance[0]["rank"] > 30:
                continue
            for segment in span.segments:
                key = (span.source_artifact_id, span.source_version,
                       span.timeline_run_id, segment.original_ordinal)
                if not segment.source_text.strip():
                    barrier = True
                    continue
                if key in seen:
                    if seen[key] != segment.source_text:
                        raise ValueError(f"conflicting original segment text at {key!r}")
                    barrier = True
                    continue
                single = _span_with_segments(span, (segment,))
                if (not barrier and selected and _same_lineage(selected[-1], single)
                        and selected[-1].segments[-1].run_local_ordinal + 1
                        == segment.run_local_ordinal):
                    selected[-1] = _merge_spans(selected[-1], single)
                else:
                    selected.append(single)
                seen[key] = segment.source_text
                barrier = False
        return ContextBuildResult(
            tuple(selected), serialize(query, normalized_intent, selected),
            tuple(span.citation_id for span in selected), False, 0,
        )
