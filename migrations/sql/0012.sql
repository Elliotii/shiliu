-- Extension installation is a separate, explicit administrator bootstrap.
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_extension e
        JOIN pg_catalog.pg_namespace n ON n.oid=e.extnamespace
        WHERE e.extname='pg_textsearch' AND e.extversion='1.5.1' AND n.nspname='shiliu_search')
        OR pg_catalog.current_setting('pg_textsearch.library_version',true) IS DISTINCT FROM '1.5.1'
    THEN RAISE EXCEPTION 'BM25 requires administrator bootstrap of shiliu_search.pg_textsearch 1.5.1 and preloaded library';
    END IF;
END $$;
CREATE INDEX retrieval_units_chunk_bm25 ON shiliu.retrieval_units
USING bm25 (tokenized_text shiliu_search.text_bm25_ops)
WITH (text_config='simple', k1=1.2, b=0.75)
WHERE unit_type='transcript_chunk';
