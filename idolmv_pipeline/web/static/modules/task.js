// Video Task Form & Run Management Module
// ==========================================================================

import store from './state.js';
import { api, post, uploadFile, copyAssetFile, extractTaskAudio, extractAudioByPath, getLyricsTimestamps, saveLyricsTimestamps } from './api.js';
import { $, $$, toast, escapeHtml, escapeAttr, formatBytes, modeName, stageName, lines, renderEmptyState } from './utils.js';

// ── Task Folder Relative Path ───────────────────────────────────────────────

export function taskFolderRelative() {
  return $('#task-dir').value.trim();
}

// ── Task Folder Empty Detection ─────────────────────────────────────────────
// 新建/选择任务目录后，检测目录内是否已有素材（图片/视频/音频），
// 若为空则提示用户去下方上传，或自行把文件放入任务目录。

const IMAGE_EXTENSIONS = new Set(['jpg', 'jpeg', 'png', 'webp', 'bmp', 'gif']);
const AV_EXTENSIONS = new Set([
  'mp4', 'mov', 'm4v', 'webm', 'avi', 'mkv',   // 视频
  'mp3', 'wav', 'm4a', 'aac', 'flac', 'ogg',   // 音频
]);
const AUDIO_EXTENSIONS = new Set(['mp3', 'wav', 'm4a', 'aac', 'flac', 'ogg', 'aiff', 'opus', 'wma']);
// 统一按扩展名判断音频，供 picker 展示、上传、选择共用，避免各处正则不一致
const isAudioName = (name) => AUDIO_EXTENSIONS.has((name.split('.').pop() || '').toLowerCase());

// 返回目录内是否已有图片 / 音视频。只下钻已知素材子目录，避免深挖 tasks/seedance 等无关目录。
const ASSET_SUBDIR_RE = /^(anchors?|references?|audio|videos?|images?|assets?|anchor-references|generated)$/i;

async function _scanFolderHasAssets(rel, depth = 0) {
  if (depth > 2) return { hasImage: false, hasAV: false };
  const data = await api(`/api/files?root=data_root&path=${encodeURIComponent(rel)}`);
  const items = data.items || [];
  let hasImage = false;
  let hasAV = false;
  for (const item of items) {
    if (item.directory) {
      // 仅下钻已知素材子目录，且限制深度（不能见到 anchors/ 目录名就认定有图片，
      // 否则新建文件夹时自动建的空 anchors/ 会被误判为「已有图片」）
      if (ASSET_SUBDIR_RE.test(item.name)) {
        const sub = await _scanFolderHasAssets(`${rel.replace(/\/$/, '')}/${item.name}`, depth + 1);
        hasImage = hasImage || sub.hasImage;
        hasAV = hasAV || sub.hasAV;
      }
      continue;
    }
    const ext = (item.name.split('.').pop() || '').toLowerCase();
    if (IMAGE_EXTENSIONS.has(ext)) hasImage = true;
    else if (AV_EXTENSIONS.has(ext)) hasAV = true;
  }
  return { hasImage, hasAV };
}

export async function checkTaskFolderEmpty() {
  const tip = $('#empty-folder-tip');
  const needDirTip = $('#need-dir-tip');
  const rel = taskFolderRelative();
  if (!rel) {
    // 未确定任务文件夹：提示先建立，而非「缺少素材」
    if (tip) tip.hidden = true;
    if (needDirTip) needDirTip.hidden = false;
    return;
  }
  if (needDirTip) needDirTip.hidden = true;
  if (!tip) return;
  try {
    const { hasImage, hasAV } = await _scanFolderHasAssets(rel);
    const missingImage = !hasImage;
    const missingAV = !hasAV;
    // 两类素材都齐 → 隐藏提示
    if (!missingImage && !missingAV) { tip.hidden = true; return; }

    // 分别提示约定子目录：图片 → anchors/，音视频 → references/
    $$('.empty-folder-path').forEach((el) => {
      const sub = el.dataset.sub || '';
      el.textContent = `data_root/${rel}/${sub}`.replace(/\/$/, '');
    });

    const imgLine = $('#empty-folder-img');
    const avLine = $('#empty-folder-av');
    if (imgLine) imgLine.style.display = missingImage ? '' : 'none';
    if (avLine) avLine.style.display = missingAV ? '' : 'none';

    tip.hidden = false;
  } catch {
    // 目录不存在（如手输的新文件夹名）：按"目录为空"提示，
    // 引导上传/现场生成，而不是静默隐藏让人以为素材已齐
    $$('.empty-folder-path').forEach((el) => {
      const sub = el.dataset.sub || '';
      el.textContent = `data_root/${rel}/${sub}`.replace(/\/$/, '');
    });
    const imgLine = $('#empty-folder-img');
    const avLine = $('#empty-folder-av');
    if (imgLine) imgLine.style.display = '';
    if (avLine) avLine.style.display = '';
    tip.hidden = false;
  }
}

// 空目录提示里的「去现场生成」：切到现场生成说明区块并滚动到 Anchor 字段
export function goGenerateAnchor() {
  window.setAnchorSource?.('generate');
  const anchorLabel = [...document.querySelectorAll('.fields > label')].find((l) => l.textContent.includes('Anchor 文件'));
  if (anchorLabel) {
    anchorLabel.scrollIntoView({ behavior: 'smooth', block: 'center' });
    anchorLabel.classList.add('flash');
    setTimeout(() => anchorLabel.classList.remove('flash'), 1600);
  }
}

// ── Preview Helpers ─────────────────────────────────────────────────────────

function previewPath(file) {
  const root = taskFolderRelative();
  const path = root ? `${root.replace(/\/$/, '')}/${file}` : file;
  return `/api/file-preview?root=data_root&path=${encodeURIComponent(path)}`;
}

export function renderAssetChips(field) {
  const container = $(`.asset-chips[data-field="${field}"]`);
  if (!container) return;
  // references 字段需根据当前 tab 区分视频(#references)还是音频(#audio-refs)
  const isAudioTab = field === 'references'
    && document.querySelector('.ref-tab.active[data-ref-tab]')?.dataset?.refTab === 'audio';
  const sourceField = isAudioTab ? 'audio-refs' : field;
  const files = lines(`#${sourceField}`);
  if (!files.length) {
    container.innerHTML = '';
    return;
  }
  container.innerHTML = files.map((file) => {
    const name = file.split('/').pop();
    return `<span class="asset-chip" title="${escapeHtml(file)}">${escapeHtml(name)}<button type="button" class="chip-remove" data-type="${field}" data-file="${escapeAttr(file)}" title="取消选中">✕</button></span>`;
  }).join('');
}

export function renderVideoAssetPreviews() {
  renderAssetChips('anchors');
  renderAssetChips('references');
  const anchorFiles = lines('#anchors');
  // 根据当前 ref-tab 决定读视频字段还是音频字段
  const isAudioTab = document.querySelector('.ref-tab.active[data-ref-tab]')?.dataset?.refTab === 'audio';
  const referenceFiles = isAudioTab ? lines('#audio-refs') : lines('#references');

  const anchorEl = $('#anchor-file-previews');
  if (anchorEl) {
    anchorEl.innerHTML = anchorFiles.length
      ? anchorFiles.map((file) => `<figure class="asset-figure" data-file="${escapeAttr(file)}"><img src="${previewPath(file)}" loading="eager" onerror="this.onerror=null;this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22100%22 height=%22100%22%3E%3Ctext x=%2250%25%22 y=%2250%25%22 text-anchor=%22middle%22%3E✗%3C/text%3E%3C/svg%3E'"><button type="button" class="asset-remove" data-type="anchors" data-file="${escapeAttr(file)}" title="取消选中">✕</button><figcaption>${escapeHtml(file.split('/').pop())}</figcaption></figure>`).join('')
      : '<p class="hint">未选择任何文件</p>';
  }

  const refEl = $('#reference-file-previews');
  if (refEl) {
    refEl.innerHTML = referenceFiles.length
      ? referenceFiles.map((file) => {
          const isAudio = /\.(mp3|wav|m4a|aac|flac|ogg)$/i.test(file);
          const media = isAudio
            ? `<div class="asset-audio-icon">♪</div>`
            : `<video src="${previewPath(file)}#t=0.1" preload="metadata" muted onerror="console.error('Failed to load:',this.src)"></video>`;
          return `<figure class="asset-figure${isAudio ? ' asset-audio' : ''}" data-file="${escapeAttr(file)}">${media}<button type="button" class="asset-remove" data-type="references" data-file="${escapeAttr(file)}" title="取消选中">✕</button><figcaption>${escapeHtml(file.split('/').pop())}</figcaption></figure>`;
        }).join('')
      : '<p class="hint">未选择任何文件</p>';
  }
  _syncPassAudioDisabled();
}

// 传了独立音频（对口型源）时，「传参考音频」（从视频提取）用不上，置灰并说明
function _syncPassAudioDisabled() {
  const cb = $('#pass-reference-audio');
  const wrap = $('#pass-audio-wrap');
  if (!cb) return;
  const hasOwnAudio = lines('#audio-refs').length > 0;
  cb.disabled = hasOwnAudio;
  wrap?.classList.toggle('disabled', hasOwnAudio);
  if (wrap) {
    let tip = wrap.querySelector('.pass-audio-note');
    if (hasOwnAudio) {
      if (!tip) {
        tip = document.createElement('span');
        tip.className = 'pass-audio-note';
        wrap.appendChild(tip);
      }
      tip.textContent = '已用独立音频对口型，视频音频不适用';
    } else if (tip) {
      tip.remove();
    }
  }
}

export function removeVideoAsset(type, file) {
  let target = type === 'anchors' ? '#anchors' : '#references';
  // references 在音频 tab 下操作 #audio-refs
  if (type === 'references') {
    const isAudioTab = document.querySelector('.ref-tab.active[data-ref-tab]')?.dataset?.refTab === 'audio';
    if (isAudioTab) target = '#audio-refs';
  }
  const el = $(target);
  if (!el) return;
  const raw = el.value.split('\n').map((v) => v.trim());
  // #audio-refs 按行号与 #references 配对：移除某行音频时用空行占位而不是删行，保持对齐
  if (target === '#audio-refs') {
    el.value = raw.map((v) => (v === file ? '' : v)).join('\n');
  } else {
    el.value = raw.filter((v) => v !== file).join('\n');
  }
  renderVideoAssetPreviews();
}

// ── Asset Picker（从文件夹选择 / 本机上传 统一入口）─────────────────────────

export async function openAssetPicker(category, opts = {}) {
  // anchor-references：Anchor 生成器的参考图选择（任务文件夹在 #anchor-id）；
  // 显式设置 anchorPickerMode，修复"上次进 anchor 选择器、未确认关闭后，
  // 再开主工作台选择器仍走 anchor 分支"的残留状态
  store.anchorPickerMode = category === 'anchor-references';
  store.assetPickerCategory = category;
  if (store.anchorPickerMode) {
    const dataDir = ($('#anchor-id')?.value || '').trim().replace(/\/+$/, '');
    if (!dataDir) {
      toast('请先填写任务文件夹（步骤 1），再添加参考图');
      return;
    }
    store.assetPickerRoot = `${dataDir}/anchors/anchor-references`;
    store.assetPickerTaskId = dataDir;
    store.assetPickerPath = store.assetPickerRoot;
    store.assetPickerSelected = new Set();
    $('#asset-picker-title').textContent = '添加 Anchor 参考图';
  } else {
    const root = taskFolderRelative().replace(/\/+$/, '');
    if (!root) {
      toast('请先选择任务文件夹（步骤 1），再添加素材');
      return;
    }
    store.assetPickerRoot = root;
    store.assetPickerTaskId = root;
    // 分类决定默认目录（约定：图片 → anchors/，音视频 → references/）。
    // 若默认目录不存在，browseAssets 会自动逐级回退到任务根目录。
    store.assetPickerPath = `${root}/${category === 'anchors' ? 'anchors' : 'references'}`;
    // 已选中项：references 在音频 tab 下读 #audio-refs
    const isAudioTab = category === 'references'
      && document.querySelector('.ref-tab.active[data-ref-tab]')?.dataset?.refTab === 'audio';
    store.assetPickerSelected = new Set(lines(category === 'anchors' ? '#anchors' : (isAudioTab ? '#audio-refs' : '#references')));
    $('#asset-picker-title').textContent = category === 'anchors' ? '选择 Anchor 图片' : '选择参考音视频';
  }
  $('#asset-picker-modal').hidden = false;
  _resetPickerUpload();
  store.assetPickerOutside = new Map();
  const fileInput = $('#picker-upload-file');
  if (fileInput) fileInput.accept = _pickerUploadAccept();
  switchPickerTab(opts.tab === 'upload' ? 'upload' : 'browse');
  // 无论初始停在哪个 tab 都预取列表，避免从上传 tab 切回时显示上一次的旧列表
  await browseAssets(store.assetPickerPath);
}

