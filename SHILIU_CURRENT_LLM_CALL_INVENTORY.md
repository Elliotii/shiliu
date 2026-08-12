# Shiliu Current LLM Call Inventory

Audit date: 2026-08-11 (Asia/Shanghai)

Status: pre-implementation routing baseline captured before Post-V5 Goal 1. The live
post-change mapping is documented in `README.md` and the final onboarding report; the
facts below intentionally preserve the coupling that this audit discovered.

Scope: repository source/configuration, installed LaunchAgents, current local `config.toml`, and the current SQLite database opened with `mode=ro&immutable=1`. No Provider was invoked, no Frozen/Held-out evaluation was rerun, and no held-out payload was semantically re-analysed. The only filesystem change made by this audit is this report.

## 1. Executive Summary

- The current product has **18 major model/provider roles** in this audit taxonomy: 4 ingestion LLM roles, 1 ASR role, 1 local embedding role, 5 taxonomy role families, 3 Ask roles, 1 Stage5 semantic-judge role, and 3 receipt-bound Research roles. Setup/control-plane probes and two historical/frozen evaluation-only role families are recorded separately and are not included in the 18-product-role count.
- Current live DeepSeek configuration is `https://api.deepseek.com/v1`; `fast_transcript_model=deepseek-v4-flash`, `formal_transcript_model=deepseek-v4-flash`, `formal_summary_model=deepseek-v4-pro`, and legacy/global `model=deepseek-v4-pro`.
- There is **partial, not complete, role-specific routing**. Transcript cleanup is isolated to the Flash field and summary is isolated to the Pro summary field. Ask `query_analysis`, Deep `agent_action`, Ask/Research `grounded_answer`, and every unrecognised role fall through to the one global `llm.model`. Every `taxonomy_*` role is deliberately remapped to `formal_summary_model`.
- Search itself has no remote LLM call. Hybrid search uses the pinned, offline Qwen embedding model; Ask adds an LLM query-analysis call before retrieval. Chapter/navigation metadata is generated inside the summary call, not by a separate model call.
- Normal V5 research web execution is provider-disabled (`provider_runs_authorized=False`) and deterministic. Receipt-bound Research Provider code is real and executable, but only explicitly authorised experiment runners wire it on. V5-B Fact/Artifact/Topic Page/refresh/reuse and V5-C personalization/routing/assistance do not themselves dispatch an LLM in the current product wiring.
- A separate current endpoint, `/api/evidence-sufficiency`, can invoke the frozen Stage5 semantic sufficiency judge through Codex CLI using `gpt-5.6-terra`, medium reasoning, temperature 0. This call is not controlled by the DeepSeek TOML fields.
- `deepseek-chat` does not occur anywhere in the audited repository. `deepseek-reasoner` occurs only as a test fixture/legacy compatibility value; it is not current product configuration. Both `deepseek-v4-pro` and `deepseek-v4-flash` are present and active in current configuration.
- Changing only the `formal_summary_model` TOML key does not change Ask or normal Research, but does change summary/refinement and all taxonomy roles. However, the normal web setup save path sets `llm.model` from the summary-model form value as well as `formal_summary_model`; changing Summary through that UI/API payload can therefore also change Ask and the identity/admission checks used by authorised Research/Eval runners.

## 2. Current Provider Architecture

The shared DeepSeek transport is `OpenAICompatibleProvider` in `src/shiliu/llm.py`. It posts OpenAI-compatible chat requests to `{base_url}/chat/completions`. The request contains the selected model, messages, optional `thinking`, optional `reasoning_effort`, `temperature=0` whenever thinking is explicitly off, optional `max_tokens`, and optional JSON response format. Default transport timeout is 120 seconds; `Application.provider()` selects 180 seconds for transcript and Ask roles and 600 seconds for other roles. `generate_structured()` adds one transport retry; `complete_json()` and `complete_raw()` add no transport retry themselves.

Other model/provider paths are independent:

- `ParaformerProvider`: DashScope asynchronous ASR, `paraformer-v2`.
- `QwenEmbeddingProvider`: pinned local/offline `Qwen/Qwen3-Embedding-0.6B` revision, no remote Provider or per-call cost.
- `FrozenSemanticJudgeAdapter`: invokes Codex CLI with hard-coded `gpt-5.6-terra`; it is not an `OpenAICompatibleProvider` call.
- V3.5 annotation providers: OpenAI Responses for the primary reviewer and DeepSeek chat completions for the secondary reviewer, with identities fixed in an evaluation registry.
- Receipt-bound Research: wraps the same product structured-call services, but dispatch is fenced by explicit authorisation, exact Provider identity, budgets, durable reservations, and receipts.

## 3. Model Configuration Sources

