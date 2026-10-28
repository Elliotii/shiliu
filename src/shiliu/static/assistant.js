(() => {
  const root = document.querySelector('.assistant-app[data-enabled="true"]');
  if (!root) return;
  const $ = id => document.getElementById(id);
  const urlState = new URL(location.href);
  const state = {
    spaceId: null,
    threadId: urlState.searchParams.get('thread'),
    runId: null,
    timer: null,
    stream: null,
    streamRunId: null,
    spaces: [],
    capabilities: {},
    historyCursor: null,
    navigationSerial: 0,
    historyRequestSerial: 0,
    navigationPending: false,
    presentedThreadId: null,
    runActionPending: false,
    savePending: false,
    knowledgeSerial: 0,
    knowledgeRenderedSerial: 0,
    knowledgeLoading: false,
    knowledgeView: 'active',
    draftThreadId: null,
    draftSpaceId: null,
    feedbackSeen: new Set(),
    feedbackSerial: 0,
    renderedThread: null,
    managementSerial: 0,
    activitySerial: 0,
  };
  const draftKey = (threadId, spaceId) => `shiliu-draft:${spaceId}:${threadId}`;
  function persistDraft() {
    if (!state.draftThreadId) return;
    try { sessionStorage.setItem(draftKey(state.draftThreadId, state.draftSpaceId), $('assistant-chat-form').elements.input.value); } catch {}
  }
  function restoreDraft(thread) {
    if (state.draftThreadId === thread.id) return;
    const input = $('assistant-chat-form').elements.input;
    try { input.value = sessionStorage.getItem(draftKey(thread.id, thread.space_id)) || ''; } catch { input.value = ''; }
    state.draftThreadId = thread.id;
    state.draftSpaceId = Number(thread.space_id);
  }
  window.addEventListener('pagehide', persistDraft);
  function beginNavigation() {
    persistDraft();
    clearTimeout($('assistant-toast')._timer); $('assistant-toast').hidden = true;
    state.draftThreadId = null;
    ++state.knowledgeSerial;
    state.stream?.close(); state.stream = null; state.streamRunId = null;
    state.navigationSerial += 1;
    state.historyRequestSerial += 1;
    state.navigationPending = true;
    state.presentedThreadId = null;
    state.threadId = null;
    state.runId = null;
    state.historyCursor = null;
    clearTimeout(state.timer);
    closeDrawer();
    $('assistant-error').hidden = true;
    $('assistant-thread-state').textContent = '正在切换对话…';
    $('assistant-chat-form').elements.input.disabled = true;
    ['assistant-send', 'assistant-cancel', 'assistant-finish', 'assistant-abandon', 'assistant-resume'].forEach(id => { $(id).hidden = true; });
    ['assistant-new-thread', 'assistant-open-history'].forEach(id => { $(id).disabled = true; });
    return state.navigationSerial;
  }
  const navigationCurrent = (serial, spaceId) =>
    serial === state.navigationSerial && spaceId === state.spaceId;
  function rememberThread(thread) {
    state.threadId = thread.id;
    state.spaceId = Number(thread.space_id);
    restoreDraft(thread);
    $('assistant-space').value = String(state.spaceId);
    sessionStorage.setItem('shiliu.assistant.thread', thread.id);
    sessionStorage.setItem('shiliu.assistant.space', String(state.spaceId));
    sessionStorage.setItem(`shiliu.assistant.space.${state.spaceId}`, thread.id);
    localStorage.setItem('shiliu.assistant.recent', thread.id);
    const url = new URL(location.href);
    url.searchParams.set('thread', thread.id);
    history.replaceState(null, '', url);
  }

  async function api(path, options = {}) {
    const response = await fetch(`/api/assistant${path}`, {
      headers: {'Content-Type': 'application/json'}, ...options,
    });
    const value = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = typeof value.detail === 'string' ? value.detail : value.detail?.error || JSON.stringify(value.detail || value);
      const error = new Error(detail || `请求失败（${response.status}）`);
      error.status = response.status;
      throw error;
    }
    return value;
  }
  const operationKey = prefix => `${prefix}:${crypto.randomUUID()}`;
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
  const parsePayload = message => { try { return JSON.parse(message.provider_payload_json || '{}'); } catch { return {}; } };

  function inlineMarkdown(text) {
    let value = escapeHtml(text);
    value = value.replace(/`([^`]+)`/g, '<code>$1</code>');
    value = value.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    value = value.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    return value;
  }

  function renderMarkdown(text) {
    const lines = String(text || '').split('\n');
    const output = [];
    let list = null;
    let code = false;
    let codeLines = [];
    const closeList = () => { if (list) { output.push(`</${list}>`); list = null; } };
    for (let index = 0; index < lines.length; index += 1) {
      const line = lines[index];
      if (line.trim().startsWith('```')) {
        closeList();
        if (code) { output.push(`<pre><code>${escapeHtml(codeLines.join('\n'))}</code></pre>`); codeLines = []; }
        code = !code;
        continue;
      }
      if (code) { codeLines.push(line); continue; }
      const heading = line.match(/^(#{1,3})\s+(.+)$/);
      const bullet = line.match(/^\s*[-*]\s+(.+)$/);
      const numbered = line.match(/^\s*\d+[.)]\s+(.+)$/);
      const nextLine = lines[index + 1] || '';
      const isTable = line.includes('|') && /^\s*\|?\s*:?-{3,}/.test(nextLine);
      if (isTable) {
        closeList();
        const cells = value => value.trim().replace(/^\||\|$/g, '').split('|').map(cell => cell.trim());
        const headers = cells(line);
        index += 2;
        const rows = [];
        while (index < lines.length && lines[index].includes('|') && lines[index].trim()) {
          rows.push(cells(lines[index])); index += 1;
        }
        index -= 1;
        output.push(`<div class="assistant-table-wrap"><table><thead><tr>${headers.map(cell => `<th>${inlineMarkdown(cell)}</th>`).join('')}</tr></thead><tbody>${rows.map(row => `<tr>${row.map(cell => `<td>${inlineMarkdown(cell)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`);
      }
      else if (heading) { closeList(); const level = heading[1].length; output.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`); }
      else if (bullet || numbered) {
        const wanted = bullet ? 'ul' : 'ol';
        if (list !== wanted) { closeList(); list = wanted; output.push(`<${wanted}>`); }
        output.push(`<li>${inlineMarkdown((bullet || numbered)[1])}</li>`);
      } else {
        closeList();
        if (line.trim()) output.push(`<p>${inlineMarkdown(line)}</p>`);
      }
    }
    closeList();
    if (codeLines.length) output.push(`<pre><code>${escapeHtml(codeLines.join('\n'))}</code></pre>`);
    return output.join('');
  }

  function toast(text) {
    state.feedbackSerial += 1;
    const node = $('assistant-toast');
    node.textContent = text; node.hidden = false;
    node.classList.remove('assistant-save-feedback');
    clearTimeout(node._timer);
    node._timer = setTimeout(() => { node.hidden = true; }, 2200);
  }

  function showSaveFeedback(feedback, scope = {spaceId: state.spaceId, threadId: state.threadId}) {
    if (!feedback?.count || !feedback.operation_key || Number(scope.spaceId) !== Number(state.spaceId) || scope.threadId !== state.threadId || (scope.serial != null && scope.serial !== state.navigationSerial)) return;
    const serial = state.navigationSerial;
    const items = (feedback.items || []).filter(item => {
      const key = `shiliu-save-feedback:${item.operation_key || `${feedback.kind}:${item.page_id || item.memory_id}:${item.version}`}`;
      if (state.feedbackSeen.has(key)) return false;
      try { if (sessionStorage.getItem(key)) return false; } catch {}
      state.feedbackSeen.add(key);
      try { sessionStorage.setItem(key, 'seen'); } catch {}
      return true;
    });
    if (!items.length) return;
    const notice = ++state.feedbackSerial;
    const node = $('assistant-toast');
    clearTimeout(node._timer); node.replaceChildren(); node.hidden = false;
    node.classList.add('assistant-save-feedback');
    const label = document.createElement('span');
    const shortTitle = title => {
      const text = String(title || '').replace(/\s+/g, ' ').trim();
      return text.length > 14 ? `${text.slice(0, 14)}…` : text;
    };
    const kinds = new Set(items.map(item => item.kind || feedback.kind));
    label.textContent = kinds.size > 1 ? '已保存知识与记忆' : kinds.has('wiki')
      ? `已保存知识${items.length > 1 ? ` · ${items.length} 页` : ''}${items.length === 1 ? ` · ${shortTitle(items[0].title)}` : ''}`
      : `已保存记忆 · ${shortTitle(items[0].title)}`;
    node.append(label);
    const current = () => notice === state.feedbackSerial && serial === state.navigationSerial && Number(state.spaceId) === Number(scope.spaceId) && state.threadId === scope.threadId;
    items.forEach(item => {
      const view = document.createElement('button'); view.type = 'button'; view.textContent = `查看${feedback.items.length > 1 ? `：${item.title}` : ''}`;
      view.onclick = async () => {
        if (!current()) return;
        try {
          if (item.page_id) { openDrawer('assistant-knowledge-panel', 'Wiki'); await openKnowledgePage(item.page_id); }
          else { await loadMemories(); if (current()) openDrawer('assistant-memory-panel', '记忆'); }
        } catch (error) { if (current()) toast(`暂时无法查看：${error.message}`); }
      };
      if (!item.undo) { node.append(view); return; }
      const undo = document.createElement('button'); undo.type = 'button';
      undo.textContent = `撤销${items.length > 1 ? `：${shortTitle(item.title)}` : ''}`;
      undo.title = item.undo.kind === 'archive' ? '撤销本次新增：可恢复归档，不是永久删除' : '撤销本次修改；后续已发生变化时将拒绝';
      const operation = operationKey('ui-save-undo');
      undo.onclick = async () => {
        if (!current() || undo.disabled) return;
        undo.disabled = true; clearTimeout(node._timer);
        try {
          const body = {space_id: scope.spaceId, expected_version: item.version, operation_key: operation};
          if (item.undo.kind === 'memory_created') {
            await api(`/memories/${item.memory_id}/undo-created`, {method: 'POST', body: JSON.stringify({...body, save_operation_key: item.undo.save_operation_key})});
          } else if (item.undo.kind === 'archive') {
            await api(`/wiki/${item.page_id}/lifecycle`, {method: 'POST', body: JSON.stringify({...body, action: 'archive'})});
          } else {
            await api(`/wiki/${item.page_id}/revert`, {method: 'POST', body: JSON.stringify({...body, target_version: item.undo.target_version})});
          }
          if (!current()) return;
          undo.textContent = '已撤销';
          node._timer = setTimeout(() => { node.hidden = true; }, 5000);
          try {
            if (item.page_id) await loadKnowledge($('assistant-knowledge-query').value.trim());
            else await loadMemories();
          } catch (error) {
            if (current()) {
              const note = document.createElement('span'); note.textContent = '已撤销；列表刷新失败，请重新打开查看'; node.append(note);
            }
          }
        } catch (error) {
          undo.disabled = false;
          if (current()) toast(`未能撤销，原结果保留：${error.message}`);
        }
      };
      node.append(undo);
    });
    const progress = document.createElement('span'); progress.className = 'assistant-feedback-progress';
    progress.setAttribute('aria-hidden', 'true'); node.append(progress);
    node._timer = setTimeout(() => { node.hidden = true; }, 5000);
  }

  function presentSaveFeedback(thread) {
    const results = thread.messages.filter(message => message.role === 'tool').map(message => {
      try {
        const savedAt = Date.parse(message.created_at);
        if (!Number.isFinite(savedAt) || Date.now() - savedAt > 30000) return null;
        return JSON.parse(message.content).coverage?.save_feedback;
      } catch { return null; }
    }).filter(Boolean);
    // A snapshot may contain several saves. Keep every unseen receipt available.
    if (results.length) showSaveFeedback({
      kind: results[0].kind, operation_key: results.map(result => result.operation_key).join('|'),
      count: results.reduce((count, result) => count + result.count, 0),
      items: results.flatMap(result => (result.items || []).map(item => ({...item,
        kind: result.kind, operation_key: item.operation_key || result.operation_key}))),
    }, {spaceId: thread.space_id, threadId: thread.id});
  }

  function openDrawer(panel, title) {
    if(panel!=='assistant-messages-panel'){++messages.serial;++messages.detailSerial;messages.selected=null;}
    $('assistant-messages-panel').parentElement.classList.toggle('assistant-drawer-messages',panel==='assistant-messages-panel');
    $('assistant-drawer-title').textContent = title;
    ++state.managementSerial; ++state.activitySerial;
    ['assistant-history-panel', 'assistant-memory-panel', 'assistant-knowledge-panel', 'assistant-settings-panel', 'assistant-spaces-panel', 'assistant-messages-panel'].forEach(id => { $(id).hidden = id !== panel; });
    $('assistant-shade').hidden = false;
    $('assistant-close-drawer').focus();
  }
  function closeDrawer() { ++messages.detailSerial; messages.selected=null; $('assistant-messages-panel').parentElement.classList.remove('assistant-drawer-messages'); ++messages.serial; ++state.managementSerial; ++state.activitySerial; $('assistant-shade').hidden = true; }

  async function loadSpaces(useDefault = false) {
    const {spaces} = await api('/spaces');
    state.spaces = spaces;
    const select = $('assistant-space');
    select.innerHTML = '';
    spaces.forEach(space => {
      const option = document.createElement('option');
      option.value = space.id; option.textContent = space.name;
      select.append(option);
    });
    if (!spaces.length) {
      state.spaceId = null;
      const option = document.createElement('option');
      option.textContent = '先创建收藏范围'; option.value = '';
      select.append(option);
      openDrawer('assistant-spaces-panel', '收藏范围');
      return;
    }
    const stored = Number(sessionStorage.getItem('shiliu.assistant.space') || localStorage.getItem('shiliu.assistant.space'));
    const defaultSpace = spaces.find(space => space.name === '全库探索' && space.all_active && !space.video_ids?.length);
    const selected = useDefault ? defaultSpace : spaces.find(space => Number(space.id) === Number(state.spaceId));
    state.spaceId = selected?.id || (spaces.some(space => space.id === stored) ? stored : spaces[0].id);
    select.value = state.spaceId;
    sessionStorage.setItem('shiliu.assistant.space', String(state.spaceId));
  }

  async function newThread() {
    if (!state.spaceId) { openDrawer('assistant-spaces-panel', '收藏范围'); return; }
    const spaceId = state.spaceId;
    const serial = state.navigationSerial;
    try {
      const {thread} = await api('/threads', {method:'POST', body:JSON.stringify({space_id:spaceId, title:''})});
      if (!navigationCurrent(serial, spaceId)) return;
      rememberThread(thread); renderThread(thread);
    } catch (error) {
      if (navigationCurrent(serial, spaceId)) showFatal(error);
    }
  }

  async function loadHistory(append = false) {
    if (!state.spaceId) return;
    const spaceId = state.spaceId;
    const serial = state.navigationSerial;
    const requestSerial = ++state.historyRequestSerial;
    if (!append) { state.historyCursor = null; $('assistant-history-list').innerHTML = ''; }
    const cursor = state.historyCursor;
    const params = new URLSearchParams({space_id:String(spaceId), limit:'20'});
    if (cursor) { params.set('before_updated_at', cursor.before_updated_at); params.set('before_id', cursor.before_id); }
    const result = await api(`/threads?${params}`);
    if (!navigationCurrent(serial, spaceId) || requestSerial !== state.historyRequestSerial) return false;
    const list = $('assistant-history-list');
    result.threads.forEach(item => {
      const button = document.createElement('button');
      button.type = 'button'; button.className = 'assistant-history-item';
      const title = document.createElement('strong'); title.textContent = item.title;
      const detail = document.createElement('span');
      const statuses = {queued:'排队中', running:'正在处理', budget_exhausted:'等待继续', interrupted:'已中断', failed:'处理失败', cancelled:'已放弃', completed:'已完成'};
      const status = item.last_error_code === 'context_budget_exceeded' && item.run_status === 'budget_exhausted'
        ? '内容超限' : (statuses[item.run_status] || '新对话');
      detail.textContent = `${new Date(item.updated_at).toLocaleString('zh-CN')} · ${status}`;
      button.append(title, detail);
      button.onclick = async () => {
        const serial = beginNavigation();
        try {
          await openThread(item.id);
          if (serial === state.navigationSerial && !state.navigationPending) closeDrawer();
        } catch (error) { if (serial === state.navigationSerial) showFatal(error); }
      };
      list.append(button);
    });
    if (!list.children.length) list.textContent = '当前范围还没有对话。';
    state.historyCursor = result.next_cursor;
    $('assistant-history-more').hidden = !state.historyCursor;
    return true;
  }

  async function openThread(id) {
    clearTimeout(state.timer);
    const spaceId = state.spaceId;
    const serial = state.navigationSerial;
    const {thread} = await api(`/threads/${encodeURIComponent(id)}`);
    if (!navigationCurrent(serial, spaceId)) return;
    if (Number(thread.space_id) !== spaceId) throw new Error('scope_changed');
    rememberThread(thread);
    renderThread(thread);
  }

  function sourcesForRun(thread, runId) {
    const run = thread.runs.find(item => item.id === runId);
    const delivered = run?.working_state?.model_delivered_materials || [];
    const current = run?.working_state?.context_observation?.material_projection || [];
    const currentKeys = new Set(current.map(item => JSON.stringify(item)));
    const seenNotes = new Set();
    return delivered.map(item => ({...item, retained:currentKeys.has(JSON.stringify(item))})).filter(item => {
      if (item.kind !== 'task_note') return true;
      const key = `${item.title}:${item.retained}`;
      if (seenNotes.has(key)) return false;
      seenNotes.add(key); return true;
    });
  }

  function createSources(thread, runId) {
    const sources = sourcesForRun(thread, runId);
    const hadMaterialTools = thread.messages.some(message => message.run_id === runId &&
      message.role === 'tool' && ['search_knowledge','collection_search','collection_read','knowledge_search','knowledge_read','run_read_result']
        .includes(parsePayload(message).name));
    if (!sources.length && !hadMaterialTools) return null;
    const run = thread.runs.find(item => item.id === runId);
    const details = document.createElement('details');
    details.className = 'assistant-sources';
    const summary = document.createElement('summary');
    summary.textContent = sources.length ? `本次参考 · ${sources.length} 项` : '本次参考 · 范围未记录';
    const list = document.createElement('div'); list.className = 'assistant-source-list';
    if (!sources.length) { const unknown = document.createElement('div'); unknown.textContent = '这条回答没有可核对的模型输入记录，无法确认实际阅读范围。'; list.append(unknown); }
    if (run?.working_state?.model_delivered_materials_truncated) {
      const warning = document.createElement('div'); warning.textContent = '记录较多，这里仅展示最近部分材料。'; list.append(warning);
    }
    const views = {candidate_excerpt:'候选摘要（未读取正文）', overview:'材料概览', description:'简介', summary:'摘要', transcript:'字幕', notes:'笔记', search_excerpt:'搜索命中片段', result_index:'结果索引'};
    sources.forEach(source => {
      const item = document.createElement('div');
      if (source.kind === 'task_note') {
        item.textContent = `${source.title} · 任务笔记摘录／回执 · ${source.retained ? '当前输入保留' : '本轮曾送入，当前未保留'} · 正文范围以原始读取记录为准`;
        list.append(item); return;
      }
      const position = source.position || {};
      const range = Number.isFinite(Number(position.start)) && Number.isFinite(Number(position.end)) && position.end !== undefined
        ? ` · 第 ${Number(position.start) + 1}–${position.end} 字符${position.total ? `／共 ${position.total}` : ''}` : ' · 范围未记录';
      const complete = source.complete ? ' · 该视图已覆盖' : ' · 部分／范围未记录';
      const state = source.retained ? '当前输入保留' : '本轮曾送入，当前未保留';
      item.textContent = `${source.title} · ${views[source.view] || source.view} · ${source.projection}${range}${complete} · ${source.origin === '历史' ? '历史依据 · ' : source.origin === 'bootstrap' ? '程序发现 · ' : ''}${state}${(source.kind?.startsWith('knowledge_') || source.source_ref?.startsWith('wiki:')) ? ' · 原视频仅作知识页血缘' : ''}`;
      list.append(item);
    });
    details.append(summary, list);
    return details;
  }

  function activeRun(thread) {
    return thread.runs.find(run => run.actions?.current && run.actions?.abandon) || null;
  }
  function currentToolName(thread, runId) {
    const values = thread.messages.filter(message => message.run_id === runId);
    for (let index = values.length - 1; index >= 0; index -= 1) {
      const payload = parsePayload(values[index]);
      if (payload.name) return payload.name;
      if (payload.tool_calls?.[0]?.function?.name) return payload.tool_calls[0].function.name;
    }
    return '';
  }
  function shortStatus(run, toolName) {
    if (run.status === 'queued') return '正在排队…';
    if (run.working_state?.finish_requested && run.status === 'running') return '正在根据已读材料收尾…';
    if (run.status === 'interrupted') return '服务曾中断，可以从上一步继续。';
    if (run.status === 'budget_exhausted') return run.last_error_code === 'context_budget_exceeded'
      ? (run.actions?.resume ? '本次内容超出容量，可尝试一次重建上下文后继续。' : '本次内容仍超出容量，请放弃本次回答后缩小范围。')
      : '本段已达到处理上限，等待继续。';
    if (run.status === 'failed') return run.last_error_code === 'context_compaction_failed' && run.actions?.resume
      ? '材料压缩未完成，已保留阅读进度；可重试一次继续。'
      : '本次处理失败，可放弃后继续聊天。';
    if (toolName === 'collection_read' || toolName === 'run_read_result') return '正在阅读材料…';
    if (toolName.startsWith('collection_')) return '正在搜索收藏…';
    if (toolName.startsWith('context7_')) return '正在读取技术文档…';
    if (toolName.startsWith('memory_')) return '正在整理记忆…';
    return '正在生成回答…';
  }

  function renderThread(thread) {
    state.renderedThread = thread;
    const scroll = $('assistant-scroll');
    const followBottom = state.presentedThreadId !== thread.id ||
      scroll.scrollHeight - scroll.scrollTop - scroll.clientHeight < 80;
    const previousTop = scroll.scrollTop;
    state.navigationPending = false;
    state.presentedThreadId = thread.id;
    ['assistant-new-thread', 'assistant-open-history'].forEach(id => { $(id).disabled = false; });
    const box = $('assistant-messages'); box.innerHTML = '';
    const visible = thread.messages.filter(message => message.role === 'user' || (message.role === 'assistant' && message.content.trim() && !parsePayload(message).tool_calls));
    $('assistant-welcome').hidden = visible.length > 0;
    box.hidden = visible.length === 0;
    visible.forEach(message => {
      const node = document.createElement('article');
      node.className = `assistant-message ${message.role}`;
      if (message.role === 'user') node.textContent = message.content;
      else {
        const label = document.createElement('div'); label.className = 'assistant-answer-label'; label.textContent = '拾流';
        const body = document.createElement('div'); body.className = 'assistant-markdown'; body.innerHTML = renderMarkdown(message.content);
        node.append(label, body);
        const sources = createSources(thread, message.run_id);
        if (sources) node.append(sources);
      }
      box.append(node);
    });
    presentSaveFeedback(thread);

    const run = activeRun(thread);
    state.runId = run?.id || null;
    const isRunning = run && ['queued','running'].includes(run.status);
    const isResumable = Boolean(run?.actions?.resume);
    const draft = run?.working_state?.answer_draft;
    if (isRunning && draft && (draft.text || draft.status === 'invalidated')) {
      const node = document.createElement('article'); node.className = 'assistant-message assistant assistant-draft';
      const label = document.createElement('div'); label.className = 'assistant-answer-label';
      label.textContent = draft.status === 'invalidated' ? '依据已变化，正在核对' : '生成中 · 尚未提交';
      const body = document.createElement('div'); body.className = 'assistant-markdown';
      body.innerHTML = renderMarkdown(draft.text || ''); node.append(label, body); box.append(node);
    }
    if (isRunning && state.streamRunId !== run.id) {
      state.stream?.close(); state.streamRunId = run.id;
      const serial = state.navigationSerial;
      state.stream = new EventSource(`/api/assistant/runs/${run.id}/stream`);
      state.stream.onerror = () => {
        if (serial !== state.navigationSerial) return;
        state.stream?.close(); state.stream = null; state.streamRunId = null;
        schedule();
      };
      state.stream.onmessage = event => {
        if (!navigationCurrent(serial, state.spaceId)) return;
        const snapshot = JSON.parse(event.data).run;
        const currentThread = state.renderedThread;
        const prior = currentThread.runs.find(item => item.id === snapshot.id);
        currentThread.runs = currentThread.runs.map(item => item.id === snapshot.id ? {...item, ...snapshot, working_state: {...item.working_state, ...snapshot.working_state}} : item);
        if (['queued', 'running'].includes(snapshot.status)) {
          if (snapshot.tool_count > (prior?.tool_count || 0)) loadThread().catch(showFatal);
          else renderThread(currentThread);
        }
        else { state.stream?.close(); state.stream = null; state.streamRunId = null; loadThread().catch(showFatal); }
      };
    } else if (!isRunning && state.stream) {
      state.stream.close(); state.stream = null; state.streamRunId = null;
    }

    const selected = new Set(thread.task_focus?.selected_source_refs || []);
    const reads = new Set((thread.task_note?.searched_scope_and_material_refs || [])
      .filter(item => item.tool === 'collection_read' && item.model_read?.received_by_answer_model)
      .flatMap(item => item.source_refs || []));
    (thread.runs || []).forEach(item => (item.working_state?.model_delivered_read_spans || [])
      .forEach(span => { if (span.source_ref) reads.add(span.source_ref); }));
    const noteStatus = selected.size
      ? `选定 ${selected.size} 份 · 已读取 ${reads.size} 份`
      : reads.size ? `已读取 ${reads.size} 份材料` : '';
    $('assistant-thread-state').textContent = run
      ? [shortStatus(run, currentToolName(thread, run.id)), noteStatus].filter(Boolean).join(' · ')
      : noteStatus;
    $('assistant-cancel').hidden = !isRunning;
    $('assistant-finish').hidden = !isRunning || Boolean(run?.working_state?.finish_requested);
    $('assistant-abandon').hidden = !run || isRunning;
    $('assistant-send').hidden = Boolean(run);
    $('assistant-resume').hidden = !isResumable;
    ['assistant-cancel', 'assistant-finish', 'assistant-abandon', 'assistant-resume'].forEach(id => {
      $(id).dataset.threadId = thread.id;
      $(id).dataset.runId = run?.id || '';
      $(id).disabled = state.runActionPending;
    });
    const input = $('assistant-chat-form').elements.input;
    input.disabled = false;
    input.placeholder = run ? '可预写下一条消息；当前任务结束或放弃后再发送' : '输入问题…';
    $('assistant-save-discussion').hidden = !thread.can_save;
    $('assistant-save-discussion').disabled = !thread.can_save || state.savePending;

    const problem = run?.status === 'failed' || run?.last_error_code === 'context_budget_exceeded' ? run : null;
    $('assistant-error').hidden = !problem;
    if (problem) {
      $('assistant-error-message').textContent = problem.actions?.resume
        ? (problem.last_error_code === 'context_budget_exceeded'
          ? '可尝试一次重建并压缩上下文，再继续本次回答。'
          : '可尝试一次修复并继续本次回答。')
        : (problem.status === 'failed'
          ? '这次回答失败。放弃本次回答后，可在同一对话继续。'
          : '本次内容仍超出容量。放弃本次回答后，可缩小问题重新提问。');
      $('assistant-error-detail').textContent = `${problem.last_error_code || 'unknown'}：${problem.last_error_message || '未知错误'}`;
      $('assistant-error-retry').hidden = true;
    }
    if (followBottom) scroll.scrollTop = scroll.scrollHeight;
    else scroll.scrollTop = previousTop;
    if (run && ['queued','running'].includes(run.status) && !state.stream) schedule();
  }

  async function loadThread() {
    if (!state.threadId || state.navigationPending) return;
    const requestedId = state.threadId;
    const serial = state.navigationSerial;
    const spaceId = state.spaceId;
    try {
      const {thread} = await api(`/threads/${requestedId}`);
      if (!navigationCurrent(serial, spaceId) || requestedId !== state.threadId || state.navigationPending) return;
      if (Number(thread.space_id) !== spaceId) throw new Error('scope_changed');
      renderThread(thread);
    } catch (error) {
      if (!navigationCurrent(serial, spaceId) || requestedId !== state.threadId || state.navigationPending) return;
      if (error.message === 'scope_changed' || error.message.includes('对话不存在')) {
        beginNavigation(); sessionStorage.removeItem('shiliu.assistant.thread'); await newThread();
      } else throw error;
    }
  }
  function schedule() {
    clearTimeout(state.timer);
    const serial = state.navigationSerial;
    state.timer = setTimeout(() => {
      if (serial === state.navigationSerial && !state.navigationPending) {
        loadThread().catch(error => { if (serial === state.navigationSerial) showFatal(error); });
      }
    }, 700);
  }

  async function loadMemories() {
    if (!state.spaceId) return;
    const spaceId = state.spaceId;
    const serial = state.navigationSerial;
    const [{memories, memory_epoch}, settings] = await Promise.all([
      api(`/memories?space_id=${spaceId}`), api('/memory-settings')
    ]);
    if (!navigationCurrent(serial, spaceId)) return;
    state.memoryEpoch = memory_epoch;
    $('assistant-auto-memory').checked = settings.auto_enabled;
    const box = $('assistant-memories'); box.innerHTML = '';
    if (!memories.length) {
      const empty = document.createElement('p'); empty.className = 'drawer-intro'; empty.textContent = '当前收藏范围和所有对话暂无可展示的记忆；已忘记的内容不会显示。'; box.append(empty);
    }
    memories.forEach(memory => {
      const card = document.createElement('article'); card.className = 'assistant-memory-card'; card.dataset.memoryId = memory.id;
      const text = document.createElement('p'); text.textContent = memory.text;
      const scope = document.createElement('div'); scope.className = 'assistant-memory-scope';
      const details = [memory.scope_kind === 'user' ? '适用范围：所有对话' : '适用范围：当前收藏范围'];
      details.push(memory.kind === 'context' && memory.expires_at ? '近期背景' : '个人记忆');
      details.push(memory.origin === 'extracted' ? '来源：对话中自动提炼' : '来源：你明确保存或修改');
      const temporal = memory.time_context || {};
      const plan = (temporal.events || []).map(event => `${event.expression} → ${event.value || '具体时间未定'}${event.end_value ? ` 至 ${event.end_value}` : ''}${event.stated_at ? `（原陈述：${new Date(event.stated_at).toLocaleDateString('zh-CN', {timeZone:temporal.timezone || 'Asia/Shanghai'})}）` : ''}`).join('；');
      if (plan) details.push(`当时计划：${plan}`);
      if (temporal.stated_at) details.push(`原陈述时间：${new Date(temporal.stated_at).toLocaleString('zh-CN', {timeZone:temporal.timezone || 'Asia/Shanghai'})}`);
      if (temporal.source_excerpt || memory.source_excerpt) details.push(`原话：${temporal.source_excerpt || memory.source_excerpt}`);
      if (memory.valid_from) details.push(`记忆生效：${new Date(memory.valid_from).toLocaleString('zh-CN', {timeZone:'Asia/Shanghai'})}`);
      if (memory.validity_note) details.push(`有效期说明：${memory.validity_note}`);
      if (memory.expires_at) details.push(`记忆有效至：${new Date(memory.expires_at).toLocaleString('zh-CN', {timeZone:'Asia/Shanghai'})}`);
      if (memory.expires_at && new Date(memory.expires_at) <= new Date()) details.push('已过期，不再用于回答');
      if (memory.status === 'needs_review') details.push('状态：存在未确认冲突，不会用于回答');
      scope.textContent = details.join(' · ');
      const actions = document.createElement('div'); actions.className = 'assistant-memory-actions';
      if (memory.source_thread_id) {
        const source = document.createElement('a');
        source.href = `/assistant?thread=${encodeURIComponent(memory.source_thread_id)}`;
        source.textContent = '查看来源对话';
        actions.append(source);
      }
      const edit = document.createElement('button'); edit.type = 'button'; edit.textContent = '修改';
      const forget = document.createElement('button'); forget.type = 'button'; forget.textContent = '忘记';
      edit.onclick = () => {
        edit.disabled = true; forget.disabled = true;
        const editor = document.createElement('div'); editor.className = 'assistant-memory-editor';
        const field = document.createElement('textarea'); field.rows = 3; field.maxLength = 400; field.value = memory.text; field.setAttribute('aria-label', '修改记忆');
        const buttons = document.createElement('div'); buttons.className = 'assistant-memory-actions';
        const save = document.createElement('button'); save.type = 'button'; save.textContent = '保存修改';
        const cancel = document.createElement('button'); cancel.type = 'button'; cancel.textContent = '取消';
        const supportsTimeContext = Object.prototype.hasOwnProperty.call(memory, 'time_context');
        const timeMode = document.createElement('select'); timeMode.setAttribute('aria-label', '计划时间处理');
        timeMode.innerHTML = '<option value="keep">保留原计划时间（只修改其他内容）</option><option value="update">按本次新表述更新计划时间</option>';
        const error = document.createElement('p'); error.setAttribute('role', 'status');
        buttons.append(save, cancel); editor.append(field); if (supportsTimeContext) editor.append(timeMode); editor.append(error, buttons); text.replaceWith(editor); field.focus();
        cancel.onclick = loadMemories;
        save.onclick = async () => {
          const value = field.value.trim(); if (!value) return;
          if (save.disabled) return;
          save.disabled = true; error.textContent = '';
          try {
            await api(`/memories/${memory.id}`, {method:'PATCH', body:JSON.stringify({text:value, expected_version:memory.version, operation_key:operationKey('ui-correct'), ...(supportsTimeContext ? {update_time_context:timeMode.value === 'update'} : {})})});
            await loadMemories(); toast('已修改');
          } catch (failure) { error.textContent = `未能修改，内容已保留：${failure.message}`; }
          finally { save.disabled = false; }
        };
      };
      forget.onclick = () => {
        forget.textContent = '确认忘记'; forget.classList.add('danger');
        forget.onclick = async () => {
          await api(`/memories/${memory.id}?expected_version=${memory.version}&operation_key=${encodeURIComponent(operationKey('ui-forget'))}`, {method:'DELETE'});
          await loadMemories(); toast('已忘记');
        };
      };
      actions.append(edit, forget); card.append(text, scope, actions); box.append(card);
    });
  }

  async function loadCapabilities() {
    const {capabilities, model} = await api('/capabilities');
    state.capabilities = capabilities;
    $('assistant-model-name').textContent = model === 'deepseek-v4-flash' ? 'DeepSeek V4 Flash' : model;
    const failures = [];
    if (capabilities.memory_index === 'unavailable') failures.push('记忆语义索引暂时不可用，正式记录仍会保存');
    const note = $('assistant-service-note'); note.hidden = failures.length === 0; note.textContent = failures.join('；');
  }

  const coverageLabel = value => ({
    metadata_only: '标题／简介', summary_based: '摘要',
    partial_transcript: '部分字幕', full_available_transcript: '完整可得字幕',
  }[value] || '材料范围未知');
  const materialViewLabel = value => ({
    summary: '摘要', transcript: '字幕', raw_subtitle: '字幕', description: '简介', metadata: '标题信息', note: '笔记', notes: '笔记', time: '时间信息',
  }[value] || '视图未知');
  function planIssueLabel(value) {
    if (value && typeof value === 'object') {
      if (value.source_ref && value.requested_view != null) {
        const views = {transcript:'字幕', summary:'摘要', description:'简介', notes:'笔记', metadata:'元数据', time:'时间信息'};
        const path = String(value.path || '').match(/topics\[(\d+)\]\.blocks\[(\d+)\]/);
        const where = path ? `主题 ${Number(path[1])+1} · 内容块 ${Number(path[2])+1}：` : '';
        return `${where}提交视图为${views[value.requested_view] || '未声明'}，已读取${(value.observed_views || []).map(v => views[v] || '其他视图').join('、') || '尚无可验证正文'}；可在原对话继续修复`;
      }
      return planIssueLabel(value.message || value.code);
    }
    const raw = String(value || '');
    const match = raw.match(/topic\[(\d+)\]\.block\[(\d+)\]\(([^)]*)\):([a-z_]+)/);
    const reasons = {
      source_block_requires_source:'来源块尚未选择依据',
      source_revision_changed:'来源版本已更新，请重新选择',
      wiki_source_out_of_scope:'来源不在当前收藏范围，请重新选择',
      versioned_video_source_required:'来源身份无效，请重新选择',
      invalid_knowledge_block:'内容块不完整',
      personal_quote_required:'个人笔记须对应用户原话',
      personal_block_source_conflict:'个人笔记不能绑定材料来源',
      external_source_not_in_result:'外部来源不在当前有效回执中',
    };
    if (match) return `主题 ${match[1]} · ${match[3] || `块 ${match[2]}`}：${reasons[match[4]] || '请检查内容与来源'}`;
    if (raw.includes('source_out_of_scope')) return '所选来源已超出当前收藏范围，请重新选择';
    if (raw.includes('knowledge_plan_version_conflict')) return '提案已有新版本，请刷新后再调整';
    return '提案内容或来源需要检查';
  }
  function formatDate(value) {
    if (value === null || value === undefined || value === '') return '时间未知';
    const date = typeof value === 'number' ? new Date(value * 1000) : new Date(value);
    return Number.isNaN(date.getTime()) ? '时间未知' : date.toLocaleDateString('zh-CN');
  }

  function guardKnowledgeButtons(box, current) {
    box.querySelectorAll('button').forEach(button => {
      if (!button.onclick || button.dataset.scoped) return;
      button.dataset.scoped = 'true';
      const handler = button.onclick;
      button.onclick = async event => {
        if (!current() || button.disabled) return;
        button.disabled = true;
        try { await handler(event); }
        catch (error) { if (current()) toast(`操作未完成，内容已保留：${error.message}`); }
        finally { if (current()) { button.disabled = false; guardKnowledgeButtons(box, current); } }
      };
    });
  }
  function knowledgeLifecycleButton(page, action, label, current, blockId = null) {
    const button = document.createElement('button'); button.type = 'button'; button.textContent = label;
    const spaceId = state.spaceId;
    const operation = operationKey('ui-wiki-lifecycle');
    button.onclick = async () => {
      if (!current()) return;
      if (action === 'archive' && !window.confirm(`归档“${page.title}”？归档后退出默认检索和自动维护，可以恢复。`)) return;
      await api(`/wiki/${page.id}/lifecycle`, {method:'POST', body:JSON.stringify({
        space_id:spaceId, action, block_id:blockId, expected_version:page.version, operation_key:operation})});
      if (!current()) return;
      toast(action === 'delete_block' ? '已逻辑删除，可撤销；原内容保留用于恢复' : '操作完成');
      if (action === 'archive' || action === 'restore') await loadKnowledge();
      else await openKnowledgePage(page.id);
    };
    return button;
  }
  async function loadKnowledge(query = '') {
    if (!state.spaceId) return;
    const serial = ++state.knowledgeSerial, nav = state.navigationSerial, spaceId = state.spaceId, threadId = state.threadId;
    const requested = () => serial === state.knowledgeSerial && navigationCurrent(nav, spaceId) && threadId === state.threadId;
    const current = () => serial === state.knowledgeRenderedSerial && !state.knowledgeLoading && navigationCurrent(nav, spaceId) && threadId === state.threadId;
    state.knowledgeLoading = true;
    const view = state.knowledgeView;
    let loaded;
    try { loaded = await Promise.all([
      (view === 'pending' || view === 'ignored') ? Promise.resolve({pages:[]}) : api(view === 'deleted' ? `/wiki-management?space_id=${spaceId}&thread_id=${threadId || ""}&status=active` : view === 'archived' ? `/wiki-management?space_id=${spaceId}&thread_id=${threadId || ""}&status=archived` : `/wiki?space_id=${spaceId}&thread_id=${threadId || ""}&query=${encodeURIComponent(query)}`),
      api(`/knowledge-plans?space_id=${spaceId}&view=${view === 'ignored' ? 'ignored' : 'pending'}`),
    ]); } catch (error) {
      if (requested()) { state.knowledgeLoading=false; toast(`知识内容加载失败，请重试：${error.message}`); }
      return;
    }
    if (!requested()) return;
    state.knowledgeLoading=false; state.knowledgeRenderedSerial=serial;
    $('assistant-knowledge-list-view').hidden = false;
    $('assistant-knowledge-detail').hidden = true;
    const [listed, {plans}] = loaded;
    const pages = view === 'ignored' ? [] : view === 'deleted' ? listed.pages.filter(page=>page.deleted_blocks?.length) : listed.pages;
    const box = $('assistant-knowledge-pages'); box.innerHTML = '';
    const filters = document.createElement('nav');
    filters.className = 'assistant-knowledge-views'; filters.setAttribute('aria-label', '知识分类');
    const unfinishedCount = plans.reduce((count, plan) => count + plan.payload.topics.filter((_, index) =>
      !['completed', 'ignored'].includes(plan.results[String(index)]?.status)).length, 0);
    [['active','知识页'],['pending','未完成'],['archived','已归档'],['deleted','已删内容'],['ignored','已忽略']].forEach(([value,label]) => {
      const button = document.createElement('button'); button.type='button';
      button.textContent = label;
      button.setAttribute('aria-current', value === view ? 'page' : 'false');
      if (value === 'pending' && view !== 'ignored' && unfinishedCount) {
        const count = document.createElement('span'); count.textContent = String(unfinishedCount); button.append(count);
      }
      button.onclick = () => { state.knowledgeView=value; return loadKnowledge(query); }; filters.append(button);
    }); box.append(filters);
    const description = document.createElement('p'); description.className = 'assistant-knowledge-view-note';
    description.textContent = {
      active:'已保存、当前可用的知识。未完成的保存请到「未完成」查看。',
      pending:'尚未保存成功的主题。展开查看原因；已保存的页面不会重复写入。',
      archived:'归档页不参与默认检索和后台整理，可以恢复。',
      deleted:'逻辑删除的内容不再用于检索和回答；原内容保留，可撤销删除。',
      ignored:'已忽略的未完成主题，保留历史记录，不会自动重试。',
    }[view]; box.append(description);
    let visiblePlans = 0;
    (view === 'pending' || view === 'ignored' ? plans : []).forEach(plan => {
      const relevant = (_, index) => view === 'ignored'
        ? plan.results[String(index)]?.status === 'ignored'
        : !['completed', 'ignored'].includes(plan.results[String(index)]?.status);
      const topics = plan.payload.topics.filter(relevant);
      if (!topics.length) return;
      visiblePlans++;
      const disclosure = document.createElement('details'); disclosure.className = 'assistant-knowledge-plan';
      const header = document.createElement('summary');
      const title = document.createElement('strong'); title.textContent = topics.map(item=>item.title).join('、');
      const meta = document.createElement('span');
      const saved = Object.values(plan.results).filter(item=>item.status==='completed').length;
      meta.textContent = `${topics.length} 个${view === 'ignored' ? '已忽略' : '未完成'}主题${saved ? ` · ${saved} 页已保存` : ''} · ${formatDate(plan.updated_at || plan.created_at)}`;
      header.append(title, meta); disclosure.append(header);
      const card = document.createElement('div'); card.className = 'assistant-knowledge-plan-body'; disclosure.append(card);
      plan.payload.topics.forEach((item, index) => {
        if (!relevant(item, index)) return;
        const section = document.createElement('section'); section.className = 'assistant-knowledge-plan-item';
        const result = plan.results[String(index)];
        const reason = result?.issues?.length ? [...new Set(result.issues.map(planIssueLabel))].join('；') : result?.reason;
        const heading = document.createElement('h3'); heading.textContent = item.title;
        const purpose = document.createElement('p'); purpose.textContent = item.purpose;
        section.append(heading, purpose);
        if (reason) {
          const issue = document.createElement('details'); issue.className = 'assistant-knowledge-plan-reason';
          const label = document.createElement('summary'); label.textContent = view === 'ignored' ? '查看忽略前的状态与原因' : '查看未完成原因';
          const text = document.createElement('p'); text.textContent = reason; issue.append(label, text); section.append(issue);
        }
        const detail = document.createElement('details');
        const detailTitle = document.createElement('summary'); detailTitle.textContent = '查看材料与整理范围';
        const detailBody = document.createElement('small');
        detailBody.textContent = '展开后加载材料与范围';
        detail.ontoggle = async () => {
          if (!detail.open || detail.dataset.loaded) return;
          detailBody.textContent = '正在加载材料…';
          try {
            const {plan:full} = await api(`/knowledge-plans/${plan.id}?space_id=${spaceId}`);
            if (!current()) return;
            const topic = full.payload.topics[index];
            detailBody.textContent = `材料：${(topic.source_labels || []).join('、') || '无材料引用'}；交叉参考：${(topic.cross_references || []).join('、') || '无'}；不纳入：${(topic.omitted || []).join('、') || '无'}`;
            detail.dataset.loaded = 'true';
          } catch (error) { if (current()) detailBody.textContent = '材料暂未加载，请收起后重试'; }
        };
        detail.append(detailTitle, detailBody); section.append(detail); card.append(section);
        if (result?.status !== 'completed') {
          const action = result?.status === 'ignored' ? 'restore' : 'ignore';
          const button = document.createElement('button'); button.type='button'; button.className='quiet-button'; button.textContent=action === 'ignore' ? '忽略此主题' : '恢复此主题';
          const operation = operationKey('ui-plan-item');
          button.onclick = async () => {
            await api(`/knowledge-plans/${plan.id}/items/${index}`, {method:'POST', body:JSON.stringify({space_id:spaceId, action, expected_version:plan.version, operation_key:operation})});
            if (current()) { toast(action === 'ignore' ? '已忽略，历史仍保留' : '已恢复，请检查当前依据后继续'); await loadKnowledge(query); }
          }; section.append(button);
          const note = document.createElement('small');
          note.textContent = '可在原对话继续此计划，只重交未成功主题；已保存页需用新的编辑操作修改。';
          section.append(note);
        }
      });
      if (plan.payload.omitted.length) {
        const omitted = document.createElement('small'); omitted.textContent = `本次不纳入：${plan.payload.omitted.join('、')}`; card.append(omitted);
      }
      if (plan.confirmable === false && plan.status === 'pending') {
        const warning = document.createElement('small');
        warning.textContent = `提案暂不可确认：${(plan.validation_issues || []).map(planIssueLabel).join('；') || '请检查来源与内容块'}`;
        card.append(warning);
      }
      if (plan.status === 'pending' && view !== 'ignored') {
        const edit = document.createElement('button'); edit.type = 'button'; edit.textContent = '调整提案'; card.append(edit);
        edit.onclick = async () => {
          edit.disabled = true;
          const form = document.createElement('div'); form.className = 'assistant-knowledge-card';
          let available = [];
          let selectedSources = new Map();
          try {
            const {plan:detail} = await api(`/knowledge-plans/${plan.id}?space_id=${spaceId}`);
            if (!current()) return;
            plan.payload = detail.payload;
            const options = await api(`/knowledge-plans/${plan.id}/sources?space_id=${spaceId}`);
            if (!current()) return;
            available = options.sources;
            selectedSources = new Map((options.selected_sources || []).map(item => [item.source_ref, item]));
          }
          catch (error) { toast('来源暂时无法加载，请稍后重试'); edit.disabled = false; return; }
          const searchWrap = document.createElement('div'); searchWrap.className = 'assistant-source-picker-search';
          const sourceSearch = document.createElement('input'); sourceSearch.type = 'search'; sourceSearch.placeholder = '候选不足？按收藏标题搜索'; sourceSearch.setAttribute('aria-label', '搜索收藏来源');
          const searchButton = document.createElement('button'); searchButton.type = 'button'; searchButton.textContent = '搜索来源';
          searchWrap.append(sourceSearch, searchButton); form.append(searchWrap);
          const fields = plan.payload.topics.map((topic, index) => {
            const section = document.createElement('div'); section.className = 'assistant-plan-topic';
            const label = document.createElement('strong'); label.textContent = `主题 ${index + 1}`; section.append(label);
            const input = (caption, value, multiline = false) => {
              const wrap = document.createElement('label'); wrap.textContent = caption;
              const control = document.createElement(multiline ? 'textarea' : 'input'); control.value = value;
              wrap.append(control); section.append(wrap); return control;
            };
            const title = input('标题', topic.title);
            const purpose = input('用途', topic.purpose, true);
            const blocks = topic.blocks.map(block => {
              const markdown = input(`内容 · ${{source:'来源',analysis:'分析',personal:'我的笔记'}[block.role] || block.role} · ${block.heading}`, block.markdown, true);
              if (block.role !== 'source') return {markdown, refs:null};
              const chosen = new Set(block.source_refs || []);
              const picker = document.createElement('fieldset'); picker.className = 'assistant-source-picker';
              const legend = document.createElement('legend'); legend.textContent = `选择支持「${block.heading}」的来源`; picker.append(legend);
              const options = document.createElement('div'); picker.append(options); section.append(picker);
              const draw = () => {
                options.replaceChildren();
                available.forEach(source => {
                  const row = document.createElement('label');
                  const checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.checked = chosen.has(source.source_ref);
                  checkbox.onchange = () => checkbox.checked ? chosen.add(source.source_ref) : chosen.delete(source.source_ref);
                  const label = document.createElement('span'); label.textContent = `${source.title}${source.uploader ? ` · ${source.uploader}` : ''} · ${source.view}`;
                  row.append(checkbox, label); options.append(row);
                });
                const missing = [...chosen].filter(ref => !available.some(source => source.source_ref === ref));
                missing.forEach(ref => {
                  const source = selectedSources.get(ref);
                  const status = {
                    revision_changed:'来源版本已更新，原绑定版本不能保存',
                    out_of_scope:'来源不在当前收藏范围，不能保存',
                    invalid:'来源身份已失效，不能保存',
                    available:'已绑定且当前可用，未列入首批候选',
                  }[source?.status] || '已绑定，当前状态未确认；保存时仍会校验';
                  const row = document.createElement('div'); row.className = 'assistant-source-bound';
                  const description = document.createElement('span');
                  description.textContent = `${source?.title || '已绑定来源'} · ${status}`;
                  const remove = document.createElement('button'); remove.type = 'button';
                  remove.textContent = '移除此来源'; remove.setAttribute('aria-label', `移除${source?.title || '已绑定来源'}`);
                  remove.onclick = () => { chosen.delete(ref); draw(); };
                  row.append(description, remove); options.append(row);
                });
                if (!available.length) { const note = document.createElement('small'); note.textContent = '暂无可选来源，可按标题搜索当前收藏。'; options.append(note); }
              };
              draw();
              return {markdown, refs:chosen, redraw:draw};
            });
            form.append(section); return {title, purpose, blocks};
          });
          searchButton.onclick = async () => {
            try {
              const found = (await api(`/knowledge-plans/${plan.id}/sources?space_id=${spaceId}&query=${encodeURIComponent(sourceSearch.value.trim())}`)).sources;
              if (!current()) return;
              available = [...new Map([...available, ...found].map(item => [item.source_ref, item])).values()];
              fields.forEach(topic => topic.blocks.forEach(block => block.redraw?.()));
            } catch (error) { toast('搜索来源失败，请稍后重试'); }
          };
          const save = document.createElement('button'); save.type = 'button'; save.textContent = '保存调整后的提案';
          save.onclick = async () => {
            const topics = plan.payload.topics.map((topic, index) => ({
              ...topic, title:fields[index].title.value.trim(), purpose:fields[index].purpose.value.trim(),
              blocks:topic.blocks.map((block, blockIndex) => ({...block,
                markdown:fields[index].blocks[blockIndex].markdown.value.trim(),
                source_refs: fields[index].blocks[blockIndex].refs
                  ? [...fields[index].blocks[blockIndex].refs]
                  : (block.source_refs || []),
              })),
            }));
            let updated;
            try { ({plan:updated} = await api(`/knowledge-plans/${plan.id}`, {method:'PATCH', body:JSON.stringify({
              space_id:spaceId, expected_version:plan.version, topics, omitted:plan.payload.omitted,
              operation_key:operationKey('ui-knowledge-plan-revise'),
            })})); }
            catch (error) {
              const issue = String(error.message).split('knowledge_plan_not_confirmable:')[1]?.split(';')[0] || error.message;
              toast(`提案未保存：${planIssueLabel(issue)}`); return;
            }
            if (!current()) return;
            toast(`提案已调整到第 ${updated.version} 版，请确认后保存`); await loadKnowledge(query);
          };
          form.append(save); card.append(form);
        };
      }
      [true, false].forEach(accept => {
        if (!accept && plan.status !== 'pending') return;
        if (view === 'ignored') return;
        const button = document.createElement('button'); button.type = 'button';
        button.textContent = accept ? (plan.status === 'pending' ? '确认并逐页保存' : '重试未完成主题') : '拒绝提案';
        if (accept && plan.status === 'pending' && plan.confirmable === false) button.disabled = true;
        button.onclick = async () => {
          const {plan:updated, save_feedback} = await api(`/knowledge-plans/${plan.id}/decide`, {method:'POST', body:JSON.stringify({
            space_id:spaceId, expected_version:plan.version, accept,
            operation_key:operationKey('ui-knowledge-plan'),
          })});
          if (!current()) return;
          toast(updated.status === 'completed' ? '主题页已保存' : updated.status === 'partial' ? '部分主题未完成，请查看原因' : '提案已拒绝');
          if (save_feedback?.count) showSaveFeedback(save_feedback);
          await loadKnowledge(query);
        }; card.append(button);
      });
      card.querySelectorAll('button').forEach(button => button.classList.add('quiet-button'));
      box.append(disclosure);
    });
    if (!pages.length && !visiblePlans) {
      const empty = document.createElement('div'); empty.className = 'assistant-knowledge-empty';
      empty.innerHTML = '<strong>还没有可用的主题页</strong><p>可以先整理当前范围；只有标题而没有实质材料的收藏不会被写成知识结论。</p>';
      if (view !== 'active') empty.textContent = {pending:'没有未完成的主题', archived:'没有归档页', deleted:'没有已删除的知识块', ignored:'没有已忽略的主题'}[view];
      box.append(empty); guardKnowledgeButtons(box,current); return true;
    }
    pages.forEach(page => {
      const card = document.createElement('button'); card.type = 'button'; card.className = 'assistant-knowledge-card';
      const title = document.createElement('strong'); title.textContent = page.title;
      const summary = document.createElement('span');
      const preview = (page.summary || '').replace(/[*_`#]/g,'');
      summary.textContent = preview ? `${preview.slice(0,170)}${preview.length>170?'…':''}` : '暂无导读';
      const meta = document.createElement('small');
      meta.textContent = `${page.blocks.length} 个知识块 · 更新于 ${formatDate(page.updated_at)}${page.availability === 'partial' ? ' · 部分可用' : ''}`;
      card.append(title, summary, meta); card.onclick = () => openKnowledgePage(page.id);
      box.append(card);
    });
    guardKnowledgeButtons(box,current);
    return true;
  }

  async function openKnowledgePage(pageId, fromMessage=false) {
    const serial = ++state.knowledgeSerial, nav = state.navigationSerial, spaceId = state.spaceId, threadId = state.threadId;
    const requested = () => serial === state.knowledgeSerial && navigationCurrent(nav, spaceId) && threadId === state.threadId;
    const current = () => serial === state.knowledgeRenderedSerial && !state.knowledgeLoading && navigationCurrent(nav, spaceId) && threadId === state.threadId;
    state.knowledgeLoading = true;
    let loaded;
    try { loaded = await Promise.all([
      api(`/wiki/${pageId}/management?space_id=${spaceId}&thread_id=${fromMessage ? "" : threadId || ""}`),
      api(`/wiki/${pageId}/changes?space_id=${spaceId}&management=true`),
      api(`/wiki?space_id=${spaceId}&thread_id=${fromMessage ? "" : threadId || ""}`),
      api(`/wiki-actions/proposals?space_id=${spaceId}`),
    ]); } catch (error) {
      if (requested()) { state.knowledgeLoading=false; toast(`知识内容加载失败，请重试：${error.message}`); }
      return;
    }
    if (!requested()) return;
    state.knowledgeLoading=false; state.knowledgeRenderedSerial=serial;
    const [{page}, {changes}, {pages}, {proposals}] = loaded;
    if (page.id !== pageId) return openKnowledgePage(page.id,fromMessage);
    $('assistant-knowledge-list-view').hidden = true;
    $('assistant-knowledge-detail').hidden = false;
    const box = $('assistant-knowledge-page'); box.innerHTML = '';
    const heading = document.createElement('div'); heading.className = 'assistant-knowledge-heading';
    const title = document.createElement('h3'); title.textContent = page.title;
    const summary = document.createElement('p');
    summary.textContent = page.summary ? `${page.summary.slice(0, 560)}${page.summary.length > 560 ? '…' : ''}` : '暂无导读';
    const meta = document.createElement('small'); meta.textContent = `更新于 ${formatDate(page.updated_at)}${page.availability === 'partial' ? ' · 当前范围仅可见部分内容' : ''}`;
    heading.append(title, summary, meta); box.append(heading);
    heading.append(knowledgeLifecycleButton(page,page.status === 'archived' ? 'restore' : 'archive',page.status === 'archived' ? '恢复归档页' : '归档此页',current));
    (page.deleted_blocks || []).forEach(block => heading.append(knowledgeLifecycleButton(page,'restore_block',`撤销删除：${block.heading}`,current,block.stable_id)));
    if (page.status === 'archived') { meta.textContent='已归档：不参与默认检索或后台维护；恢复后仍检查依赖';guardKnowledgeButtons(box,current);return; }

    const noteForm = document.createElement('details'); noteForm.className = 'assistant-knowledge-history';
    const noteTitle = document.createElement('summary'); noteTitle.textContent = '添加我的笔记';
    const noteText = document.createElement('textarea'); noteText.rows = 3; noteText.maxLength = 4000;
    noteText.placeholder = '写下你自己的理解；它会与材料观点分开保存';
    const noteSave = document.createElement('button'); noteSave.type = 'button'; noteSave.textContent = '保存笔记';
    const noteOperation=operationKey('ui-wiki-note');
    noteSave.onclick = async () => {
      await api(`/wiki/${pageId}/notes`, {method:'POST', body:JSON.stringify({
        space_id:spaceId, text:noteText.value, expected_version:page.version,
        operation_key:noteOperation,
      })});
      if(current()){toast('个人笔记已保存'); await openKnowledgePage(pageId);}
    };
    noteForm.append(noteTitle, noteText, noteSave); box.append(noteForm);
    const mergeTargets = pages.filter(item => item.id !== page.id);
    if (mergeTargets.length) {
      const mergeForm = document.createElement('details'); mergeForm.className = 'assistant-knowledge-history';
      const mergeTitle = document.createElement('summary'); mergeTitle.textContent = '合并重复主题';
      const select = document.createElement('select');
      mergeTargets.forEach(item => { const option = document.createElement('option'); option.value = item.id; option.textContent = item.title; select.append(option); });
      const mergeButton = document.createElement('button'); mergeButton.type = 'button'; mergeButton.textContent = '合并到所选主题';
      mergeButton.onclick = async () => {
        const target = mergeTargets.find(item => item.id === select.value);
        if (!target) return;
        const {result} = await api('/wiki-actions/merge', {method:'POST', body:JSON.stringify({
          space_id:spaceId, source_page_id:page.id, target_page_id:target.id,
          source_version:page.version, target_version:target.version,
          operation_key:operationKey('ui-wiki-merge'),
        })});
        if (!current()) return;
        toast(result.status === 'merged' ? '主题已合并' : result.status === 'pending' ? '人工内容有差异，请查看待确认项' : '同一差异已被拒绝');
        await openKnowledgePage(result.status === 'merged' ? target.id : page.id);
      };
      mergeForm.append(mergeTitle, select, mergeButton); box.append(mergeForm);
    }
    if(proposals.some(item=>item.kind==='source_patch' && item.target_page_id===page.id)) {
      const review=document.createElement('button');review.type='button';review.className='quiet-button';review.textContent='查看视频正文修改建议';review.onclick=openMessages;box.append(review);
    }
    proposals.filter(item => item.kind==='merge' && (item.source_page_id === page.id || item.target_page_id === page.id)).forEach(item => {
      const pending = document.createElement('details'); pending.className = 'assistant-knowledge-history';
      const title = document.createElement('summary'); title.textContent = `待确认：合并「${item.source_title}」与「${item.target_title}」`;
      pending.append(title);
      item.differences.forEach(diff => {
        const paragraph = document.createElement('p');
        paragraph.textContent = `${diff.heading}：原页「${diff.source_text}」；目标页「${diff.target_text}」`;
        pending.append(paragraph);
      });
      [true, false].forEach(accept => {
        const button = document.createElement('button'); button.type = 'button';
        button.textContent = accept ? '保留两种判断并合并' : '拒绝本次合并';
        button.onclick = async () => {
          try {
            const {result} = await api(`/wiki-actions/proposals/${item.id}/decide`, {method:'POST', body:JSON.stringify({
              space_id:spaceId, accept, operation_key:operationKey('ui-wiki-proposal'),
            })});
            if (!current()) return;
            if (result.status === 'accepted' || result.status === 'merged') toast('已合并，两个判断均已保留');
            else if (result.status === 'rejected') toast('已拒绝本次合并');
            else if (result.status === 'stale') toast('提案已过期，请查看当前主题');
            else toast('提案状态已更新');
            await openKnowledgePage(result.page_id || page.id);
          } catch (error) {
            if (!current()) return;
            if (String(error.message).includes('wiki_proposal_stale')) {
              toast('提案已过期，请查看当前主题');
              await openKnowledgePage(page.id);
            } else throw error;
          }
        };
        pending.append(button);
      });
      box.append(pending);
    });
    page.blocks.forEach(block => {
      const article = document.createElement('article'); article.className = 'assistant-knowledge-block';
      const h = document.createElement('h4'); h.textContent = block.heading;
      const body = document.createElement('div'); body.className = 'assistant-markdown'; body.innerHTML = renderMarkdown(block.markdown);
      const detail = document.createElement('div'); detail.className = 'assistant-knowledge-source';
      const sources = block.sources || [];
      if (block.assessment === 'user_explicit') {
        detail.textContent = block.user_input_source === 'memory_derived' ?
          '我的笔记 · 依赖当前记忆' : '我的笔记 · 由我明确输入';
        if (block.historical_statement) detail.textContent += ' · 历史陈述';
        else if (block.expires_at) detail.textContent += ` · 有效至 ${formatDate(block.expires_at)}`;
      } else {
        const role = block.assessment === 'user_annotation' ? '已有注释（归属未核实）' :
          block.assessment === 'system_synthesis' ? '系统归纳（请核对来源）' : '来源说法';
        const condition = block.applicability ? ` · 条件：${block.applicability}` : '';
        const speaker = block.speaker ? ` · 发言者 ${block.speaker}` : '';
        const cited = block.cited_source ? ` · 引用 ${block.cited_source}（原文未核对）` : '';
        detail.append(document.createTextNode(`${role}${condition}${speaker}${cited}`));
        sources.forEach(source => {
          const row = document.createElement('div');
          const link = document.createElement('a'); link.textContent = source.title;
          if (source.url && /^https:\/\//.test(source.url)) {
            link.href = source.url; link.target = '_blank'; link.rel = 'noopener noreferrer';
          }
          const usedView = block.source_view ? materialViewLabel(block.source_view) : '未记录或混合视图';
          row.append(link, document.createTextNode(
            `${source.uploader ? ` · 上传者 ${source.uploader}` : ''} · 本页依据：${usedView}`
          ));
          const sourceMore = document.createElement('details');
          const sourceMoreTitle = document.createElement('summary'); sourceMoreTitle.textContent = '查看来源详情';
          const sourceMoreBody = document.createElement('small');
          sourceMoreBody.textContent = `来源卡视图：${materialViewLabel(source.material_view)}（不代表本块依据） · ${coverageLabel(source.coverage)} · 发布 ${formatDate(source.published_at)} · 收藏 ${formatDate(source.collected_at)}`;
          sourceMore.append(sourceMoreTitle, sourceMoreBody); row.append(sourceMore);
          detail.append(row);
        });
        (block.external_sources || []).forEach(source => {
          const row = document.createElement('div');
          const link = document.createElement('a'); link.href = source.url;
          link.target = '_blank'; link.rel = 'noopener noreferrer'; link.textContent = source.url;
          row.append(link, document.createTextNode(` · 公开文档回执 · 取得 ${formatDate(source.captured_at)}`));
          detail.append(row);
        });
      }
      const actions = document.createElement('div'); actions.className = 'assistant-memory-actions';
      const edit = document.createElement('button'); edit.type = 'button'; edit.textContent = block.manual_lock ? '修改人工修订' : '编辑';
      edit.onclick = () => {
        const editor = document.createElement('div'); editor.className = 'assistant-knowledge-editor';
        const field = document.createElement('textarea'); field.rows = 8; field.maxLength = 20000; field.value = block.markdown;
        const save = document.createElement('button'); save.type = 'button'; save.textContent = '保存修订';
        const cancel = document.createElement('button'); cancel.type = 'button'; cancel.textContent = '取消';
        const buttons = document.createElement('div'); buttons.className = 'assistant-memory-actions'; buttons.append(save, cancel);
        editor.append(field, buttons); body.replaceWith(editor); field.focus();
        cancel.onclick = () => openKnowledgePage(pageId);
        save.onclick = async () => {
          await api(`/wiki/${pageId}`, {method:'PATCH', body:JSON.stringify({
            space_id:spaceId, block_id:block.stable_id, markdown:field.value,
            expected_version:page.version, operation_key:operationKey('ui-wiki-edit'),
          })});
          if(current()){toast('知识页已修订'); await openKnowledgePage(pageId);}
        };
      };
      actions.append(edit, knowledgeLifecycleButton(page,'delete_block','逻辑删除（可撤销）',current,block.stable_id)); article.append(h, body, detail, actions);
      if (block.assessment === 'user_explicit') {
        const fold = document.createElement('details');
        const foldTitle = document.createElement('summary'); foldTitle.textContent = '查看我的笔记';
        fold.append(foldTitle, article); box.append(fold);
      } else box.append(article);
    });
    const associated = (page.materials || []).filter(item => item.relation === 'associated');
    if (associated.length) {
      const section = document.createElement('details'); section.className = 'assistant-knowledge-history';
      const title = document.createElement('summary'); title.textContent = `相关材料（尚未纳入具体说法，${associated.length}）`;
      section.append(title);
      associated.forEach(item => {
        const link = document.createElement('a'); link.textContent = item.title;
        if (item.url && /^https:\/\//.test(item.url)) { link.href = item.url; link.target = '_blank'; link.rel = 'noopener noreferrer'; }
        section.append(link);
      });
      box.append(section);
    }
    const history = document.createElement('details'); history.className = 'assistant-knowledge-history';
    const historyTitle = document.createElement('summary'); historyTitle.textContent = `查看更新记录（${changes.length}）`;
    const historyList = document.createElement('div');
    changes.forEach(change => {
      const row = document.createElement('div');
      const text = document.createElement('span'); text.textContent = `${change.summary} · ${formatDate(change.created_at)}`;
      row.append(text);
      if (change.version < page.version && change.can_revert) {
        const restore = document.createElement('button'); restore.type = 'button'; restore.textContent = '恢复到这里';
        const revertOperation=operationKey('ui-wiki-revert');
        restore.onclick = async () => {
          await api(`/wiki/${pageId}/revert`, {method:'POST', body:JSON.stringify({
            space_id:spaceId, target_version:change.version,
            expected_version:page.version, operation_key:revertOperation,
          })});
          if(current()){toast('已生成恢复版本'); await openKnowledgePage(pageId);}
        };
        row.append(restore);
      }
      historyList.append(row);
    });
    history.append(historyTitle, historyList); box.append(history);
    guardKnowledgeButtons(box,current);
  }

  async function loadKnowledgeStatus() {
    const nav=state.navigationSerial, spaceId=state.spaceId;
    const {jobs} = await api(`/jobs${state.spaceId ? `?space_id=${state.spaceId}` : ''}`);
    if(!navigationCurrent(nav,spaceId))return;
    const kinds = new Set(['source_reconcile','source_extract','wiki_integrate']);
    const relevant = jobs.filter(job => kinds.has(job.kind));
    const active = relevant.filter(job => ['queued','running','retry_wait','budget_wait'].includes(job.status)).length;
    const blocked = relevant.filter(job => job.status === 'blocked').length;
    const status = $('assistant-knowledge-status');
    status.textContent = state.capabilities.background_maintenance === 'paused' ? `后台暂停；${active} 项尚未执行` : active ? `正在整理 ${active} 项材料…` : (blocked ? `${blocked} 项暂未完成，可稍后重试` : '已整理到当前进度');
    return active;
  }

  function backgroundLabel() {
    if(state.capabilities.background_maintenance === 'paused') return '后台已暂停；现有设置保留，不会自动恢复服务或收藏同步。';
    if(state.capabilities.background_maintenance === 'enabled') return '后台已启用；自动整理仍需满足空闲、范围和预算条件。';
    return '后台运行状态尚未确认；设置操作不会启动服务或收藏同步。';
  }

  async function loadSpaceManager() {
    const serial = ++state.managementSerial, nav = state.navigationSerial;
    const list = $('assistant-space-list'); list.textContent = '正在加载 Space…';
    $('assistant-space-editor').replaceChildren();
    try {
      const {spaces} = await api('/spaces');
      if (serial !== state.managementSerial || nav !== state.navigationSerial) return;
      list.replaceChildren();
      spaces.forEach(space => {
        const row = document.createElement('div'); row.className = 'assistant-space-row';
        const name = document.createElement('strong'); name.textContent = space.name;
        const detail = document.createElement('small');
        detail.textContent = `${space.all_active ? '全部活跃收藏' : `${space.source_ids.length} 个来源`}${space.video_ids.length ? ` · 限定 ${space.video_ids.length} 个视频` : ''} · ${space.maintenance_mode === 'automatic' ? '范围内自动维护' : '按需整理'}`;
        const edit = document.createElement('button'); edit.type = 'button'; edit.className = 'quiet-button'; edit.textContent = '编辑';
        edit.onclick = () => editSpace(space.id);
        const change = document.createElement('button'); change.type = 'button'; change.className = 'quiet-button';
        change.textContent = Number(space.id) === state.spaceId ? '当前使用' : '切换'; change.disabled = Number(space.id) === state.spaceId;
        change.onclick = () => { $('assistant-space').value = space.id; $('assistant-space').dispatchEvent(new Event('change')); };
        row.append(name, detail, edit, change); list.append(row);
      });
    } catch (error) { if (serial === state.managementSerial) list.textContent = `加载失败：${error.message}`; }
  }

  async function editSpace(id) {
    const serial = ++state.managementSerial, nav = state.navigationSerial;
    const box = $('assistant-space-editor'); box.textContent = '正在读取范围…';
    const current = () => serial === state.managementSerial && nav === state.navigationSerial && !$('assistant-shade').hidden;
    try {
      const {space} = await api(`/spaces/${id}`);
      if (!current()) return;
      const form = document.createElement('form'); form.className = 'assistant-space-form assistant-space-edit';
      form.innerHTML = `<h3>编辑 Space</h3><label>名称<input name="name" required maxlength="100" value="${escapeHtml(space.name)}"></label>
        <label>用途<textarea name="goal" rows="2" maxlength="1000">${escapeHtml(space.goal)}</textarea></label>
        <label class="assistant-check"><input type="checkbox" name="all_active" ${space.all_active ? 'checked' : ''}> 全部活跃收藏</label>
        <fieldset><legend>来源范围</legend></fieldset>
        <div class="assistant-selected-videos"></div>
        <label>Wiki 维护模式<select name="maintenance_mode"><option value="on_demand">按需整理</option><option value="automatic">范围内自动维护</option></select></label>
        <p class="drawer-intro">${backgroundLabel()} 全库不能直接开启自动深度整理；自动模式可能产生模型费用。Memory 自动提炼是独立的全局设置。</p>
        <p class="assistant-space-error" role="status"></p><button type="submit">保存修改</button>`;
      const fieldset = form.querySelector('fieldset');
      const choices = new Map(space.sources.map(source => [source.id, source]));
      space.source_ids.forEach(sourceId => { if (!choices.has(sourceId)) choices.set(sourceId, {id:sourceId,folder_title:`来源 ${sourceId}（不可用）`}); });
      choices.forEach(source => {
        const label = document.createElement('label'); label.className = 'assistant-check';
        const input = document.createElement('input'); input.type = 'checkbox'; input.name = 'source_ids'; input.value = source.id; input.checked = space.source_ids.includes(source.id);
        const title = document.createElement('span'); title.textContent = source.folder_title || `来源 ${source.id}`;
        label.append(input,title); fieldset.append(label);
      });
      if (space.video_ids.length) {
        const selected = form.querySelector('.assistant-selected-videos');
        const names = new Map(space.selected_videos.map(video => [video.id,video.title]));
        const label = document.createElement('label'); label.className = 'assistant-check';
        const keep = document.createElement('input'); keep.type='checkbox'; keep.name='keep_video_limit'; keep.checked=true;
        label.append(keep,document.createTextNode('保留当前具体视频限制')); selected.append(label);
        const titles = document.createElement('p'); titles.textContent = space.video_ids.map(videoId=>names.get(videoId)||`视频 ${videoId}（不可用）`).join('、'); selected.append(titles);
      }
      form.elements.maintenance_mode.value = space.maintenance_mode;
      const all = form.elements.all_active;
      all.onchange = () => { fieldset.disabled = all.checked; }; all.onchange();
      form.onsubmit = async event => {
        event.preventDefault(); if (!current()) return;
        const button = form.querySelector('button[type=submit]'); if(button.disabled) return;
        const error = form.querySelector('.assistant-space-error'); error.textContent='';
        const patch = {expected_scope_version:space.scope_version};
        if (form.elements.name.value.trim() !== space.name) patch.name=form.elements.name.value.trim();
        if (form.elements.goal.value.trim() !== space.goal) patch.goal=form.elements.goal.value.trim();
        if (all.checked !== space.all_active) patch.all_active=all.checked;
        const ids = [...form.querySelectorAll('[name=source_ids]:checked')].map(input=>Number(input.value)).sort((a,b)=>a-b);
        if(JSON.stringify(ids)!==JSON.stringify([...space.source_ids].sort((a,b)=>a-b))) patch.source_ids=ids;
        if(space.video_ids.length && !form.elements.keep_video_limit.checked) patch.video_ids=[];
        const mode = form.elements.maintenance_mode.value;
        if(mode!==space.maintenance_mode) patch.maintenance_mode=mode;
        if(mode==='automatic' && (all.checked || (!ids.length && (!space.video_ids.length || patch.video_ids)))) {
          error.textContent='请先限定具体来源范围，或选择按需整理。'; return;
        }
        const rangeChanged=['all_active','source_ids','video_ids'].some(key=>key in patch);
        if(rangeChanged && !confirm('修改资料范围会结束这个 Space 中正在执行的回答，旧材料需要按新范围核验。继续吗？')) return;
        if(mode==='automatic' && (mode!==space.maintenance_mode || rangeChanged) && !confirm('允许后台在此范围自动维护 Wiki，可能产生模型费用。当前后台暂停时只保存策略，不会启动。继续吗？')) return;
        if(Object.keys(patch).length===1) { error.textContent='没有需要保存的修改。'; return; }
        button.disabled=true;
        try {
          await api(`/spaces/${id}`,{method:'PATCH',body:JSON.stringify(patch)});
          if(!current()) return;
          await loadSpaces();
          if(!current()) return;
          if(rangeChanged && Number(id)===state.spaceId) await loadThread();
          if(!current()) return;
          toast('Space 设置已保存'); await loadSpaceManager();
        } catch(failure) { if(current()) error.textContent=`未能保存，输入已保留：${failure.message}`; }
        finally {button.disabled=false;}
      };
      box.replaceChildren(form);
    } catch(error) {if(current())box.textContent=`读取失败：${error.message}`;}
  }

  const messages = {serial:0, detailSerial:0, cursor:null, query:null, selected:null, rows:new Map(), scroll:0, trigger:null};
  const messageLabels = {pending:'待确认',partial:'部分完成，待处理',applied:'已更新',rejected:'已拒绝',expired:'已过期',undone:'已撤销',important_failure:'异常',unavailable:'记录不可用'};
  const messageSources = {dialogue:'对话',auto_memory:'自动记忆',video:'视频来源',manual:'手动',system:'系统'};
  function messageElement(tag,text) {const el=document.createElement(tag);el.textContent=text;return el;}
  function messageTime(value) {if(!value)return '';const date=new Date(value);return Number.isNaN(date.getTime())?String(value):date.toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false});}
  function messageTitle(item) {return item.object_label && item.object_label!=='业务记录' ? item.object_label : item.business_state==='important_failure' ? '一项'+(item.object_type==='memory'?'记忆提炼':'后台处理')+'未完成' : item.object_type==='memory'?'记忆变更':'Wiki 变更';}
  async function messageCount() {
    const data=await api('/messages/unread-count');
    $('assistant-open-messages').textContent=`消息${data.unread_count ? ` · ${data.unread_count}` : ''}`;
  }
  function messageQuery() {
    const query=new URLSearchParams();
    ['view','object_type','source_type','space_id'].forEach(key=>{const value=$(`assistant-message-${key}`).value;if(value)query.set(key,value);});
    ['unread_only','show_history'].forEach(key=>query.set(key,$(`assistant-message-${key}`).checked));
    return query;
  }
  function messageFilterSummary(query) {
    const box=$('assistant-message-active');box.replaceChildren();
    ['object_type','source_type','space_id'].forEach(key=>{if(query.get(key)){const select=$(`assistant-message-${key}`);box.append(messageElement('span',select.selectedOptions?.[0]?.textContent || query.get(key)));}});
    if(query.get('show_history')==='true') {const close=messageElement('button','包含历史消息 ×');close.type='button';close.setAttribute('aria-label','关闭历史消息筛选');close.onclick=()=>{$('assistant-message-show_history').checked=false;loadMessages();};box.append(close);}
  }
  function renderMessageRow(item,article) {
    article.replaceChildren();article.className=`assistant-activity-item${['pending','partial'].includes(item.business_state)?' is-pending':''}`;
    const button=messageElement('button','');button.type='button';button.className='assistant-message-row';
    const heading=messageElement('span','');heading.className='assistant-message-row-head';
    const title=messageElement('strong',messageTitle(item));const status=messageElement('span',messageLabels[item.business_state] || '记录');status.className='assistant-message-status';
    const dot=messageElement('span',item.read_at?'':'●');dot.className='assistant-message-unread';dot.setAttribute('aria-label',item.read_at?'已读':'未读');
    heading.append(dot,title,status);button.append(heading);
    if(item.change_summary && item.change_summary!==messageTitle(item)) {const summary=messageElement('span',item.change_summary);summary.className='assistant-message-summary';button.append(summary);}
    const meta=messageElement('small',`${item.object_type==='memory'?'记忆':'Wiki'} · ${messageSources[item.source_type] || '来源未记录'}${item.activity_at?' · '+messageTime(item.activity_at):''}`);button.append(meta);
    if(item._notice)button.append(messageElement('small',item._notice));
    button.onclick=()=>openMessage(item.id,button);article.append(button);
  }
  function backToMessages() {
    ++messages.detailSerial;messages.selected=null;
    $('assistant-message-detail-view').hidden=true;$('assistant-message-list-view').hidden=false;
    $('assistant-message-scroll').scrollTop=messages.scroll;
    messages.trigger?.focus({preventScroll:true});
  }
  async function openMessage(id,trigger) {
    messages.scroll=$('assistant-message-scroll').scrollTop;messages.trigger=trigger;messages.selected=id;
    $('assistant-message-list-view').hidden=true;$('assistant-message-detail-view').hidden=false;
    const box=$('assistant-message-detail');box.replaceChildren(messageElement('p','正在读取消息…'));box.scrollTop=0;
    $('assistant-message-actions').replaceChildren();$('assistant-message-actions').hidden=true;
    $('assistant-message-back').focus();
    const detailSerial=messages.detailSerial+1;
    try {await showMessage(id,box);} catch(error) {if(messages.selected===id && detailSerial===messages.detailSerial){box.replaceChildren(messageElement('p',`读取失败，列表已保留：${error.message}`));messageReload(id,box);}}
  }
  function messageReload(id,box) {const retry=messageElement('button','重新读取');retry.type='button';retry.className='quiet-button';retry.onclick=async()=>{const detailSerial=messages.detailSerial+1;try{await showMessage(id,box);}catch(error){if(messages.selected===id && detailSerial===messages.detailSerial)toast(`读取失败：${error.message}`);}};box.append(retry);}
  async function loadMessages(append=false) {
    if(append && (!messages.cursor || !messages.query || messages.query!==messageQuery().toString()))return;
    const serial=++messages.serial, query=new URLSearchParams(append?messages.query:messageQuery());
    if(!append){messages.cursor=null;$('assistant-message-more').hidden=true;}
    $('assistant-message-more').disabled=true;
    if(append)query.set('cursor',messages.cursor);
    $('assistant-message-error').textContent='正在更新，暂时保留上次结果…';
    try {
      const data=await api(`/messages?${query}`);
      if(serial!==messages.serial)return;
      const box=$('assistant-message-list');
      if(!append){box.replaceChildren();messages.rows.clear();messages.query=messageQuery().toString();$('assistant-message-scroll').scrollTop=0;}
      messages.cursor=data.next_cursor;
      $('assistant-message-more').disabled=false;$('assistant-message-more').hidden=!messages.cursor;
      data.items.forEach(item=>{if(messages.rows.has(item.id))return;const article=document.createElement('article');article.dataset.messageId=item.id;renderMessageRow(item,article);messages.rows.set(item.id,{item,article});box.append(article);});
      if(!box.children.length)box.textContent=Array.from(query.entries()).some(([key,value])=>key!=='view'&&value&&value!=='false') || query.get('view')!=='all' ? '此筛选下暂无消息。' : '暂无消息，后续变更会显示在这里。';
      messageFilterSummary(query);$('assistant-message-error').textContent='';
    } catch(error) {if(serial===messages.serial)$('assistant-message-error').textContent=`筛选更新失败，仍显示上次结果：${error.message}。请刷新重试。`;}
  }
  async function showMessage(id,box) {
    const serial=messages.serial, detailSerial=++messages.detailSerial;
    const current=()=>serial===messages.serial && detailSerial===messages.detailSerial && messages.selected===id && !$('assistant-messages-panel').hidden;
    $('assistant-message-actions').querySelectorAll('button').forEach(button=>button.disabled=true);
    let item;
    try {({message:item}=await api(`/messages/${id}`));}
    catch(error){if(current()){if(!box.querySelector('h3'))box.replaceChildren();box.append(messageElement('p',`读取失败，原预览和列表已保留：${error.message}`));messageReload(id,box);}return false;}
    if(!current())return false;
    box.replaceChildren(messageElement('p',messageLabels[item.business_state]),messageElement('h3',messageTitle(item)));
    $('assistant-message-actions').replaceChildren();$('assistant-message-actions').hidden=true;
    const existingRow=messages.rows.get(id);if(existingRow){existingRow.item={...existingRow.item,...item};renderMessageRow(existingRow.item,existingRow.article);messages.trigger=existingRow.article.querySelector('button');}
    const preview=item.detail;
    const technical=messageElement('details','');technical.append(messageElement('summary','版本与技术详情'));
    if(item.change_summary && item.change_summary!==messageTitle(item))box.append(messageElement('p',item.change_summary));
    if(preview?.kind==='source_patch') {
      technical.append(messageElement('p',`原审核内容 v${preview.content_version} · 目标页 v${preview.target_version} · ${({add_block:'新增正文块',revise_block:'修订正文块',source_integrated:'已纳入来源',source_amended:'已修订正文'}[preview.operation] || '来源修改')}${preview.supersedes_id ? ` · 替代 ${preview.supersedes_id}` : ''}`));
      if(preview.before)box.append(messageElement('pre',`${preview.operation==='add_block'?'当前内容 · 确认后保留':'修改前'}\n${preview.before.summary || ''}\n${preview.before.blocks.map(b=>`${b.heading}\n${b.markdown}`).join('\n\n')}`));
      if(preview.after)box.append(messageElement('pre',`${item.business_state==='applied'?'修改后':preview.operation==='add_block'?'拟新增正文块':'拟修改后'}\n${preview.after.blocks.map(b=>`${b.heading}\n${b.markdown}`).join('\n\n')}`));
    } else if(preview?.payload?.topics) {
      box.append(messageElement('p','完整计划预览：确认将处理下面全部尚未完成主题；已成功项不会重复保存。'));
      preview.payload.topics.forEach((topic,index)=>{
        box.append(messageElement('strong',`${index+1}. ${topic.title} · ${preview.results?.[String(index)]?.status || '待确认'}`));
        topic.blocks.forEach(block=>box.append(messageElement('p',`${block.heading || ''}\n${block.markdown || ''}`)));
      });
    } else if(preview?.differences) {
      preview.differences.forEach(diff=>box.append(messageElement('pre',`${diff.heading}\n来源：${diff.source_text}\n目标：${diff.target_text}`)));
    } else if(preview) {
      ['before','after'].forEach(key=>{
        if(!preview[key])return;
        const value=preview[key];
        box.append(messageElement('strong',key==='before'?'修改前':'修改后'));
        box.append(messageElement('pre',value.text || (value.blocks || []).map(b=>`${b.heading || ''}\n${b.markdown || ''}`).join('\n\n') || '无可展示正文'));
        if(value.materials?.length)box.append(messageElement('p',`材料关联：${value.materials.map(m=>`视频 ${m.video_id} · ${m.relation || '关联'} · ${m.status || ''}`).join('；')}`));
      });
    }
    if(!preview)box.append(messageElement('p',item.reason || '当前记录无可展示正文；已遗忘或失效的内容不会恢复展示。'));
    else if(item.reason || preview.reason)technical.append(messageElement('p',item.reason || preview.reason));
    if(['pending','partial'].includes(item.business_state))box.append(messageElement('small',item.business_state==='partial'?'已保存项保持原样；确认将处理尚未完成主题。':'尚未发布；确认后生效。'));
    box.append(messageElement('h4','来源与时间'));
    if(!item.links?.length)box.append(messageElement('p','来源未记录或已不可用。'));
    const times=[...(item.source_times || []).map(t=>`${({dialogue:'对话发生',video_published:'视频发布'}[t.kind] || t.kind || '来源时间')}：${messageTime(t.at)}`),...(item.processing_times || []).map(t=>`${({started_at:'后台开始',completed_at:'后台完成'}[t.kind] || t.kind || '后台处理')}：${messageTime(t.at)}`),item.created_at?`消息生成：${messageTime(item.created_at)}`:'',item.applied_at?`正式修改：${messageTime(item.applied_at)}`:''].filter(Boolean);
    if(times.length)box.append(messageElement('small',times.join('\n')));
    (item.links || []).forEach(link=>{
      if(link.kind==='thread') {const a=messageElement('a','查看来源对话');a.href=`/assistant?thread=${encodeURIComponent(link.id)}`;box.append(a);return;}
      if(link.kind==='video') {const a=messageElement('a','查看 B站视频');a.href=link.url;a.target='_blank';a.rel='noopener';box.append(a);return;}
      if(!['wiki','memory'].includes(link.kind))return;
      const button=messageElement('button',link.kind==='wiki'?'查看当前 Wiki':'查看当前记忆');button.type='button';button.className='quiet-button';
      button.onclick=async()=>{
        try {
          if(link.space_id && Number(link.space_id)!==state.spaceId){$('assistant-space').value=link.space_id;await $('assistant-space').onchange({target:$('assistant-space')});}
          if(link.kind==='wiki') {openDrawer('assistant-knowledge-panel','Wiki');await openKnowledgePage(link.id,true);}
          else {await loadMemories();openDrawer('assistant-memory-panel','记忆');$('assistant-memories').querySelector(`[data-memory-id="${CSS.escape(link.id)}"]`)?.scrollIntoView({block:'center'});}
        } catch(error){toast(`对象暂时无法打开：${error.message}`);}
      };box.append(button);
    });
    if(technical.children.length>1)box.append(technical);
    const actions=$('assistant-message-actions');actions.hidden=!(item.actions || []).length;
    let busy=false, conflict=false;
    (item.actions || []).forEach(action=>{
      const decisions=['undo','proposal_refresh'].includes(action.kind)?[null]:[true,false];
      decisions.forEach(accept=>{
        const button=messageElement('button',action.kind==='undo'?'撤销本次修改':action.kind==='proposal_refresh'?'重新生成建议（消耗正常模型额度）':accept?(action.expected_content_version?(preview?.operation==='add_block'?'确认增补':'确认修订'):preview?.payload?.topics?'确认完整计划':'确认提案'):'拒绝');button.type='button';button.className=accept?'assistant-message-primary':'quiet-button';
        button.onclick=async()=>{
          if(busy || conflict || !current())return;busy=true;
          actions.querySelectorAll('button').forEach(b=>b.disabled=true);
          const operation=operationKey('message');
          try {
            let path,payload;
            if(action.kind==='undo'){path=`/messages/${id}/undo`;payload={expected_version:action.expected_version,operation_key:operation};}
            else if(action.kind==='proposal_refresh'){path=`/wiki-actions/proposals/${action.id}/request-refresh`;payload={space_id:action.space_id,operation_key:operation};}
            else {path=action.kind==='proposal'?`/wiki-actions/proposals/${action.id}/decide`:`/knowledge-plans/${action.id}/decide`;payload={space_id:action.space_id,accept,operation_key:operation};if(action.expected_version)payload.expected_version=action.expected_version;if(action.expected_content_version)payload.expected_content_version=action.expected_content_version;if(action.expected_target_version)payload.expected_target_version=action.expected_target_version;}
            await api(path,{method:'POST',body:JSON.stringify(payload)});
            if(current()){const refreshed=await showMessage(id,box);if(refreshed && messages.selected===id && serial===messages.serial && messages.detailSerial===detailSerial+1){const row=messages.rows.get(id);if(row){row.item._notice='状态已更新，刷新后按当前筛选显示';renderMessageRow(row.item,row.article);messages.trigger=row.article.querySelector('button');}await messageCount();}}
          } catch(error){if(current()){conflict=/conflict|stale|version/.test(error.message);box.append(messageElement('p',`操作失败，当前预览保留${conflict?'，版本已变化，请重新读取后决定':''}：${error.message}`));messageReload(id,box);}}
          finally {busy=false;if(current())actions.querySelectorAll('button').forEach(b=>b.disabled=conflict);}
        };actions.append(button);
      });
    });
    // Reading is a separate explicit write; a failed acknowledgement stays visible.
    try {
      await api('/messages/read',{method:'POST',body:JSON.stringify({ids:[id]})});
      if(current()) {
        const row=messages.rows.get(id);if(row){row.item={...row.item,read_at:true};if($('assistant-message-unread_only').checked)row.item._notice='已读，刷新后移出仅未读列表';renderMessageRow(row.item,row.article);messages.trigger=row.article.querySelector('button');}
      }
      await messageCount();
    }
    catch(error){if(current())box.append(messageElement('p',`已读未保存，可重新读取重试：${error.message}`));}
    return current();
  }
  function openMessages() {
    const select=$('assistant-message-space_id');const selected=select.value;
    select.replaceChildren(new Option('我的全部范围',''));
    state.spaces.forEach(space=>select.append(new Option(space.name,space.id)));
    select.value=selected;backToMessages();openDrawer('assistant-messages-panel','消息');loadMessages();
  }
  $('assistant-open-messages').onclick=openMessages;
  $('assistant-message-back').onclick=backToMessages;
  $('assistant-message-filter-toggle').onclick=()=>{const box=$('assistant-message-secondary');box.hidden=!box.hidden;$('assistant-message-filter-toggle').setAttribute('aria-expanded',String(!box.hidden));};
  $('assistant-message-tabs').querySelectorAll('button').forEach(button=>{button.onclick=()=>{$('assistant-message-view').value=button.dataset.view;$('assistant-message-tabs').querySelectorAll('button').forEach(tab=>tab.setAttribute('aria-pressed',String(tab===button)));loadMessages();};});
  $('assistant-message-filters').onchange=()=>loadMessages();
  $('assistant-message-refresh').onclick=()=>loadMessages();
  $('assistant-message-more').onclick=()=>loadMessages(true);
  messageCount().catch(()=>{});
  function showFatal(error) {
    $('assistant-thread-state').textContent = '助手暂时不可用';
    ['assistant-new-thread', 'assistant-open-history'].forEach(id => { $(id).disabled = false; });
    $('assistant-error').hidden = false;
    $('assistant-error-message').textContent = '连接服务失败，请稍后重试。';
    $('assistant-error-detail').textContent = error.message;
  }

  $('assistant-space').onchange = async event => {
    if (!event.target.value) return;
    state.spaceId = Number(event.target.value);
    const serial = beginNavigation();
    sessionStorage.setItem('shiliu.assistant.space', String(state.spaceId));
    const recent = sessionStorage.getItem(`shiliu.assistant.space.${state.spaceId}`);
    closeDrawer();
    if (recent) {
      try { await openThread(recent); }
      catch (error) {
        if (!navigationCurrent(serial, state.spaceId)) return;
        if (error.message === 'scope_changed' || error.message.includes('对话不存在')) await newThread();
        else { showFatal(error); return; }
      }
    } else await newThread();
    if (serial !== state.navigationSerial || state.navigationPending) return;
    await loadMemories();
    if (serial === state.navigationSerial) toast('已切换收藏范围');
  };
  $('assistant-space-form').onsubmit = async event => {
    event.preventDefault();
    const form = new FormData(event.target);
    const created = await api('/spaces', {method:'POST', body:JSON.stringify({
      name:form.get('name'), goal:form.get('goal') || '', source_ids:form.getAll('source_ids').map(Number), all_active:form.get('all_active') === 'on',
    })});
    await loadSpaces(); state.spaceId=Number(created.space.id); $('assistant-space').value=String(state.spaceId); beginNavigation(); await newThread();
    if (state.navigationPending) return;
    await loadMemories(); closeDrawer(); toast('收藏范围已创建');
  };
  $('assistant-chat-form').onsubmit = async event => {
    event.preventDefault();
    if (state.navigationPending || state.presentedThreadId !== state.threadId) return;
    const input = event.target.elements.input;
    const text = input.value.trim(); if (!text) return;
    const threadId = state.threadId;
    const serial = state.navigationSerial;
    const active = state.runId && $('assistant-cancel').hidden === false;
    if (active) {
      if (/^(?:先回答|现在回答|先说结论|就现在回答|别再查了，?先回答)/.test(text)) {
        if(await runAction($('assistant-finish'), 'finish', '正在根据已读材料收尾') && input.value.trim()===text){input.value='';persistDraft();}
      } else if (/^(?:停止|先停|别搜了|不要再搜|不用继续查)/.test(text)) {
        if(await runAction($('assistant-cancel'), 'cancel', '已停止') && input.value.trim()===text){input.value='';persistDraft();}
      } else toast('当前任务还在处理；可以先回答或停止后再发送新要求');
      return;
    }
    try {
      const saveKey = `shiliu-save-text:${threadId}`;
      const isSave = /保存|存入|写入|知识页/.test(text);
      let request = isSave ? JSON.parse(localStorage.getItem(saveKey) || 'null') : null;
      if (request && request.input !== text) {
        const {thread} = await api(`/threads/${threadId}`);
        if (!thread.runs.some(run => run.request_id === request.request_id)) {
          throw new Error('上次保存结果尚未确认，请先重试原保存请求');
        }
        request = null;
      }
      request = request || {input:text, request_id:operationKey('ui-run')};
      if (isSave) localStorage.setItem(saveKey, JSON.stringify(request));
      const {run} = await api(`/threads/${threadId}/runs`, {method:'POST', body:JSON.stringify(request)});
      if (isSave) localStorage.removeItem(saveKey);
      if (serial !== state.navigationSerial || threadId !== state.threadId || state.navigationPending) return;
      state.runId = run.id;
      if (input.value.trim() === text) { input.value = ''; persistDraft(); }
      $('assistant-scroll').scrollTop = $('assistant-scroll').scrollHeight; await loadThread();
    } catch (error) { if (serial === state.navigationSerial && threadId === state.threadId) { showFatal(error); input.focus(); } }
  };
  $('assistant-chat-form').elements.input.addEventListener('input', persistDraft);
  $('assistant-chat-form').elements.input.onkeydown = event => {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); $('assistant-chat-form').requestSubmit(); }
  };
  async function runAction(button, operation, confirmation) {
    const threadId = button.dataset.threadId;
    const runId = button.dataset.runId;
    const serial = state.navigationSerial;
    if (state.navigationPending || state.runActionPending || !runId ||
        threadId !== state.threadId || threadId !== state.presentedThreadId || runId !== state.runId) return;
    state.runActionPending = true;
    ['assistant-cancel', 'assistant-finish', 'assistant-abandon', 'assistant-resume'].forEach(id => { $(id).disabled = true; });
    try {
      await api(`/runs/${runId}/${operation}`, {method:'POST'});
      if (serial !== state.navigationSerial || threadId !== state.threadId || state.navigationPending) return;
      await loadThread();
      if (serial !== state.navigationSerial || threadId !== state.threadId || state.navigationPending) return;
      if (confirmation) toast(confirmation);
      return true;
    } catch (error) {
      if (serial === state.navigationSerial && threadId === state.threadId && !state.navigationPending) showFatal(error);
    } finally {
      state.runActionPending = false;
      if (!state.navigationPending) {
        ['assistant-cancel', 'assistant-finish', 'assistant-abandon', 'assistant-resume'].forEach(id => { $(id).disabled = false; });
      }
    }
  }
  $('assistant-cancel').onclick = event => runAction(event.currentTarget, 'cancel', '已停止');
  $('assistant-finish').onclick = event => runAction(event.currentTarget, 'finish', '正在根据已读材料收尾');
  $('assistant-abandon').onclick = event => runAction(event.currentTarget, 'cancel', '已放弃本次回答，可以继续聊天');
  $('assistant-resume').onclick = event => runAction(event.currentTarget, 'resume', '');
  $('assistant-save-discussion').onclick = async () => {
    if (state.savePending || state.navigationPending || state.presentedThreadId !== state.threadId) return;
    state.savePending = true;
    const threadId = state.threadId;
    const serial = state.navigationSerial;
    const key = `shiliu-save:${threadId}`;
    try {
      const {thread} = await api(`/threads/${threadId}`);
      if (!navigationCurrent(serial, state.spaceId) || threadId !== state.threadId) return;
      let pending = JSON.parse(localStorage.getItem(key) || 'null');
      const accepted = pending && thread.runs.find(run => run.request_id === pending.request_id);
      if (accepted) {
        localStorage.removeItem(key);
        state.runId = accepted.id;
        await loadThread();
        toast('已恢复原保存请求，请查看原结果');
        return;
      }
      if (thread.runs.some(run => ['queued', 'running', 'interrupted', 'budget_exhausted', 'failed'].includes(run.status))) {
        toast('请先处理当前任务，再保存讨论成果'); return;
      }
      if (!pending) {
        const answer = thread.can_save && thread.messages.find(message => message.id === thread.save_answer_message_id);
        if (!answer) { toast('还没有可保存的正式回答'); return; }
        pending = {request_id: operationKey('ui-save'), answer_message_id: answer.id,
          input: '请整理并保存刚才讨论的内容为知识页；多个主题分别成页，保留条件、来源和缺口。'};
        if (state.capabilities.save_receipt_completion) pending.receipt_only = true;
        localStorage.setItem(key, JSON.stringify(pending));
      }
      const {run} = await api(`/threads/${threadId}/runs`, {method:'POST', body:JSON.stringify(pending)});
      localStorage.removeItem(key);
      if (serial !== state.navigationSerial || threadId !== state.threadId || state.navigationPending) return;
      state.runId = run.id;
      await loadThread();
    } catch (error) {
      // A definite rejection created no run; network/5xx outcomes retain identity.
      if ([400, 404, 409, 422].includes(error.status)) localStorage.removeItem(key);
      // Preserve both the operation identity and the unrelated chat draft.
      if (serial === state.navigationSerial && threadId === state.threadId) {
        showFatal(error); toast('保存结果尚未确认；重试将查询并复用原请求');
      }
    } finally {
      state.savePending = false;
      if(serial===state.navigationSerial && threadId===state.threadId && !state.navigationPending) $('assistant-save-discussion').disabled = $('assistant-save-discussion').hidden;
    }
  };
  async function showMaintenance() {
    const nav=state.navigationSerial,spaceId=state.spaceId;
    if(!spaceId)return;
    const {jobs} = await api(`/jobs${state.spaceId ? `?space_id=${state.spaceId}` : ''}`);
    if(!navigationCurrent(nav,spaceId))return;
    const pending = jobs.filter(job => ['queued', 'running', 'retry_wait', 'budget_wait'].includes(job.status));
    $('assistant-maintenance-status').textContent = state.capabilities.background_maintenance === 'paused' ? `后台暂停；${pending.length} 项尚未执行` : pending.length ?
      `待空闲整理 ${pending.length} 项${pending.some(job => job.status === 'retry_wait') ? ' · 已暂停，稍后继续' : ''}` : '';
  }
  showMaintenance().catch(() => {});
  setInterval(() => {showMaintenance().catch(() => {});messageCount().catch(()=>{});}, 15000);
  $('assistant-new-thread').onclick = () => { beginNavigation(); return newThread(); };
  $('assistant-open-history').onclick = async () => {
    if (state.navigationPending) return;
    const serial = state.navigationSerial;
    const spaceId = state.spaceId;
    try {
      if (await loadHistory() && navigationCurrent(serial, spaceId) && !state.navigationPending) openDrawer('assistant-history-panel', '历史对话');
    } catch (error) { if (navigationCurrent(serial, spaceId) && !state.navigationPending) showFatal(error); }
  };
  $('assistant-history-more').onclick = async () => {
    const serial = state.navigationSerial;
    const spaceId = state.spaceId;
    try { await loadHistory(true); }
    catch (error) { if (navigationCurrent(serial, spaceId) && !state.navigationPending) showFatal(error); }
  };
  $('assistant-open-knowledge').onclick = async () => {
    const serial=state.navigationSerial, spaceId=state.spaceId, threadId=state.threadId;
    try {
      const [loaded] = await Promise.all([loadKnowledge(), loadKnowledgeStatus()]);
      if(loaded && navigationCurrent(serial,spaceId) && threadId===state.threadId && !state.navigationPending) openDrawer('assistant-knowledge-panel', 'Wiki');
    } catch(error) { if(navigationCurrent(serial,spaceId) && threadId===state.threadId) toast(`知识面板加载失败：${error.message}`); }
  };
  $('assistant-knowledge-back').onclick = () => loadKnowledge($('assistant-knowledge-query').value.trim());
  $('assistant-knowledge-query').oninput = event => {
    clearTimeout(event.target._timer);
    event.target._timer = setTimeout(() => loadKnowledge(event.target.value.trim()).catch(showFatal), 250);
  };
  $('assistant-knowledge-organize').onclick = async () => {
    const button = $('assistant-knowledge-organize'); button.disabled = true;
    try {
      const {bootstrap} = await api(`/spaces/${state.spaceId}/bootstrap?limit=10&thread_id=${encodeURIComponent(state.threadId || "")}`, {method:'POST'});
      toast(bootstrap.queued ? `已加入 ${bootstrap.queued} 项整理` : '当前范围没有待整理材料');
      for (let attempt = 0; attempt < 8; attempt += 1) {
        await new Promise(resolve => setTimeout(resolve, 900));
        const active = await loadKnowledgeStatus();
        if (!active) break;
      }
      await loadKnowledge($('assistant-knowledge-query').value.trim());
    } finally { button.disabled = false; }
  };
  $('assistant-open-memory').onclick = async () => {
    const serial = state.navigationSerial, spaceId = state.spaceId;
    await loadMemories();
    if (navigationCurrent(serial, spaceId)) openDrawer('assistant-memory-panel', '记忆');
  };
  $('assistant-open-settings').onclick = async () => { const nav=state.navigationSerial; await loadCapabilities(); if(nav!==state.navigationSerial)return; $('assistant-background-state').textContent=backgroundLabel()+' Memory 自动提炼请在记忆面板设置；Wiki 维护模式在 Space 管理中设置。'; openDrawer('assistant-settings-panel', '设置'); };
  $('assistant-manage-spaces').onclick = () => { openDrawer('assistant-spaces-panel', 'Space 管理'); loadSpaceManager(); };
  $('assistant-open-maintenance').onclick = openMessages;
  $('assistant-close-drawer').onclick = closeDrawer;
  $('assistant-shade').onclick = event => { if (event.target === $('assistant-shade')) closeDrawer(); };
  document.addEventListener('keydown', event => { if (event.key === 'Escape') closeDrawer(); });
  document.querySelectorAll('[data-prompt]').forEach(button => button.onclick = () => {
    const input = $('assistant-chat-form').elements.input; input.value = button.dataset.prompt; input.focus();
  });
  $('assistant-memory-form').onsubmit = async event => {
    event.preventDefault(); const form = new FormData(event.target); const scopeKind = form.get('scope_kind');
    const scope = {spaceId: state.spaceId, threadId: state.threadId, serial: state.navigationSerial};
    const button = event.target.querySelector('button[type="submit"], button');
    if (button.disabled) return;
    button.disabled = true;
    try {
      const result = await api('/memories', {method:'POST', body:JSON.stringify({text:form.get('text'), scope_kind:scopeKind, scope_id:scopeKind === 'space' ? scope.spaceId : null, operation_key:operationKey('ui-memory')})});
      if (scope.serial !== state.navigationSerial) return;
      event.target.reset();
      if (result.save_feedback) showSaveFeedback(result.save_feedback, scope);
      else toast('已保存记忆');
      const notice = state.feedbackSerial;
      await loadMemories().catch(error => {
        if (scope.serial === state.navigationSerial && notice === state.feedbackSerial) {
          const note = document.createElement('span'); note.textContent = '已保存；列表刷新失败，请重新打开记忆';
          $('assistant-toast').append(note);
        }
      });
    } catch (error) { if (scope.serial === state.navigationSerial) toast(`未能保存，输入已保留：${error.message}`); }
    finally { button.disabled = false; }
  };
  $('assistant-auto-memory').onchange = async event => {
    const enabled = event.target.checked;
    try {
      await api('/memory-settings', {method:'PATCH', body:JSON.stringify({enabled})});
      toast(enabled ? '已开启自动记忆' : '已关闭自动记忆');
    } catch (error) {
      event.target.checked = !enabled;
      toast('设置失败，请重试');
    }
  };
  setInterval(() => {
    if ($('assistant-memory-panel').hidden || state.navigationPending || state.memoryEpoch == null) return;
    api(`/memory-changes?after_epoch=${state.memoryEpoch}&space_id=${state.spaceId}`)
      .then(change => {
        if (change.items.length) return loadMemories();
        state.memoryEpoch = change.current_epoch;
      }).catch(() => {});
  }, 5000);

  (async () => {
    try {
      await loadSpaces(true);
      if (state.spaceId) {
        if (state.threadId) {
          const threadId = state.threadId;
          const serial = beginNavigation();
          const {thread} = await api(`/threads/${encodeURIComponent(threadId)}`);
          if (serial !== state.navigationSerial) return;
          state.spaceId = Number(thread.space_id);
          rememberThread(thread); renderThread(thread);
        } else { beginNavigation(); await newThread(); }
      }
      await loadCapabilities();
    } catch (error) { showFatal(error); }
  })();
})();