export function closeAssetPicker() {
  $('#asset-picker-modal').hidden = true;
  // 使在途上传批次失效：关闭弹窗后剩余文件不再继续传，残留状态不影响下次打开
  if (_pickerUpload.uploading) {
    toast('已取消剩余文件的上传（已传完的文件保留在文件夹里）');
  }
  _resetPickerUpload();
}

// ── Picker 上传 tab ─────────────────────────────────────────────────────────

const _pickerUpload = { session: 0, uploading: false, rows: [] };

function _pickerUploadAccept() {
  return store.assetPickerCategory === 'references'
    ? '.mp4,.mov,.m4v,.webm,.avi,.mkv,.mp3,.wav,.m4a,.aac,.flac,.ogg'
    : 'image/*';
}

// 上传落点与勾选值约定（与后端 handle_upload 一一对应，勿改动单边）：
// - anchors:           X-Category=anchors           → data/<dir>/anchors/<name>，返回 anchors/<name>，
//                      列表值相对 <dir>，与返回值一致，直接用
// - references:        X-Category=references        → data/<dir>/references/<name>，同上直接用
// - anchor-references: X-Category=anchor-references → data/<dir>/anchors/anchor-references/<name>，
//                      返回 anchors/anchor-references/<name>；列表值相对 assetPickerRoot
//                      （<dir>/anchors/anchor-references），需取纯文件名
function _pickerUploadContext() {
  const category = store.assetPickerCategory;
  if (category === 'anchor-references') {
    return {
      taskId: store.assetPickerTaskId,
      destRel: store.assetPickerRoot,
      value: (serverPath) => String(serverPath).split('/').pop(),
    };
  }
  const sub = category === 'anchors' ? 'anchors' : 'references';
  return {
    taskId: store.assetPickerTaskId,
    destRel: `${store.assetPickerRoot}/${sub}`,
    value: (serverPath) => serverPath,
  };
}

function _resetPickerUpload() {
  _pickerUpload.session += 1;
  _pickerUpload.uploading = false;
  _pickerUpload.rows = [];
  const listEl = $('#picker-upload-list');
  if (listEl) listEl.innerHTML = '';
  const input = $('#picker-upload-file');
  if (input) input.value = '';
  _updatePickerConfirmBtn();
}

export function switchPickerTab(tab) {
  const isUpload = tab === 'upload';
  $$('.picker-tabs .ref-tab[data-picker-tab]').forEach((b) => {
    b.classList.toggle('active', b.dataset.pickerTab === tab);
  });
  const browse = $('#asset-picker-browse');
  if (browse) browse.hidden = isUpload;
  const upload = $('#asset-picker-upload');
  if (upload) upload.hidden = !isUpload;
  // 引导行按 tab 说明当前能做什么、另一个 tab 是干什么的，
  // 让「本机上传」入口即使不点也看得懂
  const label = store.assetPickerCategory === 'references' ? '音视频'
    : store.assetPickerCategory === 'anchor-references' ? '参考图' : '图片';
  const hintEl = $('#asset-picker-hint');
  if (hintEl) {
    hintEl.textContent = isUpload
      ? `选本机文件直接上传到任务文件夹（自动勾选），再点「添加已选文件」加入`
      : `勾选任务文件夹里已有的${label}；文件夹里没有？切「⬆ 本机上传」从电脑直接传`;
  }
  if (isUpload) _renderPickerUploadZone();
}

function _renderPickerUploadZone() {
  const ctx = _pickerUploadContext();
  const btn = $('#picker-upload-btn');
  const dest = $('#picker-upload-dest');
  if (!ctx.taskId) {
    if (btn) btn.disabled = true;
    if (dest) dest.textContent = '请先选择任务文件夹，再上传';
    return;
  }
  if (btn) btn.disabled = _pickerUpload.uploading;
  if (dest) dest.textContent = `将上传到 data/${ctx.destRel}/`;
}

function _renderPickerUploadRows() {
  const listEl = $('#picker-upload-list');
  if (!listEl) return;
  listEl.innerHTML = _pickerUpload.rows.map((row) => {
    const status = row.state === 'done'
      ? '<span class="picker-upload-ok">✓ 已上传并选中</span>'
      : row.state === 'failed'
        ? `<span class="picker-upload-err">✗ ${escapeHtml(row.error || '上传失败')}</span>`
        : row.state === 'uploading'
          ? `<span class="picker-upload-pct">${row.percent}%</span>`
          : '<span class="picker-upload-pct">等待中</span>';
    return `<div class="picker-upload-row ${row.state}"><span class="picker-upload-name" title="${escapeAttr(row.file.name)}">${escapeHtml(row.file.name)}</span>${status}</div>`;
  }).join('');
}

function _updatePickerConfirmBtn() {
  const btn = $('#picker-confirm-btn');
  if (!btn) return;
  btn.disabled = _pickerUpload.uploading;
  const n = store.assetPickerSelected ? store.assetPickerSelected.size : 0;
  btn.textContent = n ? `添加已选文件 (${n})` : '添加已选文件';
}

export async function handlePickerUploadFiles(fileList) {
  const files = [...(fileList || [])];
  const input = $('#picker-upload-file');
  if (input) input.value = '';
  if (!files.length) return;
  const ctx = _pickerUploadContext();
  if (!ctx.taskId) {
    toast('请先选择任务文件夹，再上传');
    return;
  }
  if (_pickerUpload.uploading) {
    toast('正在上传中，请稍候');
    return;
  }

  // 同名冲突确认：后端对同名文件是覆盖写，这里在覆盖前让用户确认
  const existing = new Set();
  try {
    const data = await api(`/api/files?root=data_root&path=${encodeURIComponent(ctx.destRel)}`);
    (data.items || []).forEach((item) => { if (!item.directory) existing.add(item.name); });
  } catch { /* 目录不存在（首次上传），视为无冲突 */ }
  const collisions = files.filter((f) => existing.has(f.name));
  if (collisions.length) {
    const names = collisions.map((f) => f.name).join('、');
    const ok = await window.showDeleteConfirm({
      title: '覆盖同名文件',
      desc: `目标目录已有同名文件：${names}。\n继续上传将覆盖它们（任务里引用旧文件的地方会使用新内容）。`,
      showFileOption: false,
      confirmText: '覆盖上传',
      danger: true,
    });
    if (!ok) return;
  }

  const session = _pickerUpload.session;
  _pickerUpload.uploading = true;
  _pickerUpload.rows = files.map((file) => ({ file, state: 'waiting', percent: 0, error: '' }));
  _renderPickerUploadRows();
  _updatePickerConfirmBtn();
  _renderPickerUploadZone();

  let anySuccess = false;
  for (const row of _pickerUpload.rows) {
    // 弹窗已关闭/重新打开（session 变化）：中止剩余文件
    if (session !== _pickerUpload.session) return;
    row.state = 'uploading';
    _renderPickerUploadRows();
    try {
      const result = await uploadFile(row.file, {
        taskId: ctx.taskId,
        category: store.assetPickerCategory,
        onProgress: (p) => { row.percent = p; _renderPickerUploadRows(); },
      });
      row.state = 'done';
      row.percent = 100;
      // 上传成功即加入勾选：值按 context 约定转换，确认后落进对应字段
      store.assetPickerSelected.add(ctx.value(result.file || row.file.name));
      anySuccess = true;
    } catch (e) {
      row.state = 'failed';
      row.error = e.message;
    }
    _renderPickerUploadRows();
  }
  _pickerUpload.uploading = false;
  _updatePickerConfirmBtn();
  _renderPickerUploadZone();
  // 全部传完：切回文件夹视图并定位到目标目录，刚上传的文件已勾选，所见即所得
  if (anySuccess && session === _pickerUpload.session && !$('#asset-picker-modal').hidden) {
    switchPickerTab('browse');
    await browseAssets(ctx.destRel);
  }
}

export async function browseAssets(path) {
  try {
    let data;
    // 逐级向上回退：默认子目录（anchors/、references/）不存在时，
    // 自动回退到父目录乃至任务根目录，让用户能看到直接放在根目录下的素材。
    // 强制边界：最多回退到任务根目录（assetPickerRoot）为止——目录不存在时展示
    // 空状态（含上传入口），绝不能爬到 data_root 根把别的任务文件夹列出来，
    // 否则勾选的相对路径不属于当前任务，保存后会解析失败。
    const stopAt = (store.assetPickerRoot || '').replace(/\/+$/, '');
    let cur = path;
    while (true) {
      try {
        data = await api(`/api/files?root=data_root&path=${encodeURIComponent(cur)}`);
        break;
      } catch (e) {
        const parent = String(cur).split('/').slice(0, -1).join('/');
        if (cur === stopAt || (!parent || parent === cur)) {
          // 任务根目录本身不存在（手输的新文件夹名等）：按空目录渲染
          data = { path: cur, items: [] };
          break;
        }
        cur = parent;
      }
    }
    store.assetPickerPath = data.path === '.' ? '' : data.path;
    $('#asset-picker-path').textContent = `data_root/${store.assetPickerPath}`;

    const parent = store.assetPickerPath.split('/').slice(0, -1).join('/');
    const base = store.assetPickerRoot ? store.assetPickerRoot.replace(/\/$/, '') + '/' : '';
    const relative = (item) => (item.path.startsWith(base) ? item.path.slice(base.length) : item.path);
    // 跨文件夹文件（不在当前任务目录下）：勾选值是 data_root 全路径，直接引用会
    // 在运行时找不到文件。记录到映射表，确认时自动复制进当前任务目录（等价本机上传）。
    const isOutside = (item) => !item.path.startsWith(base);
    if (!store.assetPickerOutside) store.assetPickerOutside = new Map();
    data.items.forEach((item) => {
      if (!item.directory && isOutside(item)) store.assetPickerOutside.set(relative(item), item.path);
    });
    const extRe = store.assetPickerCategory === 'references'
      ? /\.(mp4|mov|m4v|webm|mp3|wav|m4a|aac|flac|ogg)$/i
      : /\.(png|jpe?g|webp)$/i;
    const allowed = (item) => extRe.test(item.name);

    // 目录过滤：隐藏内部目录（seedance/ tasks/），并根据类别过滤无关目录。
    // 选音视频 → 隐藏 anchor 图片目录；选图片 → 隐藏音视频目录（references/ audio/ 等）。
    const INTERNAL_DIR = /^(seedance|tasks|\.|\.\.)$/i;
    const allowedDir = (item) => {
      if (INTERNAL_DIR.test(item.name)) return false;
      if (store.assetPickerCategory === 'references') {
        return !/^anchors?$|anchor/i.test(item.name);
      }
      return !/^(references?|audio|videos?)$/i.test(item.name);
    };

    const root = store.assetPickerRoot ? store.assetPickerRoot.replace(/\/$/, '') : '';
    // 当前目录下符合类别的文件数
    const currentFiles = data.items.filter((item) => !item.directory && allowed(item));
    // 若当前目录（默认子目录）没有可选文件，但任务主目录里有同类文件，引导用户去主目录找
    // 注意：root 目录（如 anchor-references/）可能不存在，请求失败时须跳过引导，否则会中断
    // 后续的列表渲染，导致上一次打开 picker 的旧文件残留显示。
    let rootHint = '';
    if (currentFiles.length === 0 && store.assetPickerPath && store.assetPickerPath !== root) {
      try {
        const rootData = await api(`/api/files?root=data_root&path=${encodeURIComponent(root)}`);
        const rootFiles = (rootData.items || []).filter((item) => !item.directory && allowed(item));
        if (rootFiles.length > 0) {
          const label = store.assetPickerCategory === 'anchors' ? '图片' : '音视频';
          rootHint = `<button class="asset-root-hint" onclick="browseAssets('${escapeAttr(root)}')"><span>💡 当前目录没有可选${label}，主目录里有 ${rootFiles.length} 个</span><span>去主目录 ›</span></button>`;
        }
      } catch {
        // root 目录不存在，跳过主目录引导，继续渲染当前目录列表
      }
    }

    // 现场生成候选引导：只要存在 generated/ 目录就提示，方便用户同时看到「现场生成的候选」和「自己上传的图」。
    let generatedHint = '';
    if (store.assetPickerCategory === 'anchors') {
      const generatedDir = data.items.find((item) => item.directory && item.name === 'generated');
      if (generatedDir) {
        const hint = currentFiles.length === 0
          ? '🎬 现场生成的候选在 generated/ 里（尚未设为 Anchor）'
          : '💡 generated/ 里还有现场生成的候选，需要的话也可进入选取';
        generatedHint = `<button class="asset-generated-hint" onclick="browseAssets('${escapeAttr(generatedDir.path)}')"><span>${hint}</span><span>进入 ›</span></button>`;
      } else if (/\/generated(\/|$)/.test(store.assetPickerPath)) {
        generatedHint = `<div class="asset-generated-tip">这些是现场生成的候选。若要固定到正式目录（anchors/ 根目录），请在 Anchor 审核页「设为 Anchor」。</div>`;
      }
    }

    const list = $('#asset-picker-list');
    const visibleItems = data.items.filter((item) => (item.directory ? allowedDir(item) : allowed(item)));
    const hasVisibleDirs = data.items.some((item) => item.directory && allowedDir(item));
    list.innerHTML =
      (store.assetPickerPath
        ? `<button onclick="browseAssets('${escapeAttr(parent)}')"><span>上一级</span><span>..</span></button>`
        : '') +
      rootHint +
      generatedHint +
      data.items
        .map((item) =>
          item.directory
            ? (allowedDir(item)
                ? `<button onclick="browseAssets('${escapeAttr(item.path)}')"><span>${escapeHtml(item.name)}</span><span>›</span></button>`
                : '')
            : allowed(item)
              ? `<label class="file-option">${(store.assetPickerCategory === 'anchors' || store.assetPickerCategory === 'anchor-references') ? `<img class="file-thumb" src="/api/file-preview?root=data_root&path=${encodeURIComponent(item.path)}" loading="lazy" onerror="this.style.display='none'" alt="">` : ''}<span class="file-name">${escapeHtml(item.name)}</span>${store.assetPickerCategory === 'references' && !isOutside(item) ? `<span class="file-kind ${isAudioName(item.name) ? 'kind-audio' : 'kind-video'}">${isAudioName(item.name) ? '🎵 音频' : '🎬 视频'}</span>` : ''}${isOutside(item) ? '<span class="file-kind kind-copy" title="不在当前任务文件夹内，添加时会自动复制过来">⧉ 跨文件夹 · 添加时复制</span>' : ''}<input type="checkbox" value="${escapeHtml(relative(item))}" ${store.assetPickerSelected.has(relative(item)) ? 'checked' : ''} onchange="toggleAsset(this)"></label>`
              : ''
        )
        .join('') +
      // 空状态提示：当前目录（及其可见子目录）都没有可选文件——给出可直接点击的上传入口
      (visibleItems.length === 0 && !hasVisibleDirs
        ? (store.assetPickerCategory === 'anchor-references'
            ? `<div class="asset-empty-tip">📂 当前目录还没有参考图。<div class="asset-empty-actions"><button class="secondary small" onclick="switchPickerTab('upload')">⬆ 从本机上传</button></div>或手动把图片放到：<br><code>data/${escapeHtml(store.assetPickerRoot || store.assetPickerPath || '<任务文件夹>/anchors/anchor-references')}</code></div>`
            : `<div class="asset-empty-tip">📂 当前目录没有可选${store.assetPickerCategory === 'references' ? '音视频' : '图片'}。<div class="asset-empty-actions"><button class="secondary small" onclick="switchPickerTab('upload')">⬆ 从本机上传</button></div>也可以把文件手动放到任务文件夹后重新打开。</div>`)
        : '');
  } catch (e) {
    toast(e.message);
  }
}

