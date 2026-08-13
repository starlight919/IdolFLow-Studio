// Review & Publish Module
// ==========================================================================

import store from './state.js';
import { api, post } from './api.js';
import { $, $$, toast, escapeHtml, delay } from './utils.js';

let reviewPollTimer = null;
let loadingRunId = null;

// ── Prepare ─────────────────────────────────────────────────────────────────

export async function prepareReview() {
  const { loadRuns } = await import('./task.js');
  await loadRuns();
  const select = $('#review-run');
  if (!select) return;
  const id = select.value;
  if (id) {
    loadReview(id);
  } else if (select.options.length > 0) {
    // 自动选中最近的任务
    select.selectedIndex = 0;
    loadReview(select.value);
  }
}

// ── Load & Render ───────────────────────────────────────────────────────────

export async function loadReview(runId) {
  clearInterval(reviewPollTimer);
  if (!runId) return;
  loadingRunId = runId;
  // 先加载一次
  await _fetchManifest(runId);
  // 如果 run 仍在生成中，定时刷新 manifest 以实时看到新候选
  reviewPollTimer = setInterval(async () => {
    // 如果 loadingRunId 已被另一个 loadReview 改变，停止轮询
    if (loadingRunId !== runId) { clearInterval(reviewPollTimer); return; }
    const run = store.runs?.find((r) => r.run_id === runId);
    if (!run || (run.status !== 'running' && run.status !== 'queued')) {
      clearInterval(reviewPollTimer);
      return;
    }
    await _fetchManifest(runId);
  }, 3000);
}

async function _fetchManifest(runId) {
  // 如果 loadingRunId 已被其他 loadReview 修改，放弃本次写入
  if (loadingRunId && loadingRunId !== runId) return;
  try {
    const prevRunId = store.reviewRunId;
    const prevCount = store.reviewManifest?.candidates?.length || 0;
    store.reviewManifest = await api(`/api/runs/${runId}/manifest`);
    // 再次检查，防止异步期间被切换
    if (loadingRunId && loadingRunId !== runId) return;
    store.reviewRunId = runId;
    const newCount = store.reviewManifest.candidates?.length || 0;
    if (newCount !== prevCount || prevRunId !== runId) {
      renderReview();
    }
  } catch (e) {
    console.error('Failed to load manifest:', e);
    if (!store.reviewManifest?.candidates) {
      store.reviewManifest = { candidates: [] };
      store.reviewRunId = runId;
      renderReview();
    }
  }
}

export function renderReview() {
  if (!store.reviewManifest) return;

  const groups = new Map();
  store.reviewManifest.candidates.forEach((c) => {
    if (!groups.has(c.anchor)) groups.set(c.anchor, { label: c.anchor_label, items: [] });
    groups.get(c.anchor).items.push(c);
  });

  const toolbar = $('#review-toolbar');
  if (toolbar) toolbar.innerHTML = '';

  const content = $('#review-content');
  if (!content) return;
  if (store.reviewManifest.candidates.length === 0) {
    const runId = $('#review-run')?.value;
    const run = store.runs?.find((r) => r.run_id === runId);
    const msg = run && run.status === 'running'
      ? '生成中，候选视频完成后将实时出现在这里…'
      : '暂无可审核的候选视频';
    content.innerHTML = `<div class="empty-state"><p>${msg}</p></div>`;
    return;
  }
  content.innerHTML = [...groups.values()]
    .map(
      (g) => `<section class="review-group">
        <h3>${escapeHtml(g.label)} <span class="meta">${g.items.length} 个</span></h3>
        <div class="review-grid">${g.items.map(reviewCard).join('')}</div>
      </section>`
    )
    .join('');
}

function reviewCard(c) {
  const run = store.reviewRunId || $('#review-run')?.value || '';
  const id = encodeURIComponent(c.id);
  return `<article class="review-card" data-id="${escapeHtml(c.id)}">
    <div class="review-meta">
      <strong>候选 ${String(c.candidate).padStart(2, '0')}</strong>
      <span class="meta">${escapeHtml(c.variant)}</span>
    </div>
    <video controls preload="metadata" src="/api/runs/${run}/media/${id}"></video>
    <div class="review-actions">
      <a href="/api/runs/${run}/download/${id}" class="btn-download" title="下载视频">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
      </a>
    </div>
  </article>`;
}

