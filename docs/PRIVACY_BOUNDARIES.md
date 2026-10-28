# Public and private data boundaries

The repository contains application code, schemas, protocols, synthetic fixtures,
and sanitized reports. Local user data and raw model artifacts are not source
code and must not be committed.

## Allowed in Git

- Runtime and evaluation code.
- Silver evaluation protocols and schemas.
- Synthetic test fixtures.
- Sanitized aggregate reports and offline analysis scripts.
- Documentation using synthetic account, folder, video, and snapshot identifiers.

## Local-only data

- API keys, cookies, login QR codes, and credential exports.
- SQLite databases, WAL/SHM files, and local backups.
- Real favorite-list exports and candidate-video JSONL files.
- Actual Silver Reference, Silver Eval, disagreement, manifest, and call records.
- Taxonomy run directories, prompts, raw responses, and repair artifacts.
- Unsanitized cost-analysis samples and report source data.
- Real video metadata, subtitles, and summaries captured for local integration tests.

Local-only artifacts must remain covered by `.gitignore`. If a real artifact is
needed for a public test, create a minimal synthetic equivalent instead of
copying user content into the repository.

Removing a file from the current branch does not remove it from earlier Git
history. Before making the repository public, publish from a sanitized history
or perform a separately reviewed history cleanup.

## PostgreSQL 0.4.0 release boundary

This release publishes a curated code/schema/test snapshot on top of existing public main, not the private development branch history. Included aggregate evaluation results explicitly separate evidence coverage, answer completion and citation support. Private S0/Query/Gold, answers, source packages, deployment bindings, paired backups, screenshots, provider logs and internal operational reports remain local. Historical author metadata and local-path examples already present in public main history are not rewritten; current examples remove the private home prefix. A regex scan is a bounded safety check, not proof against every possible credential format.