export function toggleAsset(input) {
  if (input.checked) {
    store.assetPickerSelected.add(input.value);
  } else {
    store.assetPickerSelected.delete(input.value);
  }
  _updatePickerConfirmBtn();
}

// 把文件合并进隐藏数据字段（追加去重，不覆盖已有内容）。
// fillBlank：#audio-refs 按行号与 #references 配对，空行是「该视频无独立音频」的占位，
// 新音频优先填入空占位行而不是追加到末尾，避免错位配对。
function _mergeIntoField(selector, files, { fillBlank = false } = {}) {
  const el = $(selector);
  if (!el) return;
  const raw = (el.value || '').split('\n').map((v) => v.trim());
  for (const f of files) {
    if (raw.includes(f)) continue;
    if (fillBlank) {
      const idx = raw.findIndex((v) => !v);
      if (idx >= 0) { raw[idx] = f; continue; }
    }
    raw.push(f);
  }
  el.value = raw.join('\n');
}

// 跨文件夹勾选的文件在确认时复制进当前任务目录（服务端复制，源文件不动），
// 复制后的本地路径替换原勾选值——与「本机上传」完全同语义。
// 复制期间复用上传中的按钮禁用；同名冲突先确认再覆盖（与上传 tab 一致）。
async function _importOutsideSelection() {
  const outside = store.assetPickerOutside;
  if (!outside || outside.size === 0) return;
  const selected = [...store.assetPickerSelected].filter((v) => outside.has(v));
  if (!selected.length) return;
  const ctx = _pickerUploadContext();

  const existing = new Set();
  try {
    const data = await api(`/api/files?root=data_root&path=${encodeURIComponent(ctx.destRel)}`);
    (data.items || []).forEach((item) => { if (!item.directory) existing.add(item.name); });
  } catch { /* 目标目录不存在（新文件夹），无冲突 */ }
  const conflictNames = selected
    .map((v) => outside.get(v).split('/').pop())
    .filter((name) => existing.has(name));
  let overwrite = false;
  if (conflictNames.length) {
    overwrite = await window.showDeleteConfirm({
      title: '复制并覆盖同名文件',
      desc: `当前任务目录已有同名文件：${[...new Set(conflictNames)].join('、')}。\n跨文件夹选择的文件将复制并覆盖它们（源文件夹不受影响）。`,
      showFileOption: false,
      confirmText: '覆盖复制',
      danger: true,
    });
  }

  _pickerUpload.uploading = true;
  _updatePickerConfirmBtn();
  let copied = 0;
  let reused = 0;
  let skipped = 0;
  for (const value of selected) {
    const src = outside.get(value);
    const name = src.split('/').pop();
    if (conflictNames.includes(name) && !overwrite) {
      store.assetPickerSelected.delete(value);
      skipped += 1;
      continue;
    }
    try {
      const result = await copyAssetFile({ src, taskId: ctx.taskId, category: store.assetPickerCategory, overwrite });
      const localValue = ctx.value(result.file || name);
      store.assetPickerSelected.delete(value);
      store.assetPickerSelected.add(localValue);
      copied += 1;
      reused += (result.migrated || []).length;
    } catch (e) {
      store.assetPickerSelected.delete(value);
      toast(`复制 ${name} 失败: ${e.message}`);
    }
  }
  _pickerUpload.uploading = false;
  _updatePickerConfirmBtn();
  if (copied) {
    toast(`已复制 ${copied} 个跨文件夹文件到当前任务目录${reused ? `，其中 ${reused} 个可直接复用已上传的云端 asset（无需重传）` : ''}${skipped ? `（${skipped} 个同名已跳过）` : ''}`);
  }
}

export async function confirmAssetSelection() {
  if (_pickerUpload.uploading) {
    toast('上传未完成，请稍候再添加');
    return;
  }
  // 强制校验：一个都没勾时拦截，引导勾选或去上传，而不是无变化地关掉弹窗
  if (!store.assetPickerSelected || store.assetPickerSelected.size === 0) {
    toast('请先勾选文件；文件夹里没有就切「⬆ 本机上传」');
    return;
  }
  // 跨文件夹勾选 → 先复制进当前任务目录，再走正常添加（全部失败/取消则终止）
  await _importOutsideSelection();
  if (!store.assetPickerSelected.size) {
    toast('没有可添加的文件（跨文件夹复制失败或已取消）');
    return;
  }
  if (store.anchorPickerMode) {
    // Import from anchor module dynamically to avoid circular deps
    import('./anchor.js').then(({ renderAnchorReferences, syncAspectSourceDropdowns }) => {
      [...store.assetPickerSelected].forEach((file) => {
        // 参考图 file 需相对 anchors/ 子目录（与上传、后端 _reference_source 解析一致）。
        // picker 的 assetPickerRoot 指向 .../anchors/anchor-references/，relative 截断后只剩
        // 纯文件名（如 IMG.jpg），需补回 anchor-references/ 前缀；含 / 的完整路径保持原样。
        const refFile = store.assetPickerCategory === 'anchor-references' && !file.includes('/')
          ? `anchor-references/${file}`
          : file;
        store.anchorReferences.push({
          id: `ref-${store.anchorReferences.length + 1}`,
          file: refFile,
          bindings: [],  // No auto-binding — user selects source per aspect in step 3
          note: '',
          remove_watermark: false,
        });
      });
      store.anchorPickerMode = false;
      renderAnchorReferences();
      syncAspectSourceDropdowns();
      // 参考图已即时落盘，刷新"还没有参考图"提示
      import('./anchor.js').then(({ checkAnchorRefDir }) => checkAnchorRefDir());
      closeAssetPicker();
    });
    return;
  }

  let target = store.assetPickerCategory === 'anchors' ? '#anchors' : '#references';
  // 参考音视频：按「文件类型」分别归位到正确 tab/字段，两个 tab 可共存（视频 + 独立音频对口型）——
  // 音频文件 → 音频 tab / #audio-refs；视频文件 → 视频 tab / #references。避免在视频 tab 选了音频却落到视频字段。
  if (store.assetPickerCategory === 'references') {
    const selected = [...store.assetPickerSelected];
    const audioFiles = selected.filter((f) => isAudioName(f));
    const videoFiles = selected.filter((f) => !isAudioName(f));
    if (videoFiles.length) {
      switchRefTab('video');
      _mergeIntoField('#references', videoFiles);
      // 若同时选了音频，保留进音频字段（共存）
      if (audioFiles.length) {
        _mergeIntoField('#audio-refs', audioFiles, { fillBlank: true });
      }
    } else {
      switchRefTab('audio');
      _mergeIntoField('#audio-refs', audioFiles, { fillBlank: true });
    }
    renderVideoAssetPreviews();
    // 新上传的文件已落盘，目录不再是"空"，同步刷新空目录提示
    checkTaskFolderEmpty();
    closeAssetPicker();
    return;
  }
  _mergeIntoField(target, [...store.assetPickerSelected]);
  renderVideoAssetPreviews();
  checkTaskFolderEmpty();
  closeAssetPicker();
}

// ── Folder Picker ───────────────────────────────────────────────────────────

export function openFolderPicker() {
  store.folderPath = '';
  store.folderPickerTarget = null;  // 任务文件夹选择器（区别于现场生成的 anchor 目录选择器）
  $('#folder-modal').hidden = false;
  browseFolder('');
}

export function closeFolderPicker() {
  $('#folder-modal').hidden = true;
}

export async function browseFolder(path) {
  try {
    const data = await api(`/api/files?root=data_root&path=${encodeURIComponent(path)}`);
    store.folderPath = data.path === '.' ? '' : data.path;
    $('#folder-path').textContent = `data_root/${store.folderPath}`;
    const parent = store.folderPath.split('/').slice(0, -1).join('/');
    // 只在顶层（data_root 根）对一级任务文件夹提供「删除文件夹」入口
    const isRoot = !store.folderPath;
    $('#folder-list').innerHTML =
      `<div class="folder-new">
        <input id="new-folder-name" type="text" placeholder="新建文件夹名称...">
        <button class="primary" onclick="createFolder()">新建</button>
      </div>` +
      (store.folderPath ? `<button onclick="browseFolder('${escapeAttr(parent)}')"><span>上一级</span><span>..</span></button>` : '') +
      data.items
        .filter((i) => i.directory)
        .map((i) => `<div class="folder-row">
          <button class="folder-row-main" onclick="browseFolder('${escapeAttr(i.path)}')"><span>${escapeHtml(i.name)}</span><span>›</span></button>
          ${isRoot ? `<button class="folder-row-del" onclick="confirmDeleteDataDir('${escapeAttr(i.name)}')" title="删除此任务文件夹及其所有任务与生成产物">🗑</button>` : ''}
        </div>`)
        .join('');
  } catch (e) {
    toast(e.message);
  }
}

