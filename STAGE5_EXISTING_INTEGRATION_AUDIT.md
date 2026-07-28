# Stage 5 Existing Integration Audit

Date: 2026-07-27

## Reused architecture

- FastAPI application factory: `src/shiliu/web.py`
- Application service composition: `src/shiliu/app.py`
- Existing product Search API and UI: `/api/search`, `/search`
- Search orchestration and Search Trace: `SearchOrchestrator`
- Search-to-formal-evidence projection: `EvidenceSearchService.search_library`
- Formal contracts: `SearchCandidateSet`, `EvidenceCandidateSet`, `EvidenceBundle`,
  `SufficiencyRequest`, `MechanicalGateDecision`, and `SufficiencyDecision`
- Existing Jinja/vanilla-JS/CSS UI; no new frontend or web framework
- Existing filesystem logging directory; no new database, queue, task system, or
  observability platform

## Added minimal integration points

- `Stage5PipelineService`: synchronous, thin frozen-component facade.
- `FrozenSemanticJudgeAdapter`: frozen Codex CLI transport only.
- `POST /api/evidence-sufficiency` and trace read route.
- Additive Stage 5 panel in the existing Search page.
- Persistent JSON Root Trace under the existing application logs directory.

## Asset integrity result

The final Stage 4B schema hashes (`93ff...` Request and `cf23...` Decision),
Judge implementation, Prompt, Policy, Stage 4A-R Seal, and Evidence Identity
Contract match their final seals. The Stage 4A source differs from the earlier
Stage 4A-R source hash only by the explicitly frozen Stage 4B additive
compatibility fields. Frozen Evaluation was not accessed.

## Existing timeout infrastructure

The Search UI had an `AbortController` but no fixed client deadline. The FastAPI
route is synchronous and offloads work to a thread. No proxy configuration is
stored in this repository. Stage 5 therefore applies a 180-second provider
deadline and leaves the client request open with a visible processing state.

