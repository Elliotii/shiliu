(() => {
  const root = document.querySelector('.assistant-app[data-enabled="true"]');
  if (!root) return;
  const $ = id => document.getElementById(id);
  const urlState = new URL(location.href);
  const state = {
    spaceId: null,
    threadId: urlState.searchParams.get('thread') || sessionStorage.getItem('shiliu.assistant.thread'),
    runId: null,
    timer: null,
    spaces: [],
    capabilities: {},
    historyCursor: null,
    navigationSerial: 0,
    historyRequestSerial: 0,
    navigationPending: false,
    presentedThreadId: null,
    runActionPending: false,
  };
  function beginNavigation() {
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
    ['assistant-send', 'assistant-cancel', 'assistant-abandon', 'assistant-resume'].forEach(id => { $(id).hidden = true; });
    ['assistant-new-thread', 'assistant-open-history'].forEach(id => { $(id).disabled = true; });
    return state.navigationSerial;
  }
  const navigationCurrent = (serial, spaceId) =>
    serial === state.navigationSerial && spaceId === state.spaceId;
  function rememberThread(thread) {
    state.threadId = thread.id;
    state.spaceId = Number(thread.space_id);
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
      throw new Error(detail || `请求失败（${response.status}）`);
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
    const node = $('assistant-toast');
    node.textContent = text; node.hidden = false;
    clearTimeout(node._timer);
    node._timer = setTimeout(() => { node.hidden = true; }, 2200);
  }

  function openDrawer(panel, title) {
    $('assistant-drawer-title').textContent = title;
    ['assistant-history-panel', 'assistant-memory-panel', 'assistant-knowledge-panel', 'assistant-settings-panel', 'assistant-spaces-panel'].forEach(id => { $(id).hidden = id !== panel; });
    $('assistant-shade').hidden = false;
    $('assistant-close-drawer').focus();
  }
  function closeDrawer() { $('assistant-shade').hidden = true; }

  async function loadSpaces(selectNewest = false) {
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
    state.spaceId = selectNewest ? spaces[0].id : (spaces.some(space => space.id === stored) ? stored : spaces[0].id);
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
    const sources = [];
    thread.messages.filter(message => message.run_id === runId && message.role === 'tool').forEach(message => {
      const meta = parsePayload(message);
      let result = {};
      try { result = JSON.parse(message.content || '{}'); } catch { result = {}; }
      if (meta.name?.startsWith('context7_')) sources.push('外部技术文档 · Context7');
      if ((result.source_refs || []).length) sources.push('当前收藏范围内的材料');
      (result.items || []).slice(0, 8).forEach(item => {
        const title = item.title || item.folder_title;
        if (title) sources.push(`收藏 · ${title}`);
      });
    });
    return [...new Set(sources)];
  }

  function createSources(thread, runId) {
    const sources = sourcesForRun(thread, runId);
    if (!sources.length) return null;
    const details = document.createElement('details');
    details.className = 'assistant-sources';
    const summary = document.createElement('summary');
    summary.textContent = `参考收藏／来源 · ${sources.length} 条`;
    const list = document.createElement('div'); list.className = 'assistant-source-list';
    sources.forEach(source => { const item = document.createElement('div'); item.textContent = source; list.append(item); });
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

    const run = activeRun(thread);
    state.runId = run?.id || null;
    const isRunning = run && ['queued','running'].includes(run.status);
    const isResumable = Boolean(run?.actions?.resume);
    const noteStatus = thread.task_note?.status === 'active' && thread.task_note.usable !== false
      ? `已保存任务进度 · 查阅记录 ${thread.task_note.searched_scope_and_material_refs.length} 项`
      : '';
    $('assistant-thread-state').textContent = run
      ? [shortStatus(run, currentToolName(thread, run.id)), noteStatus].filter(Boolean).join(' · ')
      : noteStatus;
    $('assistant-cancel').hidden = !isRunning;
    $('assistant-abandon').hidden = !run || isRunning;
    $('assistant-send').hidden = Boolean(run);
    $('assistant-resume').hidden = !isResumable;
    ['assistant-cancel', 'assistant-abandon', 'assistant-resume'].forEach(id => {
      $(id).dataset.threadId = thread.id;
      $(id).dataset.runId = run?.id || '';
      $(id).disabled = state.runActionPending;
    });
    const input = $('assistant-chat-form').elements.input;
    input.disabled = Boolean(run);

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
    const scroll = $('assistant-scroll');
    scroll.scrollTop = scroll.scrollHeight;
    if (run && ['queued','running'].includes(run.status)) schedule();
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
      const card = document.createElement('article'); card.className = 'assistant-memory-card';
      const text = document.createElement('p'); text.textContent = memory.text;
      const scope = document.createElement('div'); scope.className = 'assistant-memory-scope';
      const details = [memory.scope_kind === 'user' ? '适用范围：所有对话' : '适用范围：当前收藏范围'];
      details.push(memory.kind === 'context' && memory.expires_at ? '近期背景' : '个人记忆');
      details.push(memory.origin === 'extracted' ? '来源：对话中自动提炼' : '来源：你明确保存或修改');
      if (memory.source_excerpt) details.push(`原话：${memory.source_excerpt}`);
      if (memory.validity_note) details.push(`有效期说明：${memory.validity_note}`);
      if (memory.expires_at) details.push(`有效至：${new Date(memory.expires_at).toLocaleString('zh-CN')}`);
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
        const editor = document.createElement('div'); editor.className = 'assistant-memory-editor';
        const field = document.createElement('textarea'); field.rows = 3; field.maxLength = 400; field.value = memory.text; field.setAttribute('aria-label', '修改记忆');
        const buttons = document.createElement('div'); buttons.className = 'assistant-memory-actions';
        const save = document.createElement('button'); save.type = 'button'; save.textContent = '保存修改';
        const cancel = document.createElement('button'); cancel.type = 'button'; cancel.textContent = '取消';
        buttons.append(save, cancel); editor.append(field, buttons); text.replaceWith(editor); field.focus();
        cancel.onclick = loadMemories;
        save.onclick = async () => {
          const value = field.value.trim(); if (!value) return;
          await api(`/memories/${memory.id}`, {method:'PATCH', body:JSON.stringify({text:value, expected_version:memory.version, operation_key:operationKey('ui-correct')})});
          await loadMemories(); toast('已修改');
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
    if (capabilities.context7 === 'unavailable') failures.push('技术文档查询暂时不可用');
    if (capabilities.memory_index === 'unavailable') failures.push('记忆语义索引暂时不可用，正式记录仍会保存');
    const note = $('assistant-service-note'); note.hidden = failures.length === 0; note.textContent = failures.join('；');
  }

  const coverageLabel = value => ({
    metadata_only: '标题／简介', summary_based: '摘要',
    partial_transcript: '部分字幕', full_available_transcript: '完整可得字幕',
  }[value] || '材料范围未知');
  function formatDate(value) {
    if (value === null || value === undefined || value === '') return '时间未知';
    const date = typeof value === 'number' ? new Date(value * 1000) : new Date(value);
    return Number.isNaN(date.getTime()) ? '时间未知' : date.toLocaleDateString('zh-CN');
  }

  async function loadKnowledge(query = '') {
    if (!state.spaceId) return;
    $('assistant-knowledge-list-view').hidden = false;
    $('assistant-knowledge-detail').hidden = true;
    const [{pages}, {plans}] = await Promise.all([
      api(`/wiki?space_id=${state.spaceId}&query=${encodeURIComponent(query)}`),
      api(`/knowledge-plans?space_id=${state.spaceId}`),
    ]);
    const box = $('assistant-knowledge-pages'); box.innerHTML = '';
    plans.filter(plan => ['pending', 'partial'].includes(plan.status)).forEach(plan => {
      const card = document.createElement('div'); card.className = 'assistant-knowledge-card';
      const title = document.createElement('strong'); title.textContent = plan.status === 'partial' ? (Object.keys(plan.results).length ? '主题整理部分完成' : '主题整理已确认，继续保存') : '待确认的主题划分'; card.append(title);
      plan.payload.topics.forEach((item, index) => {
        const section = document.createElement('div');
        const result = plan.results[String(index)];
        section.textContent = `${index + 1}. ${item.title} · ${item.purpose} · ${item.page_id ? '更新现有页' : '新建'}${result ? ` · ${result.status}${result.reason ? `（${result.reason}）` : ''}` : ''}`;
        const detail = document.createElement('small');
        detail.textContent = `材料：${(item.source_labels || []).join('、') || '无材料引用'}；交叉参考：${item.cross_references.join('、') || '无'}；不纳入：${item.omitted.join('、') || '无'}`;
        section.append(detail); card.append(section);
        (item.blocks || []).forEach(block => {
          const point = document.createElement('p');
          const role = {source:'来源', analysis:'分析', personal:'我的笔记'}[block.role] || '内容';
          point.textContent = `${role} · ${block.heading}：${block.markdown.slice(0, 180)}${block.markdown.length > 180 ? '…' : ''}`;
          section.append(point);
        });
      });
      if (plan.payload.omitted.length) {
        const omitted = document.createElement('small'); omitted.textContent = `本次不纳入：${plan.payload.omitted.join('、')}`; card.append(omitted);
      }
      if (plan.status === 'pending') {
        const edit = document.createElement('button'); edit.type = 'button'; edit.textContent = '调整提案'; card.append(edit);
        edit.onclick = () => {
          edit.disabled = true;
          const form = document.createElement('div'); form.className = 'assistant-knowledge-card';
          const fields = plan.payload.topics.map((topic, index) => {
            const section = document.createElement('div');
            const label = document.createElement('strong'); label.textContent = `主题 ${index + 1}`; section.append(label);
            const input = (caption, value, multiline = false) => {
              const wrap = document.createElement('label'); wrap.textContent = caption;
              const control = document.createElement(multiline ? 'textarea' : 'input'); control.value = value;
              wrap.append(control); section.append(wrap); return control;
            };
            const title = input('标题', topic.title);
            const purpose = input('用途', topic.purpose, true);
            const blocks = topic.blocks.map(block => input(`内容 · ${{source:'来源',analysis:'分析',personal:'我的笔记'}[block.role] || block.role} · ${block.heading}`, block.markdown, true));
            form.append(section); return {title, purpose, blocks};
          });
          const save = document.createElement('button'); save.type = 'button'; save.textContent = '保存调整后的提案';
          save.onclick = async () => {
            const topics = plan.payload.topics.map((topic, index) => ({
              ...topic, title:fields[index].title.value.trim(), purpose:fields[index].purpose.value.trim(),
              blocks:topic.blocks.map((block, blockIndex) => ({...block, markdown:fields[index].blocks[blockIndex].value.trim()})),
            }));
            const {plan:updated} = await api(`/knowledge-plans/${plan.id}`, {method:'PATCH', body:JSON.stringify({
              space_id:state.spaceId, expected_version:plan.version, topics, omitted:plan.payload.omitted,
              operation_key:operationKey('ui-knowledge-plan-revise'),
            })});
            toast(`提案已调整到第 ${updated.version} 版，请确认后保存`); await loadKnowledge(query);
          };
          form.append(save); card.append(form);
        };
      }
      [true, false].forEach(accept => {
        if (!accept && plan.status !== 'pending') return;
        const button = document.createElement('button'); button.type = 'button';
        button.textContent = accept ? (plan.status === 'pending' ? '确认并逐页保存' : '重试未完成主题') : '拒绝提案';
        button.onclick = async () => {
          const {plan:updated} = await api(`/knowledge-plans/${plan.id}/decide`, {method:'POST', body:JSON.stringify({
            space_id:state.spaceId, expected_version:plan.version, accept,
            operation_key:operationKey('ui-knowledge-plan'),
          })});
          toast(updated.status === 'completed' ? '主题页已保存' : updated.status === 'partial' ? '部分主题未完成，请查看原因' : '提案已拒绝');
          await loadKnowledge(query);
        }; card.append(button);
      });
      box.append(card);
    });
    if (!pages.length) {
      const empty = document.createElement('div'); empty.className = 'assistant-knowledge-empty';
      empty.innerHTML = '<strong>还没有可用的主题页</strong><p>可以先整理当前范围；只有标题而没有实质材料的收藏不会被写成知识结论。</p>';
      box.append(empty); return;
    }
    pages.forEach(page => {
      const card = document.createElement('button'); card.type = 'button'; card.className = 'assistant-knowledge-card';
      const title = document.createElement('strong'); title.textContent = page.title;
      const summary = document.createElement('span');
      summary.textContent = page.summary ? `${page.summary.slice(0, 170)}${page.summary.length > 170 ? '…' : ''}` : '暂无导读';
      const meta = document.createElement('small');
      meta.textContent = `${page.blocks.length} 个知识块 · 更新于 ${formatDate(page.updated_at)}${page.availability === 'partial' ? ' · 部分可用' : ''}`;
      card.append(title, summary, meta); card.onclick = () => openKnowledgePage(page.id);
      box.append(card);
    });
  }

  async function openKnowledgePage(pageId) {
    const [{page}, {changes}, {pages}, {proposals}] = await Promise.all([
      api(`/wiki/${pageId}?space_id=${state.spaceId}`),
      api(`/wiki/${pageId}/changes?space_id=${state.spaceId}`),
      api(`/wiki?space_id=${state.spaceId}`),
      api(`/wiki-actions/proposals?space_id=${state.spaceId}`),
    ]);
    if (page.id !== pageId) return openKnowledgePage(page.id);
    $('assistant-knowledge-list-view').hidden = true;
    $('assistant-knowledge-detail').hidden = false;
    const box = $('assistant-knowledge-page'); box.innerHTML = '';
    const heading = document.createElement('div'); heading.className = 'assistant-knowledge-heading';
    const title = document.createElement('h3'); title.textContent = page.title;
    const summary = document.createElement('p');
    summary.textContent = page.summary ? `${page.summary.slice(0, 560)}${page.summary.length > 560 ? '…' : ''}` : '暂无导读';
    const meta = document.createElement('small'); meta.textContent = `更新于 ${formatDate(page.updated_at)}${page.availability === 'partial' ? ' · 当前范围仅可见部分内容' : ''}`;
    heading.append(title, summary, meta); box.append(heading);
    const noteForm = document.createElement('details'); noteForm.className = 'assistant-knowledge-history';
    const noteTitle = document.createElement('summary'); noteTitle.textContent = '添加我的笔记';
    const noteText = document.createElement('textarea'); noteText.rows = 3; noteText.maxLength = 4000;
    noteText.placeholder = '写下你自己的理解；它会与材料观点分开保存';
    const noteSave = document.createElement('button'); noteSave.type = 'button'; noteSave.textContent = '保存笔记';
    noteSave.onclick = async () => {
      await api(`/wiki/${pageId}/notes`, {method:'POST', body:JSON.stringify({
        space_id:state.spaceId, text:noteText.value, expected_version:page.version,
        operation_key:operationKey('ui-wiki-note'),
      })});
      toast('个人笔记已保存'); await openKnowledgePage(pageId);
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
          space_id:state.spaceId, source_page_id:page.id, target_page_id:target.id,
          source_version:page.version, target_version:target.version,
          operation_key:operationKey('ui-wiki-merge'),
        })});
        toast(result.status === 'merged' ? '主题已合并' : result.status === 'pending' ? '人工内容有差异，请查看待确认项' : '同一差异已被拒绝');
        await openKnowledgePage(result.status === 'merged' ? target.id : page.id);
      };
      mergeForm.append(mergeTitle, select, mergeButton); box.append(mergeForm);
    }
    proposals.filter(item => item.source_page_id === page.id || item.target_page_id === page.id).forEach(item => {
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
              space_id:state.spaceId, accept, operation_key:operationKey('ui-wiki-proposal'),
            })});
            if (result.status === 'accepted' || result.status === 'merged') toast('已合并，两个判断均已保留');
            else if (result.status === 'rejected') toast('已拒绝本次合并');
            else if (result.status === 'stale') toast('提案已过期，请查看当前主题');
            else toast('提案状态已更新');
            await openKnowledgePage(result.page_id || page.id);
          } catch (error) {
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
          row.append(link, document.createTextNode(
            `${source.uploader ? ` · 上传者 ${source.uploader}` : ''} · ${coverageLabel(source.coverage)} · ${source.material_view || '材料视图未知'} · 发布 ${formatDate(source.published_at)} · 收藏 ${formatDate(source.collected_at)}`
          ));
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
            space_id:state.spaceId, block_id:block.stable_id, markdown:field.value,
            expected_version:page.version, operation_key:operationKey('ui-wiki-edit'),
          })});
          toast('知识页已修订'); await openKnowledgePage(pageId);
        };
      };
      actions.append(edit); article.append(h, body, detail, actions);
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
        restore.onclick = async () => {
          await api(`/wiki/${pageId}/revert`, {method:'POST', body:JSON.stringify({
            space_id:state.spaceId, target_version:change.version,
            expected_version:page.version, operation_key:operationKey('ui-wiki-revert'),
          })});
          toast('已生成恢复版本'); await openKnowledgePage(pageId);
        };
        row.append(restore);
      }
      historyList.append(row);
    });
    history.append(historyTitle, historyList); box.append(history);
  }

  async function loadKnowledgeStatus() {
    const {jobs} = await api('/jobs');
    const kinds = new Set(['source_reconcile','source_extract','wiki_integrate']);
    const relevant = jobs.filter(job => kinds.has(job.kind));
    const active = relevant.filter(job => ['queued','running','retry_wait'].includes(job.status)).length;
    const blocked = relevant.filter(job => job.status === 'blocked').length;
    const status = $('assistant-knowledge-status');
    status.textContent = active ? `正在整理 ${active} 项材料…` : (blocked ? `${blocked} 项暂未完成，可稍后重试` : '已整理到当前进度');
    return active;
  }

  async function loadJobProblems() {
    const {jobs} = await api('/jobs');
    const blocked = jobs.filter(job => job.status === 'blocked');
    if (!blocked.length) return;
    const note = $('assistant-service-note');
    note.hidden = false;
    const labels = {memory_extract:'记忆提炼', memory_index:'记忆索引', source_reconcile:'来源同步', source_extract:'材料整理', wiki_integrate:'知识整理'};
    const counts = {};
    blocked.forEach(job => { const label = labels[job.kind] || '后台处理'; counts[label] = (counts[label] || 0) + 1; });
    note.textContent = `暂未完成：${Object.entries(counts).map(([label, count]) => `${label} ${count} 项`).join('、')}。`;
  }
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
    await api('/spaces', {method:'POST', body:JSON.stringify({
      name:form.get('name'), goal:form.get('goal') || '', source_ids:form.getAll('source_ids').map(Number), all_active:form.get('all_active') === 'on',
    })});
    await loadSpaces(true); beginNavigation(); await newThread();
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
    try {
      const {run} = await api(`/threads/${threadId}/runs`, {method:'POST', body:JSON.stringify({input:text, request_id:operationKey('ui-run')})});
      if (serial !== state.navigationSerial || threadId !== state.threadId || state.navigationPending) return;
      state.runId = run.id; input.value = ''; await loadThread();
    } catch (error) { if (serial === state.navigationSerial && threadId === state.threadId) { showFatal(error); input.focus(); } }
  };
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
    ['assistant-cancel', 'assistant-abandon', 'assistant-resume'].forEach(id => { $(id).disabled = true; });
    try {
      await api(`/runs/${runId}/${operation}`, {method:'POST'});
      if (serial !== state.navigationSerial || threadId !== state.threadId || state.navigationPending) return;
      await loadThread();
      if (confirmation) toast(confirmation);
    } catch (error) {
      if (serial === state.navigationSerial && threadId === state.threadId && !state.navigationPending) showFatal(error);
    } finally {
      state.runActionPending = false;
      if (!state.navigationPending) {
        ['assistant-cancel', 'assistant-abandon', 'assistant-resume'].forEach(id => { $(id).disabled = false; });
      }
    }
  }
  $('assistant-cancel').onclick = event => runAction(event.currentTarget, 'cancel', '已停止');
  $('assistant-abandon').onclick = event => runAction(event.currentTarget, 'cancel', '已放弃本次回答，可以继续聊天');
  $('assistant-resume').onclick = event => runAction(event.currentTarget, 'resume', '');
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
    await Promise.all([loadKnowledge(), loadKnowledgeStatus()]);
    openDrawer('assistant-knowledge-panel', '知识');
  };
  $('assistant-knowledge-back').onclick = () => loadKnowledge($('assistant-knowledge-query').value.trim());
  $('assistant-knowledge-query').oninput = event => {
    clearTimeout(event.target._timer);
    event.target._timer = setTimeout(() => loadKnowledge(event.target.value.trim()).catch(showFatal), 250);
  };
  $('assistant-knowledge-organize').onclick = async () => {
    const button = $('assistant-knowledge-organize'); button.disabled = true;
    try {
      const {bootstrap} = await api(`/spaces/${state.spaceId}/bootstrap?limit=10`, {method:'POST'});
      toast(bootstrap.queued ? `已加入 ${bootstrap.queued} 项整理` : '当前范围没有待整理材料');
      for (let attempt = 0; attempt < 8; attempt += 1) {
        await new Promise(resolve => setTimeout(resolve, 900));
        const active = await loadKnowledgeStatus();
        if (!active) break;
      }
      await loadKnowledge($('assistant-knowledge-query').value.trim());
    } finally { button.disabled = false; }
  };
  $('assistant-open-memory').onclick = async () => { await loadMemories(); openDrawer('assistant-memory-panel', '记忆'); };
  $('assistant-open-settings').onclick = async () => { await Promise.all([loadCapabilities(), loadJobProblems()]); openDrawer('assistant-settings-panel', '设置'); };
  $('assistant-manage-spaces').onclick = () => openDrawer('assistant-spaces-panel', '收藏范围');
  $('assistant-close-drawer').onclick = closeDrawer;
  $('assistant-shade').onclick = event => { if (event.target === $('assistant-shade')) closeDrawer(); };
  document.addEventListener('keydown', event => { if (event.key === 'Escape') closeDrawer(); });
  document.querySelectorAll('[data-prompt]').forEach(button => button.onclick = () => {
    const input = $('assistant-chat-form').elements.input; input.value = button.dataset.prompt; input.focus();
  });
  $('assistant-memory-form').onsubmit = async event => {
    event.preventDefault(); const form = new FormData(event.target); const scopeKind = form.get('scope_kind');
    await api('/memories', {method:'POST', body:JSON.stringify({text:form.get('text'), scope_kind:scopeKind, scope_id:scopeKind === 'space' ? state.spaceId : null})});
    event.target.reset(); await loadMemories(); toast('已记住');
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
      await loadSpaces();
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