export async function createFolder() {
  const input = $('#new-folder-name');
  const name = input.value.trim();
  if (!name) { toast('请输入文件夹名称'); return; }
  try {
    await post('/api/folders', { root: 'data_root', parent: store.folderPath, name });
    input.value = '';
    toast(`文件夹"${name}"已创建`);
    await browseFolder(store.folderPath);
  } catch (e) { toast(e.message); }
}

export async function confirmDeleteDataDir(dataDir) {
  // 先取关联信息，用于强确认弹窗明确列出级联删除的全部内容
  let usage;
  try {
    usage = await api(`/api/data-dirs/${encodeURIComponent(dataDir)}`);
  } catch (e) {
    toast(`获取目录信息失败: ${e.message}`);
    return;
  }

  const tasks = usage.tasks || [];
  const anchor = usage.anchor_task;
  const runTotal = (usage.video_runs || 0) + (usage.anchor_runs || 0);

  // 构造级联树：目录 → 各类资源 → 关联运行/产物
  const row = (children, label, detail) => `<div class="cascade-row"><span class="cascade-line">${children}</span><span class="cascade-label">${label}</span>${detail ? `<span class="cascade-detail">${detail}</span>` : ''}</div>`;

  let body = '';
  body += `<div class="cascade-root">📁 <strong>${escapeHtml(dataDir)}</strong></div>`;

  // 视频任务（每个任务单独一行，标注关联运行数）
  tasks.forEach((t, i) => {
    const isLast = i === tasks.length - 1 && !anchor;
    const detail = t.run_count > 0 ? `${t.run_count} 次运行 · 生成产物` : '无运行';
    body += row(isLast ? '└─' : '├─', `视频任务「${escapeHtml(t.name)}」`, detail);
  });

  // Anchor 任务
  if (anchor) {
    const detail = anchor.run_count > 0 ? `${anchor.run_count} 次运行 · 候选图` : '无运行';
    body += row('└─', `Anchor 任务「${escapeHtml(anchor.name)}」`, detail);
  }

  // 素材与缓存
  const refDetail = (usage.ref_count || 0) > 0 ? `${usage.ref_count} 个文件` : '空';
  body += row('├─', '参考音视频（references/）', refDetail);
  body += row('├─', 'Anchor 图片与候选（anchors/）', anchor ? '随 Anchor 任务删除' : '（无 Anchor 任务）');
  body += row(usage.has_seedance ? '└─' : '└─', 'Seedance 素材缓存', usage.has_seedance ? '存在' : '无');

  const totalTasks = tasks.length + (anchor ? 1 : 0);
  const summary = `<div class="cascade-summary">共 ${totalTasks} 个任务 · ${runTotal} 条运行记录 · 删除后不可恢复</div>`;

  const htmlDesc = body + summary;

  const ok = await window.showDeleteConfirm({
    title: '删除整个任务文件夹',
    htmlDesc,
    showFileOption: false,
    confirmText: '确认删除整个目录',
    danger: true,
  });
  if (!ok) return;

  try {
    await fetch(`/api/data-dirs/${encodeURIComponent(dataDir)}`, { method: 'DELETE' });
    toast(`已删除目录「${dataDir}」`);
    await browseFolder(store.folderPath);
    await loadTasks();
    await loadRuns();
  } catch (e) {
    toast(`删除失败: ${e.message}`);
  }
}

export async function chooseFolder() {
  const target = store.folderPickerTarget;
  const inputId = target === 'anchor' ? '#anchor-id' : '#task-dir';
  const newPath = store.folderPath || '';
  const oldPath = $(inputId).value.trim();

  // 切换任务文件夹时，若已填素材/歌词/约束，需清空并提醒确认
  if (inputId === '#task-dir' && newPath !== oldPath) {
    const hasSelected =
      lines('#anchors').length > 0 ||
      lines('#references').length > 0 ||
      lines('#audio-refs').length > 0 ||
      !!($('#lyrics')?.value.trim()) ||
      !!($('#constraints')?.value.trim());
    const promptTA = $('#prompt-preview');
    const hasCustomPrompt = store.customPromptDirty && (promptTA?.value || '').trim();
    if (hasSelected || hasCustomPrompt) {
      const ok = await window.showDeleteConfirm({
        title: '切换任务文件夹',
        desc: `切换将清空已选的 Anchor 图片、参考音视频、歌词、附加约束和自定义 Prompt。\n\n从「${oldPath || '(未设置)'}」切换到「${newPath || '(根目录)'}」`,
        showFileOption: false,
        confirmText: '确认切换',
        danger: false,
      });
      if (!ok) {
        store.folderPickerTarget = null;
        closeFolderPicker();
        return;  // 用户取消，保持原目录和已填内容不变
      }
    }
    // 清空上一个文件夹残留的素材、歌词、约束和自定义 Prompt
    $('#anchors').value = '';
    $('#references').value = '';
    $('#audio-refs').value = '';
    if ($('#lyrics')) $('#lyrics').value = '';
    if ($('#constraints')) $('#constraints').value = '';
    if (promptTA) promptTA.value = '';
    store.customPromptDirty = false;
    // 素材已清空，同步清掉编辑态，否则后续保存仍按「更新旧任务」弹二选一、
    // 重置按钮也停留在「取消」
    store.currentTask = null;
    store.pendingLyricsTimestamps = null;
    store.originalPadMode = null;
    setTaskResetBtnLabel();
    _updatePromptModeBadge();
    renderVideoAssetPreviews();
  }

  // 切换 Anchor 任务文件夹时，清空上一个目录残留的参考图（与任务文件夹清空逻辑一致）
  let anchorMod = null;
  if (inputId === '#anchor-id' && newPath !== oldPath) {
    const hasRefs = store.anchorReferences.length > 0;
    if (hasRefs) {
      const ok = await window.showDeleteConfirm({
        title: '切换任务文件夹',
        desc: `切换将清空已选的参考图片。\n\n从「${oldPath || '(未设置)'}」切换到「${newPath || '(根目录)'}」`,
        showFileOption: false,
        confirmText: '确认切换',
        danger: false,
      });
      if (!ok) {
        store.folderPickerTarget = null;
        closeFolderPicker();
        return;  // 用户取消，保持原目录和已选参考图不变
      }
    }
    store.anchorReferences = [];
    store.currentAnchorTask = null;
    anchorMod = await import('./anchor.js');
    anchorMod.syncAspectSourceDropdowns();
    anchorMod.renderAnchorReferences();
  }

  $(inputId).value = newPath;
  store.folderPickerTarget = null;
  closeFolderPicker();
  // 选择的是任务文件夹时，检测目录内是否已有素材
  if (inputId === '#task-dir') checkTaskFolderEmpty();
  // 选择的是 Anchor 任务文件夹时，检查目录内是否已有参考图
  if (inputId === '#anchor-id') anchorMod?.checkAnchorRefDir?.();
}

export function taskFolderName() {
  return $('#task-dir').value.trim();
}

// ── Task Form ───────────────────────────────────────────────────────────────

export function formTask() {
  const name = ($('#task-name')?.value || '').trim();
  const taskDir = $('#task-dir').value.trim();
  if (!name) throw new Error('请输入任务名称');
  if (!taskDir) throw new Error('请选择任务文件夹');
  const dataRoot = store.workspaceSettings?.data_root || '';
  const dirName = taskDir.split('/').pop() || taskDir;
  return {
    name,
    task_dir: dataRoot + '/' + taskDir,
    data_dir: dirName,
    mode: $('[name=mode]:checked').value,
    candidates: Number($('#candidates').value),
    filename_prefix: name,
    anchors: lines('#anchors').map((file, i) => ({ key: `anchor-${i + 1}`, label: `Anchor ${i + 1}`, file })),
    references: (() => {
      const videoRefs = lines('#references');
      const audioRefs = lines('#audio-refs');
      // 当前在音频 tab 下：纯音频模式，不传视频
      const isAudioTab = document.querySelector('.ref-tab.active[data-ref-tab]')?.dataset?.refTab === 'audio';
      if (isAudioTab) {
        return audioRefs.map((file, i) => ({
          name: `reference-${i + 1}`,
          file,
          duration: 15,
          pass_reference_audio: true,
          pass_reference_video: false,
          pad_mode: 'none',
        }));
      }
      // 视频 tab：传视频 + 可选「独立音频」（音频 tab 传的，对口型源，优先于从视频提取）
      // 独立音频按行号与视频一一配对：保留 #audio-refs 中的空行占位（editTask 回填时按
      // reference 顺序生成，空行 = 该视频无独立音频），因此必须用原始行读取而不是 lines() 过滤
      const padEl = document.getElementById('pad-mode');
      const passAudioEl = document.getElementById('pass-reference-audio');
      const audioRaw = ($('#audio-refs')?.value || '').split('\n').map((v) => v.trim());
      const audioCount = audioRaw.filter(Boolean).length;
      if (audioCount > videoRefs.length) {
        throw new Error(`独立音频（${audioCount} 个）多于参考视频（${videoRefs.length} 个），请按「每行视频对应一行音频、无则留空」配对`);
      }
      return videoRefs.map((file, i) => {
        const ownAudio = audioRaw[i] || null;
        return {
          name: `reference-${i + 1}`,
          file,
          duration: 15,
          // 有独立音频 → 用独立音频对口型（pass_reference_audio 强制 true，上传它）；
          // 无独立音频 → 按「传参考音频」勾选决定是否从视频提取
          pass_reference_audio: ownAudio ? true : (passAudioEl?.checked ?? true),
          pass_reference_video: true,
          pad_mode: padEl?.value || 'none',
          ...(ownAudio ? { audio_file: ownAudio } : {}),
        };
      });
    })(),
    lyrics: $('#lyrics').value.trim(),
    constraints: $('#constraints').value.trim(),
    // 自定义 prompt：仅当用户在预览框手动编辑过才带上，否则后端自动生成
    ...(_promptEdited() ? { custom_prompt: ($('#prompt-preview')?.value || '').trim() } : {}),
    lyrics_timestamps: store.currentTask?.lyrics_timestamps || store.pendingLyricsTimestamps || [],
    // 高级视频设置（默认值与后端 VideoTaskAdapter 一致）
    resolution: $('#video-resolution')?.value || '720p',
    ratio: $('#video-ratio')?.value || '9:16',
    generate_audio: $('#video-generate-audio')?.checked ?? false,
    watermark: $('#video-watermark')?.checked ?? false,
    output_format: $('#video-output-format')?.value || 'mp4',
  };
}

// 对口型 / 口型+动作 必须填歌词：在「启动生成」前就拦截，避免跑到后端生成时才失败
// （保存草稿不强制，与后端 store.validate strict=False 语义一致）
function _validateLyricsForMode(data) {
  const needLyrics = data.mode === 'lip_sync' || data.mode === 'dance_lip_sync';
  if (needLyrics && !(data.lyrics || '').trim()) {
    throw new Error('「' + (data.mode === 'lip_sync' ? '对口型' : '口型 + 动作') + '」模式必须填写歌词才能生成');
  }
}

export function switchRefTab(tab) {
  const audioTA = $('#audio-refs');
  const padRow = $('.pad-mode-row');
  const passAudioWrap = $('#pass-audio-wrap');
  const mode = $('[name=mode]:checked')?.value;
  // #references 与 #audio-refs 均为隐藏数据载体（不直接显示裸文本框），
  // 选中文件的展示统一走 chips / previews，随 tab 切换重渲染。
  if (audioTA) audioTA.hidden = true;
  if (tab === 'video') {
    if (padRow) padRow.style.display = '';
    // motion 模式不显示"传参考音频"
    if (passAudioWrap) passAudioWrap.style.display = mode === 'motion' ? 'none' : '';
  } else {
    // 音频 tab：隐藏时长对齐 + "传参考音频"（选音频 tab 就是要传音频）
    if (padRow) padRow.style.display = 'none';
    if (passAudioWrap) passAudioWrap.style.display = 'none';
  }
  $$('.ref-tab[data-ref-tab]').forEach(b => b.classList.toggle('active', b.dataset.refTab === tab));
  renderVideoAssetPreviews();
}

