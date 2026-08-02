(() => {
  const root = document.querySelector('[data-research-page]');
  const evidenceUI = window.ShiliuEvidenceUI;
  if (!root || !evidenceUI) return;

  const {element, renderEvidenceCard} = evidenceUI;
  const createForm = root.querySelector('[data-research-create]');
  const taskList = root.querySelector('[data-task-list]');
  const workspace = root.querySelector('[data-task-workspace]');
  const emptyWorkspace = root.querySelector('[data-empty-workspace]');
  const taskContent = root.querySelector('[data-task-content]');
  const taskLoading = root.querySelector('[data-task-loading]');
  const taskError = root.querySelector('[data-task-error]');
  let activeTaskId = root.dataset.initialTaskId || '';
  let current = null;
  let pollTimer = null;

  const commandId = prefix => {
    const identity = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    return `product:${prefix}:${identity}`;
  };
  const lines = value => value.split('\n').map(item => item.trim()).filter(Boolean);
  const errorMessage = data => data?.error?.message || data?.detail || '请求失败，请刷新持久状态后重试。';

  const requestJson = async (url, options = {}) => {
    const response = await fetch(url, {
      ...options,
      headers: {'Content-Type': 'application/json', ...(options.headers || {})},
    });
    const data = await response.json();
    if (!response.ok || data.ok === false) throw new Error(errorMessage(data));
    return data;
  };

  const showTaskState = name => {
    taskLoading.hidden = name !== 'loading';
    taskError.hidden = name !== 'error';
    taskContent.hidden = name !== 'content';
  };

  const setActiveTask = taskId => {
    activeTaskId = taskId;
    history.pushState({}, '', `/research/${encodeURIComponent(taskId)}`);
    workspace.hidden = false;
    emptyWorkspace.hidden = true;
    loadTask();
    loadList();
  };

  const loadList = async () => {
    try {
      const data = await requestJson('/api/research/product/tasks?limit=30');
      taskList.replaceChildren();
      if (!data.tasks.length) {
        taskList.append(element('p', 'muted', '还没有 Research Task。'));
        return;
      }
      data.tasks.forEach(task => {
        const button = element('button', `research-task-card${task.task_id === activeTaskId ? ' is-active' : ''}`);
        button.type = 'button';
        button.append(
          element('span', 'task-card-state', task.status_label),
          element('strong', '', task.objective),
          element('span', '', `${task.task_id} · ${task.updated_at}`),
        );
        button.addEventListener('click', () => setActiveTask(task.task_id));
        taskList.append(button);
      });
    } catch (error) {
      taskList.replaceChildren(element('p', 'research-error', error.message));
    }
  };

  const renderAnswer = product => {
    const section = root.querySelector('[data-answer-section]');
    const container = root.querySelector('[data-answer-blocks]');
    container.replaceChildren();
    const numbering = new Map(product.citations.map((item, index) => [item.citation_id, index + 1]));
    (product.answer_blocks || []).forEach(block => {
      const card = element('article', 'research-answer-block');
      card.append(element('span', '', block.text));
      (block.citation_ids || []).forEach(id => {
        const number = numbering.get(id);
        if (!number) return;
        const marker = element('button', 'research-citation-button', `[${number}]`);
        marker.type = 'button';
        marker.addEventListener('click', () => document.getElementById(`research-citation-${number}`)?.scrollIntoView({behavior: 'smooth'}));
        card.append(marker);
      });
      container.append(card);
    });
    section.hidden = !product.answer_blocks.length && !product.limitations.length;
    const limitations = root.querySelector('[data-limitations]');
    limitations.hidden = !product.limitations.length;
    const list = limitations.querySelector('ul');
    list.replaceChildren(...product.limitations.map(value => element('li', '', value)));
  };

  const renderEvidence = product => {
    const section = root.querySelector('[data-evidence-section]');
    const list = root.querySelector('[data-evidence-list]');
    list.replaceChildren();
    product.citations.forEach((citation, index) => {
      const current = citation.currentness === 'current';
      const wrapper = element('div', `research-evidence-card${current ? '' : ' is-stale'}`);
      wrapper.append(element('span', `research-currentness${current ? '' : ' is-stale'}`, citation.currentness));
      wrapper.append(renderEvidenceCard({
        id: `research-citation-${index + 1}`,
        evidenceId: citation.citation_id,
        videoId: citation.video_id,
        eyebrow: `证据 [${index + 1}] · ${citation.source_type}`,
        title: citation.title,
        startTime: citation.start_time,
        endTime: citation.end_time,
        quote: citation.quote_text,
        sourceType: citation.source_type,
        jumpUrl: citation.jump_url,
        metadata: [
          ['Evidence ID', citation.citation_id],
          ['Evidence Use', citation.evidence_use_id],
          ['Source Version', citation.source_version],
          ['Attempt', citation.attempt_id],
        ],
      }));
      list.append(wrapper);
    });
    root.querySelector('[data-evidence-count]').textContent = `${product.citations.length} 条`;
    section.hidden = !product.citations.length;
  };

  const renderDeltas = product => {
    const grid = root.querySelector('[data-delta-grid]');
    grid.replaceChildren();
    const snapshot = product.candidate_deltas;
    if (!snapshot) {
      grid.append(element('p', 'muted', '任务尚未到达需要形成 Candidate Delta 的持久边界。'));
      return;
    }
    snapshot.deltas.forEach(delta => {
      const card = element('article', 'research-delta-card');
      card.append(element('span', 'research-delta-status', 'CANDIDATE ONLY'), element('h4', '', delta.delta_kind));
      if (!delta.items.length) {
        card.append(element('p', '', `空候选：${delta.empty_reason}`));
      } else {
        const list = element('ul');
        delta.items.forEach(item => list.append(element('li', '', item.summary || item.reason_code || JSON.stringify(item))));
        card.append(list);
      }
      card.append(element('p', '', `hash · ${delta.candidate_hash.slice(0, 16)}…`));
      grid.append(card);
    });
  };

  const renderTrace = product => {
    const trace = product.trace;
    const list = root.querySelector('[data-trace-timeline]');
    list.replaceChildren();
    trace.timeline.slice().reverse().forEach(item => {
      const row = element('li');
      const body = element('div');
      body.append(element('strong', '', item.summary));
      const details = Object.keys(item.details).length ? ` · ${JSON.stringify(item.details)}` : '';
      body.append(element('small', '', `${item.created_at}${details}`));
      row.append(element('span', 'trace-sequence', `#${item.sequence}`), body);
      list.append(row);
    });
    root.querySelector('[data-trace-counts]').textContent = `${trace.counts.events} events · ${trace.counts.receipts} receipts`;
    root.querySelector('[data-advanced-trace]').textContent = JSON.stringify({
      checkpoints: trace.checkpoints,
      actions: trace.actions,
      audits: trace.audits,
      receipts: trace.receipts,
      controls: trace.controls,
    }, null, 2);
  };

  const executeControl = async kind => {
    const context = current.control.action_context;
    if (kind === 'cancel' && !window.confirm('取消会形成持久终态；未知外部副作用会进入 cancel-pending。继续吗？')) return;
    const status = root.querySelector('[data-control-status]');
    status.textContent = '正在提交持久控制命令…';
    try {
      await requestJson(`/api/research/tasks/${encodeURIComponent(activeTaskId)}/control`, {
        method: 'POST',
        body: JSON.stringify({
          command_id: commandId(kind),
          kind,
          expected_state_version: context.expected_state_version,
          expected_checkpoint_id: context.expected_checkpoint_id,
          expected_control_generation: context.expected_control_generation,
          reason: `product ${kind}`,
        }),
      });
      status.textContent = '已提交；正在读取新的持久状态。';
      await loadTask();
    } catch (error) {
      status.textContent = `${error.message} 请刷新后重试。`;
    }
  };

  const runTask = async () => {
    const status = root.querySelector('[data-control-status]');
    status.textContent = '已请求本地无 Provider runner…';
    try {
      await requestJson(`/api/research/product/tasks/${encodeURIComponent(activeTaskId)}/run`, {
        method: 'POST', body: JSON.stringify({command_id: commandId('run')}),
      });
      await loadTask();
    } catch (error) { status.textContent = error.message; }
  };

  const deriveTask = async kind => {
    const context = current.control.action_context;
    if (!context.expected_checkpoint_id) return;
    try {
      const data = await requestJson(`/api/research/tasks/${encodeURIComponent(activeTaskId)}/derivations`, {
        method: 'POST',
        body: JSON.stringify({
          command_id: commandId(kind), kind,
          source_checkpoint_id: context.expected_checkpoint_id,
        }),
      });
      setActiveTask(data.outcome.task_id);
    } catch (error) { root.querySelector('[data-control-status]').textContent = error.message; }
  };

  const retryTask = async () => {
    try {
      const data = await requestJson(`/api/research/tasks/${encodeURIComponent(activeTaskId)}/commands`, {
        method: 'POST',
        body: JSON.stringify({
          command_id: commandId('retry'), kind: 'retry',
          objective: current.goal.objective,
          success_constraints: current.goal.success_constraints,
          evidence_policy: {authority: 'live_current_exact_replay'},
        }),
      });
      setActiveTask(data.outcome.task_id);
    } catch (error) { root.querySelector('[data-control-status]').textContent = error.message; }
  };

  const resolveEffect = async effect => {
    if (!effect || effect.status !== 'unknown') return;
    const confirmed = window.confirm(
      `确认将 SideEffect ${effect.side_effect_id}（${effect.effect_kind}）记录为失败吗？此决定不可撤销。`,
    );
    if (!confirmed) return;
    const context = current.control.action_context;
    try {
      await requestJson(`/api/research/tasks/${encodeURIComponent(activeTaskId)}/side-effects/resolve`, {
        method: 'POST',
        body: JSON.stringify({
          command_id: commandId('resolve'), side_effect_id: effect.side_effect_id,
          expected_state_version: context.expected_state_version,
          expected_control_generation: context.expected_control_generation,
          resolution: 'confirmed_failed',
          reason: 'product operator confirmed external action failed',
        }),
      });
      await loadTask();
    } catch (error) { root.querySelector('[data-control-status]').textContent = error.message; }
  };

  const renderControls = product => {
    const container = root.querySelector('[data-control-buttons]');
    container.replaceChildren();
    const labels = {run: '继续安全运行', interrupt: '中断', resume: '恢复', cancel: '取消', derive: '派生', retry: '创建重试 Task'};
    product.control.allowed_operations.forEach(operation => {
      if (operation === 'derive') {
        ['branch', 'replay'].forEach(kind => {
          const button = element('button', 'ghost', kind === 'branch' ? '创建 Branch' : '创建 Replay');
          button.type = 'button';
          button.addEventListener('click', () => deriveTask(kind));
          container.append(button);
        });
        return;
      }
      const button = element('button', operation === 'cancel' ? 'ghost is-destructive' : 'ghost', labels[operation] || operation);
      button.type = 'button';
      button.addEventListener('click', () => operation === 'run' ? runTask() : operation === 'retry' ? retryTask() : executeControl(operation));
      container.append(button);
    });
    if (!container.children.length) container.append(element('p', 'muted', '当前没有可安全执行的操作。'));
  };

  const renderEffects = product => {
    const panel = root.querySelector('[data-effect-panel]');
    const list = root.querySelector('[data-effect-list]');
    const effects = product.control.unresolved_side_effects;
    panel.hidden = !effects.length;
    list.replaceChildren();
    effects.forEach(effect => {
      const card = element('article', 'research-effect-card');
      card.dataset.sideEffectId = effect.side_effect_id;
      card.append(
        element('strong', '', effect.effect_kind),
        element('code', '', effect.side_effect_id),
        element('span', 'research-currentness is-stale', `状态 · ${effect.status}`),
      );
      if (effect.status === 'unknown') {
        const button = element('button', 'ghost is-destructive', '确认该外部动作失败');
        button.type = 'button';
        button.addEventListener('click', () => resolveEffect(effect));
        card.append(button);
      } else {
        card.append(element('p', 'muted', '该状态尚不能人工解析，请等待受 fence 保护的恢复流程。'));
      }
      list.append(card);
    });
  };

  const renderInput = product => {
    const panel = root.querySelector('[data-input-panel]');
    const input = product.control.open_input_requests[0];
    panel.hidden = !input;
    if (!input) return;
    panel.querySelector('[data-input-prompt]').textContent = input.prompt;
    panel.querySelector('[name=objective]').value = product.goal.objective;
    panel.querySelector('[name=constraints]').value = product.goal.success_constraints.join('\n');
  };

  const renderTask = product => {
    current = product;
    root.querySelector('[data-task-objective]').textContent = product.goal.objective;
    root.querySelector('[data-task-id]').textContent = `${product.task.task_id} · Goal revision ${product.goal.revision}`;
    root.querySelector('[data-task-status]').textContent = product.task.status_label;
    root.querySelector('[data-task-phase]').textContent = product.state.phase || 'pending';
    root.querySelector('[data-answer-status]').textContent = product.state.answer_status;
    root.querySelector('[data-termination-reason]').textContent = product.state.termination_reason || '尚未停止';
    root.querySelector('[data-failure-class]').textContent = product.state.failure_class;
    root.querySelector('[data-task-reason]').textContent = product.state.reason_detail || product.state.stop_reason || product.state.blocker || product.state.termination_label;
    renderControls(product);
    renderEffects(product);
    renderInput(product);
    renderAnswer(product);
    renderEvidence(product);
    renderDeltas(product);
    renderTrace(product);
    showTaskState('content');
    if (pollTimer !== null) window.clearTimeout(pollTimer);
    // A background run can still be claiming a freshly created READY task when
    // the first projection arrives. Keep observing both transitory states so
    // the page reaches the next durable boundary without a manual refresh.
    if (['ready', 'running'].includes(product.task.status)) {
      pollTimer = window.setTimeout(loadTask, 1800);
    }
  };

  async function loadTask() {
    if (!activeTaskId) return;
    workspace.hidden = false;
    emptyWorkspace.hidden = true;
    showTaskState('loading');
    try {
      const data = await requestJson(`/api/research/product/tasks/${encodeURIComponent(activeTaskId)}`);
      renderTask(data.product);
      loadList();
    } catch (error) {
      taskError.textContent = error.message;
      showTaskState('error');
    }
  }

  createForm.addEventListener('submit', async event => {
    event.preventDefault();
    const objective = createForm.elements.objective.value.trim();
    const status = root.querySelector('[data-create-status]');
    if (!objective) { status.textContent = '请填写研究目标。'; return; }
    status.textContent = '正在先创建持久 Task…';
    root.querySelector('[data-create-submit]').disabled = true;
    try {
      const data = await requestJson('/api/research/product/tasks', {
        method: 'POST',
        body: JSON.stringify({
          command_id: commandId('create'), objective,
          success_constraints: lines(createForm.elements.constraints.value),
          run_immediately: true,
        }),
      });
      status.textContent = 'Task 已持久创建；本地 runner 正在推进。';
      createForm.reset();
      setActiveTask(data.outcome.task_id);
    } catch (error) { status.textContent = error.message; }
    finally { root.querySelector('[data-create-submit]').disabled = false; }
  });

  root.querySelector('[data-input-form]').addEventListener('submit', async event => {
    event.preventDefault();
    const input = current.control.open_input_requests[0];
    if (!input) return;
    const context = current.control.action_context;
    const form = event.currentTarget;
    try {
      await requestJson(`/api/research/tasks/${encodeURIComponent(activeTaskId)}/inputs/decisions`, {
        method: 'POST',
        body: JSON.stringify({
          command_id: commandId('input'), input_request_id: input.input_request_id,
          expected_state_version: context.expected_state_version,
          expected_control_generation: context.expected_control_generation,
          decision_kind: 'clarify_goal',
          response: {
            objective: form.elements.objective.value.trim(),
            success_constraints: lines(form.elements.constraints.value),
            evidence_policy: {authority: 'live_current_exact_replay'},
          },
        }),
      });
      await loadTask();
    } catch (error) { root.querySelector('[data-control-status]').textContent = error.message; }
  });

  root.querySelector('[data-refresh-list]').addEventListener('click', loadList);
  window.addEventListener('popstate', () => {
    const match = location.pathname.match(/^\/research\/([^/]+)$/);
    activeTaskId = match ? decodeURIComponent(match[1]) : '';
    if (activeTaskId) loadTask();
  });

  loadList();
  if (activeTaskId) {
    workspace.hidden = false;
    emptyWorkspace.hidden = true;
    loadTask();
  }
})();
