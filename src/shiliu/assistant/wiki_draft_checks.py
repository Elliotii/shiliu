"""Bind explicit current and historical user authorization to real messages."""
import re


def requests_memory_write(message):
    """Only route clear destination instructions, not the research topic Memory."""
    for clause in re.split(r'[。；，,;\n]', message):
        if re.search(r'(?:不|别|无需|禁止).{0,8}(?:Memory|记忆)', clause, re.I):
            continue
        if re.search(r'(?:在|到|进|入)\s*(?:Memory|记忆)(?:里|中|\s|记住|保存|$)|(?:Memory|记忆)(?:里|中)?\s*(?:记住|保存|更正|更新)|(?:更正|更新|修改).{0,8}(?:Memory|记忆)', clause, re.I):
            return True
    return False


def bind_scope(message, quotes):
    """The caller selects spans, but only the actual user can supply their text."""
    if not quotes or any(not q.strip() or q not in message for q in quotes):
        raise ValueError('wiki_scope_requires_exact_user_quotes')
    # A mixed-destination request must select a Wiki-specific clause, not the
    # whole message. Provenance checks below are independent of these markers.
    for quote in quotes:
        if requests_memory_write(quote):
            raise ValueError('wiki_scope_contains_memory_instruction')
    if requests_memory_write(message) and any(not re.search(r'Wiki|知识页|知识库', q, re.I) for q in quotes):
        raise ValueError('mixed_destination_requires_wiki_clause')
    return list(dict.fromkeys(quotes))


def bind_history_quotes(store, conn, thread_id, current_id, instruction, refs):
    if not refs:
        return []
    from shiliu.assistant.tools import _direct_knowledge_save_requested
    if not current_id or not _direct_knowledge_save_requested(instruction):
        raise ValueError('historical_wiki_authorization_required')
    current = store.knowledge_message(current_id, thread_id=thread_id, wiki_evidence=True, conn=conn)
    previous = conn.execute("SELECT id FROM assistant_messages WHERE workspace_id=%s AND thread_id=%s AND role='user' AND seq<%s ORDER BY seq DESC LIMIT 1",
                            (store.workspace_id, thread_id, current['seq'])).fetchone()
    result=[]
    for ref in refs:
        old=store.knowledge_message(ref['message_id'], thread_id=thread_id, wiki_evidence=True, conn=conn)
        quote=ref['quote']
        if old['role']!='user' or old['seq']>=current['seq'] or quote not in old['content']:
            raise ValueError('historical_wiki_quote_invalid')
        if quote not in instruction and not (previous and previous['id']==old['id'] and re.search(r'刚才|上一条|上一轮',instruction)):
            raise ValueError('historical_wiki_reference_ambiguous')
        if requests_memory_write(quote):
            raise ValueError('historical_scope_requires_content_not_memory_instruction')
        result.append(ref)
    return result