export function updateMode() {
  const radio = $('[name=mode]:checked');
  if (!radio) return;
  const mode = radio.value;
  $('#lyrics-wrap').style.display = mode === 'motion' ? 'none' : 'flex';
  // "传参考音频"的显示由当前 ref-tab 决定（switchRefTab），这里只处理 motion 强制不传
  const cb = $('#pass-reference-audio');
  const wrap = $('#pass-audio-wrap');
  if (mode === 'motion' && cb && wrap) {
    wrap.style.display = 'none';
    cb.checked = false;
  }
  // 切换模式后同步当前 ref-tab 的显示状态
  const currentTab = document.querySelector('.ref-tab.active[data-ref-tab]')?.dataset?.refTab;
  if (currentTab) switchRefTab(currentTab);
  // "传参考视频"选项：lip_sync 通过 ref-tabs 控制（视频/音频 tab），不显示 checkbox
  // dance_lip_sync / motion 强制传视频，也不显示
  const videoWrap = $('#pass-video-wrap');
  if (videoWrap) videoWrap.style.display = 'none';
  // 音频 tab：motion 模式隐藏，对口型模式显示
  const audioTab = document.querySelector('[data-ref-tab="audio"]');
  if (audioTab) audioTab.style.display = mode === 'motion' ? 'none' : '';
  // 如果当前在音频 tab 且切换到了 motion，强制切回视频 tab
  if (mode === 'motion' && audioTab && audioTab.classList.contains('active')) {
    switchRefTab('video');
  }
}

/* ── 时长对齐 tab 切换 ── */
export function switchPadMode(mode) {
  const el = document.getElementById('pad-mode');
  if (el) el.value = mode;
  document.querySelectorAll('[data-pad-mode]').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.padMode === mode);
  });
}

// ── Auto-Fill ───────────────────────────────────────────────────────────────
// (deprecated — folder name is the sole identifier; kept for backwards compat)

export function autoFillTaskFields(source) {
  // no-op: folder name is the only entry point now
}

export function markAsManuallyEdited(input) {
  input.dataset.autoFilled = 'false';
}

// ── Task CRUD ───────────────────────────────────────────────────────────────

export async function saveTask(event, mode = 'auto') {
  event?.preventDefault();
  let data;
  try {
    data = formTask();
  } catch (e) {
    toast(e.message);
    return null;
  }
  const newId = `${data.data_dir}__${data.name}`;
  const editingId = store.currentTask?.id;

  if (mode === 'auto') {
    if (editingId && editingId !== newId) {
      // 改了名字或文件夹：让用户选择新建还是更新
      showSaveModeDialog(data, editingId);
      return;
    }
    // 编辑已有任务时改了「时长对齐（pad_mode）」：强制二选一（推荐新建）
    const curPad = $('#pad-mode')?.value || 'none';
    if (editingId && store.originalPadMode != null && curPad !== store.originalPadMode) {
      showSaveModeDialog(data, editingId, 'padMode', { from: store.originalPadMode, to: curPad });
      return;
    }
    // 编辑同名任务（名字/文件夹未变）：视为更新
    if (editingId && editingId === newId) {
      mode = 'update';
    }
  }

  try {
    const task = await _doSave(data, editingId, mode);
    store.currentTask = task;
    toast('任务已保存');
    await loadTasks();
    return task;
  } catch (e) {
    toast(e.message);
    return null;
  }
}

async function _doSave(data, editingId, mode) {
  const newId = `${data.data_dir}__${data.name}`;
  // 检查同名任务是否存在（同名更新除外）
  const existing = store.tasks?.find(t => t.id === newId);
  if (existing && mode !== 'update') {
    throw new Error(`同名任务"${data.name}"已存在，请改名或选择更新已有任务`);
  }
  const task = await post('/api/tasks', data);
  // mode=update 且 id 变了（改名/改文件夹）：先保存新任务成功，再删旧任务。
  // 若先删后存，保存校验失败会把旧任务一并丢掉（无回滚）
  if (mode === 'update' && editingId && editingId !== newId) {
    try {
      await api(`/api/tasks/${encodeURIComponent(editingId)}`, { method: 'DELETE' });
    } catch (e) {
      toast(`旧任务「${editingId}」删除失败，请手动删除: ${e.message}`);
    }
  }
  return task;
}

function showSaveModeDialog(data, editingId, reason = 'identity', extra = {}) {
  const tName = escapeHtml(store.currentTask?.name || '');
  let desc;
  if (reason === 'padMode') {
    const from = escapeHtml(PAD_MODE_NAMES[extra.from] || extra.from || '');
    const to = escapeHtml(PAD_MODE_NAMES[extra.to] || extra.to || '');
    desc = `你正在编辑已有任务 <strong>${tName}</strong>，并把「时长对齐」从 <strong>${from}</strong> 改成了 <strong>${to}</strong>。`
      + `对齐方式会影响产物重建，建议保存为新任务以保留原任务。`;
  } else {
    desc = `你正在编辑已有任务 <strong>${tName}</strong>，但修改了名称或文件夹，这会导致创建新任务。`;
  }
  // padMode 弹窗保存成功后同步原始值，避免下次保存重复弹窗
  const syncPadMode = () => { if (reason === 'padMode') store.originalPadMode = extra.to; };
  const modal = document.createElement('div');
  modal.className = 'modal';
  modal.innerHTML = `<div class="modal-card" style="max-width:400px">
    <h3>保存方式</h3>
    <p>${desc}</p>
    <div class="actions" style="flex-direction:column;gap:8px">
      <button onclick="this.closest('.modal').remove(); window._saveAsNew?.()" style="width:100%">保存为新任务</button>
      <button class="secondary" onclick="this.closest('.modal').remove(); window._updateExisting?.()" style="width:100%">更新原任务</button>
      <button class="secondary" onclick="this.closest('.modal').remove()" style="width:100%">取消</button>
    </div>
  </div>`;
  document.body.appendChild(modal);
  modal.hidden = false;

  window._saveAsNew = async () => {
    try {
      const task = await _doSave(data, null, 'new');
      store.currentTask = task;
      syncPadMode();
      toast('已保存为新任务');
      await loadTasks();
      _afterSaveMaybeStart();
    } catch (e) { toast(e.message); }
  };
  window._updateExisting = async () => {
    try {
      const task = await _doSave(data, editingId, 'update');
      store.currentTask = task;
      syncPadMode();
      toast('任务已更新');
      await loadTasks();
      _afterSaveMaybeStart();
    } catch (e) { toast(e.message); }
  };
}

// 保存方式弹窗保存成功后，若此前是「启动」触发的保存，直接接续启动流程
function _afterSaveMaybeStart() {
  if (!store._pendingStart) return;
  store._pendingStart = false;
  if (store.currentTask?.id) requestStart(store.currentTask.id);
}

const PAD_MODE_NAMES = { none: '原始时长', back: '后补齐', front: '前补齐' };

function _taskConfigChips(t) {
  const chips = [];
  chips.push(`<span class="cfg-chip cfg-mode">${modeName(t.mode)}</span>`);
  // 时长对齐（取第一个 reference 的 pad_mode，旧数据缺省 back）
  const pad = t.references?.[0]?.pad_mode || 'back';
  chips.push(`<span class="cfg-chip">⏱ ${PAD_MODE_NAMES[pad] || pad}</span>`);
  // 音视频传入
  const hasVideo = t.references?.some((r) => r.pass_reference_video !== false);
  const hasAudio = t.references?.some((r) => r.pass_reference_audio !== false);
  if (hasVideo && hasAudio) chips.push(`<span class="cfg-chip">🎬 视频+音频</span>`);
  else if (hasVideo) chips.push(`<span class="cfg-chip">🎬 仅视频</span>`);
  else if (hasAudio) chips.push(`<span class="cfg-chip">🎵 仅音频</span>`);
  // 歌词时间戳（打了几个有效时间点）
  const timedCount = (t.lyrics_timestamps || []).filter((x) => x?.time != null).length;
  if (timedCount > 0) chips.push(`<span class="cfg-chip cfg-ts">🎤 时间戳 ${timedCount} 句</span>`);
  // 候选数
  chips.push(`<span class="cfg-chip">${t.candidates} 候选</span>`);
  return chips.join('');
}

export async function loadTasks() {
  store.tasks = await api('/api/tasks');
  _renderTaskList();
}

// ── 任务列表按文件夹分组 ─────────────────────────────────────────────────────
// 素材/asset/运行都以文件夹为单位组织，列表按文件夹分组展示符合心智模型；
// 不同文件夹下的同名任务（如 街道风/冻结 与 冻结/冻结）靠分组头自然区分。
// 折叠状态记在 localStorage，跨会话保留。

const COLLAPSED_KEY = 'idolflow-task-collapsed-folders';

function _collapsedFolders() {
  if (!store.collapsedFolders) {
    try {
      store.collapsedFolders = new Set(JSON.parse(localStorage.getItem(COLLAPSED_KEY) || '[]'));
    } catch {
      store.collapsedFolders = new Set();
    }
  }
  return store.collapsedFolders;
}

export function toggleTaskGroup(dir) {
  const set = _collapsedFolders();
  if (set.has(dir)) set.delete(dir); else set.add(dir);
  try { localStorage.setItem(COLLAPSED_KEY, JSON.stringify([...set])); } catch { /* ignore */ }
  _renderTaskList();
}

function _fmtMtimeShort(mtime) {
  if (!mtime) return '';
  const d = new Date(mtime * 1000);
  if (Number.isNaN(d.getTime())) return '';
  const p = (n) => String(n).padStart(2, '0');
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function _renderTaskList() {
  const list = $('#task-list');
  if (!list) return;
  _updateSortButtons('#task-sort-group', store.taskSort);
  const taskCmp = (a, b) => {
    const keyA = a.name || a.id;
    const keyB = b.name || b.id;
    switch (store.taskSort) {
      case 'name-asc': return keyA.localeCompare(keyB, 'zh-Hans-CN');
      case 'name-desc': return keyB.localeCompare(keyA, 'zh-Hans-CN');
      // 时间排序：time-desc 最新在前，time-asc 最早在前（mtime 缺省按 0 兜底）
      case 'time-asc': return (a.mtime || 0) - (b.mtime || 0);
      default: return (b.mtime || 0) - (a.mtime || 0);
    }
  };
  // 按文件夹分组；组间排序：时间模式按组内最新编辑时间，名字模式按文件夹名
  const groups = new Map();
  for (const t of store.tasks) {
    const dir = t.data_dir || '未分组';
    if (!groups.has(dir)) groups.set(dir, []);
    groups.get(dir).push(t);
  }
  const groupNewest = (dir) => Math.max(...groups.get(dir).map((t) => t.mtime || 0));
  const dirs = [...groups.keys()].sort((x, y) => {
    if (store.taskSort === 'name-asc') return x.localeCompare(y, 'zh-Hans-CN');
    if (store.taskSort === 'name-desc') return y.localeCompare(x, 'zh-Hans-CN');
    if (store.taskSort === 'time-asc') return groupNewest(x) - groupNewest(y);
    return groupNewest(y) - groupNewest(x);
  });

  const card = (t) => {
    // 缺 Anchor 或参考音视频的任务不能直接运行（与表单「启动生成」的前置校验一致）
    const missing = [];
    if (!(t.anchors || []).length) missing.push('Anchor 图片');
    if (!(t.references || []).length) missing.push('参考音视频');
    const runDisabled = missing.length ? ' disabled' : '';
    const runTitle = missing.length ? ` title="缺少${missing.join('、')}，请先编辑补全"` : '';
    return `<article class="task" data-id="${escapeHtml(t.id)}">
      <div class="task-info">
        <h3>${escapeHtml(t.name || t.id)}</h3>
        <div class="meta">${(t.anchors || []).length} anchors · ${escapeHtml(t.id)}</div>
        <div class="cfg-chips">${_taskConfigChips(t)}</div>
      </div>
      <div class="actions">
        <button class="secondary" data-action="task-assets">Assets</button>
        <button class="secondary" data-action="task-edit">编辑</button>
        <button data-action="task-run"${runDisabled}${runTitle}>运行</button>
        <button class="danger" onclick="confirmDeleteTask('${escapeAttr(t.id)}')">删除</button>
      </div>
    </article>`;
  };

  const collapsed = _collapsedFolders();
  const html = dirs
    .map((dir) => {
      const tasks = [...groups.get(dir)].sort(taskCmp);
      const isCollapsed = collapsed.has(dir);
      const newest = _fmtMtimeShort(groupNewest(dir));
      const head = `<button type="button" class="task-group-head" onclick="toggleTaskGroup('${escapeAttr(dir)}')" title="${isCollapsed ? '展开' : '折叠'}该文件夹的任务">
        <span class="group-caret${isCollapsed ? '' : ' open'}">▸</span>
        <span class="group-name">📁 ${escapeHtml(dir)}</span>
        <span class="group-count">${tasks.length} 个任务</span>
        ${newest ? `<span class="group-meta">最近编辑 ${newest}</span>` : ''}
      </button>`;
      const body = isCollapsed
        ? ''
        : `<div class="task-group-body">${tasks.map(card).join('')}</div>`;
      return `<section class="task-group" data-dir="${escapeAttr(dir)}">${head}${body}</section>`;
    })
    .join('');
  list.innerHTML = html || renderEmptyState('📋', '还没有保存任务', '填写表单后点击"保存任务"即可添加');
}

export function toggleTaskSort(mode) {
  store.taskSort = mode;
  _renderTaskList(); // 内部会同步按钮高亮
}

function _updateSortButtons(groupSelector, mode) {
  const group = $(groupSelector);
  if (!group) return;
  group.querySelectorAll('.sort-toggle').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.sort === mode);
  });
}

