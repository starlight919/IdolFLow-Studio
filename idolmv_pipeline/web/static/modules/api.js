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
