# Shiliu V3 Model Adoption State

```text
adoption_version: v3-model-adoption-v1
current_phase: ADOPTION_COMPLETE
selected_model: Qwen/Qwen3-Embedding-0.6B
model_revision: 97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3
model_path: /Users/elliot/Library/Caches/Shiliu/model-selection/Qwen3-Embedding-0.6B
provider_version: v3-qwen3-embedding-provider-v1
projection_version: v3-dense-projection-qwen-v1; 127 of 142 Video projections changed under Qwen tokenizer
query_instruction_version: v3-qwen-query-instruction-v1
input_policy_version: v3-qwen-input-512-v1
candidate_build_id: qwen-20260720-adoption-v2
candidate_table: retrieval_dense_vectors_candidate
corpus_fingerprint: b7dfee25f76bcfa2ba96aa97d46b3b5358f9a1d48a256033dbb9633cd9db154c
formal_dense_before_fingerprint: 2efd810b46ed00510034138b096a418a70e46be4924dc0b68d74a2ae4a3977c6
formal_backup_path: /Users/elliot/Library/Application Support/Shiliu/backups/shiliu.pre-qwen-cutover.20260719T174309Z.db
shadow_build_status: ready; v2 has 1547 validated vectors; candidate fingerprint 2583cfbc99c100acca9e010593f7d72e320aa3943b7d637a5afb66870eab70c9
cutover_authorized: true; user authorization received after requesting writer shutdown
cutover_status: complete; atomic transaction committed at 2026-07-19T18:28:37+00:00; formal fingerprint 21d6ccf1b37bdda3997b62c1dac7b16e87b3be864a28d3211dcfd44004db7cc2
lifecycle_validation_status: complete; formal Dense/Hybrid, two reconciles, unchanged sync-video, temporary Product-owner tests, integrity and Product hashes passed
last_completed_action: formal Qwen cutover, Stage 3 lifecycle validation, and original LaunchAgent restoration completed; web HTTP 200
next_required_action: Version Session reviews the delivered Adoption evidence; Stage 4 remains not started
```

Stage 4 remains not started. Hybrid remains non-default. Transcript Chunk
boundaries, timestamps, FTS, BM25 and RRF remain unchanged.
