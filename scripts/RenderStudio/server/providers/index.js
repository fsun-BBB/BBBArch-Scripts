// ---------------------------------------------------------------------------
// PROVIDER ADAPTERS
//
// Every provider is normalised to the same two-call shape:
//
//   submit(job)  -> { remoteId }        kick off work
//   poll(job)    -> { status, images[], progress, error }
//
// `status` is one of queued | running | succeeded | failed. The routes layer
// never knows which provider it is talking to, so adding a provider means
// adding a file here and one entry in `adapters`.
//
// In MOCK mode every adapter is replaced by a timer that resolves to a
// placeholder image, so the whole UI is exercisable with no accounts.
// ---------------------------------------------------------------------------
import { config, hasKey } from '../config.js';

const FAL_QUEUE = 'https://queue.fal.run';
const REPLICATE = 'https://api.replicate.com/v1';
const GEMINI = 'https://generativelanguage.googleapis.com/v1beta/models';

async function jsonFetch(url, options) {
  const res = await fetch(url, options);
  const text = await res.text();
  let body;
  try {
    body = text ? JSON.parse(text) : {};
  } catch {
    body = { raw: text };
  }
  if (!res.ok) {
    const detail = body?.error?.message || body?.detail || body?.raw || res.statusText;
    throw new Error(`${res.status} ${typeof detail === 'string' ? detail : JSON.stringify(detail)}`);
  }
  return body;
}

// --------------------------------------------------------------------- fal
// Queue API: POST to the model path, then poll the returned status_url.
const fal = {
  headers: () => ({
    Authorization: `Key ${config.keys.fal}`,
    'Content-Type': 'application/json',
  }),

  async submit(job) {
    const body = await jsonFetch(`${FAL_QUEUE}/${job.endpoint}`, {
      method: 'POST',
      headers: fal.headers(),
      body: JSON.stringify(job.input),
    });
    return { remoteId: body.request_id, statusUrl: body.status_url, responseUrl: body.response_url };
  },

  async poll(job) {
    const status = await jsonFetch(job.statusUrl || `${FAL_QUEUE}/${job.endpoint}/requests/${job.remoteId}/status`, {
      headers: fal.headers(),
    });
    if (status.status === 'IN_QUEUE') return { status: 'queued', progress: 0 };
    if (status.status === 'IN_PROGRESS') return { status: 'running', progress: 0.5 };

    const result = await jsonFetch(job.responseUrl || `${FAL_QUEUE}/${job.endpoint}/requests/${job.remoteId}`, {
      headers: fal.headers(),
    });
    // Training jobs return a safetensors file; inference returns images.
    if (result.diffusers_lora_file?.url) {
      return { status: 'succeeded', progress: 1, artifact: result.diffusers_lora_file.url, meta: result };
    }
    const images = (result.images || []).map((i) => i.url).filter(Boolean);
    return { status: 'succeeded', progress: 1, images, meta: result };
  },
};

// --------------------------------------------------------------- replicate
const replicate = {
  headers: () => ({
    Authorization: `Bearer ${config.keys.replicate}`,
    'Content-Type': 'application/json',
  }),

  async submit(job) {
    const body = await jsonFetch(`${REPLICATE}/predictions`, {
      method: 'POST',
      headers: replicate.headers(),
      body: JSON.stringify({ version: job.version || job.endpoint, input: job.input }),
    });
    return { remoteId: body.id, statusUrl: body.urls?.get };
  },

  async poll(job) {
    const body = await jsonFetch(job.statusUrl || `${REPLICATE}/predictions/${job.remoteId}`, {
      headers: replicate.headers(),
    });
    const map = { starting: 'queued', processing: 'running', succeeded: 'succeeded', failed: 'failed', canceled: 'failed' };
    const status = map[body.status] || 'running';
    const out = body.output;
    const images = Array.isArray(out) ? out.filter((u) => typeof u === 'string') : out ? [out] : [];
    return { status, images, progress: status === 'succeeded' ? 1 : 0.5, error: body.error, meta: body };
  },
};