export function editTask(id) {
  const t = store.tasks.find((x) => x.id === id);
  if (!t) return;
  store.currentTask = t;
  const nameEl = $('#task-name');
  if (nameEl) nameEl.value = t.name || '';
  // 任务文件夹回填：优先用 task_dir（绝对路径）剥掉 data_root 前缀还原相对路径，
  // 避免嵌套目录（如 a/b）被 data_dir（仅末级目录名）截断，保存后任务跑到错误位置
  let dir = t.data_dir || '';
  const dataRoot = store.workspaceSettings?.data_root || '';
  if (t.task_dir && dataRoot) {
    const norm = (p) => p.replace(/\/+$/, '');
    if (norm(t.task_dir).startsWith(norm(dataRoot) + '/')) {
      dir = norm(t.task_dir).slice(norm(dataRoot).length + 1);
    }
  }
  $('#task-dir').value = dir;
  // 规范化路径：去掉可能存在的 data_dir 前缀（历史脏数据），保证相对 task_dir
  const stripDirPrefix = (file) => {
    const prefix = dir.replace(/\/+$/, '') + '/';
    return file && file.startsWith(prefix) ? file.slice(prefix.length) : file;
  };
  $('#candidates').value = t.candidates;
  $('#anchors').value = t.anchors.map((x) => stripDirPrefix(x.file)).join('\n');
  // 参考音视频：纯音频任务（pass_reference_video=false）写入音频字段，否则写入视频字段
  // 视频任务若有独立音频（audio_file，对口型源），回填到音频字段，编辑时可见、可改
  const isAudioOnly = t.references?.length > 0 && t.references.every(r => r.pass_reference_video === false);
  const refFiles = t.references.map((x) => stripDirPrefix(x.file));
  // 独立音频按 reference 顺序回填（无 audio_file 的位置留空行占位），
  // 保持与 #references 行号的对应关系；formTask 按行号配对，否则编辑再保存会张冠李戴
  const audioFiles = t.references.map((x) => (x.audio_file ? stripDirPrefix(x.audio_file) : ''));
  if (isAudioOnly) {
    $('#references').value = '';
    $('#audio-refs').value = refFiles.join('\n');
    switchRefTab('audio');
  } else {
    $('#references').value = refFiles.join('\n');
    $('#audio-refs').value = audioFiles.join('\n');
    switchRefTab('video');
  }
  const passAudio = t.references[0]?.pass_reference_audio;
  const passAudioEl = document.getElementById('pass-reference-audio');
  if (passAudioEl) passAudioEl.checked = passAudio !== false;
  const passVideo = t.references[0]?.pass_reference_video;
  const passVideoEl = document.getElementById('pass-reference-video');
  if (passVideoEl) passVideoEl.checked = passVideo !== false;
  const padMode = t.references[0]?.pad_mode || 'none';
  switchPadMode(padMode);
  store.originalPadMode = padMode;  // 记录原始对齐方式，供保存时检测用户改动
  $('#lyrics').value = t.lyrics || '';
  if (!store.currentTask.lyrics_timestamps) store.currentTask.lyrics_timestamps = [];
  $('#constraints').value = t.constraints || '';

  // 回填高级视频设置（默认值与后端 VideoTaskAdapter 一致）
  const resEl = $('#video-resolution');
  if (resEl) resEl.value = t.resolution || '720p';
  const ratioEl = $('#video-ratio');
  if (ratioEl) ratioEl.value = t.ratio || '9:16';
  const genAudioEl = $('#video-generate-audio');
  if (genAudioEl) genAudioEl.checked = t.generate_audio === true;
  const wmEl = $('#video-watermark');
  if (wmEl) wmEl.checked = t.watermark === true;
  const fmtEl = $('#video-output-format');
  if (fmtEl) fmtEl.value = t.output_format || 'mp4';

  // 回填自定义 prompt：有则显示为自定义（用户可继续编辑），无则保持自动生成
  const promptTA = $('#prompt-preview');
  const savedCustom = (t.custom_prompt || '').trim();
  if (promptTA) promptTA.value = savedCustom;
  store.customPromptDirty = !!savedCustom;
  _updatePromptModeBadge();

  const radio = $(`[name=mode][value="${t.mode}"]`);
  if (radio) radio.checked = true;
  $$('.mode').forEach((m) => m.classList.toggle('active', m.contains(radio)));
  updateMode();
  renderVideoAssetPreviews();
  checkTaskFolderEmpty();
  checkMissingAssets(id);
  setTaskResetBtnLabel();
  // 编辑后滚动到「素材」区，让用户直接看到已选素材与现场生成候选提示
  const materialsPanel = $('#task-materials-panel');
  if (materialsPanel) materialsPanel.scrollIntoView({ block: 'start', behavior: 'auto' });
  else scrollTo({ top: 0, behavior: 'auto' });
}

// 检测任务引用的文件是否已被删除/不存在，给出明确提示
export async function checkMissingAssets(taskId) {
  const banner = $('#missing-assets-banner');
  if (!banner) return;
  if (!taskId) {
    banner.hidden = true;
    banner.innerHTML = '';
    return;
  }
  try {
    const result = await api(`/api/tasks/${encodeURIComponent(taskId)}/missing-assets`);
    const missing = [...(result.missing_anchors || []), ...(result.missing_references || [])];
    if (!missing.length) {
      banner.hidden = true;
      banner.innerHTML = '';
      return;
    }
    const names = missing.map((m) => m.file.split('/').pop()).join('、');
    banner.hidden = false;
    banner.innerHTML = `⚠️ 以下文件已不存在：<strong>${escapeHtml(names)}</strong>。请在素材区移除或重新选择，否则保存/生成会失败。`;
    // 标记预览区对应文件
    markMissingPreviews(missing.map((m) => m.file));
  } catch (e) {
    // 检测失败（服务异常等）不静默吞掉：明确提示，避免用户误以为素材都在
    banner.hidden = false;
    banner.innerHTML = `⚠️ 素材状态检测失败（${escapeHtml(e.message)}），请确认服务正常后重试`;
  }
}

function markMissingPreviews(missingFiles) {
  const set = new Set(missingFiles);
  $$('.asset-figure').forEach((fig) => {
    const file = fig.dataset.file;
    if (file && set.has(file)) {
      fig.classList.add('missing');
      const cap = fig.querySelector('figcaption');
      if (cap) cap.textContent = cap.textContent.replace(/（文件已不存在）$/, '') + '（文件已不存在）';
    }
  });
}

export function resetForm() {
  $('#task-form').reset();
  // 显式清空素材字段（form.reset 对 hidden input 的清空在部分场景下不可靠）
  $('#anchors').value = '';
  $('#references').value = '';
  $('#audio-refs').value = '';
  store.currentTask = null;
  store.pendingLyricsTimestamps = null;
  store.originalPadMode = null;
  // 清空自定义 prompt 状态（预览框在 form 外，form.reset 不会清它）
  const promptTA = $('#prompt-preview');
  if (promptTA) promptTA.value = '';
  store.customPromptDirty = false;
  _updatePromptModeBadge();
  $$('.mode').forEach((m, i) => m.classList.toggle('active', i === 0));
  updateMode();
  // 重置到视频 tab 并恢复被音频 tab 隐藏的行（pad-mode / 传参考音频），
  // 否则上次编辑纯音频任务后新建，表单仍停留在音频 tab，误存为纯音频任务
  switchRefTab('video');
  renderVideoAssetPreviews();
  checkMissingAssets('');
  checkTaskFolderEmpty();
  setTaskResetBtnLabel();
}

// 编辑态显示「取消」，非编辑态显示「新任务」
export function setTaskResetBtnLabel() {
  const btn = $('#task-reset-btn');
  if (btn) btn.textContent = store.currentTask ? '取消' : '新任务';
}

// 把 mtime 纳秒时间戳格式化为「MM-DD HH:mm」可读时间；无效时返回空串
function _fmtMtime(mtimeNs) {
  if (!mtimeNs) return '';
  try {
    const d = new Date(Math.floor(mtimeNs / 1e6));
    if (Number.isNaN(d.getTime())) return '';
    const p = (n) => String(n).padStart(2, '0');
    return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
  } catch { return ''; }
}

// 根据 AssetPlanner Decision（action/reason）映射面板状态徽标
function _assetStatus(item) {
  const action = item.action;
  // 阻断类
  if (!item.can_submit) {
    return {
      cls: ' asset-row-changed',
      badge: `<span class="asset-changed-badge">🔴 无法使用 · 需处理</span>`,
      hint: escapeHtml(item.block_reason || '此素材无法继续提交，请处理'),
    };
  }
  switch (action) {
    case 'REUSE_REMOTE':
      return {
        cls: '',
        badge: `<span class="asset-fresh-badge">✓ 复用已上传资源</span>`,
        hint: item.reason === 'SOURCE_MISSING_REMOTE_REUSE'
          ? '☁ 仅云端版本 · 本地源已删除，仍可复用；修改对齐/裁剪/分段需重新提供源文件'
          : '',
      };
    case 'UPLOAD_EXISTING_ARTIFACT':
      return { cls: '', badge: `<span class="asset-fresh-badge">✓ 复用本地产物 · 将上传</span>`, hint: '' };
    case 'BUILD_AND_UPLOAD':
      return {
        cls: ' asset-row-changed',
        badge: `<span class="asset-changed-badge">🔄 将重新生成并上传</span>`,
        hint: item.reason === 'SOURCE_CHANGED' ? '源文件已修改'
          : item.reason === 'TRANSFORM_CHANGED' ? '源文件或处理参数（对齐/裁剪/分段）已变化'
          : '',
      };
    case 'NEED_SOURCE_FOR_REBUILD':
      return { cls: ' asset-row-changed', badge: `<span class="asset-changed-badge">⚠️ 需重新提供源文件</span>`, hint: '处理参数已变但本地源已删除' };
    case 'NEED_MATERIAL_REBIND':
      return { cls: ' asset-row-changed', badge: `<span class="asset-changed-badge">⚠️ 需重新选择素材</span>`, hint: '素材缺失或不可识别' };
    default:
      return { cls: '', badge: `<span class="asset-fresh-badge">${escapeHtml(action || '未知')}</span>`, hint: '' };
  }
}

