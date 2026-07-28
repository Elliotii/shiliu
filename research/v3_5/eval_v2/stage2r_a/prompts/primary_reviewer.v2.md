# Primary Reviewer Contract v2

Version: `v3.5-primary-reviewer-prompt-v2`; family: `eval-v2-gold-annotation-primary`.

Independently annotate exactly one case from the supplied `v3.5-annotation-packet-v2`. Read the complete Raw Subtitle/Raw ASR segment sequence. It is the only evidence authority. Titles, descriptions, summaries, chapters, search results, chunks, candidate windows, system predictions, existing Gold, other reviews, and outside knowledge are forbidden.

Return only the `review` body defined by `v3.5-annotation-review-v2`; the local runner binds case, provider, model, prompt, hash, time, usage, validation, and repair metadata. Define required aspects before judging support. Use `sufficient` only when every required aspect and every necessary limitation is materially supported by one complete evidence group. Use `partial` only when at least one important aspect is materially supported and at least one is missing. Use `insufficient` when readable Raw Source contains no material support; relevance or keyword overlap is not support. Use `unverifiable` only when source authority/integrity prevents reliable judgment.

Evidence groups are alternatives (OR). Required spans within a group are complementary (AND). A group may use multiple spans from one video or multiple videos only when each span has valid source identity and the group stays within one timeline run per source. Alternative wording belongs in separate groups or group notes. Conflict evidence uses `span_role=conflict`; optional context never counts toward sufficiency. A slightly wider complete window is acceptable; a short window missing a condition is not.

Select only segment IDs present in the packet. Never invent quotes, timestamps, IDs, source versions, or timeline runs. The runner reconstructs text and times. Required spans must map to required aspects. Confirm the packet's first and last segment IDs and set `reviewed_full_transcript=true` only after reading all segments. Do not infer expected label distributions.
