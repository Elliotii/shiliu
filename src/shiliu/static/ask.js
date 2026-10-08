(() => {
  const root = document.querySelector('[data-ask-page]');
  const evidenceUI = window.ShiliuEvidenceUI;
  const askKeyboard = window.ShiliuAskKeyboard;
  if (!root || !evidenceUI || !askKeyboard) return;

  const {element, formatTime, renderEvidenceCard, sourceLabels} = evidenceUI;
  const {shouldSubmitOnEnter} = askKeyboard;
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
  const outcomeLabels = {
    source_lookup_complete: '已找到相关视频',
    generation_failed: '回答生成失败',
    evidence_unavailable: '证据不可用',
    evidence_insufficient: '证据不足',
  };
  const modeLabels = {fast: '快速回答', deep: '深入搜索'};
  const lifecycleLabels = {
    run_created: '已创建持久运行记录', requirements_ready: '已完成问题与范围解析',
    search_started: '正在执行字幕检索', search_completed: '已提交一轮真实检索结果',
    evidence_batch_ready: '已提交当前字幕证据批次', deep_round_completed: '已提交一轮深入搜索决策',
    evidence_preview: '已找到相关视频片段，正在生成带引用的回答',
    route_decided: '已提交证据路由决策', claim_verification_started: '正在验证回答中的结论',
    claim_verification_completed: '已提交结论验证结果', minimum_trust_passed: '最小可信门已通过',
    trusted_answer_block: '已提交可信回答段落', answer_completed: '首个可信回答已完成',
    soft_review_started: '正在执行本地软复核', answer_revision_created: '软复核发现变化并创建可见修订',
    soft_review_completed: '本地软复核已完成', soft_review_skipped: '本次没有可复核的可信回答',
    run_completed: '运行已完成', run_failed: '运行失败', run_interrupted: '运行已中断',
  };
  let activeController = null;
  let requestSequence = 0;
  let lastRequest = null;
  let lastResponse = null;
  let traceLoadedFor = null;
  const seenPreviewCitationIds = new Set();

  const showState = name => {
    Object.entries(states).forEach(([key, node]) => { node.hidden = key !== name; });
  };

  const resetPreview = () => {
    seenPreviewCitationIds.clear();
    root.querySelector('[data-preview-evidence-list]').replaceChildren();
    root.querySelector('[data-evidence-preview]').hidden = true;
    root.querySelector('[data-preview-count]').textContent = '';
  };

  const updatePreviewStatus = state => {
    const copy = {
      ready: ['已找到一些可能相关的视频片段，正在生成带引用的回答。', '你可以先查看下面的内容。'],
      final: ['回答已经生成。', '你仍然可以查看下面的相关视频片段。'],
      failed: ['已找到相关内容，但本次回答生成失败。', '你仍然可以查看下面的视频片段。'],
    }[state];
    root.querySelector('[data-preview-title]').textContent = copy[0];
    root.querySelector('[data-preview-copy]').textContent = copy[1];
  };

  const renderEvidencePreview = event => {
    const list = root.querySelector('[data-preview-evidence-list]');
    (event.payload?.items || []).slice(0, 3).forEach(citation => {
      if (!citation.citation_id || seenPreviewCitationIds.has(citation.citation_id)) return;
      seenPreviewCitationIds.add(citation.citation_id);
      list.append(renderEvidenceCard({
        id: `preview-${citation.citation_id}`,
        evidenceId: citation.citation_id,
        videoId: citation.video_id,
        eyebrow: `相关视频片段 · ${sourceLabels[citation.source_type] || sourceLabels.unknown}`,
        title: citation.title || `Video ${citation.video_id}`,
        startTime: citation.start_time,
        endTime: citation.end_time,
        quote: citation.quote_text,
        sourceType: citation.source_type,
        jumpUrl: citation.jump_url,
        jumpLabel: `从 ${formatTime(citation.start_time)} 播放`,
      }));
    });
    if (!seenPreviewCitationIds.size) return;
    root.querySelector('[data-preview-count]').textContent = `${seenPreviewCitationIds.size} 条片段`;
    root.querySelector('[data-evidence-preview]').hidden = false;
    updatePreviewStatus('ready');
  };

  const showLifecycle = event => {
    const target = root.querySelector('[data-lifecycle-status]');
    target.textContent = lifecycleLabels[event.event_type] || `已提交事件：${event.event_type}`;
    target.dataset.sequence = String(event.sequence || '');
    if (event.event_type === 'evidence_preview') renderEvidencePreview(event);
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
    ...(state.mode === 'deep' ? {implementation_version: 'deep-v2'} : {}),
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
      const copy = data.execution_outcome === 'generation_failed'
        ? '字幕检索可能已经完成，但回答服务未能生成可验证的事实答案。'
        : data.execution_outcome === 'evidence_unavailable'
          ? '相关权威字幕证据不可用，因此没有生成事实答案。'
          : '当前没有足够的权威字幕证据，因此没有生成事实答案。';
      container.append(element('p', 'insufficient-copy', copy));
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
        marker.setAttribute('aria-label', `定位到回答依据 ${number}`);
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
      heading.append(element('span', '', `${values.length} 条引用`));
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
    appendMetric(metrics, '有效字幕证据', trace.valid_evidence_count ?? '未记录');
    appendMetric(metrics, '停止原因', terminationLabels[data.termination_reason] || data.termination_reason);
    if (trace.query_count) appendMetric(metrics, '查询数', trace.query_count);
    if (trace.retrieval_count) appendMetric(metrics, '字幕检索', trace.retrieval_count);
    if (trace.stale_evidence_count) appendMetric(metrics, '过期证据', trace.stale_evidence_count);
    if (trace.context_truncated) appendMetric(metrics, '材料范围', '使用部分材料');
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
    const limitations = data.limitations || [];
    const budgetCopy = '上下文预算已截断部分候选证据';
    root.querySelector('[data-context-scope-note]').hidden = !limitations.includes(budgetCopy);
    const warnings = limitations.filter(value => value !== budgetCopy);
    list.replaceChildren(...warnings.map(value => element('li', '', value)));
    panel.hidden = !warnings.length;
  };

  const renderCandidateDisclosure = data => {
    const section = root.querySelector('[data-candidate-disclosure]');
    const disclosure = data.candidate_disclosure;
    const sources = data.source_matches || [];
    section.hidden = !disclosure && !sources.length;
    if (!disclosure && !sources.length) return;
    section.open = data.execution_outcome === 'source_lookup_complete';
    const candidates = disclosure?.candidates || [];
    const countCopy = disclosure?.truncated
      ? `· 显示 ${candidates.length} 条，另有候选未展开`
      : `· ${sources.length + candidates.length} 条`;
    root.querySelector('[data-candidate-count]').textContent = countCopy;
    const list = root.querySelector('[data-candidate-list]');
    const empty = root.querySelector('[data-candidate-empty]');
    list.replaceChildren();
    sources.forEach(source => {
      const article = element('article', 'candidate-card');
      article.append(element('p', 'candidate-kind', '相关视频来源 · 导航资料'));
      article.append(element('h3', '', source.title || `Video ${source.video_id}`));
      if (source.uploader) article.append(element('p', 'candidate-identity', `作者：${source.uploader}`));
      if (source.matched_excerpt) article.append(element('blockquote', '', source.matched_excerpt));
      if (source.url) {
        const link = element('a', '', '打开视频');
        link.href = source.url;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        article.append(link);
      }
      list.append(article);
    });
    candidates.forEach(candidate => {
      const article = element('article', 'candidate-card');
      const kind = candidate.candidate_kind === 'metadata_lead'
        ? '相关视频线索 · 无可用字幕，不能作为回答证据'
        : '字幕候选 · 未被采用为回答引用';
      article.append(element('p', 'candidate-kind', kind));
      article.append(element('h3', '', candidate.title || `Video ${candidate.video_id}`));
      const identityCopy = candidate.identity_status === 'stale'
        ? '历史字幕身份已过期；未用当前其他字幕替代。'
        : candidate.identity_status === 'unavailable'
          ? '历史视频身份当前不可用；未替换为其他视频。'
          : `当前视频状态：${candidate.video_status}`;
      article.append(element('p', 'candidate-identity', identityCopy));
      article.append(element('p', 'candidate-origin', `检索：${candidate.search_query || '（未记录）'} · 排名 ${candidate.search_rank}`));
      if (candidate.excerpt) article.append(element('blockquote', '', candidate.excerpt));
      const actions = element('div', 'candidate-actions');
      if (candidate.start_time !== null && candidate.start_time !== undefined) {
        actions.append(element('span', '', `${formatTime(candidate.start_time)}–${formatTime(candidate.end_time)}`));
      }
      if (candidate.jump_url) {
        const link = element('a', '', candidate.candidate_kind === 'metadata_lead' ? '打开视频' : '从候选位置播放');
        link.href = candidate.jump_url;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        actions.append(link);
      } else if (candidate.detail_url) {
        const link = element('a', '', '查看当前视频记录');
        link.href = candidate.detail_url;
        actions.append(link);
      }
      if (actions.childNodes.length) article.append(actions);
      list.append(article);
    });
    const emptyMessages = {
      no_durable_search_lineage: '本次运行没有可用于重建的持久化检索链路。',
      search_presentations_unavailable: '检索链路存在，但候选呈现当前不可重建。',
      no_unadopted_candidates: '没有未被回答采用的可重建候选。',
      candidate_reconstruction_failed: '候选重建暂时不可用；这不影响回答与引用。',
    };
    empty.textContent = emptyMessages[disclosure?.empty_reason] || '本次检索没有可展示的候选。';
    empty.hidden = candidates.length + sources.length !== 0;
  };

  const renderResult = data => {
    lastResponse = data;
    const researchParams = new URLSearchParams({objective: lastRequest?.q || queryInput.value.trim()});
    root.querySelector('[data-ask-research]').href = `/research?${researchParams}`;
    root.querySelector('[data-result-title]').textContent = `${modeLabels[data.mode] || '回答'}结果`;
    const badge = root.querySelector('[data-status-badge]');
    const badgeState = data.execution_outcome === 'generation_failed'
      ? 'generation-failed'
      : data.status;
    const hasFinalAnswer = data.execution_outcome === 'answer_generated'
      && (data.answer_blocks || []).length > 0;
    badge.className = `status-badge status-${badgeState}`;
    badge.textContent = outcomeLabels[data.execution_outcome] || statusLabels[data.status] || data.status;
    root.querySelector('[data-termination-copy]').textContent = data.execution_outcome === 'evidence_insufficient'
      ? '未找到足够证据'
      : hasFinalAnswer
        ? terminationLabels.answer_ready
        : terminationLabels[data.termination_reason] || data.termination_reason;
    renderAnswerBlocks(data);
    renderLimitations(data);
    renderCandidateDisclosure(data);
    renderEvidence(data);
    renderUserTrace(data);
    if (data.execution_outcome === 'evidence_insufficient') {
      resetPreview();
    } else if (hasFinalAnswer) {
      root.querySelector('[data-evidence-preview]').hidden = true;
    } else if (seenPreviewCitationIds.size) {
      updatePreviewStatus(
        data.execution_outcome === 'generation_failed' ? 'failed' : 'final',
      );
    }
    root.querySelector('[data-continue-deep]').hidden = !(
      data.mode === 'fast'
      && data.execution_outcome !== 'generation_failed'
      && ['partial', 'insufficient'].includes(data.status)
    );
    resetDeveloperTrace(data.run_id);
    showState('result');
    window.__shiliuLastAsk = {
      runId: data.run_id,
      mode: data.mode,
      status: data.status,
      executionOutcome: data.execution_outcome,
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
    if (seenPreviewCitationIds.size) updatePreviewStatus('failed');
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
    lastRequest = state;
    submitButton.disabled = true;
    submitButton.textContent = state.mode === 'deep' ? '深入搜索中' : '回答中';
    root.querySelector('[data-loading-title]').textContent = state.mode === 'deep'
      ? '正在导航视频并逐步查找字幕证据，可能需要几分钟……'
      : '正在检索字幕并生成有依据的回答……';
    root.querySelector('[data-lifecycle-status]').textContent = '正在创建持久运行记录…';
    resetPreview();
    showState('loading');
    try {
      const data = state.mode === 'fast'
        ? await executeFastStream(requestPayload(state), controller.signal)
        : await executeDeepRun(requestPayload(state), controller.signal);
      if (sequence !== requestSequence) return;
      renderResult(data);
    } catch (error) {
      if (error.name !== 'AbortError' && sequence === requestSequence) showError(error.status || 0, error.data || {});
    } finally {
      if (sequence === requestSequence) {
        submitButton.disabled = false;
        submitButton.textContent = '开始回答';
      }
    }
  };

  const responseError = async response => {
    const error = new Error(`request failed: ${response.status}`);
    error.status = response.status;
    error.data = await response.json().catch(() => ({}));
    return error;
  };

  const terminalResult = async (runId, signal) => {
    const response = await fetch(`/api/ask/runs/${encodeURIComponent(runId)}`, {signal});
    if (!response.ok) throw await responseError(response);
    const data = await response.json();
    if (!data.result) {
      const error = new Error(data.run?.error?.message || '运行没有可显示的可信结果');
      error.data = {error: data.run?.error || {}};
      throw error;
    }
    return data.result;
  };

  const executeTerminalCompatibility = async (payload, signal) => {
    const response = await fetch('/api/ask', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload), signal,
    });
    if (!response.ok) throw await responseError(response);
    return response.json();
  };

  const executeFastStream = async (payload, signal) => {
    if (!globalThis.ReadableStream) return executeTerminalCompatibility(payload, signal);
    const response = await fetch('/api/ask/stream', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload), signal,
    });
    if (!response.ok) throw await responseError(response);
    const runId = response.headers.get('X-Shiliu-Run-ID');
    if (!runId || !response.body) throw new Error('流式运行缺少持久身份');
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const {value, done} = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), {stream: !done});
      const chunks = buffer.split('\n');
      buffer = done ? '' : chunks.pop();
      chunks.filter(Boolean).forEach(line => showLifecycle(JSON.parse(line)));
      if (done) break;
    }
    if (buffer.trim()) showLifecycle(JSON.parse(buffer));
    return terminalResult(runId, signal);
  };

  const executeDeepRun = async (payload, signal) => {
    const created = await fetch('/api/ask/runs', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload), signal,
    });
    if (!created.ok) throw await responseError(created);
    const identity = await created.json();
    let cursor = 0;
    while (true) {
      const response = await fetch(`${identity.events_href}?after_sequence=${cursor}`, {signal});
      if (!response.ok) throw await responseError(response);
      const data = await response.json();
      (data.events || []).forEach(event => {
        cursor = Math.max(cursor, Number(event.sequence) || 0);
        showLifecycle(event);
      });
      if (data.result) return data.result;
      if (data.run?.lifecycle_status === 'failed') {
        const error = new Error(data.run.error?.message || '深入搜索运行失败');
        error.data = {error: data.run.error || {}};
        throw error;
      }
      await new Promise((resolve, reject) => {
        const timer = window.setTimeout(resolve, 500);
        signal.addEventListener('abort', () => {
          window.clearTimeout(timer);
          reject(new DOMException('Aborted', 'AbortError'));
        }, {once: true});
      });
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
    if (shouldSubmitOnEnter(event)) {
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
  root.querySelector('[data-save-knowledge-draft]').addEventListener('click', async event => {
    if (!lastResponse?.run_id) return;
    const button = event.currentTarget;
    const status = root.querySelector('[data-draft-status]');
    button.disabled = true;
    status.textContent = '正在保存草稿…';
    try {
      const response = await fetch('/api/knowledge/drafts', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({source_kind: 'ask_run', source_id: lastResponse.run_id, command_id: `ask-draft:${crypto.randomUUID()}`}),
      });
      const data = await response.json();
      if (!response.ok || data.ok === false) throw new Error(data.error?.message || '草稿保存失败');
      status.textContent = `草稿已保存（版本 ${data.draft.version}），可到知识草稿继续整理。`;
      button.textContent = '草稿已保存';
    } catch (error) {
      status.textContent = error.message;
      button.disabled = false;
    }
  });
  window.addEventListener('popstate', () => {
    activeController?.abort();
    requestSequence += 1;
    submitButton.disabled = false;
    submitButton.textContent = '开始回答';
    restoreForm();
    resetPreview();
    showState('idle');
  });

  restoreForm();
  showState('idle');
  window.__shiliuAsk = {
    execute: executeAsk,
    formState,
    renderResult,
    resetPreview,
    showError,
    showLifecycle,
    showState,
    shouldSubmitOnEnter,
  };
})();