| Source | Current facts | Scope / precedence |
|---|---|---|
| `~/Library/Application Support/Shiliu/config.toml` | DeepSeek base URL; global `model=deepseek-v4-pro`; transcript Flash fields; summary Pro field; ASR endpoint/model | Authoritative live product configuration loaded at `Application` construction |
| `AppConfig.model_for(role)` | `fast_transcript` → fast field; `formal_transcript` also prefers the fast field; `formal_summary` → summary field; every other role → global model | Actual routing function |
| `Application.provider(role)` | All `taxonomy_*` roles are remapped to `formal_summary`; thinking/timeout varies by role | Shared Provider factory for ingestion, taxonomy and Ask |
| macOS Keychain | Stores credentials referenced by `api_key_ref`; the audit did not read Keychain values | Credentials only; no model routing |
| Environment | `SHILIU_STATE_DIR` and `SHILIU_CONTENT_DIR` select paths; Qwen path/cache and offline flags select local embedding runtime | No live DeepSeek model-name environment override was found |
| Web setup API/UI | Can save global, transcript and summary fields; Provider-test requests accept an arbitrary temporary model/thinking selection | Persistent config mutation on setup save; test override is control-plane only |
| CLI setup | Accepts one model and writes only legacy/global `llm_model`; role fields then fall back to that model in the in-memory config/save behavior | Legacy setup path; less isolated than current web UI |
| SQLite | Stores observed stage/model metadata and Research receipts, not the current live model setting | Observability/provenance, not routing configuration |
| LaunchAgents | Hourly `shiliu sync --scheduled`; separate `shiliu serve`; no model/environment override in either installed plist | Trigger only; both load the same TOML |
| Hard-coded constants | Stage5 judge, V3.5 reviewer identities, Research price policy default, and V5-D frozen runner identity | Isolated protocol/experiment identity; not changed by summary TOML alone |

### Is there true role-specific model routing?

Only partially:

```text
fast_transcript + actual formal transcript cleanup -> fast_transcript_model (Flash now)
formal_summary + refinement review              -> formal_summary_model (Pro now)
all taxonomy_*                                  -> formal_summary_model (Pro now)
query_analysis / agent_action / grounded_answer -> global llm.model (Pro now)
any other OpenAI-compatible role                -> global llm.model
```

`formal_transcript_model` is persisted and displayed, but current `model_for("formal_transcript")` prefers `fast_transcript_model`, and the pipeline itself requests `fast_transcript`; it is not an independently effective route in the current call graph.

## 4. Complete Model Call Inventory

Legend: “Current” means reachable in normal product wiring; “authorised-only” means executable code whose normal app wiring blocks Provider dispatch; “historical/frozen” means retained protocol/experiment identity and must not be silently changed. “Typical” token sizes are `Unknown` unless an existing usage record supports them.

