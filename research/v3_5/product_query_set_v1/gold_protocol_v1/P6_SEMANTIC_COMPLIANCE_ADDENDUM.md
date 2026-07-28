# P6 Semantic Compliance Addendum

```yaml
decision_ledger_semantics_changed_by_codex:
  value: false
  details: >-
    The generated protocol, three schemas, reason-code registry, review policy,
    Frozen Evaluation isolation contract, validator, audit, and manifest preserve
    the Decision Ledger and Task Contract semantics. No semantic rule was added,
    removed, relaxed, or reinterpreted by Codex.

retrieval_gold:
  known_relevant_subset_of_acceptable_enforced:
    value: true
    details: >-
      The validator requires known_relevant_video_ids to be a subset of
      acceptable_video_ids.
  hard_negative_requires_explicit_human_judgment:
    value: true
    details: >-
      The protocol requires explicit human review; the Schema requires review
      authority and the reviewed-video set, and the validator requires every hard
      negative to occur in that explicitly reviewed set.
  outside_pool_is_unjudged_not_negative:
    value: true
    details: >-
      unjudged_outside_pool_is_negative is fixed to false, and the protocol
      identifies an outside-pool return as unjudged.
  exhaustive_const_false:
    value: true
    details: "The Retrieval Gold Schema fixes exhaustive with const: false."

evidence_gold:
  authoritative_sources_only_official_subtitle_or_asr:
    value: true
    details: >-
      span_registry source_type is restricted to official_subtitle and
      asr_transcript by both Schema and validator.
  navigation_sources_forbidden_as_gold_evidence:
    value: true
    details: >-
      Title, description, AI summary, and AI chapter are navigation-only;
      navigation_sources_used_as_gold_evidence is fixed to false.
  groups_between_are_or:
    value: true
    details: "acceptable_evidence_groups_logic is fixed to OR."
  required_spans_within_group_are_and:
    value: true
    details: "required_span_sets_within_group is fixed to AND."
  multi_video_groups_supported:
    value: true
    details: >-
      The Schema places no single-video restriction on a group, the protocol
      explicitly permits cross-video groups, and the synthetic Evidence fixture
      exercises a two-video group.
  retrieval_output_does_not_limit_gold:
    value: true
    details: "builder_or_retrieval_output_limits_gold is fixed to false."
  builder_output_does_not_limit_gold:
    value: true
    details: "builder_or_retrieval_output_limits_gold is fixed to false."
  source_text_and_language_preserved:
    value: true
    details: >-
      Every span requires quote_text and source_language. The protocol preserves
      original source text and states that translated_gloss cannot replace it.

sufficiency_gold:
  sufficient_boundary_enforced:
    value: true
    details: >-
      Authoritative sources must be reviewable, every material aspect must be
      supported, and no material aspect may be missing.
  partial_boundary_enforced:
    value: true
    details: >-
      At least one material aspect must be supported and at least one must be
      missing or unresolved; together they must cover the material-aspect set.
  insufficient_boundary_enforced:
    value: true
    details: >-
      Authoritative sources must be reviewable, no material aspect may be
      supported, and every material aspect must be missing.
  unverifiable_boundary_enforced:
    value: true
    details: >-
      Authoritative sources must not be reliably reviewable, no material aspect
      may be reliably supported, and all material aspects remain unresolved.
  mixed_source_rule_enforced:
    value: true
    some_material_support_plus_blocked_remainder: partial
    no_reliable_material_judgment_due_to_source_failure: unverifiable
    reviewable_source_but_no_material_support: insufficient

governance:
  downstream_failure_codes_forbidden_in_gold:
    value: true
    details: >-
      Gold-state and downstream-attribution namespaces are separate; the registry
      forbids downstream codes in Gold and the validator rejects their prefixes.
  unresolved_disagreement_final_authority_is_user:
    value: true
    details: >-
      The Review Policy assigns unresolved disagreement and final human authority
      to the user.
  frozen_gold_content_hidden_from_v3_5_b:
    value: true
    details: >-
      The isolation contract permits only construction metadata and mechanical
      status while forbidding Gold content visibility before the formal Frozen run.
  semantic_protocol_changes_require_new_version:
    value: true
    details: >-
      The protocol and manifest require a new protocol version and re-annotation
      of affected cases for semantic changes.

fixtures:
  synthetic_only:
    value: true
    details: >-
      All six fixtures use explicit SYNTH identifiers, x-synthetic language, and
      invented synthetic source text.
  real_query_ids_present: false
  real_video_ids_present: false
  real_segment_ids_present: false
  real_transcript_text_present: false

artifact_identity:
  PRODUCT_QUERY_GOLD_PROTOCOL_V1.md:
    sha256: 1da2fd575a091ac5adff7e823080b8d90564fbf912abdb3cc5ee409599886e06
  product_retrieval_gold.schema.json:
    sha256: 6017dc5eaabae1be34701e0a4941ed205ce0e16a7db3885b431d665366b397c0
  product_evidence_gold.schema.json:
    sha256: c6d065464e833d1eb36b27c2247e9362ab0040b10cd590451c6c8cdd22eb5947
  product_sufficiency_gold.schema.json:
    sha256: 56054395bb3ab1997bc58474ad34759026c9f4bc774f9164dbe66aedffa638f3
  product_gold_reason_code_registry.json:
    sha256: 7d759383aeb20aa2730254e2785ac8fc867ef5ecaf8fbcd42909cdf0c83ca50b
  product_gold_review_policy.json:
    sha256: 45514dffb722b4c64c410b00980021889d4f869a827fef2d469c7a0f6538e545
  product_frozen_evaluation_isolation_contract.md:
    sha256: d0c3edaa60762432b84e918e958fa3e981677fe4795ca5a38a6a854e96ab5fd6
  product_gold_protocol_v1.manifest.json:
    sha256: cf998e8d9b5562ff3b8018795582d89a6fd0d0ecf7ab707454a071ad0f7fe396
  product_gold_protocol_v1.audit.json:
    sha256: d0176c30a683226072e08c049ff6690cc137ff98777d5e8ac93b47717aa88996
  scripts/validate_product_gold_protocol_v1.py:
    sha256: c2e61bb73cfb29193a983229019032f17ef0cfd37fedf79699df2029af1a7103

p6_semantic_compliance:
  status: pass
  unresolved_semantic_differences: 0
  files_modified_in_this_followup: 0
  p7_started: false
  acceptance_status: pending_v3_5_b_and_user_review
```
