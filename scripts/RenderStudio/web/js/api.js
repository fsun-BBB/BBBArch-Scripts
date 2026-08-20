const json = async (res) => {
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || `${res.status} ${res.statusText}`);
  return body;
};

const get = (url) => fetch(url).then(json);
const post = (url, body) =>
  fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(json);
const del = (url) => fetch(url, { method: 'DELETE' }).then(json);

export const api = {
  models: () => get('/api/models'),

  uploadImage: (dataUrl, filename) => post('/api/assets', { dataUrl, filename }),

  generate: (payload) => post('/api/generate', payload),
  job: (id) => get(`/api/jobs/${id}`),
  jobs: (limit = 40) => get(`/api/jobs?limit=${limit}`),

  datasets: () => get('/api/datasets'),
  saveDataset: (dataset) => post('/api/datasets', dataset),
  deleteDataset: (id) => del(`/api/datasets/${id}`),

  validateTrigger: (trigger) => post('/api/training/validate-trigger', { trigger }),
  suggestTrigger: (seed) => get(`/api/training/suggest-trigger?seed=${encodeURIComponent(seed || 'bbb')}`),
  audit: (dataset, presetId) => post('/api/training/audit', { dataset, presetId }),
  normaliseCaptions: (images, trigger) => post('/api/training/normalise-captions', { images, trigger }),
  estimate: (baseId, steps, presetId) => post('/api/training/estimate', { baseId, steps, presetId }),
  startTraining: (payload) => post('/api/training/start', payload),

  loras: () => get('/api/loras'),
  deleteLora: (id) => del(`/api/loras/${id}`),

  graphs: () => get('/api/graphs'),
  graph: (id) => get(`/api/graphs/${id}`),
  saveGraph: (graph) => post('/api/graphs', graph),
};

/** Poll a job until it settles. onTick receives each intermediate state. */
export async function pollJob(id, onTick, { intervalMs = 1200, timeoutMs = 15 * 60 * 1000 } = {}) {
  const started = Date.now();
  for (;;) {
    const job = await api.job(id);
    onTick?.(job);
    if (job.status === 'succeeded' || job.status === 'failed') return job;
    if (Date.now() - started > timeoutMs) throw new Error('Job timed out.');
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}

/** File -> data URL, then upload, returning the served asset path. */
export function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const fr = new FileReader();
    fr.onload = () => resolve(fr.result);
    fr.onerror = () => reject(new Error(`Could not read ${file.name}`));
    fr.readAsDataURL(file);
  });
}

/** Natural pixel size of an image URL, used for the resolution audit. */
export function imageSize(url) {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve({ width: img.naturalWidth, height: img.naturalHeight });
    img.onerror = () => resolve({ width: 0, height: 0 });
    img.src = url;
  });
}