| # | Call Site / Symbol | Product Role | Trigger; Online / Offline | Current Provider / Model; Config Source | Thinking / Reasoning; Output | Input Shape; Typical Size | Retry / Repair | Evidence Critical / Derived-only / Recomputable | Latency / Volume | Frozen Eval | Changing Model Affects | Confidence |
|---:|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `src/shiliu/asr.py: ParaformerProvider.submit/query/fetch_result` | Speech-to-text when subtitles are unavailable | Ingestion; scheduled/background or manual; remote async | DashScope / `paraformer-v2`; `[asr]` TOML | N/A; Provider JSON converted to timestamped segments | Audio file; sizes/tokens Unknown | Job polling; retryable job up to 3 service attempts | Evidence-critical because raw ASR becomes transcript authority; not derived-only; recomputable if audio remains available | Low user-interactive sensitivity; low volume (7 completed jobs in current DB) | no | ASR only, then downstream transcript/summary/index | Confirmed |
| 2 | `pipeline.py: _run_transcript_stage` | Faithful transcript cleanup/translation/sectioning | Video ingestion; scheduled/background; remote | OpenAI-compatible DeepSeek / `deepseek-v4-flash`; `fast_transcript_model` | thinking off, temperature 0; JSON `TranscriptResult` | Full raw subtitle segments; input tokens Unknown; output cap 16,384–24,576 | Pipeline retry up to 3 attempts; no JSON repair call | Evidence-adjacent: Ask cites raw transcript, not cleaned transcript; derived-only yes; safely recomputable | Low online sensitivity; high ingestion volume (one per eligible video) | no | Transcript cleanup and actual refined transcript cleanup only | Confirmed |
| 3 | `pipeline.py: _run_refined_transcript_stage` | Re-run transcript cleanup during manual-ASR refinement | Background refinement; remote | Same as #2 | thinking off, temperature 0; JSON | Raw segments; tokens Unknown; same cap | Up to 3 refinement attempts; no repair | Derived-only; recomputable | Low; low volume | no | Same fast transcript route as #2 | Confirmed |
| 4 | `pipeline.py: _run_summary_stage` + `prompts.py: build_summary_prompt` | Structured summary, entities, action items, important chapters/navigation metadata | Ingestion; scheduled/background; remote | OpenAI-compatible DeepSeek / `deepseek-v4-pro`; `formal_summary_model` | thinking on, reasoning high; JSON `SummaryResult` | Cleaned or mechanically bucketed full transcript + metadata; tokens Unknown; output cap 32,768–65,536 | Pipeline retry up to 3 attempts; no repair | Not citation authority; derived-only yes; recomputable | Low online sensitivity; high ingestion volume (one per summarised video) | no | Summary plus chapter/navigation metadata; same config also affects every taxonomy role | Confirmed |
| 5 | `pipeline.py: _run_refinement_review_stage` | Compare fast summary with refined transcript; keep or fully revise | Background refinement; remote | Same DeepSeek Pro summary route | thinking on, reasoning high; JSON `SummaryReviewResult` | Full refined transcript + existing fast summary; tokens Unknown; same summary cap | Up to 3 refinement attempts; no repair | Derived-only; recomputable | Low; low volume | no | Summary route and taxonomy coupling | Confirmed |
| 6 | `retrieval/qwen.py: QwenEmbeddingProvider.embed_documents/embed_query` | Dense indexing and query embedding | Index/background and search request; local offline | Local Qwen `Qwen/Qwen3-Embedding-0.6B`, pinned revision `97b0…b3`; code constant + optional model-path env | N/A; 512-d float vectors | Documents/queries capped at 512 tokens; current index has 1,633 units | No model repair; deterministic failure/fallback handled by retrieval orchestration | Retrieval-critical but does not author claims; recomputable index | High query sensitivity; high volume | model adoption identity is pinned, but not an LLM frozen eval call | Changes dense indexing/search only | Confirmed |
| 7 | `taxonomy/facets.py: FacetExtractionService.run` and `taxonomy/model_calls.py: AuditedJsonCaller` | Per-video/local facet extraction | Explicit taxonomy CLI/workflow; offline batch; remote | DeepSeek Pro via `taxonomy_local` → `formal_summary_model` | thinking off, temperature 0; typed JSON | Video cards/transcript-derived metadata; role-level typical tokens Unknown | Primary plus at most one audited JSON repair; resume/single-flight protection | Derived taxonomy metadata; recomputable with a new run identity | Low online sensitivity; medium/high batch volume | no | All callers using `formal_summary_model` if config changes | Confirmed |
| 8 | `taxonomy/workflow.py: _model_stage`, discovery/domain/consolidation/completion services | Global discovery, hierarchy/domain synthesis, consolidation, unresolved adjudication | Explicit taxonomy batch | DeepSeek Pro via `taxonomy_global` → summary field | thinking on, reasoning high; typed JSON | Batches/candidate tables/state; DB aggregate for all thinking taxonomy rows: 29 usage rows, 240,846 input, 284,144 output, 151,043 reasoning tokens | Audited primary + one repair; resumable single-flight | Derived taxonomy; can affect navigation/routing metadata but not raw Evidence authority; recomputable under new run | Low online sensitivity; medium volume, highest per-call latency (DB avg 131.14s for thinking rows) | some historical runs/protocols are frozen; live workflow itself no | Summary model and every taxonomy thinking role | Confirmed |
| 9 | Taxonomy workflow/content-type/purity/assignment paths | Content-type discovery/consolidation/purity and classification assignment | Explicit taxonomy batch | DeepSeek Pro via light `taxonomy_*` routes → summary field | thinking off, temperature 0; typed JSON | Candidate batches/cards; aggregate light-taxonomy usage: 77 usage rows, 489,098 input, 239,473 output tokens | Audited primary + one repair where `AuditedJsonCaller` is used | Derived taxonomy metadata; recomputable | Low online sensitivity; high batch volume (125 model-labelled light rows) | no, except retained run identities | Summary model and all light taxonomy roles | Confirmed |
| 10 | `taxonomy/profiles.py`, `taxonomy/comparison.py` | Classification profile generation and semantic validation/comparison | Explicit taxonomy experiment/batch | DeepSeek Pro via `taxonomy_profile`, `taxonomy_validator`, repair; summary field | light roles thinking off; typed JSON | Snapshot/profile candidates; typical tokens Unknown | Primary plus one repair | Derived/evaluation metadata; recomputable unless run frozen | Low; low/medium volume | some historical comparison artifacts frozen | Summary model and taxonomy profiles/validator | Confirmed |
| 11 | `taxonomy/model_calls.py: AuditedJsonCaller._repair` | JSON/schema/semantic-selection repair for taxonomy outputs | Only after invalid primary output; offline batch | DeepSeek Pro via `taxonomy_repair` → summary field | thinking off, temperature 0; typed JSON | Prior raw output + validation error + schema; typical Unknown | At most one repair call for a call directory | Can alter derived taxonomy output; recomputable but audit identity matters | Low; event-driven low volume | follows parent run | Summary model and all taxonomy repairs | Confirmed |
| 12 | `ask/query_analysis.py: QueryAnalyzer.analyze` | Intent analysis and up to two retrieval rewrites | `/ask` Fast; online remote | DeepSeek Pro via `query_analysis` → global `llm.model` | thinking off, temperature 0; JSON `QueryAnalysis`; max 1,200 | User query; typical tokens Unknown | One transport retry; on any failure deterministic original-query fallback, no repair | Not directly evidence-critical; derived routing; recomputable | High latency sensitivity; high request volume relative to Deep | no | Fast Ask query analysis; authorised Research planning uses same service but a separate runner gate | Confirmed |
| 13 | `ask/answer.py: GroundedAnswerService.answer/_call` | Evidence-bounded answer generation and finalization | `/ask` Fast and final phase of `/ask` Deep; online remote | DeepSeek Pro via `grounded_answer` → global model | thinking on, reasoning high; JSON `GroundedAnswerDraft`; max 4,096 | User question + transcript Evidence context (Deep cap 12,000 chars); tokens Unknown | One transport retry per logical call; one application repair call after invalid output/validation | Directly Evidence/claim/citation critical; not derived-only; answer is recomputable | High; high for Fast, medium for Deep | no | Both Fast and Deep final answers; authorised Research synthesis reuses same answer service | Confirmed |
| 14 | `ask/deep/decision.py: AgentDecisionService.decide` | Deep planning/replanning/tool selection/stop decision | `/ask` Deep; online remote, up to 6 decision rounds | DeepSeek Pro via `agent_action` → global model | thinking off, temperature 0; JSON `AgentDecision`; max 1,200 | Query + bounded state, recent navigation/evidence/open questions | One transport retry; graph records error and stops/falls back; no JSON repair | Evidence-selection critical indirectly; navigation actions do not themselves assert claims; recomputable | High; medium volume per Deep request (0–6 calls) | no | Deep only in normal product; V5-D treatment subclasses also use this role | Confirmed |
| 15 | `stage5.py: FrozenSemanticJudgeAdapter.judge` | Semantic evidence sufficiency/verifier after deterministic mechanical gate | `/api/evidence-sufficiency`; online subprocess/provider call only when gate is judge-eligible | `openai-codex-cli` / hard-coded `gpt-5.6-terra` | reasoning medium, temperature 0; strict JSON schema | Sufficiency request + selected evidence bundle; tokens Unknown; one saved call latency 38,137ms | Up to one retry; invalid structured output gets a mechanical repair prompt | Directly Evidence-sufficiency critical; not derived-only; recomputable only outside frozen claims | High; endpoint volume Unknown | yes: frozen Stage4B identity embedded in current endpoint | Only Stage5 sufficiency endpoint; unaffected by DeepSeek config | Confirmed |
| 16 | `research/provider_product.py: ReceiptBoundDeepResearchExecutor` → `QueryAnalyzer` | Research objective analysis/planning | Explicit authorised receipt-bound Research experiment only; normal app blocks it | DeepSeek Pro, exact identity from global model plus hard-coded price policy/runner check | thinking off; JSON; 1,200 | Research objective; typical Unknown | One transport retry; durable reservation/receipt; failed analysis aborts | Routing-derived; recomputable only under experiment protocol | Low normal-product volume (zero); experiment-only | yes for V5-A/V5-D runs | Global model and frozen runner admission/identity | Confirmed executable, Confirmed disabled in product |
| 17 | Same executor → `AgentDecisionService` | Research navigation/planning/replanning | Explicit authorised experiment only | DeepSeek Pro via `agent_action` | thinking off; JSON; 1,200 | Research state/evidence/navigation | One transport retry; durable receipt; bounded rounds | Indirectly Evidence-selection critical | Zero normal-product volume; bounded experiment volume | yes | Global model and V5-D baseline/treatment identities | Confirmed executable, Confirmed disabled in product |
| 18 | Same executor → `GroundedAnswerService` | Research provisional/final grounded synthesis committed into a provisional artifact | Explicit authorised experiment only | DeepSeek Pro via `grounded_answer` | thinking on, high; JSON; 4,096 | Current transcript Evidence context | One transport retry + at most one answer repair; durable receipts/cost accounting | Directly Evidence/claim/citation critical | Zero normal-product volume; bounded experiment volume | yes | Global model and V5-A/V5-D experiment identity | Confirmed executable, Confirmed disabled in product |

