# Internal Caller Compatibility Review

The review searched Product Search API use, `ProductSearchRequest(...)` construction, fixtures, scripts, and documentation for callers that could depend on an omitted mode resolving to lexical.

| Caller group | Classification | Action |
| --- | --- | --- |
| Browser main search | Product-default semantics | Keeps omitted URL mode as Auto and sends `mode: auto` in its first API request. |
| `src/shiliu/eval/pooling.py` | Explicit modes already supplied | No change. |
| CLI grouped search | Explicit mode already supplied | No change. |
| Stage 3A frozen input projection | Explicit lexical required | Changed its historical replay construction to `mode="lexical"`. |
| Stage 3R / QC frozen scripts and assets | Historical artifacts / explicit bases | No frozen artifact changed. |
| Test-only evidence helpers | Fixture-local behavior | Covered by the full suite; no production caller change required. |

No repository evidence identified a published external Product Search API client. Therefore no external-client compatibility claim or migration is inferred.

The historical Stage 3A projection was the one live internal caller relying on the old omitted-mode behavior. Making it explicit preserves its frozen lexical replay while allowing the product endpoint default to become Auto.
