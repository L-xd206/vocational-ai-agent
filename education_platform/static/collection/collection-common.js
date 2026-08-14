(function () {
  'use strict';

  const COLORS = { job:'#18a8ed', ability:'#f4a51c', unit:'#ec5a8d' };

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>'"]/g, char => ({
      '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;'
    })[char]);
  }

  function evidenceList(value) {
    if (value === null || value === undefined || value === '') return [];
    return Array.isArray(value) ? value : [value];
  }

  function evidenceHeader(node) {
    const types = {
      ability:{icon:'能', title:'岗位能力采集详情', className:'ability'},
      unit:{icon:'单', title:'能力单元采集详情', className:'unit'},
      point:{icon:'技', title:'技能点/知识点采集详情', className:'point'}
    };
    const type = types[node?.node_type] || types.point;
    return `<div class="evidence-heading"><span class="evidence-icon ${type.className}">${type.icon}</span>
      <div><div class="evidence-heading-title">${type.title}</div>
      <div class="evidence-heading-subtitle">${escapeHtml(node?.name || '')}</div></div></div>`;
  }

  function formatCapturedAt(value) {
    if (!value) return '暂无记录';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? escapeHtml(value) : date.toLocaleString('zh-CN', {hour12:false});
  }

  function evidenceDetailsHtml(node) {
    const evidence = evidenceList(node?.evidence).filter((item, index, items) => {
      if (typeof item === 'string') {
        return items.findIndex(value => typeof value === 'string' && value === item) === index;
      }
      // 公共招聘网的列表接口不提供职位详情 URL，多条招聘记录会共同回退到
      // 采集源首页。弹窗展示的是“采集来源”，所以相同来源与网址只展示一次。
      const key = `${item?.source_name || ''}|${item?.source_url || ''}`;
      if (key === '|') return true;
      return items.findIndex(value => typeof value === 'object' && value !== null
        && `${value.source_name || ''}|${value.source_url || ''}` === key) === index;
    });
    if (!evidence.length) return '<div class="confirm-text">该节点没有附带采集来源。</div>';
    return `<div class="evidence-details">${evidence.map(item => {
      if (typeof item === 'string') {
        return `<div class="evidence-detail-card"><div class="evidence-detail-row"><span>分析依据</span><strong>${escapeHtml(item)}</strong></div></div>`;
      }
      const url = item?.source_url || '';
      return `<div class="evidence-detail-card">
        <div class="evidence-detail-row"><span>数据源</span><strong>${escapeHtml(item?.source_name || '暂无记录')}</strong></div>
        <div class="evidence-detail-row"><span>采集网址</span>${url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(url)}</a>` : '<strong>暂无记录</strong>'}</div>
        <div class="evidence-detail-row"><span>抓取时间</span><strong>${formatCapturedAt(item?.captured_at)}</strong></div>
      </div>`;
    }).join('')}</div>`;
  }

  function cookie(name) {
    const prefix = `${name}=`;
    const item = document.cookie.split(';').map(value => value.trim())
      .find(value => value.startsWith(prefix));
    return item ? decodeURIComponent(item.slice(prefix.length)) : '';
  }

  async function request(url, options = {}) {
    const method = String(options.method || 'GET').toUpperCase();
    const headers = new Headers(options.headers || {});
    if (!['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method)) {
      const token = cookie('csrftoken');
      if (token) headers.set('X-CSRFToken', token);
    }
    const response = await fetch(url, { credentials:'same-origin', ...options, headers });
    let data = {};
    try { data = await response.json(); } catch (_) {}
    if (!response.ok) {
      const error = new Error(data.error || `请求失败（${response.status}）`);
      error.status = response.status;
      error.data = data;
      throw error;
    }
    return data;
  }

  function toast(message) {
    const element = document.getElementById('toast');
    if (!element) return;
    element.textContent = message;
    element.classList.add('show');
    clearTimeout(element._timer);
    element._timer = setTimeout(() => element.classList.remove('show'), 2800);
  }

  function filterTree(tree, filters) {
    const abilityKey = filters.ability.trim().toLowerCase();
    const unitKey = filters.unit.trim().toLowerCase();
    const pointKey = filters.point.trim().toLowerCase();
    return (tree || []).flatMap(ability => {
      if (abilityKey && !ability.name.toLowerCase().includes(abilityKey)) return [];
      const units = (ability.children || []).flatMap(unit => {
        if (unitKey && !unit.name.toLowerCase().includes(unitKey)) return [];
        const points = (unit.children || []).filter(point =>
          !pointKey || point.name.toLowerCase().includes(pointKey)
        );
        if (pointKey && !points.length) return [];
        return [{ ...unit, children:points }];
      });
      if ((unitKey || pointKey) && !units.length) return [];
      return [{ ...ability, children:units }];
    });
  }

  function metaFor(node, mode) {
    if (node.context_only) return '路径信息';
    if (mode === 'rejected') return '已拒纳';
    if (node.node_type === 'ability' && node.college) return node.college;
    if (node.is_virtual) return node.decision_status === 'adopted' ? '已引用' : 'AI分析新增';
    return '能力图谱中已存在';
  }

  function nodeCard(node, level, parentKey, mode) {
    const key = `node-${node.id}`;
    const virtual = node.is_virtual && node.decision_status === 'pending';
    const tag = node.context_only
      ? '<span class="tag tag-path">路径</span>'
      : mode === 'rejected' ? '<span class="tag tag-ai">已拒纳</span>'
      : virtual ? '<span class="tag tag-ai">AI新增</span>' : '<span class="tag tag-real">已存在</span>';
    let actions = '';
    if (mode === 'candidate' && virtual) {
      actions = `<div class="node-actions">
        <button class="node-btn info" data-action="evidence" data-node-id="${node.id}" title="查看分析依据">i</button>
        <button class="node-btn adopt" data-action="adopt" data-node-id="${node.id}">引用</button>
        <button class="node-btn reject" data-action="reject" data-node-id="${node.id}" data-node-name="${escapeHtml(node.name)}">拒纳</button>
      </div>`;
    } else if (mode === 'rejected' && !node.context_only) {
      actions = `<div class="node-actions">
        ${node.evidence && node.evidence.length ? `<button class="node-btn info" data-action="evidence" data-node-id="${node.id}">i</button>` : ''}
        <button class="node-btn adopt" data-action="restore" data-node-id="${node.restore_node_id || node.id}">引用</button>
      </div>`;
    } else if (node.evidence && node.evidence.length) {
      actions = `<div class="node-actions"><button class="node-btn info" data-action="evidence" data-node-id="${node.id}">i</button></div>`;
    }
    return `<div class="node-card${virtual ? ' virtual' : ''}${node.context_only ? ' context-only' : ''}"
      data-level="${level}" data-node-key="${key}" data-parent-key="${parentKey || ''}">
      <span class="node-dot"></span><div class="node-main"><div class="node-name" title="${escapeHtml(node.name)}">${escapeHtml(node.name)}</div>
      <div class="node-meta">${escapeHtml(metaFor(node, mode))}</div></div>${tag}${actions}</div>`;
  }

  function jobCard(item, mode) {
    const batch = item.batch;
    const state = batch ? batch.status : 'not_started';
    const labels = {
      not_started:'尚无AI分析结果', pending:'等待分析', processing:'AI分析中', completed:'候选树已生成',
      skipped:batch?.error_message || '有效招聘数据不足', failed:batch?.error_message || '分析失败'
    };
    return `<div class="node-card" data-level="job" data-node-key="job-${item.job.id}">
      <button class="toggle-btn" data-action="toggle-job" data-job-id="${item.job.id}" title="展开/收缩">›</button>
      <span class="node-dot"></span><div class="node-main"><div class="node-name">${escapeHtml(item.job.name)}</div>
      <div class="node-meta">${escapeHtml(item.job.chain_name)} · ${escapeHtml(labels[state] || state)}</div></div></div>`;
  }

  function render(container, items, filters, options = {}) {
    const mode = options.mode || 'candidate';
    const jobKey = filters.job.trim().toLowerCase();
    const visible = [];
    for (const item of items) {
      if (jobKey && !item.job.name.toLowerCase().includes(jobKey)) continue;
      const tree = filterTree(item.tree || [], filters);
      if ((filters.ability || filters.unit || filters.point) && !tree.length) continue;
      visible.push({ ...item, tree });
    }
    if (!visible.length) {
      container.innerHTML = '<div class="tree-empty">没有符合条件的数据</div>';
      return;
    }
    container.innerHTML = visible.map(item => {
      const abilities = item.tree || [];
      const units = abilities.flatMap(ability => (ability.children || []).map(unit => ({ ...unit, _parent:`node-${ability.id}` })));
      const points = units.flatMap(unit => (unit.children || []).map(point => ({ ...point, _parent:`node-${unit.id}` })));
      return `<section class="job-tree" data-job-tree="${item.job.id}">
        <svg class="connector-layer" aria-hidden="true"></svg>
        <div class="tree-column">${jobCard(item, mode)}</div>
        <div class="tree-column">${abilities.length ? abilities.map(node => nodeCard(node,'ability',`job-${item.job.id}`,mode)).join('') : '<div class="node-meta">暂无候选岗位能力</div>'}</div>
        <div class="tree-column">${units.map(node => nodeCard(node,'unit',node._parent,mode)).join('')}</div>
        <div class="tree-column">${points.map(node => nodeCard(node,'point',node._parent,mode)).join('')}</div>
      </section>`;
    }).join('');
    requestAnimationFrame(() => drawConnections(container));
  }

  function drawConnections(container) {
    container.querySelectorAll('.job-tree').forEach(group => {
      if (group.classList.contains('collapsed')) return;
      const svg = group.querySelector('.connector-layer');
      const bounds = group.getBoundingClientRect();
      svg.setAttribute('viewBox', `0 0 ${bounds.width} ${bounds.height}`);
      const paths = [];
      group.querySelectorAll('[data-parent-key]').forEach(child => {
        const parentKey = child.dataset.parentKey;
        if (!parentKey) return;
        const parent = group.querySelector(`[data-node-key="${CSS.escape(parentKey)}"]`);
        if (!parent) return;
        const p = parent.getBoundingClientRect(), c = child.getBoundingClientRect();
        const x1 = p.right - bounds.left, y1 = p.top + p.height / 2 - bounds.top;
        const x2 = c.left - bounds.left, y2 = c.top + c.height / 2 - bounds.top;
        const mid = x1 + Math.max(18, (x2 - x1) * .5);
        const level = parent.dataset.level || 'job';
        paths.push(`<path d="M${x1},${y1} C${mid},${y1} ${mid},${y2} ${x2},${y2}" stroke="${COLORS[level] || COLORS.job}"/>`);
      });
      svg.innerHTML = paths.join('');
    });
  }

  function bindTreeActions(container, handlers) {
    container.addEventListener('click', event => {
      const button = event.target.closest('[data-action]');
      if (!button) return;
      const action = button.dataset.action;
      if (action === 'toggle-job') {
        button.closest('.job-tree')?.classList.toggle('collapsed');
        requestAnimationFrame(() => drawConnections(container));
        return;
      }
      handlers[action]?.(button);
    });
  }

  window.addEventListener('resize', () => {
    const container = document.querySelector('.tree-content');
    if (container) drawConnections(container);
  });

  window.CollectionUI = {
    escapeHtml, evidenceList, evidenceHeader, evidenceDetailsHtml,
    request, toast, render, drawConnections, bindTreeActions
  };
})();
