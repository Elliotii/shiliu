(() => {
  // Append actual execution steps; keep parallel work within its shared step.
  window.ShiliuAskResearch = {create(root) {
    const panel = root.querySelector('[data-deep-research]');
    if (!panel) return {reset() {}, event() {}, answerStarted() {}, finish() {}, fail() {}};
    const title = panel.querySelector('[data-research-current]');
    const meta = panel.querySelector('[data-research-meta]');
    const list = panel.querySelector('[data-research-tasks]');
    const note = panel.querySelector('[data-research-note]');
    let state;
    const text = (node, value) => { if (node.textContent !== value) node.textContent = value; };
    const node = (tag, className, value) => {
      const result = document.createElement(tag); result.className = className;
      if (value !== undefined) result.textContent = value;
      return result;
    };
    const labels = {search_videos:'查找视频', search_transcripts:'检索字幕', read_context:'读取上下文'};
    const statuses = {queued:'等待开始', searching:'检索中', found:'已找到资料', reducing:'整理中',
      done:'已整理', cached:'已复用资料', empty:'未找到资料', unresolved:'未形成摘要',
      error:'未能完成', timeout:'超时', stale:'资料已过期'};
    const unsuccessful = status => ['empty','unresolved','error','timeout','stale'].includes(status);
    const reset = (mode, runId = null) => {
      state = {runId, sequence:0, tasks:new Map(), steps:new Map(), hasBatch:false,
        phase:'waiting', terminal:false, answerStarted:false};
      panel.hidden = mode !== 'deep'; panel.open = true; panel.dataset.phase = 'waiting';
      text(title,'正在开始深入搜索'); text(meta,''); text(note,'');
      list.replaceChildren();
    };
    const addStep = (id, label) => {
      if (state.steps.has(id)) return state.steps.get(id);
      const row = node('li','research-step'); row.dataset.kind = id.split(':')[0];
      const mark = node('span','research-step-mark'); mark.setAttribute('aria-hidden','true');
      const heading = node('div','research-step-heading');
      const labelNode = node('span','research-step-label',label);
      const statusNode = node('span','research-step-status','进行中');
      heading.append(labelNode,statusNode);
      const tasks = node('ul','research-step-tasks');
      row.append(mark,heading,tasks); row.dataset.status = 'active'; list.append(row);
      const step = {id,row,mark,labelNode,statusNode,tasks,items:new Map(),done:false};
      state.steps.set(id,step);
      return step;
    };
    const endStep = (step, failed = false) => {
      if (!step) return;
      step.done = true; step.row.dataset.status = failed ? 'warning' : 'done';
      text(step.mark,failed ? '·' : '✓'); text(step.statusNode,failed ? '部分未完成' : '已完成');
    };
    const taskItem = (step, task, status) => {
      let item = step.items.get(task.task_id);
      if (!item) {
        const row = node('li','research-task');
        const label = node('span','research-task-label',task.label || labels[task.kind] || '查找资料');
        label.title = label.textContent;
        const statusNode = node('span','research-task-status');
        row.append(label,statusNode); step.tasks.append(row);
        item = {row,statusNode,status}; step.items.set(task.task_id,item);
      }
      item.status = status; item.row.dataset.status = status;
      text(item.statusNode,statuses[status] || '已处理');
    };
    const render = () => {
      const phrases = {waiting:'正在开始深入搜索', controller_started:state.hasBatch
        ? '正在判断是否需要补充资料' : '正在确定检索方向',
        controller_completed:'正在推进研究', batch_started:'正在查找资料',
        tool_started:'正在查找资料', tool_completed:'正在查找资料',
        jev_started:'正在使用 Jev 筛选并整理资料', reduce_started:'正在整理资料', reduce_completed:'正在整理资料', batch_completed:'正在汇总资料',
        research_finished:'研究已结束', final:'正在生成回答', answer:'回答正在展开',
        failed:'研究已停止', terminal:'研究记录'};
      text(title,phrases[state.phase] || '正在研究');
      text(meta,''); panel.dataset.phase = state.phase;
    };
    const event = event => {
      if (!state || state.terminal || (state.runId && state.runId !== event.source_id) ||
          Number(event.sequence) <= state.sequence) return;
      if (event.event_type === 'answer_generation_started') {
        state.runId ||= event.source_id; state.sequence = Number(event.sequence); state.phase = 'final';
        state.finalStep = addStep('final','生成回答'); render(); return;
      }
      if (event.event_type !== 'deep_research') return;
      state.runId ||= event.source_id; state.sequence = Number(event.sequence);
      const p = event.payload || {}; state.phase = p.phase;
      if (p.phase === 'controller_started') {
        if (state.controllerStep && !state.controllerStep.done) endStep(state.controllerStep,true);
        state.controllerStep = addStep(`controller:${p.round}:${p.attempt}`,
          state.hasBatch ? '判断是否需要补充资料' : '确定检索方向');
      }
      if (p.phase === 'controller_completed') endStep(state.controllerStep);
      if (p.phase === 'batch_started') {
        const tasks = (p.tasks || []).slice(0,4);
        state.tasks = new Map(tasks.map(task=>[task.task_id,task])); state.hasBatch = true;
        state.searchStep = addStep(`search:${p.round}`,tasks.length > 1
          ? `同时检索 ${tasks.length} 条线索` : '查找相关资料');
        state.reduceStep = null;
        tasks.forEach(task=>taskItem(state.searchStep,task,'queued'));
      }
      const task = state.tasks.get(p.task_id);
      if (task && p.phase === 'tool_started') taskItem(state.searchStep,task,'searching');
      if (task && p.phase === 'tool_completed') {
        taskItem(state.searchStep,task,p.status === 'ok' ? p.cached ? 'cached' : 'found' : p.status);
        const items = [...state.searchStep.items.values()];
        if (items.every(i=>!['queued','searching'].includes(i.status))) {
          endStep(state.searchStep,items.some(i=>unsuccessful(i.status)));
        }
      }
      if (p.phase === 'jev_started') {
        state.reduceStep ||= addStep(`reduce:${p.round}`,'整理检索到的资料');
        text(state.reduceStep.labelNode,'使用 Jev 筛选并整理资料');
      }
      if (task && p.phase === 'reduce_started') {
        state.reduceStep ||= addStep(`reduce:${p.round}`,'整理检索到的资料');
        taskItem(state.reduceStep,task,'reducing');
      }
      if (task && p.phase === 'reduce_completed' && state.reduceStep) {
        taskItem(state.reduceStep,task,p.status === 'ok' ? 'done' : p.status === 'empty' ? 'unresolved' : p.status);
      }
      if (p.phase === 'batch_completed') {
        if (state.reduceStep) endStep(state.reduceStep,
          [...state.reduceStep.items.values()].some(i=>unsuccessful(i.status)));
      }
      if (p.phase === 'research_finished') {
        const stops = {timeout:'研究已到时间上限，将依据现有资料回答。',
          controller_budget_exhausted:'研究已到运行上限，将依据现有资料回答。',
          tool_budget_exhausted:'检索已到运行上限，将依据现有资料回答。',
          provider_error:'部分研究未能继续，将依据可用资料处理。',
          invalid_structured_output:'下一步研究未能确认，将依据可用资料处理。',
          cancelled:'研究已中断。', no_new_evidence:'继续检索未发现新的有效资料。',
          evidence_unavailable:'研究未找到足够的可用证据。'};
        text(note,stops[p.reason] || '');
        for (const step of state.steps.values()) if (!step.done) endStep(step,true);
      }
      render();
    };
    const answerStarted = () => {
      if (!state || panel.hidden || state.terminal || state.answerStarted) return;
      state.answerStarted = true; state.phase = 'answer'; panel.open = false; render();
    };
    const finish = result => {
      if (!state || panel.hidden) return;
      state.terminal = true; state.phase = 'terminal';
      if (!state.answerStarted) panel.open = false;
      endStep(state.finalStep,result.status === 'insufficient');
      if (result.status === 'insufficient') text(note,'研究已结束，未形成有效的事实正文。');
      render();
    };
    const fail = () => {
      if (!state || panel.hidden) return;
      state.terminal = true; state.phase = 'failed'; panel.open = false;
      for (const step of state.steps.values()) {
        if (!step.done) {
          for (const item of step.items.values()) if (['queued','searching','reducing'].includes(item.status)) {
            item.status = 'error'; item.row.dataset.status = 'error'; text(item.statusNode,statuses.error);
          }
          endStep(step,true);
        }
      }
      text(note,'连接或运行中断，当前进展不代表最终答案。'); render();
    };
    reset('fast');
    return {reset,event,answerStarted,finish,fail};
  }};
})();