// ------------------------------------------------------------------ gemini
// Synchronous request/response - no queue. We complete on submit and store
// the resulting inline image, so poll() just reports what submit already got.
const gemini = {
  async submit(job) {
    const parts = [{ text: job.input.prompt || '' }];
    for (const img of job.input.images || []) {
      parts.push({ inline_data: { mime_type: img.mime || 'image/png', data: img.base64 } });
    }
    const body = await jsonFetch(`${GEMINI}/${job.endpoint}:generateContent?key=${config.keys.gemini}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        contents: [{ parts }],
        generationConfig: { responseModalities: ['IMAGE'], imageConfig: { aspectRatio: job.input.aspect || '16:9' } },
      }),
    });
    const inline = body.candidates?.[0]?.content?.parts?.find((p) => p.inline_data || p.inlineData);
    const data = inline?.inline_data?.data || inline?.inlineData?.data;
    if (!data) throw new Error('Gemini returned no image. Check the prompt did not trip a safety filter.');
    return { remoteId: 'sync', images: [`data:image/png;base64,${data}`], done: true };
  },

  async poll(job) {
    return { status: 'succeeded', progress: 1, images: job.images || [] };
  },
};

// ------------------------------------------------------------ huggingface
// Used for model metadata and private LoRA hosting. HF inference routes to
// third-party providers and is billed - it is not a free Flux endpoint.
const huggingface = {
  async submit(job) {
    const body = await fetch(`https://router.huggingface.co/hf-inference/models/${job.endpoint}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${config.keys.huggingface}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ inputs: job.input.prompt, parameters: job.input.parameters || {} }),
    });
    if (!body.ok) throw new Error(`${body.status} ${await body.text()}`);
    const buf = Buffer.from(await body.arrayBuffer());
    return { remoteId: 'sync', images: [`data:image/png;base64,${buf.toString('base64')}`], done: true };
  },

  async poll(job) {
    return { status: 'succeeded', progress: 1, images: job.images || [] };
  },
};

// -------------------------------------------------------------------- mock
// Deterministic fake that walks queued -> running -> succeeded on wall clock,
// so progress bars, polling, and error states are all exercisable offline.
const MOCK_MS = { generate: 3500, train: 12000 };

const mock = {
  async submit(job) {
    return { remoteId: `mock_${job.id}`, startedAt: Date.now() };
  },

  async poll(job) {
    const span = MOCK_MS[job.kind] || MOCK_MS.generate;
    const elapsed = Date.now() - (job.startedAt || Date.now());
    const progress = Math.min(1, elapsed / span);
    if (progress < 0.15) return { status: 'queued', progress };
    if (progress < 1) return { status: 'running', progress };
    if (job.kind === 'train') {
      return { status: 'succeeded', progress: 1, artifact: `mock://lora/${job.id}.safetensors` };
    }
    return { status: 'succeeded', progress: 1, images: [placeholder(job)] };
  },
};

// An SVG data URI so mock runs produce something visibly labelled rather than
// a broken image icon. Shows the settings actually used, which is genuinely
// useful when checking wiring.
function placeholder(job) {
  const p = job.input?.params || {};
  const lines = [
    job.nodeTitle || 'Render',
    p.control ? `control: ${p.control} @ ${p.controlScale ?? '-'}` : '',
    p.loraWeight !== undefined ? `lora: ${p.loraName || 'none'} @ ${p.loraWeight}` : '',
    p.guidance !== undefined ? `guidance: ${p.guidance}` : '',
    `seed: ${job.input?.seed ?? 'random'}`,
  ].filter(Boolean);
  const text = lines
    .map((l, i) => `<text x="32" y="${70 + i * 34}" font-family="ui-monospace,monospace" font-size="19" fill="#dbe4f0">${escapeXml(l)}</text>`)
    .join('');
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="768" height="432">
    <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#12213a"/><stop offset="1" stop-color="#1d1633"/>
    </linearGradient></defs>
    <rect width="768" height="432" fill="url(#g)"/>
    <rect x="16" y="16" width="736" height="400" fill="none" stroke="#3d5afe" stroke-width="2" stroke-dasharray="6 6" opacity="0.55"/>
    <text x="32" y="40" font-family="ui-sans-serif,system-ui" font-size="13" fill="#7f8fa6" letter-spacing="2">MOCK RENDER</text>
    ${text}
  </svg>`;
  return `data:image/svg+xml;base64,${Buffer.from(svg).toString('base64')}`;
}

const escapeXml = (s) =>
  String(s).replace(/[<>&'"]/g, (c) => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', "'": '&apos;', '"': '&quot;' }[c]));

const adapters = { fal, replicate, gemini, huggingface, mock };

// Route to mock when globally mocked, when the provider has no key, or when
// the node is a purely local operation.
export function adapterFor(provider) {
  if (config.mock) return mock;
  if (provider === 'local') return mock;
  if (!adapters[provider]) return mock;
  if (!hasKey(provider)) return mock;
  return adapters[provider];
}

export function providerStatus() {
  return {
    mock: config.mock,
    providers: ['fal', 'replicate', 'gemini', 'huggingface'].map((id) => ({
      id,
      configured: hasKey(id),
      live: !config.mock && hasKey(id),
    })),
  };
}