### Control-plane Provider calls (not counted in 18 product roles)

- `POST /api/setup/models` calls `GET /models`; it is discovery, not inference.
- `POST /api/setup/test-provider`, setup completion, and legacy CLI setup call a small “return exactly OK” completion with the submitted temporary model/thinking settings. They can incur a Provider call but do not produce a product artifact.
- ASR setup obtains an upload policy to validate credentials; it is not speech inference.

## 5. Role / Model Matrix

| Role | Current Model | Volume | Quality Sensitivity | Evidence Criticality | Recomputability | Config Isolation | Potential Flash Candidate? |
|---|---|---|---|---|---|---|---|
| ASR | `paraformer-v2` | Low | High | High: creates raw ASR authority | Audio-dependent | Separate ASR config | Unknown |
| Transcript cleanup/refinement | `deepseek-v4-flash` | High ingestion | High fidelity | Indirect; raw transcript remains Ask authority | High | Isolated fast field | Strong Candidate (already Flash) |
| Structured summary + chapters | `deepseek-v4-pro` | High ingestion | Medium/High | Derived, not citation authority | High | Summary field, but shared with taxonomy and UI can also write global | Possible Candidate |
| Summary refinement review | `deepseek-v4-pro` | Low | High | Derived | High | Same summary field | Possible Candidate |
| Offline Qwen embedding | `Qwen3-Embedding-0.6B` | High | High retrieval sensitivity | Indirect | High | Fully separate/pinned | Do Not Change Without New Eval |
| Taxonomy local/content-type/assignment | `deepseek-v4-pro` | High batch | Medium/High | Derived routing metadata | High outside frozen runs | Shared summary field | Possible Candidate |
| Taxonomy global/consolidation/adjudication | `deepseek-v4-pro` | Medium | High | Derived but structurally consequential | High outside frozen runs | Shared summary field | Keep Pro Candidate |
| Taxonomy profile/validator/repair | `deepseek-v4-pro` | Low/Medium | High | Derived/eval-sensitive | Depends on run freeze | Shared summary field | Do Not Change Without New Eval |
| Ask query analysis/rewrite | `deepseek-v4-pro` | High query-time | Medium | Routing only | High | Global model, shared with Ask/Deep/authorised Research | Strong Candidate |
| Ask grounded answer + repair | `deepseek-v4-pro` | High query-time | Very High | Direct claim/citation | High, but user-facing | Global shared | Keep Pro Candidate |
| Deep agent decision/replanning | `deepseek-v4-pro` | Medium | High | Indirect selection/sufficiency | High | Global shared | Do Not Change Without New Eval |
| Stage5 semantic sufficiency judge | `gpt-5.6-terra` | Unknown | Very High | Direct verifier | Protocol-bound | Hard-coded, isolated | Do Not Change Without New Eval |
| Authorised Research planning/decision | `deepseek-v4-pro` | Zero in normal app | High | Indirect selection | Experiment-bound | Global + exact hard-coded admission | Do Not Change Without New Eval |
| Authorised Research grounded synthesis | `deepseek-v4-pro` | Zero in normal app | Very High | Direct claim/citation | Experiment-bound | Global + exact hard-coded admission | Do Not Change Without New Eval |

