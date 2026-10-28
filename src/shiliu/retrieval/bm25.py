"""Fixed Collection subtitle ranking contract; bootstrap is operator-only."""
from psycopg import sql
from shiliu.storage.errors import StorageError

VERSION = '1.5.1'
SOURCE_COMMIT = 'fa142d049d08eac45a263f5abc250c8877ae076e'
SCHEMA = 'shiliu_search'
INDEX = 'shiliu.retrieval_units_chunk_bm25'
RANKING_VERSION = 'pg-collection-chunk-bm25-v1'
QUERY_FUNCTIONS = (
    'to_bm25query(text,text)',
    'bm25_text_bm25query_score(text,shiliu_search.bm25query)',
    'bm25_get_current_score()',
)


def check_extension(conn):
    row = conn.execute("SELECT e.extversion,n.nspname,pg_catalog.current_setting('pg_textsearch.library_version',true) AS library_version FROM pg_catalog.pg_extension e JOIN pg_catalog.pg_namespace n ON n.oid=e.extnamespace WHERE e.extname='pg_textsearch'").fetchone()
    values = tuple(row.values()) if isinstance(row, dict) else row
    if values != (VERSION, SCHEMA, VERSION):
        raise StorageError('bm25_extension_version_or_schema_mismatch')


def check_index(conn):
    check_extension(conn)
    row = conn.execute("""SELECT i.indisvalid AND i.indisready AND a.amname='bm25'
        AND i.indrelid=pg_catalog.to_regclass('shiliu.retrieval_units')
        AND pg_catalog.pg_get_expr(i.indpred,i.indrelid) = '(unit_type = ''transcript_chunk''::text)'
        AND pg_catalog.pg_get_indexdef(i.indexrelid,1,true)='tokenized_text'
        AND c.reloptions @> ARRAY['text_config=simple','k1=1.2','b=0.75']::text[] AS ready
        FROM pg_catalog.pg_index i JOIN pg_catalog.pg_class c ON c.oid=i.indexrelid
        JOIN pg_catalog.pg_am a ON a.oid=c.relam
        WHERE i.indexrelid=pg_catalog.to_regclass('shiliu.retrieval_units_chunk_bm25')""").fetchone()
    if row is None or (row['ready'] if isinstance(row,dict) else row[0]) is not True:
        raise StorageError('bm25_index_not_ready')


def identity(tokenizer_profile):
    return dict(index_name=INDEX, index_version=RANKING_VERSION,
                tokenizer='jieba-simple-bm25', lexical_profile=tokenizer_profile,
                extension='pg_textsearch', extension_version=VERSION,
                source_commit=SOURCE_COMMIT, text_config='simple', k1=1.2, b=0.75)


def install_extension(conn):
    """Dedicated administrative bootstrap, never called by Application startup."""
    conn.execute('CREATE SCHEMA IF NOT EXISTS shiliu_search')
    conn.execute('REVOKE ALL ON SCHEMA shiliu_search FROM PUBLIC')
    conn.execute("CREATE EXTENSION IF NOT EXISTS pg_textsearch WITH SCHEMA shiliu_search VERSION '1.5.1'")
    check_extension(conn)
    conn.execute('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA shiliu_search FROM PUBLIC')
    conn.execute('REVOKE ALL ON TYPE shiliu_search.bm25query,shiliu_search.bm25vector FROM PUBLIC')


def grant_query_access(conn, role, *, grant_option=False):
    """The restore operator may receive these capabilities WITH GRANT OPTION."""
    suffix = sql.SQL(' WITH GRANT OPTION' if grant_option else '')
    for object_sql in ('SCHEMA shiliu_search', 'TYPE shiliu_search.bm25query',
                       *(f'FUNCTION shiliu_search.{f}' for f in QUERY_FUNCTIONS)):
        privilege = 'USAGE' if object_sql.startswith(('SCHEMA','TYPE')) else 'EXECUTE'
        conn.execute(sql.SQL('GRANT '+privilege+' ON '+object_sql+' TO {}').format(sql.Identifier(role)) + suffix)
