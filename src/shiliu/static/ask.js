(() => {
  const root = document.querySelector('[data-ask-page]');
  const evidenceUI = window.ShiliuEvidenceUI;
  if (!root || !evidenceUI) return;

  const {element, formatTime, renderEvidenceCard, sourceLabels} = evidenceUI;
  const form = root.querySelector('[data-ask-form]');
  const queryInput = form.elements.q;
  const submitButton = root.querySelector('[data-ask-submit]');
  const states = {
    idle: root.querySelector('[data-idle-state]'),
    loading: root.querySelector('[data-loading-state]'),
    error: root.querySelector('[data-error-state]'),
    result: root.querySelector('[data-result-state]'),
  };
  const terminationLabels = {
    answer_ready: '已找到可用字幕证据并完成本次回答',
    no_new_evidence: '继续搜索没有发现新的有效字幕',
    repeated_search: '后续搜索开始重复已有结果',
    budget_exhausted: '已达到本次搜索的安全上限',
    provider_error: '回答服务暂时不可用',
    evidence_unavailable: '相关线索的当前字幕证据不可用或已过期',
  };
  const statusLabels = {
    complete: '证据充分',
    partial: '部分回答',
    insufficient: '证据不足',
  };
  const modeLabels = {fast: '快速回答', deep: '深入搜索'};
  let activeController = null;
  let requestSequence = 0;
  let elapsedTimer = null;
  let lastRequest = null;
  let lastResponse = null;
  let traceLoadedFor = null;

  const showState = name => {
    Object.entries(states).forEach(([key, node]) => { node.hidden = key !== name; });
  };

  const stopElapsed = () => {
    if (elapsedTimer !== null) window.clearInterval(elapsedTimer);
    elapsedTimer = null;
  };

  const startElapsed = started => {
    stopElapsed();
    const target = root.querySelector('[data-elapsed-time]');
    const update = () => {
      const seconds = Math.max(0, Math.floor((performance.now() - started) / 1000));
      target.textContent = `${seconds} 秒`;
    };
    update();
    elapsedTimer = window.setInterval(update, 1000);
  };

  const dateEpoch = (value, endOfDay = false) => {
    if (!value) return null;
    const parsed = new Date(`${value}${endOfDay ? 'T23:59:59' : 'T00:00:00'}`);
    return Number.isNaN(parsed.getTime()) ? null : Math.floor(parsed.getTime() / 1000);
  };

  const selectedMode = () => form.elements.mode.value === 'deep' ? 'deep' : 'fast';

  const formState = () => ({
    q: queryInput.value.trim(),
    mode: selectedMode(),
    folder_id: form.elements.folder_id.value,
    reading_state: form.elements.reading_state.value,
    marked: form.elements.marked.value,
    uploader_contains: form.elements.uploader_contains.value.trim(),
    favorite_time_from: form.elements.favorite_time_from.value,
    favorite_time_to: form.elements.favorite_time_to.value,
    archived: form.elements.archived.checked,
    ignored: form.elements.ignored.checked,
  });

  const filterPayload = state => {
    const filters = {ignored: Boolean(state.ignored)};
    if (state.folder_id) filters.folder_id = Number(state.folder_id);
    if (state.reading_state) filters.reading_state = state.reading_state;
    if (state.marked) filters.marked = state.marked === 'true';
    if (state.uploader_contains) filters.uploader_contains = state.uploader_contains;
    const from = dateEpoch(state.favorite_time_from);
    const to = dateEpoch(state.favorite_time_to, true);
    if (from !== null) filters.favorite_time_from = from;
    if (to !== null) filters.favorite_time_to = to;
    if (state.archived) filters.archived = true;
    return filters;
  };

  const requestPayload = state => ({
    query: state.q,
    mode: state.mode,
    filters: filterPayload(state),
  });

  const updateFilterCount = () => {
    const state = formState();
    const count = [
      state.folder_id,
      state.reading_state,
      state.marked,
      state.uploader_contains,
      state.favorite_time_from,
      state.favorite_time_to,
      state.archived,
      state.ignored,
    ].filter(Boolean).length;
    root.querySelector('[data-filter-count]').textContent = count ? `· ${count} 项` : '';
  };

  const updateUrl = (state, replace = false) => {
    const params = new URLSearchParams();
    if (state.q) params.set('q', state.q);
    if (state.mode === 'deep') params.set('mode', 'deep');
    for (const name of [
      'folder_id',
      'reading_state',
      'marked',
      'uploader_contains',
      'favorite_time_from',
      'favorite_time_to',
    ]) {
      if (state[name]) params.set(name, state[name]);
    }
    if (state.archived) params.set('archived', 'true');
    if (state.ignored) params.set('ignored', 'true');
    history[replace ? 'replaceState' : 'pushState']({}, '', `${location.pathname}${params.size ? `?${params}` : ''}`);
  };

  const restoreForm = () => {
    const params = new URLSearchParams(location.search);
    queryInput.value = params.get('q') || '';
    const mode = params.get('mode') === 'deep' ? 'deep' : 'fast';
    form.querySelector(`input[name=mode][value=${mode}]`).checked = true;
    for (const name of [
      'folder_id',
      'reading_state',
      'marked',
      'uploader_contains',
      'favorite_time_from',
      'favorite_time_to',
    ]) {
      form.elements[name].value = params.get(name) || '';
    }
    form.elements.archived.checked = params.get('archived') === 'true';
    form.elements.ignored.checked = params.get('ignored') === 'true';
    updateFilterCount();
  };

  const resetDeveloperTrace = runId => {
    const details = root.querySelector('[data-developer-trace]');
    details.open = false;
    details.dataset.runId = runId || '';
    traceLoadedFor = null;
    root.querySelector('[data-developer-trace-body]').replaceChildren(
      element('p', '', '展开后读取本次内存 Trace。'),
    );
  };

  const citationNumberMap = citations => new Map(
    (citations || []).map((citation, index) => [citation.citation_id, index + 1]),
  );

  const focusCitation = number => {
    const card = document.getElementById(`citation-${number}`);
    if (!card) return;
    const hiddenGroup = card.closest('.citation-extra[hidden]');
    if (hiddenGroup) {
      hiddenGroup.hidden = false;
      const toggle = hiddenGroup.parentElement?.querySelector('.citation-toggle');
      if (toggle) {
        toggle.setAttribute('aria-expanded', 'true');
        toggle.textContent = '收起其他证据';
      }
    }
    card.scrollIntoView({behavior: 'smooth', block: 'center'});
    card.focus({preventScroll: true});
    card.classList.add('is-citation-target');
    window.setTimeout(() => card.classList.remove('is-citation-target'), 2200);
  };

  const renderAnswerBlocks = data => {
    const container = root.querySelector('[data-answer-blocks]');
    const numbering = citationNumberMap(data.citations);
    container.replaceChildren();
    if (data.status === 'insufficient') {
      container.append(element('p', 'insufficient-copy', '当前没有足够的权威字幕证据，因此没有生成事实答案。'));
      return;
    }
    (data.answer_blocks || []).forEach(block => {
      const article = element('article', 'answer-block');
      const paragraph = element('p', '', block.text);
      const markers = element('span', 'citation-markers');
      (block.citation_ids || []).forEach(citationId => {
        const number = numbering.get(citationId);
        if (!number) return;
        const marker = element('button', 'citation-marker', `[${number}]`);
        marker.type = 'button';
        marker.dataset.citationId = citationId;
        marker.setAttribute('aria-label', `定位到字幕证据 ${number}`);
        marker.addEventListener('click', () => focusCitation(number));
        markers.append(marker);
      });
      paragraph.append(markers);
      article.append(paragraph);
      container.append(article);
    });
  };

  const renderCitation = (citation, number) => renderEvidenceCard({
    id: `citation-${number}`,
    evidenceId: citation.citation_id,
    videoId: citation.video_id,
    eyebrow: `证据 [${number}] · ${sourceLabels[citation.source_type] || sourceLabels.unknown}`,
    title: citation.title || `Video ${citation.video_id}`,
    startTime: citation.start_time,
    endTime: citation.end_time,
    quote: citation.quote_text,
    sourceType: citation.source_type,
    jumpUrl: citation.jump_url,
    jumpLabel: `从 ${formatTime(citation.start_time)} 播放`,
    metadata: [
      ['Stable Citation ID', citation.citation_id],
      ['Identity Version', citation.citation_identity_version],
      ['Source Artifact', citation.source_artifact_id],
      ['Source Version', citation.source_version],
      ['Timeline Run', citation.timeline_run_id],
      ['Segment IDs', (citation.segment_ids || []).join(', ')],
    ],
  });

  const renderEvidence = data => {
    const citations = data.citations || [];
    root.querySelector('[data-evidence-count]').textContent = `${citations.length} 条引用`;
    const section = root.querySelector('[data-evidence-section]');
    section.hidden = citations.length === 0;
    const groups = root.querySelector('[data-citation-groups]');
    groups.replaceChildren();
    const numbering = citationNumberMap(citations);
    const byVideo = new Map();
    citations.forEach(citation => {
      if (!byVideo.has(citation.video_id)) byVideo.set(citation.video_id, []);
      byVideo.get(citation.video_id).push(citation);
    });
    byVideo.forEach(values => {
      const group = element('section', 'citation-video-group');
      const heading = element('div', 'citation-video-heading');
      heading.append(element('h3', '', values[0].title || `Video ${values[0].video_id}`));
      heading.append(element('span', '', `${values.length} 条字幕证据`));
      group.append(heading, renderCitation(values[0], numbering.get(values[0].citation_id)));
      if (values.length > 1) {
        const extra = element('div', 'citation-extra');
        extra.hidden = true;
        values.slice(1).forEach(value => extra.append(renderCitation(value, numbering.get(value.citation_id))));
        const toggle = element('button', 'citation-toggle', `展开另外 ${values.length - 1} 条证据`);
        toggle.type = 'button';
        toggle.setAttribute('aria-expanded', 'false');
        toggle.addEventListener('click', () => {
          const expanded = toggle.getAttribute('aria-expanded') === 'true';
          toggle.setAttribute('aria-expanded', String(!expanded));
          toggle.textContent = expanded ? `展开另外 ${values.length - 1} 条证据` : '收起其他证据';
          extra.hidden = expanded;
        });
        group.append(toggle, extra);
      }
      groups.append(group);
    });
  };

  const appendMetric = (container, term, value) => {
    const wrapper = element('div', 'trace-metric');
    wrapper.append(element('dt', '', term), element('dd', '', value));
    container.append(wrapper);
  };

  const renderUserTrace = data => {
    const trace = data.trace_summary || {};
    const metrics = root.querySelector('[data-trace-metrics]');
    metrics.replaceChildren();
    appendMetric(metrics, '模式', modeLabels[data.mode] || data.mode);
    appendMetric(metrics, '总耗时', `${Math.round(Number(trace.latency_ms) || 0).toLocaleString()} ms`);
    appendMetric(metrics, '有效字幕证据', Number(trace.valid_evidence_count || 0));
    appendMetric(metrics, '停止原因', terminationLabels[data.termination_reason] || data.termination_reason);
    if (trace.query_count) appendMetric(metrics, '查询数', trace.query_count);
    if (trace.retrieval_count) appendMetric(metrics, '字幕检索', trace.retrieval_count);
    if (trace.stale_evidence_count) appendMetric(metrics, '过期证据', trace.stale_evidence_count);
    if (trace.context_truncated) appendMetric(metrics, '上下文', '已按预算截断');
    if (data.mode === 'deep') {
      if (trace.decision_rounds) appendMetric(metrics, '决策轮次', trace.decision_rounds);
      if (trace.tool_calls) appendMetric(metrics, '工具调用', trace.tool_calls);
      if (trace.visited_video_count) appendMetric(metrics, '查看视频', trace.visited_video_count);
      if (trace.visited_segment_count) appendMetric(metrics, '查看字幕段', trace.visited_segment_count);
      if (trace.navigation_result_count) appendMetric(metrics, '导航结果', trace.navigation_result_count);
      if (trace.evidence_candidate_dropped_count) appendMetric(metrics, '包络外候选', trace.evidence_candidate_dropped_count);
    }
    root.querySelector('[data-action-timeline]').hidden = true;
  };

  const renderLimitations = data => {
    const panel = root.querySelector('[data-limitations-panel]');
    const list = root.querySelector('[data-limitations-list]');
    list.replaceChildren(...(data.limitations || []).map(value => element('li', '', value)));
    panel.hidden = !(data.limitations || []).length;
  };

  const renderResult = data => {
    lastResponse = data;
    root.querySelector('[data-result-title]').textContent = `${modeLabels[data.mode] || '回答'}结果`;
    const badge = root.querySelector('[data-status-badge]');
    badge.className = `status-badge status-${data.status}`;
    badge.textContent = statusLabels[data.status] || data.status;
    root.querySelector('[data-termination-copy]').textContent = terminationLabels[data.termination_reason] || data.termination_reason;
    renderAnswerBlocks(data);
    renderLimitations(data);
    renderEvidence(data);
    renderUserTrace(data);
    root.querySelector('[data-continue-deep]').hidden = !(
      data.mode === 'fast' && ['partial', 'insufficient'].includes(data.status)
    );
    resetDeveloperTrace(data.run_id);
    showState('result');
    window.__shiliuLastAsk = {
      runId: data.run_id,
      mode: data.mode,
      status: data.status,
      terminationReason: data.termination_reason,
      citations: (data.citations || []).length,
    };
  };

  const showError = (status, data) => {
    const error = data?.error || {};
    const code = typeof error === 'object' ? error.code : '';
    const message = typeof error === 'object' ? error.message : '';
    const title = root.querySelector('[data-error-title]');
    const copy = root.querySelector('[data-error-message]');
    if (status === 422 || status === 400) {
      title.textContent = '问题或限定范围无效';
      copy.textContent = '请检查问题内容和限定范围后重试。';
    } else if (code === 'provider_error') {
      title.textContent = '回答服务暂时不可用';
      copy.textContent = message || '字幕检索可能已经完成，但回答服务未能返回可验证结果。';
    } else {
      title.textContent = '无法连接回答服务';
      copy.textContent = '网络或服务请求失败。你可以保留当前问题直接重试。';
    }
    showState('error');
  };

  const executeAsk = async ({push = true} = {}) => {
    const state = formState();
    if (!state.q) {
      showError(422, {});
      queryInput.focus();
      return;
    }
    if (submitButton.disabled) return;
    queryInput.value = state.q;
    if (push) updateUrl(state);
    activeController?.abort();
    const controller = new AbortController();
    activeController = controller;
    const sequence = ++requestSequence;
    const started = performance.now();
    lastRequest = state;
    submitButton.disabled = true;
    submitButton.textContent = state.mode === 'deep' ? '深入搜索中' : '回答中';
    root.querySelector('[data-loading-title]').textContent = state.mode === 'deep'
      ? '正在导航视频并逐步查找字幕证据，可能需要几分钟……'
      : '正在检索字幕并生成有依据的回答……';
    startElapsed(started);
    showState('loading');
    try {
      const response = await fetch('/api/ask', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(requestPayload(state)),
        signal: controller.signal,
      });
      const data = await response.json().catch(() => ({}));
      if (sequence !== requestSequence) return;
      if (!response.ok) showError(response.status, data);
      else renderResult(data);
    } catch (error) {
      if (error.name !== 'AbortError' && sequence === requestSequence) showError(0, {});
    } finally {
      if (sequence === requestSequence) {
        stopElapsed();
        submitButton.disabled = false;
        submitButton.textContent = '开始回答';
      }
    }
  };

  const safeActionLabel = event => {
    const kind = event?.action?.kind;
    return {
      search_navigation: '导航视频',
      search_transcripts: '搜索字幕',
      read_transcript_window: '读取字幕上下文',
      finish: '根据证据完成',
      stop: '按边界停止',
    }[kind] || kind || event.event_type;
  };

  const renderDeveloperTrace = trace => {
    const body = root.querySelector('[data-developer-trace-body]');
    const grid = element('dl', 'developer-trace-grid');
    const rows = [
      ['Run ID', trace.run_id],
      ['Mode', trace.mode],
      ['Policy Version', trace.policy_version],
      ['Status', trace.status],
      ['Termination', trace.termination_reason],
      ['Query rewrites', (trace.queries || []).join(' · ')],
      ['Decision rounds', trace.decision_rounds],
      ['Tool calls', trace.tool_calls],
      ['Visited videos', trace.visited_video_count],
      ['Visited segments', trace.visited_segment_count],
      ['Dropped candidates', trace.evidence_candidate_dropped_count],
      ['Latency', trace.total_latency_ms ?? trace.latency_ms],
    ].filter(([, value]) => value !== undefined && value !== null && value !== '');
    rows.forEach(([term, value]) => grid.append(element('dt', '', term), element('dd', '', value)));
    body.replaceChildren(grid);

    const events = (trace.events || []).slice(0, 40);
    if (events.length) {
      body.append(element('h3', '', '有界行动与 Observation'));
      const list = element('ol', 'developer-events');
      events.forEach(event => {
        const parts = [safeActionLabel(event)];
        if (event.observation_kind) parts.push(event.observation_kind);
        if (event.bounded_observation_summary) parts.push(event.bounded_observation_summary);
        if (event.guard_decision) parts.push(`guard=${event.guard_decision}`);
        if (event.latency_ms !== undefined && event.latency_ms !== null) parts.push(`${Math.round(event.latency_ms)} ms`);
        list.append(element('li', '', parts.join(' · ')));
      });
      body.append(list);
    }
    const usage = trace.usage || trace.answer_usage || trace.finalization?.answer_usage;
    if (usage) {
      body.append(element('h3', '', 'Provider Usage'));
      body.append(element('code', '', JSON.stringify(usage)));
    }
  };

  const loadDeveloperTrace = async () => {
    const details = root.querySelector('[data-developer-trace]');
    if (!details.open || !lastResponse || traceLoadedFor === lastResponse.run_id) return;
    const runId = lastResponse.run_id;
    const body = root.querySelector('[data-developer-trace-body]');
    body.replaceChildren(element('p', '', '正在读取本次内存 Trace……'));
    try {
      const response = await fetch(`/api/ask/traces/${encodeURIComponent(runId)}`);
      const data = await response.json().catch(() => ({}));
      if (!lastResponse || lastResponse.run_id !== runId) return;
      traceLoadedFor = runId;
      if (response.status === 404) {
        body.replaceChildren(element('p', '', '该内存 Trace 已不可用；这不影响已经返回的 Answer 和 Citation。'));
      } else if (!response.ok || !data.trace) {
        body.replaceChildren(element('p', '', '暂时无法读取开发者 Trace。'));
      } else {
        renderDeveloperTrace(data.trace);
      }
    } catch (_error) {
      if (lastResponse?.run_id === runId) body.replaceChildren(element('p', '', '暂时无法读取开发者 Trace。'));
    }
  };

  form.addEventListener('submit', event => {
    event.preventDefault();
    executeAsk();
  });
  form.addEventListener('change', updateFilterCount);
  queryInput.addEventListener('keydown', event => {
    if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
      event.preventDefault();
      executeAsk();
    }
  });
  root.querySelector('[data-clear-filters]').addEventListener('click', () => {
    for (const name of ['folder_id', 'reading_state', 'marked', 'uploader_contains', 'favorite_time_from', 'favorite_time_to']) {
      form.elements[name].value = '';
    }
    form.elements.archived.checked = false;
    form.elements.ignored.checked = false;
    updateFilterCount();
  });
  root.querySelectorAll('[data-example-query]').forEach(button => {
    button.addEventListener('click', () => {
      queryInput.value = button.dataset.exampleQuery;
      queryInput.focus();
    });
  });
  root.querySelector('[data-retry-ask]').addEventListener('click', () => {
    if (lastRequest) {
      queryInput.value = lastRequest.q;
      form.querySelector(`input[name=mode][value=${lastRequest.mode}]`).checked = true;
    }
    executeAsk({push: false});
  });
  root.querySelector('[data-edit-question]').addEventListener('click', () => {
    showState('idle');
    queryInput.focus();
  });
  root.querySelector('[data-use-deep]').addEventListener('click', () => {
    form.querySelector('input[name=mode][value=deep]').checked = true;
    const state = formState();
    updateUrl(state);
    showState('idle');
    submitButton.textContent = '开始深入搜索';
    form.scrollIntoView({behavior: 'smooth', block: 'start'});
    form.querySelector('input[name=mode][value=deep]').focus();
  });
  root.querySelector('[data-developer-trace]').addEventListener('toggle', loadDeveloperTrace);
  window.addEventListener('popstate', () => {
    activeController?.abort();
    requestSequence += 1;
    stopElapsed();
    submitButton.disabled = false;
    submitButton.textContent = '开始回答';
    restoreForm();
    showState('idle');
  });

  restoreForm();
  showState('idle');
  window.__shiliuAsk = {execute: executeAsk, formState};
})();
