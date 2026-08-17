// DOM & Formatting Utilities
// ==========================================================================

/**
 * Shorthand for document.querySelector
 */
export const $ = (sel) => document.querySelector(sel);

/**
 * Shorthand for document.querySelectorAll
 */
export const $$ = (sel) => document.querySelectorAll(sel);

/**
 * Show a toast notification
 */
export function toast(text) {
  const el = $('#toast');
  if (!el) return;
  el.textContent = text;
  el.classList.add('show');
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => el.classList.remove('show'), 4500);
}

/**
 * 居中弹窗提示（用于表单校验等必须被用户看到的错误）。
 * 复用通用 #modal：填充标题/正文，隐藏密码输入行，仅保留「知道了」按钮。
 * 与提交密码弹窗（requestStart）共用 #modal，但本函数不依赖 submit-password。
 */
export function showErrorModal(title, message) {
  const modal = $('#modal');
  if (!modal) return;
  const titleEl = $('#modal-title');
  const bodyEl = $('#modal-body');
  const pwRow = $('#modal-pw-row');
  const actions = $('#modal-actions');
  if (titleEl) titleEl.textContent = title || '提示';
  if (bodyEl) bodyEl.textContent = message || '';
  if (pwRow) pwRow.hidden = true;
  if (actions) {
    actions.innerHTML = '<button class="primary" onclick="closeErrorModal()">知道了</button>';
  }
  modal.hidden = false;
}

// 供内联 onclick 调用
window.closeErrorModal = function closeErrorModal() {
  const modal = $('#modal');
  const pwRow = $('#modal-pw-row');
  const actions = $('#modal-actions');
  if (modal) modal.hidden = true;
  // 还原为默认的提交密码弹窗结构，避免影响后续 requestStart 使用
  if (pwRow) pwRow.hidden = false;
  if (actions) {
    actions.innerHTML =
      '<button class="secondary" onclick="closeModal()">取消</button>' +
      '<button onclick="confirmStart()">启动</button>';
  }
};

/**
 * Promise-based delay
 */
export function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Escape HTML entities
 */
export function escapeHtml(value) {
  const div = document.createElement('div');
  div.textContent = value ?? '';
  // 同时转义引号，使其既可用于元素文本，也可安全用于属性值上下文
  return div.innerHTML.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

/**
 * Escape string for use in HTML attribute values
 */
export function escapeAttr(value) {
  // 用于两种上下文：① 双引号 HTML 属性（data-* / title）→ 需转义 " 与 &
  // ② 双引号 HTML 属性内、单引号 JS 字符串（onclick="fn('...')"）→ " 解码后落入单引号串是安全的，
  //    但 ' 与 \ 必须转义。先转 & 再转其他，避免嵌套二次解码。
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, "\\'")
    .replace(/\\/g, '\\\\')
    .replace(/\n/g, ' ')
    .replace(/\r/g, ' ');
}

/**
 * Format bytes as human-readable string
 */
export function formatBytes(value) {
  if (value == null) return '';
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

/**
 * Split textarea value into non-empty trimmed lines
 */
export function lines(id) {
  const el = $(id);
  return el ? el.value.split('\n').map((v) => v.trim()).filter(Boolean) : [];
}

/**
 * Human-readable mode name
 */
const MODE_NAMES = { lip_sync: '对口型', dance_lip_sync: '口型 + 动作', motion: '模仿动作', custom: '自由定制' };
export function modeName(v) {
  return MODE_NAMES[v] || v;
}

/**
 * Human-readable stage name
 */
const STAGE_NAMES = {
  queued: '排队', validating: '校验', preparing: '处理素材', tunnel: '隧道',
  uploading: '上传', submitting: '提交', generating: '生成', downloading: '下载',
  muxing: '音频回灌', manifest: '生成清单', completed: '完成', failed: '失败',
  interrupted: '已中断',
};
export function stageName(v) {
  return STAGE_NAMES[v] || v;
}

// ── Loading & Skeleton Helpers ──────────────────────────────────────────────

/**
 * Show a loading indicator in a container
 */
export function showLoading(container) {
  container.classList.add('is-loading');
  container.setAttribute('aria-busy', 'true');
}

/**
 * Remove loading indicator from a container
 */
export function hideLoading(container) {
  container.classList.remove('is-loading');
  container.removeAttribute('aria-busy');
}

/**
 * Render skeleton placeholders while content loads
 * @param {'list'|'video-grid'|'image-grid'} type
 * @param {number} count
 */
export function renderSkeleton(type, count = 4) {
  if (type === 'list') {
    return `<div class="skeleton-grid">${Array(count).fill('<div class="skeleton skeleton-card"></div>').join('')}</div>`;
  }
  if (type === 'video-grid') {
    return `<div class="review-grid">${Array(count).fill('<div class="skeleton skeleton-video"></div>').join('')}</div>`;
  }
  if (type === 'image-grid') {
    return `<div class="anchor-review-grid">${Array(count).fill('<div class="skeleton skeleton-video" style="aspect-ratio:2/3"></div>').join('')}</div>`;
  }
  return '';
}

/**
 * Render an empty state placeholder
 * @param {string} icon  — emoji or text icon
 * @param {string} message
 * @param {string} hint   — optional sub-text
 */
export function renderEmptyState(icon, message, hint = '') {
  return [
    '<div class="empty-state">',
    `<div class="empty-icon">${icon}</div>`,
    `<p>${escapeHtml(message)}</p>`,
    hint ? `<p class="hint">${escapeHtml(hint)}</p>` : '',
    '</div>',
  ].join('');
}
