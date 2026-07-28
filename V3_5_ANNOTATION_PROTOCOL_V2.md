# Shiliu Annotation Protocol v2

Status: locked for Stage 2R-A. Version: `v3.5-annotation-protocol-v2`.

Each case receives one fresh isolated Primary Codex-side context and one fresh isolated DeepSeek V4 Pro Max request. Both receive content-equivalent full-transcript packets with the same `case_input_sha256`. Neither sees prior cases, label distributions, the other review, system predictions, existing Gold, adjudication, or the network. Primary workspaces exclude `secondary_reviews`, `agreements`, `adjudications`, `existing_gold`, and `system_predictions`; the Secondary builder consumes only packet + secondary prompt.

The packet contains query identity, complete authoritative segments with IDs/times/language/type/run/artifact/version, schema/protocol versions, and hash. Search/chunks/windows/summaries are prohibited. Reviewer output references real segments only; local validation reconstructs quote and time, verifies source/version/run and packet boundaries, and treats `reviewed_full_transcript` as a declaration rather than proof.

Pipeline: parse → schema validation → segment/source validation. One repair receives only original output, errors, and original packet. Failure after repair is `invalid`; there are no further retries and no automatic Gold. Runs record initial-valid, repair, invalid-after-repair, missing-field, invalid-ID, source/run, illegal-label, and illegal-group/reference rates plus latency, usage/token/cost fields and rework reason.

Agreement is local and deterministic, version `v3.5-annotation-agreement-v2`. Text is NFKC/case/punctuation normalized. Exact normalized aspects pass; otherwise deterministic token Jaccard must reach `0.80`, with count mismatch or ambiguity marked unresolved. Required segment IoU and time-region IoU thresholds are both `0.50`; both directional recalls and group overlap are reported. Equal labels alone never pass.

Mandatory human review: label/aspect/group disagreement or unresolved aspect; partial; multiple required spans/groups; ASR error; cross-language; unclear source/version/run; low confidence; boundary dispute; conflict; invalid-after-repair; evidence-region difference; suspected outside knowledge; incomplete transcript review; or sufficient versus insufficient/unverifiable. Ordinary core-agreement cases use deterministic SHA-256 seed `stage2r-a-v2`, default 20% spot check, configurable only from 15–25%. Systemic findings may expand review by query family, model, source type, label, or evidence pattern.

Human packets show query, source metadata, both reviews, deterministic differences, reconstructed relevant regions, full-transcript reference, and blank decision template. The user is final adjudicator. Agreement-passed records retain `human_adjudication_required=false` and spot-check status.

Gold prompts must not become Stage 4B Judge prompts. Reviews and Judge outputs remain mutually blind; system predictions never enter annotation packets; frozen Gold changes only through a new Gold version after an independently found annotation error. DeepSeek may later also be evaluated as Semantic Judge. Gold freezing, prompt separation, blind inputs and human adjudication are required to reduce shared-model reviewer risk.

No formal cases, reviews, Gold, provider calls, or pilot selection occur in Stage 2R-A.

