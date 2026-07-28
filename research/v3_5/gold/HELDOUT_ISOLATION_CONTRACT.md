# Shiliu V3.5 Held-out Isolation Contract

Status: **Locked procedural contract**  
Version: `v3.5-heldout-isolation-v1`

Development labels and Evidence are available for implementation, deterministic debugging, prompt work, and policy development.

Held-out Query metadata may be used only by the formal Eval runner as required to execute evaluation. Held-out labels, required Aspects, Evidence Groups, Segment IDs, spans, and reason codes must not be inspected or used while developing the Candidate Builder, Selector, Sufficiency Judge, prompts, thresholds, windows, or case rules.

Subsequent Codex implementation sessions must not tune against Held-out, inspect Held-out failure details before the formal run, add video/case-specific exceptions, or change Gold after observing Held-out results. Formal Eval uses one frozen semantic run; permitted infrastructure-only reruns must preserve the original failed Trace and record the reason without changing system versions.

The V3.5 Version Session has already handled the Human Gold during Stage 2. This contract governs all later implementation sessions and is procedural isolation, not a claim that the Version Session itself was blind to Gold.