export async function showAssets(id) {
  const existing = $('#asset-panel');
  // 已展开且是同一个任务 → 关闭（toggle）
  if (existing && existing.dataset.taskId === id) {
    existing.remove();
    return;
  }
  try {
    const data = await api(`/api/tasks/${encodeURIComponent(id)}/assets`);
    if (existing) existing.remove();
    const card = $(`.task[data-id="${CSS.escape(id)}"]`);
    const panel = document.createElement('div');
    panel.id = 'asset-panel';
    panel.dataset.taskId = id;
    panel.className = 'panel asset-panel-inline';
    panel.innerHTML = `
      <div class="section-head"><h3>Asset 清单</h3></div>
      <div class="asset-hint">素材复用/重传由<b>统一决策引擎</b>判定：源文件与处理参数未变则复用已上传资源，<b>源文件或被处理参数（对齐/裁剪/分段）改变时自动重新上传</b>；源文件已删除时需按状态处理。已上传的云端资源通常<b>不会失效</b>，无需担心；仅当你确实需要<b>强制重新上传</b>某个素材时才点 🗑 清缓存。</div>
      <div class="asset-list">${data.items.length
        ? data.items
            .map((item) => {
              const type = item.key.startsWith('anchor_') ? 'Anchor 图片' : item.key.endsWith(':audio') ? '参考音频' : '参考视频';
              // 依据 Planner Decision（action/reason）渲染状态徽标
              const st = _assetStatus(item);
              return `<div class="asset-row${st.cls}">
                <div><strong>${escapeHtml(item.key)}</strong><div class="meta">${escapeHtml(item.asset_id || '未上传')}</div></div>
                <div class="meta">${escapeHtml(type)}</div>
                ${st.badge}
                ${st.hint ? `<div class="meta asset-status-hint">${st.hint}</div>` : ''}
                <button class="text-button danger-text" onclick="clearTaskAssets('${escapeAttr(id)}','${escapeAttr(item.key)}')" title="清除此素材缓存，下次运行会重新上传">🗑</button>
              </div>`;
            })
            .join('')
        : '<p class="hint">尚无已上传 Asset；首次运行时会按需创建。</p>'}</div>
      <div class="actions"><button class="secondary" onclick="clearTaskAssets('${escapeAttr(id)}')">清除全部缓存</button></div>`;
    if (card) card.after(panel);
    else $('#task-list').after(panel);
    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch (e) {
    toast(e.message);
  }
}

export function closeAssets() {
  const panel = $('#asset-panel');
  if (panel) panel.remove();
}

// 记录用户是否手动编辑过预览 Prompt（true=自定义，false=自动生成）
function _promptEdited() {
  return store.customPromptDirty === true;
}

function _updatePromptModeBadge() {
  const modeEl = $('#prompt-preview-mode');
  const tipEl = $('#prompt-preview-tip');
  const custom = _promptEdited();
  if (modeEl) {
    modeEl.textContent = custom ? '自定义' : '自动生成';
    modeEl.classList.toggle('is-custom', custom);
    modeEl.title = custom
      ? '当前内容为手动编辑，将整段用于生成'
      : '系统按歌词、参考素材与「任务附加约束」自动生成';
  }
  if (tipEl) {
    // 两种模式给用户不同的引导，讲清「附加约束（追加小补）」与「编辑框（整段重写）」的区别
    tipEl.innerHTML = custom
      ? '<strong>自定义 Prompt</strong>：保存 / 生成将<strong>整段</strong>使用下框文本，不再叠加歌词、时间戳与「任务附加约束」。点上方「恢复自动生成」可回到系统版本。'
      : '<strong>自动生成</strong>：系统按歌词、参考素材与「任务附加约束」自动拼装。<strong>想小幅补充</strong> → 在素材区「任务附加约束」加几句即可（追加在末尾，不影响其他部分）；<strong>想整段重写</strong> → 直接在下框修改，将切换为「自定义 Prompt」（不再叠加歌词 / 时间戳 / 约束）。两者二选一。';
  }
}

export async function previewPrompt() {
  const ta = $('#prompt-preview');
  const wrap = $('#prompt-preview-wrap');
  // 已展开 → 收起
  if (wrap && !wrap.hidden) {
    wrap.hidden = true;
    return;
  }
  try {
    const t = formTask();
    // 已有自定义内容时，重新打开仍保留用户文本，不再覆盖
    if (!_promptEdited()) {
      const result = await post('/api/prompt-preview', t);
      if (ta) ta.value = result.prompt;
    }
    _updatePromptModeBadge();
    if (wrap) wrap.hidden = false;
    else if (ta) ta.hidden = false;
  } catch (e) {
    toast(e.message);
  }
}

// 用户手动编辑 textarea → 标记为自定义 prompt
export function markPromptEdited() {
  store.customPromptDirty = true;
  _updatePromptModeBadge();
}

// 恢复自动生成：清空自定义标记，重新请求自动 prompt
export async function resetPromptToAuto() {
  const ta = $('#prompt-preview');
  if (ta) ta.value = '';
  store.customPromptDirty = false;
  try {
    const t = formTask();
    const result = await post('/api/prompt-preview', t);
    if (ta) ta.value = result.prompt;
  } catch (e) {
    toast(e.message);
  }
  _updatePromptModeBadge();
}

export function closePromptPreview() {
  const wrap = $('#prompt-preview-wrap');
  if (wrap) wrap.hidden = true;
}

// ── Run Submission ──────────────────────────────────────────────────────────

export function requestStart(id) {
  store.pendingTask = id;
  store.pendingAnchorTask = null;
  $('#submit-password').value = '';
  $('#modal').hidden = false;
  $('#submit-password').focus();
}

export async function startCurrent() {
  try {
    const data = formTask();
    // 提交前校验：anchor 与参考音视频必填
    if (!data.anchors.length) throw new Error('请先选择或生成 Anchor 图片');
    if (!data.references.length) throw new Error('请先上传参考音视频');
    _validateLyricsForMode(data);
    const newId = `${data.data_dir}__${data.name}`;
    const editingId = store.currentTask?.id;
    if (editingId && editingId !== newId) {
      // 改名/改文件夹后启动：先走保存二选一弹窗，保存成功后由
      // _afterSaveMaybeStart 接续 requestStart，无需用户再手动点启动
      store._pendingStart = true;
      await saveTask();
      return;
    }
    const task = await saveTask(null, 'auto');
    requestStart(task.id);
  } catch (e) {
    toast(e.message);
  }
}

export function closeModal() {
  $('#modal').hidden = true;
  store.pendingTask = null;
  store.pendingAnchorTask = null;
}

export async function confirmStart() {
  try {
    if (store.pendingAnchorTask) {
      const job = await post('/api/anchor-runs', {
        task_id: store.pendingAnchorTask,
        password: $('#submit-password').value,
      });
      closeModal();
      toast('Anchor 任务已进入生成队列');
      const { showView } = await import('../app.js');
      showView('anchors');
      const { loadAnchorRuns, openAnchorPoll } = await import('./anchor.js');
      await loadAnchorRuns();
      openAnchorPoll();
      return;
    }
    const job = await post('/api/runs', {
      task_id: store.pendingTask,
      password: $('#submit-password').value,
    });
    closeModal();
    toast('任务已进入运行队列');
    const { showView } = await import('../app.js');
    showView('runs');
    await loadRuns();
    openRunPoll();
  } catch (e) {
    toast(e.message);
  }
}

// ── Runs ────────────────────────────────────────────────────────────────────

export async function loadRuns() {
  store.runs = await api('/api/runs');
  // 轮询场景（每 1.5s）下，数据未变化则跳过重渲染，避免整列表/审核下拉框反复重建导致的闪烁与选中态抖动
  const sig = JSON.stringify(store.runs.map((r) => [r.run_id, r.status, r.stage, r.completed, r.total, r.message]));
  if (sig === store._runsSig) return;
  store._runsSig = sig;
  const list = $('#run-list');
  if (!list) return;
  list.innerHTML = store.runs.map(runCard).join('') || renderEmptyState('🚀', '还没有运行记录', '配置并启动一个任务后即可看到进度');
  refreshReviewOptions();
}

function runCard(r) {
  const percent = r.total ? Math.round(((r.completed || 0) / r.total) * 100) : r.status === 'completed' ? 100 : 0;
  const isRunning = ['queued', 'running'].includes(r.status);
  const canReview = r.manifest || r.status === 'running';
  const resumeBtn = r.can_resume ? `<button class="run-resume" onclick="event.stopPropagation(); resumeRun('${escapeAttr(r.run_id)}')" title="重新恢复轮询">↻ 恢复</button>` : '';
  // 文件夹标识：不同文件夹下的同名任务（如 街道风/冻结 与 冻结/冻结）在运行列表也能区分
  const dir = (r.task_id || '').split('__')[0] || '';
  return `<article class="run-card${canReview ? ' clickable' : ''}" data-id="${escapeHtml(r.run_id)}"${canReview ? ` onclick="openRunReview('${escapeAttr(r.run_id)}')"` : ''}>
    <div class="run-main">
      <h3>${dir ? `<span class="run-dir">📁 ${escapeHtml(dir)}</span>` : ''}${escapeHtml(r.task_name)} <span class="badge">${stageName(r.stage)}</span></h3>
      <div class="meta">${r.run_id} · ${escapeHtml(r.message || '')}</div>
      <div class="progress"><i style="width:${percent}%"></i></div>
    </div>
    <div class="run-right">
      <strong>${r.completed || 0}/${r.total || 0}</strong>
      ${r.error ? `<div class="meta">${escapeHtml(r.error)}</div>` : ''}
      ${resumeBtn}
    </div>
    <button class="run-delete" onclick="event.stopPropagation(); confirmDeleteRun('${escapeAttr(r.run_id)}', this)" title="${isRunning ? '运行中无法删除' : '删除此记录'}" ${isRunning ? 'disabled' : ''}>✕</button>
  </article>`;
}

export function openRunPoll() {
  clearInterval(store.pollTimer);
  store.pollTimer = setInterval(async () => {
    if (!$('#runs').classList.contains('active')) return;
    await loadRuns();
    if (!store.runs.some((r) => ['queued', 'running'].includes(r.status))) clearInterval(store.pollTimer);
  }, 1500);
}

function refreshReviewOptions() {
  // 有 manifest 的 run（已完成/生成中）均可进入审核，实时预览已生成的候选；
  // 但失败的 run 不再进入审核（其 manifest 可能是失败前残留的候选，不应继续审核）
  const available = store.runs.filter((r) => (r.manifest || r.status === 'running') && r.status !== 'failed' && r.status !== 'cancelled');
  const select = $('#review-run');
  if (!select) return;
  const current = select.value;
  select.innerHTML = available
    .map((r) => {
      const dir = (r.task_id || '').split('__')[0] || '';
      const label = dir ? `${dir} / ${r.task_name}` : r.task_name;
      return `<option value="${r.run_id}">${escapeHtml(label)} · ${r.run_id}${r.status === 'running' ? ' (生成中)' : ''}</option>`;
    })
    .join('');
  if (available.some((r) => r.run_id === current)) {
    select.value = current;
  } else if (available.length > 0) {
    // 之前的选中项不存在了，选第一个（但仅在没有当前审核内容时）
    select.value = '';
  }
}

/* ── Rolling lyrics timestamps editor ── */
let _lyricsTsState = {
  lines: [],
  activeIndex: 0,
  audioUrl: null,
  extracting: false,
  scrollY: null,
};
let _lyricsAudioEl = null;
let _keyboardHelpShown = false;

function _formatTs(seconds) {
  if (seconds == null || Number.isNaN(seconds)) return '—';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  const ms = Math.round((seconds % 1) * 1000);
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}.${String(ms).padStart(3, '0')}`;
}

function _parseLyricsText(text) {
  return text.split('\n').map((line) => line.trim()).filter((line) => line.length > 0);
}

export function showLyricsShortcuts() {
  toast('空格：播放/暂停  ·  Enter：添加时间点  ·  ↑/↓：切换歌词行  · Esc：关闭');
}

function _formReferenceFiles() {
  // 实时读取表单里的音视频引用：视频 tab 用 #references，音频 tab 用 #audio-refs
  const isAudioTab = document.querySelector('.ref-tab.active[data-ref-tab]')?.dataset?.refTab === 'audio';
  const files = isAudioTab ? lines('#audio-refs') : lines('#references');
  return { files, isAudioTab };
}

function _isMediaFile(name) {
  return /\.(mp3|wav|m4a|aac|flac|ogg|mp4|mov|m4v|avi|mkv|webm)$/i.test(name || '');
}

function _resolveAudioSource() {
  // 打时间戳的音频来源，优先级：
  // 1) 音频 tab 选过的「纯音频」（#audio-refs）—— 用户传了音频就用音频本身对口型，最准
  // 2) 当前 tab 的参考媒体（视频则从视频提取音频）
  // 3) 已保存任务的 references
  const audioFile = lines('#audio-refs').find((f) => _isMediaFile(f));
  if (audioFile) {
    return { source: 'form', index: 0, file: audioFile };
  }
  const { files } = _formReferenceFiles();
  const formFile = files.find((f) => _isMediaFile(f));
  if (formFile) {
    return { source: 'form', index: 0, file: formFile };
  }
  const saved = store.currentTask?.references || [];
  const firstSaved = saved.find((r) => _isMediaFile(r.file));
  if (firstSaved) {
    return { source: 'task', index: saved.indexOf(firstSaved), file: firstSaved.file };
  }
  return null;
}

// 相对 data_root 的文件路径 = task_dir + '/' + 表单文件值（值已含 category 子目录）
function _relativeDataRootPath(file) {
  const taskDir = ($('#task-dir').value || '').trim().replace(/\/+$/, '');
  return taskDir ? `${taskDir}/${file}` : file;
}

function _applyLyricsText(texts, timestamps) {
  // texts 为新歌词行；timestamps 为已存时间戳（按 text 匹配保留 time）
  const timeByText = {};
  (timestamps || []).forEach((ts) => {
    if (ts?.text != null && ts.time != null) timeByText[ts.text] = ts.time;
  });
  _lyricsTsState.lines = texts.map((text) => ({
    text,
    time: timeByText[text] != null ? timeByText[text] : null,
  }));
  if (_lyricsTsState.activeIndex >= _lyricsTsState.lines.length) {
    _lyricsTsState.activeIndex = _lyricsTsState.lines.length - 1;
  }
}

export async function openLyricsTimestampsEditor() {
  const task = store.currentTask;
  const raw = $('#lyrics').value || '';
  const texts = _parseLyricsText(raw);

  // 音视频必须存在（歌词允许为空，未保存任务也允许）
  const ref = _resolveAudioSource();
  if (!ref) {
    return toast('请先上传音视频，再打时间戳');
  }

  const modal = $('#lyrics-timestamps-modal');
  _lyricsTsState.scrollY = window.scrollY;  // 记录滚动位置，关闭时恢复
  modal.hidden = false;
  if (!_keyboardHelpShown) {
    showLyricsShortcuts();
    _keyboardHelpShown = true;
  }

  const existing = task?.lyrics_timestamps || store.pendingLyricsTimestamps || [];
  _applyLyricsText(texts, existing);
  _lyricsTsState.activeIndex = 0;
  _lyricsTsState.audioUrl = null;
  _lyricsTsState.extracting = false;

  _lyricsAudioEl = $('#lyrics-audio');
  _lyricsAudioEl.src = '';
  _lyricsAudioEl.load();
  // 播放时自动滚动到当前时间对应的已打点句子
  _lyricsAudioEl.addEventListener('timeupdate', _autoLocateByTime);

  renderLyricsTimestampLines();
  _refreshAddButton();

  try {
    _lyricsTsState.extracting = true;
    $('#add-timestamp-btn').disabled = true;
    let res;
    if (ref.source === 'task') {
      res = await extractTaskAudio(task.id, ref.index);
    } else {
      res = await extractAudioByPath(_relativeDataRootPath(ref.file));
    }
    _lyricsTsState.audioUrl = res.audio_url;
    _lyricsAudioEl.src = res.audio_url;
    _lyricsAudioEl.load();
  } catch (e) {
    toast(`音频准备失败: ${e.message}`);
  } finally {
    _lyricsTsState.extracting = false;
    _refreshAddButton();
  }
}

function updateLyricsCountHint() {
  const hint = $('#lyrics-count-hint');
  if (!hint) return;
  const total = _lyricsTsState.lines.length;
  const set = _lyricsTsState.lines.filter((l) => l.time != null).length;
  hint.textContent = total ? `共 ${total} 句 · 已打点 ${set} 句` : '尚未填写歌词';
}

export function closeLyricsTimestampsEditor() {
  const modal = $('#lyrics-timestamps-modal');
  modal.hidden = true;
  if (_lyricsAudioEl) {
    _lyricsAudioEl.pause();
    _lyricsAudioEl.removeEventListener('timeupdate', _autoLocateByTime);
    _lyricsAudioEl.src = '';
    _lyricsAudioEl.load();
  }
  _lyricsTsState.audioUrl = null;
  // 恢复打开弹窗前的滚动位置（避免关闭后页面滚回顶部）
  if (typeof _lyricsTsState.scrollY === 'number') {
    requestAnimationFrame(() => window.scrollTo({ top: _lyricsTsState.scrollY, behavior: 'auto' }));
    _lyricsTsState.scrollY = null;
  }
}

function _refreshAddButton() {
  const btn = $('#add-timestamp-btn');
  if (!btn) return;
  const hasLyrics = (_lyricsTsState.lines || []).length > 0;
  btn.disabled = _lyricsTsState.extracting || !_lyricsAudioEl || !_lyricsAudioEl.src || !hasLyrics;
}

export function renderLyricsTimestampLines() {
  const container = $('#lyrics-timestamp-lines');
  if (!container) return;
  if (!_lyricsTsState.lines.length) {
    container.innerHTML = '<div class="lyrics-empty">歌词为空，请在上方逐行填写歌词后点击「应用歌词」</div>';
    return;
  }
  container.innerHTML = _lyricsTsState.lines.map((line, i) => {
    const tsClass = line.time != null ? 'set' : '';
    const activeClass = i === _lyricsTsState.activeIndex ? 'active' : '';
    const redoBtn = line.time != null
      ? `<button type="button" class="line-redo" data-index="${i}" title="重新打这一句">↺</button>`
      : '<span class="line-redo-placeholder"></span>';
    return `<div class="lyrics-line ${activeClass}" data-index="${i}">
      <div class="ts ${tsClass}">${_formatTs(line.time)}</div>
      <div class="text">${escapeHtml(line.text)}</div>
      ${redoBtn}
    </div>`;
  }).join('');
  container.querySelectorAll('.lyrics-line').forEach((el) => {
    el.addEventListener('click', () => clickLyricsLine(parseInt(el.dataset.index, 10)));
  });
  container.querySelectorAll('.line-redo').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation(); // 不触发行点击
      redoLyricsLine(parseInt(btn.dataset.index, 10));
    });
  });
  updateLyricsCountHint();
}

export function setActiveLine(index) {
  if (index < 0 || index >= _lyricsTsState.lines.length) return;
  _lyricsTsState.activeIndex = index;
  renderLyricsTimestampLines();
  _scrollActiveToSecondRow();
}

// 让当前打标句尽量滚动到第二行（第一句除外，它在顶部）
function _scrollActiveToSecondRow() {
  const container = $('#lyrics-timestamp-lines');
  if (!container) return;
  const active = container.querySelector('.lyrics-line.active');
  if (!active) return;
  const rows = container.querySelectorAll('.lyrics-line');
  const rowHeight = rows[0]?.offsetHeight || 0;
  const gap = 8;
  // 目标：active 行出现在第二行（即其上方只露出第一行）
  const targetTop = _lyricsTsState.activeIndex === 0
    ? 0
    : (_lyricsTsState.activeIndex - 1) * (rowHeight + gap);
  container.scrollTo({ top: targetTop, behavior: 'smooth' });
}

// 播放时根据当前时间自动定位到对应已打点句子
function _autoLocateByTime() {
  if (!_lyricsAudioEl || _lyricsAudioEl.paused) return;
  // 当前正在打点一个未打点的句子时，不自动回拉（尊重用户手动跳句）
  const currentLine = _lyricsTsState.lines[_lyricsTsState.activeIndex];
  if (currentLine && currentLine.time == null) return;
  const t = _lyricsAudioEl.currentTime;
  let target = -1;
  for (let i = 0; i < _lyricsTsState.lines.length; i++) {
    const time = _lyricsTsState.lines[i].time;
    if (time != null && time <= t) target = i;
    else if (time != null && time > t) break;
  }
  if (target >= 0 && target !== _lyricsTsState.activeIndex) {
    _lyricsTsState.activeIndex = target;
    renderLyricsTimestampLines();
    _scrollActiveToSecondRow();
  }
}

export function clickLyricsLine(index) {
  const line = _lyricsTsState.lines[index];
  if (!line) return;
  setActiveLine(index);
  // 已打点句子：点击跳转到对应时间点（仅定位，不清空）
  if (line.time != null && _lyricsAudioEl && _lyricsAudioEl.src) {
    _lyricsAudioEl.currentTime = line.time;
  }
}

export function redoLyricsLine(index) {
  const line = _lyricsTsState.lines[index];
  if (!line || line.time == null) return;
  // 清空这一句的时间点（只清这一句，不影响其它句）
  line.time = null;
  renderLyricsTimestampLines();

  // 选中定位到要重打的这一句
  setActiveLine(index);

  if (_lyricsAudioEl && _lyricsAudioEl.src) {
    if (index === 0) {
      // 第一句：从音频开头播放
      _lyricsAudioEl.currentTime = 0;
    } else {
      // 从上一句的时间点开始播放（留出准备缓冲），选中仍定位到要重打的这句
      const prev = _lyricsTsState.lines[index - 1];
      const startTime = prev && prev.time != null ? prev.time : Math.max(0, line.time - 2);
      _lyricsAudioEl.currentTime = startTime;
    }
  }
  toast(`从上一句开始播放，到「${line.text}」时按 Enter 重打`);
}

export function addTimestamp() {
  if (!_lyricsAudioEl || _lyricsTsState.extracting) return;
  if (!_lyricsTsState.lines.length) {
    toast('请先在任务表单中填写歌词');
    return;
  }
  const idx = _lyricsTsState.activeIndex;
  const time = _lyricsAudioEl.currentTime;
  const line = _lyricsTsState.lines[idx];
  if (!line) return;
  // 只覆盖当前句的时间点，不影响其它句子
  line.time = time;
  renderLyricsTimestampLines();
  if (_lyricsTsState.activeIndex < _lyricsTsState.lines.length - 1) {
    setActiveLine(_lyricsTsState.activeIndex + 1);
  }
  // 未播放时打点（如第一句 0s）后自动开始播放，方便连续打点
  if (_lyricsAudioEl.paused) {
    _lyricsAudioEl.play();
  }
}

export function resetTimestamps() {
  _lyricsTsState.lines.forEach((line) => { line.time = null; });
  _lyricsTsState.activeIndex = 0;
  renderLyricsTimestampLines();
}

export async function saveLyricsTimestampsFromModal() {
  const task = store.currentTask;
  const timestamps = _lyricsTsState.lines.map((line) => ({
    text: line.text,
    time: line.time,
  }));
  // 把 modal 里编辑的歌词同步回主表单
  const lyricsText = _lyricsTsState.lines.map((l) => l.text).join('\n');
  if ($('#lyrics')) $('#lyrics').value = lyricsText;
  // 任务尚未保存时，先暂存到内存，随任务保存时一并写入；否则直接持久化
  if (!task) {
    store.pendingLyricsTimestamps = timestamps;
    closeLyricsTimestampsEditor();
    toast('已暂存时间戳，保存任务后自动写入');
    return;
  }
  try {
    await saveLyricsTimestamps(task.id, timestamps);
    task.lyrics_timestamps = timestamps;
    closeLyricsTimestampsEditor();
    toast('歌词时间戳已保存');
  } catch (e) {
    toast(`保存失败: ${e.message}`);
  }
}

export function previewLyricsTimestamps() {
  const data = _lyricsTsState.lines.map((line) => ({
    text: line.text,
    time: line.time,
  }));
  console.log('[lyrics timestamps preview]', JSON.stringify(data, null, 2));
  toast(`已记录 ${_lyricsTsState.lines.filter((l) => l.time != null).length} 个时间点（按 F12 查看）`);
}

export function onLyricsTimestampsKey(e) {
  if ($('#lyrics-timestamps-modal').hidden) return;
  if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) return;
  if (e.code === 'Space') {
    e.preventDefault();
    if (_lyricsAudioEl.paused) _lyricsAudioEl.play(); else _lyricsAudioEl.pause();
  } else if (e.code === 'Enter') {
    e.preventDefault();
    addTimestamp();
  } else if (e.code === 'ArrowUp') {
    e.preventDefault();
    setActiveLine(_lyricsTsState.activeIndex - 1);
  } else if (e.code === 'ArrowDown') {
    e.preventDefault();
    setActiveLine(_lyricsTsState.activeIndex + 1);
  }
  // Escape 关闭已统一由 app.js 的全局 modal 处理
}
