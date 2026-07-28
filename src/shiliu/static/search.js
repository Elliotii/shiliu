(() => {
  const root = document.querySelector('[data-search-page]');
  if (!root) return;

  const form = root.querySelector('[data-search-form]');
  const queryInput = form.elements.q;
  const submitButton = root.querySelector('[data-search-submit]');
  const states = {
    idle: root.querySelector('[data-idle-state]'),
    loading: root.querySelector('[data-loading-state]'),
    empty: root.querySelector('[data-empty-state]'),
    error: root.querySelector('[data-error-state]'),
    success: root.querySelector('[data-success-state]'),
  };
  const fallbackNotice = root.querySelector('[data-fallback-state]');
  const resultList = root.querySelector('[data-result-list]');
  const modeHelp = root.querySelector('[data-mode-help]');
  let activeController = null;
  let requestSequence = 0;

  const modeLabels = {lexical: '关键词搜索', auto: '自动搜索', dense: '语义搜索', hybrid: '混合搜索'};
  const modeHelpText = {
    lexical: '适合明确工具、项目或术语',
    auto: '系统根据查询形式选择方式',
    dense: '适合自然语言问题',
    hybrid: '结合关键词和语义结果',
  };
  const readingLabels = {unread: '未阅', in_progress: '正在阅读', read: '已阅'};
  const sourceLabels = {human: '人工字幕', ai: 'AI 字幕', asr: 'ASR 转录'};
  const preciseSources = new Set(['exact_query_phrase', 'exact_entity_term', 'keyword_overlap']);

  const element = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  };

  const showState = name => {
    Object.entries(states).forEach(([key, node]) => { node.hidden = key !== name; });
    if (name !== 'success') resultList.replaceChildren();
  };

  const formatTime = value => {
    const seconds = Math.max(0, Math.floor(Number(value) || 0));
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const rest = seconds % 60;
    return hours ? `${hours}:${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}` : `${minutes}:${String(rest).padStart(2, '0')}`;
  };

  const formatDuration = value => {
    const seconds = Math.max(0, Math.round(Number(value) || 0));
    const minutes = Math.floor(seconds / 60);
    const rest = seconds % 60;
    if (!minutes) return `${rest}秒`;
    return rest ? `${minutes}分${rest}秒` : `${minutes}分钟`;
  };

  const dateEpoch = (value, endOfDay = false) => {
    if (!value) return null;
    const suffix = endOfDay ? 'T23:59:59' : 'T00:00:00';
    const parsed = new Date(`${value}${suffix}`);
    return Number.isNaN(parsed.getTime()) ? null : Math.floor(parsed.getTime() / 1000);
  };

  const formState = () => ({
    q: queryInput.value.trim(),
    mode: form.elements.mode.value || 'auto',
    scope: form.elements.scope.value || 'all',
    folder_id: form.elements.folder_id.value,
    reading_state: form.elements.reading_state.value,
    marked: form.elements.marked.value,
    uploader_contains: form.elements.uploader_contains.value.trim(),
    favorite_time_from: form.elements.favorite_time_from.value,
    favorite_time_to: form.elements.favorite_time_to.value,
    archived: form.elements.archived.checked,
    ignored: form.elements.ignored.checked,
    sufficiency: form.elements.sufficiency.checked,
  });

  const restoreForm = () => {
    const params = new URLSearchParams(location.search);
    queryInput.value = params.get('q') || '';
    form.elements.mode.value = ['lexical', 'auto', 'dense', 'hybrid'].includes(params.get('mode')) ? params.get('mode') : 'auto';
    form.elements.scope.value = ['all', 'video', 'transcript_chunk'].includes(params.get('scope')) ? params.get('scope') : 'all';
    for (const name of ['folder_id', 'reading_state', 'marked', 'uploader_contains', 'favorite_time_from', 'favorite_time_to']) {
      form.elements[name].value = params.get(name) || '';
    }
    form.elements.archived.checked = params.get('archived') === 'true';
    form.elements.ignored.checked = params.get('ignored') === 'true';
    form.elements.sufficiency.checked = params.get('sufficiency') === 'true';
    updateModeHelp();
  };

  const updateUrl = (state, replace = false) => {
    const params = new URLSearchParams();
    if (state.q) params.set('q', state.q);
    if (state.mode !== 'auto') params.set('mode', state.mode);
    if (state.scope !== 'all') params.set('scope', state.scope);
    for (const name of ['folder_id', 'reading_state', 'marked', 'uploader_contains', 'favorite_time_from', 'favorite_time_to']) {
      if (state[name]) params.set(name, state[name]);
    }
    if (state.archived) params.set('archived', 'true');
    if (state.ignored) params.set('ignored', 'true');
    if (state.sufficiency) params.set('sufficiency', 'true');
    const url = `${location.pathname}${params.size ? `?${params}` : ''}`;
    history[replace ? 'replaceState' : 'pushState']({}, '', url);
  };

  const requestPayload = state => {
    const filters = {archived: Boolean(state.archived), ignored: Boolean(state.ignored)};
    if (state.folder_id) filters.folder_id = Number(state.folder_id);
    if (state.reading_state) filters.reading_state = state.reading_state;
    if (state.marked) filters.marked = state.marked === 'true';
    if (state.uploader_contains) filters.uploader_contains = state.uploader_contains;
    const from = dateEpoch(state.favorite_time_from);
    const to = dateEpoch(state.favorite_time_to, true);
    if (from !== null) filters.favorite_time_from = from;
    if (to !== null) filters.favorite_time_to = to;
    return {query: state.q, mode: state.mode, scope: state.scope, result_limit: 10, max_windows_per_video: 5, filters};
  };

  const appendMeta = (container, text, className = '') => container.append(element('span', className, text));

  const renderWindow = (windowValue, id) => {
    const section = element('section', 'evidence-window');
    section.id = id;
    const heading = element('div', 'window-heading');
    heading.append(element('strong', '', `相关片段 ${formatTime(windowValue.window_start)}–${formatTime(windowValue.window_end)}`));
    heading.append(element('span', 'window-duration', `持续 ${formatDuration(windowValue.duration)}`));
    section.append(heading);
    if (windowValue.chapter) {
      section.append(element('p', 'chapter-label', `AI 章节：${windowValue.chapter.title || '未命名章节'}`));
      if (windowValue.chapter.summary) section.append(element('p', 'chapter-summary', windowValue.chapter.summary));
    }
    section.append(element('p', 'window-excerpt', windowValue.excerpt || '该时间段暂无可显示的字幕摘录。'));
    const footer = element('div', 'window-footer');
    const tags = element('div', 'subtitle-tags');
    (windowValue.subtitle_sources || []).forEach(source => tags.append(element('span', 'subtitle-tag', sourceLabels[source] || '字幕')));
    footer.append(tags);
    if (windowValue.jump_url) {
      const precise = preciseSources.has(windowValue.jump_source);
      const label = precise ? `从 ${formatTime(windowValue.jump_time)} 播放` : `从相关片段 ${formatTime(windowValue.jump_time)} 开始`;
      const link = element('a', 'jump-link', label);
      link.href = windowValue.jump_url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.dataset.jumpSource = precise ? 'precise' : 'fallback';
      footer.append(link);
    }
    section.append(footer);
    return section;
  };

  const renderResult = (result, index, warningVideoIds) => {
    const card = element('article', 'search-result-card');
    card.dataset.videoId = result.video_id;
    card.dataset.resultIndex = index;
    const cover = element('div', 'result-cover');
    const fallback = element('div', 'cover-fallback', 'NO COVER');
    cover.append(fallback);
    if (result.cover_url) {
      const image = element('img');
      image.alt = `${result.title} 的封面`;
      image.loading = 'lazy';
      image.src = result.cover_url;
      image.addEventListener('load', () => {
        fallback.hidden = true;
        cover.classList.toggle(
          'is-portrait-cover',
          image.naturalHeight > image.naturalWidth * 1.08,
        );
      }, {once: true});
      image.addEventListener('error', () => { image.hidden = true; fallback.hidden = false; }, {once: true});
      cover.prepend(image);
    }
    card.append(cover);
    const body = element('div', 'result-body');
    body.append(element('h2', 'result-title', result.title || '未命名视频'));
    body.append(element('p', 'result-uploader', result.uploader || '未知 UP 主'));
    const meta = element('div', 'result-meta');
    appendMeta(meta, readingLabels[result.reading_state] || result.reading_state || '未阅');
    (result.folder_names || []).forEach(folder => appendMeta(meta, folder));
    if (result.marked) appendMeta(meta, '已 Mark', 'marked-tag');
    if (result.duration) appendMeta(meta, `时长 ${formatTime(result.duration)}`);
    body.append(meta);
    const summary = result.windows?.length
      ? `命中 ${result.matched_unit_count} 处内容 · ${result.total_window_count} 个相关时间段`
      : '视频概览与查询相关';
    body.append(element('p', 'match-summary', summary));
    if (result.windows?.length) {
      body.append(renderWindow(result.windows[0], `video-${result.video_id}-window-0`));
      if (result.windows.length > 1) {
        const extraId = `video-${result.video_id}-additional-windows`;
        const toggle = element('button', 'additional-toggle', `另外 ${result.windows.length - 1} 处相关内容`);
        toggle.type = 'button';
        toggle.setAttribute('aria-expanded', 'false');
        toggle.setAttribute('aria-controls', extraId);
        const extra = element('div', 'additional-windows');
        extra.id = extraId;
        extra.hidden = true;
        result.windows.slice(1).forEach((windowValue, windowIndex) => extra.append(renderWindow(windowValue, `video-${result.video_id}-window-${windowIndex + 1}`)));
        toggle.addEventListener('click', () => {
          const expanded = toggle.getAttribute('aria-expanded') === 'true';
          toggle.setAttribute('aria-expanded', String(!expanded));
          toggle.textContent = expanded ? `另外 ${result.windows.length - 1} 处相关内容` : '收起其他相关内容';
          extra.hidden = expanded;
        });
        body.append(toggle, extra);
      }
      if (result.additional_window_count > 0) body.append(element('p', 'unshown-windows', `另有 ${result.additional_window_count} 处相关片段未展示`));
    } else if (result.match_excerpt) {
      body.append(element('p', 'video-match-excerpt', result.match_excerpt));
    }
    if (warningVideoIds.has(Number(result.video_id))) body.append(element('p', 'partial-warning', '未能读取完整字幕定位，已显示可用结果。'));
    const actions = element('div', 'result-actions');
    const detail = element('a', 'detail-link', '查看拾流详情');
    detail.href = result.detail_url;
    actions.append(detail);
    body.append(actions);
    card.append(body);
    return card;
  };

  const renderSuccess = data => {
    if (data.pipeline_contract_version) {
      renderPipeline(data);
      return;
    }
    root.querySelector('[data-pipeline-summary]').hidden = true;
    root.querySelector('[data-integration-limitations]').hidden = true;
    fallbackNotice.hidden = !data.fallback;
    const count = Number(data.returned_group_count ?? data.results?.length ?? 0);
    root.querySelector('[data-result-summary]').textContent = `找到 ${count} 个相关视频`;
    root.querySelector('[data-mode-summary]').textContent = modeLabels[data.executed_mode] || '搜索结果';
    const warningVideoIds = new Set((data.warnings || []).map(item => Number(item.video_id)).filter(Number.isFinite));
    resultList.replaceChildren(...(data.results || []).map((result, index) => renderResult(result, index, warningVideoIds)));
    showState(count ? 'success' : 'empty');
  };

  const listBlock = (title, values) => {
    const block = element('div', 'decision-list');
    block.append(element('strong', '', title));
    const list = element('ul');
    (values?.length ? values : ['无']).forEach(value => list.append(element('li', '', value)));
    block.append(list);
    return block;
  };

  const renderFormalEvidence = evidence => {
    const card = element('article', 'formal-evidence-card');
    card.dataset.evidenceId = evidence.evidence_id;
    const heading = element('div', 'formal-evidence-heading');
    heading.append(element('h3', '', evidence.title_or_available_video_metadata || `Video ${evidence.video_id}`));
    heading.append(element('span', 'evidence-range', `${formatTime(evidence.start_time)}–${formatTime(evidence.end_time)}`));
    card.append(heading, element('p', 'authoritative-quote', evidence.quote_text));
    const meta = element('dl', 'evidence-identity');
    [
      ['Evidence ID', evidence.evidence_id],
      ['Segment IDs', (evidence.segment_ids || []).join(', ')],
      ['Source', `${evidence.source_language || 'und'} · ${evidence.source_type || 'unknown'}`],
      ['Selector', evidence.selector_method],
    ].forEach(([term, value]) => {
      meta.append(element('dt', '', term), element('dd', '', value || '—'));
    });
    card.append(meta);
    return card;
  };

  const renderPipeline = data => {
    fallbackNotice.hidden = true;
    const summary = root.querySelector('[data-pipeline-summary]');
    summary.hidden = false;
    summary.replaceChildren();
    const status = element('div', 'pipeline-status-grid');
    const stages = data.trace?.stages || [];
    const currentStage = data.pipeline_status === 'completed'
      ? 'completed'
      : (stages.length ? stages[stages.length - 1].stage_name : 'failed');
    [
      ['Query', data.query],
      ['Status', data.pipeline_status],
      ['Current Stage', currentStage],
      ['Total Latency', `${Number(data.total_latency_ms || 0).toLocaleString()} ms`],
      ['Trace ID', data.trace_id],
    ].forEach(([term, value]) => {
      const item = element('div', 'pipeline-status-item');
      item.append(element('span', '', term), element('strong', '', value));
      status.append(item);
    });
    summary.append(status);

    const gate = data.mechanical_gate_result || {};
    const gateCard = element('section', 'decision-card mechanical-card');
    gateCard.append(element('p', 'decision-kicker', 'MECHANICAL GATE'));
    gateCard.append(element('h3', `decision-status status-${gate.status || 'unknown'}`, gate.status || '未执行'));
    gateCard.append(listBlock('Reason Codes', gate.reason_codes || []));
    summary.append(gateCard);

    const semantic = data.sufficiency_decision;
    const semanticCard = element('section', 'decision-card semantic-card');
    semanticCard.append(element('p', 'decision-kicker', 'SEMANTIC SUFFICIENCY'));
    if (semantic) {
      semanticCard.append(element('h3', `decision-status status-${semantic.status}`, semantic.status));
      semanticCard.append(
        listBlock('Supported Aspects', semantic.supported_aspects),
        listBlock('Missing Aspects', semantic.missing_aspects),
        listBlock('Conflicts', semantic.conflicts),
        listBlock('Reason Codes', semantic.reason_codes),
      );
      semanticCard.append(element('p', 'decision-meta', `Confidence ${semantic.confidence} · Policy ${semantic.policy_version}`));
      semanticCard.append(element('p', 'decision-meta evidence-ids-used', `Evidence IDs Used: ${(semantic.evidence_ids_used || []).join(', ') || '无'}`));
    } else {
      semanticCard.append(element('h3', 'decision-status status-bypassed', 'bypassed'));
      semanticCard.append(element('p', 'decision-meta', `Bypass Reason: ${data.semantic_sufficiency?.bypass_reason || 'mechanical terminal status'}`));
    }
    summary.append(semanticCard);

    if (data.errors?.length) {
      const errorCard = element('section', 'decision-card integration-error-card');
      errorCard.append(element('p', 'decision-kicker', 'INTEGRATION ERROR'));
      data.errors.forEach(error => {
        errorCard.append(element('h3', 'decision-status status-invalid', error.type || 'internal_integration_error'));
        errorCard.append(element('p', 'decision-meta', `${error.stage || 'integration'} · ${error.message || '未知错误'}`));
      });
      summary.append(errorCard);
    }

    const traceDetails = element('details', 'trace-details');
    traceDetails.append(element('summary', '', '查看 End-to-End Trace'));
    const traceList = element('ol', 'trace-stage-list');
    stages.forEach(stage => {
      traceList.append(element('li', '', `${stage.stage_name} · ${stage.component_version} · ${stage.status} · ${stage.latency_ms} ms · retry ${stage.retry_count}`));
    });
    traceDetails.append(traceList);
    summary.append(traceDetails);

    const evidence = data.evidence_bundle?.evidence || [];
    root.querySelector('[data-result-summary]').textContent = `正式 EvidenceBundle · ${evidence.length} 条证据`;
    root.querySelector('[data-mode-summary]').textContent = '证据充分性链路';
    resultList.replaceChildren(...evidence.map(renderFormalEvidence));
    root.querySelector('[data-integration-limitations]').hidden = false;
    showState('success');
  };

  const showError = (status, data) => {
    fallbackNotice.hidden = true;
    const error = data?.error || {};
    const code = typeof error === 'object' ? error.code : '';
    const title = root.querySelector('[data-error-title]');
    const message = root.querySelector('[data-error-message]');
    const lexical = root.querySelector('[data-error-lexical]');
    title.textContent = '搜索失败';
    lexical.hidden = ![409, 503].includes(status);
    if (status === 400 || status === 422) message.textContent = '请求内容无效，请检查搜索条件。';
    else if (status === 409 || code === 'dense_rebuild_required') message.textContent = '语义索引需要更新，暂时无法完成该搜索。';
    else if (status === 503) message.textContent = '语义搜索暂不可用。';
    else message.textContent = '搜索失败，请稍后重试。';
    const requestId = root.querySelector('[data-request-id]');
    const traceId = typeof error === 'object' ? error.trace_id : null;
    requestId.hidden = !traceId;
    requestId.textContent = traceId ? `请求编号：${traceId}` : '';
    showState('error');
  };

  const executeSearch = async ({push = true} = {}) => {
    const state = formState();
    if (!state.q) {
      fallbackNotice.hidden = true;
      showError(422, {});
      return;
    }
    queryInput.value = state.q;
    if (push) updateUrl(state);
    activeController?.abort();
    const controller = new AbortController();
    activeController = controller;
    const sequence = ++requestSequence;
    const started = performance.now();
    submitButton.disabled = true;
    submitButton.textContent = '搜索中';
    fallbackNotice.hidden = true;
    root.querySelector('[data-loading-title]').textContent = state.sufficiency ? '正在判断现有证据是否充分……' : '正在搜索……';
    root.querySelector('[data-loading-stage]').textContent = state.sufficiency
      ? 'Current Stage: retrieval → candidate builder → fine selector → gate → semantic judge'
      : 'Current Stage: retrieval';
    showState('loading');
    try {
      const response = await fetch(state.sufficiency ? '/api/evidence-sufficiency' : '/api/search', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(requestPayload(state)),
        signal: controller.signal,
      });
      const data = await response.json().catch(() => ({}));
      if (sequence !== requestSequence) return;
      if ((!response.ok || data.ok === false) && !data.pipeline_contract_version) showError(response.status, data);
      else renderSuccess(data);
      window.__shiliuLastSearch = {
        query: state.q,
        status: response.status,
        resultCount: Number(data.returned_group_count || 0),
        browserVisibleMs: Math.round(performance.now() - started),
        timing: data.timing || null,
      };
    } catch (error) {
      if (error.name !== 'AbortError' && sequence === requestSequence) showError(500, {});
    } finally {
      if (sequence === requestSequence) {
        submitButton.disabled = false;
        submitButton.textContent = '搜索';
      }
    }
  };

  const resetFilters = ({run = true} = {}) => {
    const query = queryInput.value;
    form.reset();
    queryInput.value = query;
    form.elements.mode.value = 'auto';
    form.elements.scope.value = 'all';
    updateModeHelp();
    if (run && query.trim()) executeSearch();
  };

  const useLexical = () => {
    form.elements.mode.value = 'lexical';
    updateModeHelp();
    executeSearch();
  };

  function updateModeHelp() {
    modeHelp.textContent = modeHelpText[form.elements.mode.value] || modeHelpText.lexical;
  }

  form.addEventListener('submit', event => { event.preventDefault(); executeSearch(); });
  queryInput.addEventListener('keydown', event => {
    if (event.key !== 'Enter') return;
    event.preventDefault();
    executeSearch();
  });
  form.elements.mode.addEventListener('change', updateModeHelp);
  root.querySelector('[data-clear-filters]').addEventListener('click', () => resetFilters());
  root.querySelector('[data-empty-clear]').addEventListener('click', () => resetFilters());
  root.querySelector('[data-empty-all]').addEventListener('click', () => { form.elements.scope.value = 'all'; executeSearch(); });
  root.querySelector('[data-use-lexical]').addEventListener('click', useLexical);
  root.querySelector('[data-error-lexical]').addEventListener('click', useLexical);
  root.querySelector('[data-retry-search]').addEventListener('click', () => executeSearch({push: false}));
  root.querySelectorAll('[data-example-query]').forEach(button => button.addEventListener('click', () => {
    queryInput.value = button.dataset.exampleQuery;
    executeSearch();
  }));
  window.addEventListener('popstate', () => {
    restoreForm();
    if (queryInput.value.trim()) executeSearch({push: false});
    else { fallbackNotice.hidden = true; showState('idle'); }
  });

  restoreForm();
  if (queryInput.value.trim()) executeSearch({push: false});
  else showState('idle');
})();
