# Shiliu V3 Model Selection Gate State

```text
gate_version: v3-model-selection-gate-v1
current_phase: QWEN_EVALUATED
baseline_model: BAAI/bge-small-zh-v1.5
current_candidate: Qwen/Qwen3-Embedding-0.6B
candidate_revision: 97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3
candidate_cache_path: /Users/elliot/Library/Caches/Shiliu/model-selection/Qwen3-Embedding-0.6B
dependency_status: complete; torch 2.13.0, transformers 5.14.1, sentence-transformers 5.6.0; pip check clean
download_status: complete by user; 12 repository files present; local directory size 1.1G
download_command: .venv/bin/hf download Qwen/Qwen3-Embedding-0.6B --revision 97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3 --local-dir "/Users/elliot/Library/Caches/Shiliu/model-selection/Qwen3-Embedding-0.6B" && printf '%s\n' '97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3' > "/Users/elliot/Library/Caches/Shiliu/model-selection/Qwen3-Embedding-0.6B/.candidate-revision"
verification_status: complete; pinned revision marker matches and required local files pass offline verification
probe_status: Qwen smoke complete; ASCII 21/21 pairs distinct, Mixed/Chinese distinct, finite normalized 512-d vectors
full_corpus_status: complete; 1547/1547 vectors, 0 failed, 0 duplicate, 0 damaged; formal Dense fingerprint unchanged
decision_status: Recommend Qwen adoption; recommendation only, no formal adoption performed
last_completed_action: Qwen full-corpus experiment, 16-query comparison, and intermediate Model Selection Report completed
next_required_action: Version Session reviews Qwen evidence and decides whether to authorize a separate V3 Model Adoption Patch
```

No candidate model files may be downloaded by Codex. Candidate execution must
use an explicit local path with offline environment variables enabled.
