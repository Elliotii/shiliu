# Backend Search Path

`POST /api/search` validates `ProductSearchRequest` (backend default `lexical`) and calls `ProductSearchService.search`, which constructs `SearchRequest` and invokes `SearchOrchestrator.search_raw`. Explicit lexical does not invoke Auto routing.
