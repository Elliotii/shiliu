SET search_path TO shiliu, public;

-- NULL preserves the protection of rows written before the boundary split.
ALTER TABLE assistant_memory_suppressions ADD COLUMN wiki_source_message_ids_json jsonb;
