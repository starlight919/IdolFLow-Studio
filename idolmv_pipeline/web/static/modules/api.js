// API Communication Layer
// ==========================================================================
//
// All HTTP calls to the backend go through this module.
// Errors are surfaced as Error with the server's `error` field as the message.

/**
 * Low-level fetch wrapper that parses JSON and throws on non-2xx responses.
 */
export async function api(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || response.statusText);
  }
  return data;
}

/**
 * Convenience for POST requests with JSON body.
 */
export function post(url, body) {
  return api(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

/**
 * Convenience for DELETE requests.
 */
export function del(url) {
  return api(url, { method: 'DELETE' });
}

/**
 * Load public workspace settings (data_root, publish_enabled, etc.)
 */
export async function loadSettings() {
  return api('/api/settings/public');
}

export async function extractTaskAudio(taskId, referenceIndex = 0) {
  return post(`/api/tasks/${taskId}/extract-audio`, { reference_index: referenceIndex });
}

export async function extractAudioByPath(file) {
  return post('/api/extract-audio', { file });
}

export async function getLyricsTimestamps(taskId) {
  return api(`/api/tasks/${taskId}/lyrics-timestamps`);
}

export async function saveLyricsTimestamps(taskId, timestamps) {
  return post(`/api/tasks/${taskId}/lyrics-timestamps`, { lyrics_timestamps: timestamps });
}

/**
 * 上传素材文件到任务文件夹（POST /api/uploads，raw body）。
 * 主工作台「上传素材」与 Anchor 生成器「本机上传」共用这一份实现，
 * 保证超时/进度/错误语义一致。调用方只负责选目标字段和 UI 反馈。
 *
 * @param {Blob|File} file 要上传的文件内容
 * @param {object} opts
 * @param {string} opts.taskId 任务文件夹（data_root 下的目录名）
 * @param {string} opts.category anchors | references | anchor-references
 * @param {string} [opts.filename] 覆盖文件名（默认取 file.name）
 * @param {(percent:number)=>void} [opts.onProgress] 上传进度回调（0-100）
 * @param {number} [opts.timeoutMs] 超时（默认 120000）
 * @returns {Promise<{file:string,size:number}>} 服务器落盘后的相对路径与大小
 */
export function uploadFile(file, { taskId, category, filename, onProgress, timeoutMs = 120000 }) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/uploads');
    xhr.timeout = timeoutMs;
    xhr.setRequestHeader('X-Task-Id', encodeURIComponent(taskId));
    xhr.setRequestHeader('X-Filename', encodeURIComponent(filename || file.name));
    xhr.setRequestHeader('X-Category', category);
    xhr.upload.onprogress = (e) => {
      if (onProgress && e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      let data = {};
      try { data = JSON.parse(xhr.responseText); } catch { /* 非 JSON 响应 */ }
      if (xhr.status < 300) {
        resolve(data);
      } else {
        reject(new Error(data.error || `上传失败 (${xhr.status})`));
      }
    };
    xhr.onerror = () => reject(new Error('上传失败：网络错误或服务未响应'));
    xhr.ontimeout = () => reject(new Error('上传超时，请重试'));
    xhr.send(file);
  });
}
