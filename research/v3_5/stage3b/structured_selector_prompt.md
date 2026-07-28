# Structured Fine Selector Prompt

```text
Structured selector contract: v3.5-structured-fine-selector-v1
Prompt version: v3.5-structured-fine-selector-prompt-v1

Select one or more existing Candidate IDs that jointly provide the most relevant, complete,
and non-duplicative raw subtitle evidence for Original Query, or abstain when the supplied
candidates do not contain sufficiently relevant evidence.

You must not answer or summarize the query. Do not create candidates, quotes, text, timestamps,
labels, or fields. Do not infer evidence outside the supplied CandidateSet. Return JSON only.

Exact output fields:
schema_version, action, selected_candidate_ids, candidate_roles, abstain_reason.
action is select or abstain. Roles are primary, complementary, or context.
For select: IDs are non-empty, unique, drawn only from the CandidateSet, at most
6; abstain_reason is null. Every role references a selected ID.
For abstain: IDs and roles are empty, and abstain_reason is one of no_relevant_candidate,
insufficient_candidate_coverage, conflicting_or_ambiguous, provider_unable_to_decide.
No additional fields are allowed.
INPUT_JSON:
{"candidates":[],"evidence_candidate_contract_version":"v3.5-evidence-candidate-v1","original_query":"<Original Query>"}
```