These labels are engineering candidates only, not a migration decision.

## 6. Ingestion-time Calls

The hourly LaunchAgent executes `python -m shiliu sync --scheduled`. Eligible new/due videos can trigger subtitle acquisition, optional Paraformer ASR, transcript cleanup, summary generation, and retrieval index sync. Manual ASR uses a fast artifact first and can later trigger refined transcript cleanup plus summary refinement review.

Duration policy is deterministic: up to 8 minutes uses the full transcript+summary pipeline; 8–16 minutes uses summary-only over mechanically bucketed raw subtitles; over 16 minutes is subtitle-only unless manual ASR makes it summary-only. Therefore not every ingested video creates every LLM call.

There is no separate chapter model call. `important_chapters`, entities, actions and limitations are fields of `SummaryResult`. Search-time chapter enrichment only reads the saved summary JSON.

## 7. Query-time Search / Ask Calls

Raw/product search has no remote LLM call. It uses lexical FTS, local Qwen dense retrieval, deterministic hybrid orchestration, grouping, anchor construction and saved-summary chapter enrichment.

`/ask Fast` performs:

1. one query-analysis call (or deterministic fallback);
2. one to three deterministic retrieval executions;
3. one grounded-answer call, with at most one answer-repair call after invalid output or citation validation failure;
4. deterministic validation/finalization.

The answer prompt explicitly limits factual material to transcript Evidence and the deterministic validator checks citation IDs/source versions. Query analysis is not an evidence sufficiency judge.

