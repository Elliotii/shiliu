# P9 F1A Candidate Builder Decision Complete

1. Amended P8 / Checkpoint identity  
   `P8_SCORING_AMENDMENT_V1`; Scoring Hash Root `54bc35083f4410ace027452b64fc2d22432111be5a2036c0ce245e6319849795`; Checkpoint 1 Amendment `complete_and_accepted`.

2. Six Builder Failure reconstruction  
   Exactly six eligible failures reproduced: `Q003`, `Q004`, `Q005`, `Q008`, `Q015`, `Q018`. `Q017` excluded as `gold_defined_evidence_absent`.

3. Mechanism taxonomy and counts  
   `bounded_candidate_pruning_coverage_gap`: 6 cases, estimated addressable 5.  
   `dedup_below_threshold_leaves_complement_gap`: 3 secondary cases (`Q003/Q004/Q015`).

4. Retrieval / Source / Scoring confound checks  
   All six have successful acceptable-video retrieval, reviewable sources, constructible evidence and valid amended eligibility. All required Gold segments were present in Retrieval-mapped raw chunks. Selector is downstream and had no complete group available.

5. Genericity finding  
   Generic mechanism confirmed across six distinct topics. All primary acceptable videos reached the 32-candidate cap; complementary segment coverage was lost during bounded allocation/pruning.

6. Bounded repair feasibility  
   One lightweight, fixed-budget cycle is feasible. Five failures fit within existing capacity. Q018 is a non-goal: its group requires 236 segments and approximately 633.341 seconds, exceeding current 192-segment nominal and 600-second bounds.

7. Decision candidate  
   `execute`  
   `f1a_authorized_by_codex: false`.

8. Single candidate design and addressable failure count  
   `bounded_coverage_reserve_v1`: retain 28 current relevance-ranked slots and reserve four of the existing 32 slots for deterministic marginal uncovered-segment coverage inside query-supported anchor regions. Addressable failures: 5 (`Q003/Q004/Q005/Q008/Q015`).

9. Cost / noise / latency risks  
   Candidate cap remains 32; window limits remain 6 segments, 60 seconds and 500 characters; total limits remain 6000 characters and 600 seconds. Selector load is unchanged. Risk is up to four lower-lexical-relevance candidates and a small deterministic pruning-pass latency increase.

10. One-cycle acceptance and stop boundary  
    Require Builder coverage ≥`8/13`, failures ≤`4`, span/aspect coverage ≥`69.23%`, no regression among current six hits, and Stress coverage ≥`11/20`. Close F1A after one cycle regardless of outcome. If any condition fails, retain `stage3b-acronym-w3.5-v1`.

11. Output paths and SHA-256  
    `F1A_CANDIDATE_BUILDER_DECISION.md` — `972e5b371afe26b0dfe8a1ddf3bc13abd7c6c44ffda9fa4cb4cfaf2330bc50ec`  
    `f1a_decision.json` — `98561230262305f6a5972412d610ad115d03e74c722bfc6181e885bf2762dfe4`  
    `f1a_failure_analysis.jsonl` — `fecf1c574b6a1397282f00badaa35af1ac07fcf8e96b439e0ddc74ed71760173`  
    `f1a_mechanism_taxonomy.json` — `9c7b15b5bf456348747e25b5a6a942f966689f6d10b7c2a7e5b22d3f92403973`  
    `f1a_candidate_design.json` — `8e591d14163178bb5ab6ad4c446324c7baaa9184773709403c20dbe409f7bad7`  
    `f1a_decision.manifest.json` — `006a5cc1cd8456a6b610ad46a94be7908ed8710f565024c186b2e52a51bc7e73`  
    `f1a_decision.audit.json` — `09705b2616438b779e0fea50747c3e9f7d65204d375689f58e6a6de8bb20c10d`  
    `f1a_decision.execution_decision.json` — `559b9084c9326918e878530413595f5ee10f4eda720c022529d8eda545030456`  
    `V3_5_P9_F1A_CANDIDATE_BUILDER_DECISION_RESTART_LEDGER.json` — `2e92fe85d5ef6ede8c3a4746ab8e7270dd4329e33152d8fea385d9b2b429ce1a`  
    `f1a_decision.file_hash_manifest.jsonl` — `ca62384ef3bef10953195198497c226299cb49351cd1a780d282d847b075c3f0`

12. Test command and result  
    `pytest` over P9 Restart, P8 Scoring Amendment, Checkpoint 1 Amendment and historical P9 Boundary contracts.  
    Result: `35 passed in 0.07s`.

13. Code / Prediction / Scoring / Query / Split / Gold changed  
    `false` for every category.

14. Frozen access and downstream stage status  
    `frozen_gold_opened: false`; `f1a_implementation_started: false`; `f1b_authorized: false`; `Stage4_started: false`; `next_stage_started: false`.

15. Acceptance status: pending V3.5-B review

16. Whether current Codex Session can be closed  
    Yes.
