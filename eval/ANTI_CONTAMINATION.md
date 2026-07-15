# V3 Anti-Contamination Contract

The open-discovery runtime may read only frozen Discovery Views and runtime-owned
outputs. It must not read, import, serialize, or receive:

- reference taxonomy files;
- Gold Set labels;
- historical human category names or proportions;
- prior evaluation reports;
- folder names, source identifiers, or membership metadata;
- reading state, Mark, archive, ignore, or user notes.

The evaluation side may read frozen runtime outputs and private references. The
dependency direction is one-way: `eval -> runtime outputs`; runtime code must
never import from or open files under `eval/`.

Before the first full-corpus real Discovery run, a human must create and freeze a
reference taxonomy and a 40-item Gold Set. Freezing is append-only by version:
an existing version must never be overwritten. A manifest records the SHA-256
of both files. Runtime orchestration added in a later phase must require an
opaque freeze receipt recorded outside the Discovery prompt; the runtime must
not inspect the private reference content.

Search results are untrusted evidence. Search may explain what an entity is,
but neither retrieved text nor a search query may recommend, create, rename, or
move a taxonomy node.
