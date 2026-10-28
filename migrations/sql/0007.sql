-- Preserve every stable unit ID while binding uniqueness to its real workspace.
ALTER TABLE shiliu.retrieval_units DROP CONSTRAINT retrieval_units_pkey;
ALTER TABLE shiliu.retrieval_units ADD PRIMARY KEY (workspace_id,unit_id);
ALTER TABLE shiliu.collection_embeddings DROP CONSTRAINT collection_embeddings_pkey;
ALTER TABLE shiliu.collection_embeddings ADD PRIMARY KEY (workspace_id,unit_id,profile_id);
-- Nullable additions preserve historical traces without inventing new algorithms.
ALTER TABLE shiliu.retrieval_search_traces ADD COLUMN storage_backend text;
ALTER TABLE shiliu.retrieval_search_traces ADD COLUMN lexical_profile text;
ALTER TABLE shiliu.retrieval_search_traces ADD COLUMN embedding_profile text;
ALTER TABLE shiliu.retrieval_search_traces ADD COLUMN degraded_reason text;
-- Rebind the two existing scoped FKs to the new primary key, then retire the
-- redundant unique constraint. No IDs or referencing rows change.
ALTER TABLE shiliu.retrieval_unit_folders DROP CONSTRAINT fk_ca2bae9c41a3ae865919;
ALTER TABLE shiliu.collection_embeddings DROP CONSTRAINT fk_f0d33a7b9f4d399497d0;
ALTER TABLE shiliu.retrieval_units DROP CONSTRAINT retrieval_units_workspace_id_unit_id_key;
ALTER TABLE shiliu.retrieval_unit_folders ADD CONSTRAINT fk_ca2bae9c41a3ae865919 FOREIGN KEY (workspace_id,unit_id) REFERENCES shiliu.retrieval_units(workspace_id,unit_id) ON DELETE CASCADE DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE shiliu.collection_embeddings ADD CONSTRAINT fk_f0d33a7b9f4d399497d0 FOREIGN KEY (workspace_id,unit_id) REFERENCES shiliu.retrieval_units(workspace_id,unit_id) ON DELETE CASCADE DEFERRABLE INITIALLY IMMEDIATE;
