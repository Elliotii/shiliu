# Corpus-aware Product Query Candidate Generation Report

## Positioning

- Authoring Method Version: `v3.5-pqs-corpus-aware-authoring-method-v1`
- Codex role: Corpus-aware Product Query Candidate Generator
- Final Product Query Set frozen: false
- User Validation started or filled: false
- Old Neutral-map Pass 1 candidate bodies read: false
- Legacy historical acceptance decisions read: false

## Repository and Corpus

- Repository root: `/Users/elliot/new-systems/agent-job-prep/Shiliu`
- Canonical collection metadata: `/Users/elliot/Library/Application Support/Shiliu/shiliu.db#favorite_sources,video_source_memberships`
- Canonical video metadata and subtitle manifest: `/Users/elliot/Library/Application Support/Shiliu/shiliu.db#videos`
- Canonical AI summaries and chapter headings: `/Users/elliot/Documents/Shiliu/videos/*/summary.md` or `summary.refined.md`, selected by `videos.summary_path`
- Current non-evaluation topic/category navigation: `/Users/elliot/Library/Application Support/Shiliu/shiliu.db#taxonomy_classification_cards`, latest populated snapshot
- Product scenario: `/Users/elliot/new-systems/agent-job-prep/Shiliu/research/v3_5/product_query_set_v1/authoring_packet/PQS_V1_PRODUCT_SCENARIO_BRIEF.md`
- Navigation asset types used: collection metadata, video metadata, descriptions, AI summaries, AI chapter headings, topic/tool tags, subtitle language/source/availability
- Targeted transcript inspection used: true
- Transcript files inspected: 16
- Full-corpus transcript dump used: false
- Inventory items: 39
- Topic clusters: 15
- Specific content identified includes Coding Agent internals and extensions, Harness/Loop verification, Agent memory safety, Skill context cost, RAG rewriting and ranking, DAG/ReAct orchestration, enterprise customer-service constraints, SFT/LoRA settings, local inference caching, browser/CLI integration, and career/interview workflows.

The production database has 146 video records and 147 current folder memberships resolving to 146 distinct current videos. Although a prior unavailable-source synchronization marked many `videos.removed_at` values, current `video_source_memberships.removed_at IS NULL` remains the canonical collection-membership indicator and was used for inventory scope.

## Candidate Generation

- Final candidate count: 40
- Initial drafted count: 44
- Removed during self-review: 4
- Candidate shape distribution: `{"career_judgment": 4, "comparison": 5, "limitation": 1, "mechanism": 10, "prerequisite": 1, "process": 9, "reported_result": 1, "risk": 2, "synthesis": 1, "tradeoff": 6}`
- Scope distribution: `{"multi": 25, "single": 15}`
- Flags distribution: `{"needs_user_wording_check": 1}`
- Excessive basic-definition concentration: false
- Excessive single-topic concentration: false
- Template-replacement pattern: false
- Adequate specificity: true
- Cross-video opportunities present: true
- Exact duplicate review completed: true
- Near-duplicate review completed: true
- Known coverage gaps: several newly saved, unavailable, or title-only items lack current AI summaries or readable subtitles; no label quota was filled from those gaps.

The four removed drafts were either near-duplicates of retained memory/RAG questions or overly broad tool-overview questions. Self-review did not judge system answerability, labels, or dataset placement.

## Isolation

- Gold read: false
- System performance or failure results read: false
- Target Video read: false
- SearchCandidateSet read: false
- Development/Frozen identity read: false
- Formal Retrieval called: false
- Candidate Builder called: false
- Selector called: false
- Mechanical Gate or Semantic Judge called: false
- System answerability predicted: false
- Expected labels generated: false
- Old user or legacy decisions read: false

## Outputs

- User Review: `/Users/elliot/new-systems/agent-job-prep/Shiliu/research/v3_5/product_query_set_v1/corpus_aware_generation/product_query_candidates.user_review.jsonl`
- Internal Basis: `/Users/elliot/new-systems/agent-job-prep/Shiliu/research/v3_5/product_query_set_v1/corpus_aware_generation/product_query_candidates.internal_basis.jsonl`
- Corpus Inventory: `/Users/elliot/new-systems/agent-job-prep/Shiliu/research/v3_5/product_query_set_v1/corpus_aware_generation/product_query_corpus_inventory.internal.jsonl`
- Audit: `/Users/elliot/new-systems/agent-job-prep/Shiliu/research/v3_5/product_query_set_v1/corpus_aware_generation/corpus_aware_candidate_generation.audit.json`
- Tests: `/Users/elliot/new-systems/agent-job-prep/Shiliu/tests/test_pqs_corpus_aware_candidate_generation_contract.py`
- Test result: 20 passed (`pytest -q tests/test_pqs_corpus_aware_candidate_generation_contract.py tests/test_pqs_corpus_aware_candidate_generation_audit_identity.py`)
- Ready for V3.5-B Review: yes, subject to passing the mechanical tests

Execution stops after C3. No user validation, query freezing, split assignment, Gold construction, evaluation, retrieval retuning, commit, or push is performed.