The separate `/api/evidence-sufficiency` endpoint is not `/ask`; it uses deterministic candidate building/selection and mechanical gating, then conditionally invokes the frozen GPT semantic judge.

## 8. Deep / Research Calls

`/ask Deep` does not call the Fast query analyzer. It starts with the original query, performs up to six `agent_action` decisions and up to twelve deterministic local tool calls within a 150-second search phase, then reserves up to 210 seconds for the same grounded-answer finalizer used by Fast.

Normal Research product/background execution is explicitly constructed with both inner and outer `provider_runs_authorized=False`. `run_product_background` therefore executes the durable deterministic/no-provider product runner. There is no live product call for “research final synthesis” in this wiring.

Receipt-bound Research Provider execution exists in source and was used by authorised V5-A/V5-D runners. It composes query analysis, Deep decisions and grounded answer synthesis with exact identity checks, durable side-effect receipts, call/token/deadline/cost budgets, and dispatch authorisation. It is not registered as a normal web product path.

## 9. V5-B / V5-C Calls

### V5-B Grounded Fact / Artifact / Topic Page / refresh / reuse

No LLM dispatch was found in the Fact, Knowledge Artifact, Topic Page, refresh, revalidation, route, or reuse services. Current implementations validate and project already-grounded Research results/evidence through deterministic database workflows. Current DB counts are 0 fact revisions, 0 knowledge-artifact revisions and 0 topic-page revisions, so there is no live corpus of these artifacts from which to infer a hidden generation model.

Provider-produced provisional Research artifacts are possible only through the separately authorised receipt-bound Research path described above; V5-B acceptance/building does not make another Provider call.

### V5-C personalization / routing / assistance

No LLM call was found. Personal workspace, routing recommendations, assistance and integrated journey code are deterministic. `allow_provider_answer` is a permission/availability signal; routing records explicitly state `provider_call_on_recommendation: false`. It does not dispatch a model on recommendation.

## 10. Eval / Frozen Provider Calls

| Frozen / historical role | Fixed identity and protocol | Boundary and effect of product model changes |
|---|---|---|
| V3.5 primary annotation reviewer | OpenAI Responses; `gpt-5.6-terra`; reasoning high; strict JSON schema; max one repair | Registry identity is part of reviewer/protocol identity. Product DeepSeek settings do not affect it. |
| V3.5 secondary annotation reviewer | DeepSeek chat completions; `deepseek-v4-pro`; thinking enabled; reasoning max; max one repair | Builder rejects any other model/reasoning. Identity is part of annotation protocol and historical interpretation. |
| V3.5 structured Fine Selector | `deepseek-v4-pro`; structured JSON; max one repair | Historical development experiment; rejected and not enabled in current Stage5/product selector. Changing product config does not rewrite artifacts, but rerunning under another model would be a different experiment. |
| Frozen Stage4B/Stage5 semantic judge | `openai-codex-cli`; `gpt-5.6-terra`; medium reasoning; temperature 0; one retry | Embedded in the live evidence-sufficiency endpoint and frozen protocol identity. Not controlled by DeepSeek settings. |
| V5-A Gate B receipt-bound Provider evaluation | DeepSeek OpenAI-compatible; exact `deepseek-v4-pro`; role-specific thinking; fixed caps | Runners hard-code/validate identity. A global product model change can make a rerun fail admission; changing the hard-coded identity would change the experiment. |
| V5-D paired Candidate experiments | `deepseek-v4-pro` for query analysis, agent action and grounded answer; baseline/treatment provider-route delta fixed at zero; deterministic/manual judge, `model_judge=false` | Model identity is explicitly frozen as experiment identity. Product model change does not alter historical files, but prevents identical rerun unless the original config is restored. |

The V3.5 usage artifacts explicitly mark some historical totals as lower bounds because not every successful draft body/repair attempt was persisted. No Frozen artifact was modified or rerun by this audit.

## 11. Existing Artifact Model Provenance

### Video transcript/summary artifacts

Saved `transcript*.json` contains only `sections`. Saved `summary*.json` contains only summary content fields. `metadata.json` contains source video metadata, not generation metadata. None embeds:

- generation Provider/model/model version;
- prompt/schema version;
- generation timestamp;
- raw source version/hash.

`pipeline_stages` records Provider, model, prompt version, timestamps, thinking/reasoning and elapsed time, but it is one mutable row per `(video_id, stage_name)`. It is not embedded in or cryptographically bound to a particular artifact revision, and later attempts can update the same row. The files also use replace/alias writes (`summary.json`, `summary.fast.json`, `summary.refined.json`).

Therefore, **if only new videos later use Flash, the current video artifact data model cannot robustly preserve artifact-level provenance distinguishing old Pro summaries from future Flash summaries**. The DB may provide a best-effort latest-stage association, but not durable artifact provenance. This is a gap only; no schema change is proposed here.

### Fact / Research Artifact / Topic Page

Research evidence identities retain source artifact/version/timeline provenance. Knowledge revisions retain task IDs, input/content hashes, build policy versions, source result IDs/boundary hashes, corpus snapshots and creation timestamps. They do not directly contain generation Provider/model/prompt identity. A receipt-bound provisional Provider artifact can be traced through a `research_side_effects` receipt and Provider identity, but current normal product builds are deterministic and the live DB contains no such rows.

Thus source provenance is stronger than model-generation provenance. A future Provider-generated Fact/Artifact/Topic Page would require an explicit durable binding to distinguish Pro from Flash; that binding is not present in the current revision tables.

## 12. Token / Latency / Cost Observability

| Store | Coverage | Completeness / usability |
|---|---|---|
| `pipeline_stages` | Video transcript, summary and refinement: Provider/model/prompt/thinking/reasoning/timestamps/elapsed | No input/output/cached/reasoning token or cost fields. Useful for latency/model history, not Flash-vs-Pro cost comparison. Historical rows show both old Pro and current Flash transcript behavior. |
| Ask in-memory traces | Query-analysis usage/latency/retry and grounded-answer usage arrays; Deep event usage | Not persisted to SQLite or a stable trace directory by current `AskService`; process-local and incomplete historically. |
| Stage5 trace JSON | Per-stage latency/retries; judge Provider/model when invoked | Three current files; one actual judge call (`gpt-5.6-terra`, 38,137ms), two bypasses. No token or cost data. |
| `taxonomy_stage_runs` and taxonomy call `audit.json` files | Model, thinking, token counts, reasoning tokens, elapsed, raw/repair audit | Current DB: 217 rows; 158 model-labelled; 106 input/output-token rows; 26 reasoning-token rows; 168 latency rows. Aggregate model-labelled usage is 729,944 input, 523,617 output, 151,043 reasoning tokens. **0 populated cost rows** despite cost columns. Suitable for partial volume/latency comparison, not complete historical cost. |
| Research receipt-bound tables/artifacts | Designed for input/cached/output tokens, latency, transport attempts, reservations and computed cost | Current live DB has zero `structured_provider_call` side effects. V5-A/V5-D evaluation runs use separate private/eval DBs/artifacts, not the live DB. Cost uses a hard-coded price policy and is computed only in that authorised path. |
| V3.5 eval usage artifacts | Per-provider/reviewer tokens, cached tokens, latency and attempt classification | B1-C records are complete for that batch; combined historical B1-B/B1-C is explicitly a lower bound. Costs are `null`/unavailable in reviewed manifests. |
| V3.5 Stage3B selector metrics | Model, latency, attempts, repair, usage when returned | Historical development-only; many failed calls have unavailable usage; cost recorded as unavailable. |
| ASR jobs / videos | Provider/model/status/timestamps | No audio duration billing/cost data. |
| Dense index metadata | Exact Qwen model/revision/provider/index identity, unit counts and build time | Good reproducibility metadata; no remote cost because the formal Qwen runtime is local/offline. |

Existing data can seed a future Flash-vs-Pro comparison for taxonomy tokens/latency and pipeline latency, but it cannot provide a complete role-wide historical cost baseline. A cost column existing in taxonomy does not imply price calculation: every current `taxonomy_stage_runs.cost_value` is null.

## 13. Configuration Coupling Risks

1. **Summary ↔ taxonomy:** every `taxonomy_*` role is forcibly mapped to `formal_summary_model`. A direct Summary-model edit affects taxonomy local/global/assignment/profile/validator/repair calls.
2. **Global Ask/Deep/Research coupling:** query analysis, Deep decisions and grounded answers all fall back to `llm.model`. There is no independent Ask/Deep/Research model map.
3. **UI save coupling:** the browser setup payload assigns `model` from the summary-model field, then persists both global and summary values. A Summary change made through this path can therefore change Ask/Deep and authorised Research identity, even though editing only `formal_summary_model` in TOML would not.
4. **Formal transcript dead/aliased field:** `formal_transcript_model` is saved, but actual routing prefers/calls the fast transcript route. Treating it as isolated active routing would be incorrect.
5. **OpenAI-compatible Provider coupling:** base URL and Keychain credential reference are global across ingestion, taxonomy and Ask. Changing endpoint/credential affects all of them even when model fields differ.
6. **Frozen runner admission:** V5-A/V5-D runners assert `config.model_for(query_analysis|agent_action|grounded_answer) == deepseek-v4-pro`. A global model change can prevent rerun or, if checks were altered, change experiment identity.
7. **Hard-coded isolation:** Stage5 GPT judge and V3.5 reviewer registry do not follow the live DeepSeek settings, so changing DeepSeek config will not change those calls.

### Direct answer: will changing only Summary accidentally affect Ask/Deep/Research?

- Direct edit of only `formal_summary_model`: **No** for Ask/Deep/Research; **Yes** for all taxonomy calls and summary/refinement.
- Change through the current setup UI/save payload: **Potentially yes**, because it also writes the global `llm.model` from the summary field.
- Change of legacy/global `llm.model`: **Yes** for Ask query analysis, Deep planning, Ask/Deep grounded answer, and authorised Research/V5-D identity; **No** for an explicitly configured summary or transcript field.

## 14. Flash Candidate Classification

The candidate labels in Section 5 reflect only current engineering properties: volume, evidence criticality, recomputability, latency and configuration isolation. They do not authorise a switch. In particular:

- already-Flash transcript cleanup is confirmed current fact, not a recommendation;
- derived/recomputable summary and light taxonomy roles are candidates for later evaluation;
- grounded answer, Deep decisions, semantic sufficiency, frozen annotation and frozen V5-D identities should not be changed without a new role-specific evaluation;
- summary cannot be evaluated as an isolated config change through the current setup UI unless the global-model write is controlled.

## 15. Unknowns / Facts Requiring Runtime Verification

- Typical input/output tokens and cached-token rates for live transcript, summary, Ask Fast, Ask Deep and Stage5 are Unknown because current persistent telemetry does not retain them.
- Current request frequency for Ask Fast, Ask Deep, evidence-sufficiency and taxonomy CLI workflows is Unknown; no durable role-level invocation counter covers them.
- Actual billed cost for live DeepSeek pipeline/Ask/taxonomy calls is Unknown. Taxonomy token data are partial and cost fields are empty; Provider pricing was not queried or inferred.
- The exact model identity returned by the Provider for every current product request is not persistently recorded; most code records the requested model only.
- Whether an operator uses direct TOML editing, the current web setup path, or legacy CLI setup for the next model change cannot be known statically; coupling differs by path.
- Separate private V5-D run databases/artifacts referenced by runners were not opened for held-out semantic analysis. Public freeze/manifests establish model identity and call budgets, but do not make live-product usage complete.
- Normal Research is statically and currently wired provider-off. Whether a future out-of-repository operator script constructs an authorised orchestrator cannot be disproved from this repository; the audited shipped web/CLI wiring does not.

## 16. Files and Symbols Audited

Primary runtime/configuration:

- `src/shiliu/config.py`: `AppConfig`, `model_for`, `load_config`, `save_config`, Keychain references.
- `src/shiliu/app.py`: `Application.provider`, product/service wiring, Research authorisation flags, Qwen wiring.
- `src/shiliu/llm.py`: `OpenAICompatibleProvider`, structured/raw calls, request body, retries/timeouts/usage.
- `src/shiliu/pipeline.py`, `src/shiliu/prompts.py`, `src/shiliu/artifacts.py`, `src/shiliu/asr.py`, `src/shiliu/sync.py`.
- `src/shiliu/retrieval/{qwen,dense,product_search,enrichment}.py` and search/evidence services.
- `src/shiliu/ask/query_analysis.py`, `answer.py`, `service.py`, `finalize.py`, validation/evidence/context, and `ask/deep/*`.
- `src/shiliu/stage5.py` and `/api/evidence-sufficiency` web routes.
- `src/shiliu/taxonomy/*`, especially `model_calls.py`, `workflow.py`, discovery/facets/profiles/comparison/consolidation/completion services.
- `src/shiliu/research/provider_wiring.py`, `provider_product.py`, inner/outer/product/knowledge/reuse/personalization/routing/assistance services.
- `src/shiliu/web.py`, `src/shiliu/cli.py`, `src/shiliu/launchd.py`, templates/static setup behavior.

Evaluation/frozen boundaries:

- `src/shiliu/eval_v3_5/eval_v2/{reviewer_registry,providers,stage2r_b_runtime,stage2r_b2_runtime,canary}.py`.
- `src/shiliu/evidence/stage3b.py` and retained V3.5 Stage3B metrics/manifests.
- V5-A Gate B Provider scripts/manifests.
- V5-D Stage2/R1 treatment, runner, evaluator scripts and three experiment-freeze JSON files.
- Public usage completeness and Provider attempt summaries under `research/v3_5/eval_v2/stage2r_b1_c/`.

Runtime state checked read-only:

- Current `config.toml` (credential references redacted in audit output).
- Installed `app.shiliu.sync.plist` and `app.shiliu.web.plist`.
- Current `shiliu.db` through immutable read-only URI: pipeline, taxonomy, ASR, dense index, Research side effects and knowledge revision counts.
- Video artifact key shapes and Stage5 trace metadata; content was not used for new held-out/Frozen semantic judgments.
