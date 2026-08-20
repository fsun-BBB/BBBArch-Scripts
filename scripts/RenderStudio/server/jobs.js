// ---------------------------------------------------------------------------
// JOB ORCHESTRATION
//
// One uniform lifecycle for both inference and training:
//   create -> submit to provider -> client polls /api/jobs/:id -> succeeded
//
// Training jobs that succeed self-register into the LoRA library, which is
// what the canvas inspector's LoRA picker reads. That closes the loop: train
// on the board, use it on the canvas in the same session.
// ---------------------------------------------------------------------------
import { store, newId } from './store.js';
import { adapterFor } from './providers/index.js';
import { byType, trainingBases, trainingPresets } from './providers/catalog.js';
import { estimateCost, normaliseCaption } from './training-rules.js';

/** Translate canvas node params into a provider payload. */
function buildInferenceInput(def, params, wired) {
  const p = { ...params };
  const lora = p.lora ? store.get('loras', p.lora) : null;

  // The trigger token is injected here rather than trusted to the user. This
  // is the one step that most often gets forgotten, and without it the LoRA
  // contributes nothing directed at all.
  let prompt = String(wired.prompt || '').trim();
  if (lora?.trigger && !prompt.toLowerCase().includes(lora.trigger.toLowerCase())) {
    prompt = prompt ? `${lora.trigger}, ${prompt}` : lora.trigger;
  }

  const base = {
    prompt,
    num_inference_steps: p.steps,
    guidance_scale: p.guidance,
    seed: p.seed ?? undefined,
    image_url: wired.image || undefined,
  };

  if (def.type === 'flux-lora') {
    Object.assign(base, {
      control_type: p.control,
      controlnet_conditioning_scale: p.control === 'img2img' ? undefined : p.controlScale,
      strength: p.control === 'img2img' ? p.controlScale : undefined,
      loras: lora?.fileUrl ? [{ path: lora.fileUrl, scale: p.loraWeight }] : [],
    });
  }
  if (def.type === 'nano-banana') {
    Object.assign(base, {
      aspect: p.aspect,
      images: wired.imageBase64 ? [{ base64: wired.imageBase64 }] : [],
      resolution: p.resolution,
    });
  }
  if (def.type === 'upscale') {
    Object.assign(base, { scale: Number(p.scale), creativity: p.creativity });
  }

  // Kept for the mock renderer so the placeholder can show real settings.
  base.params = { ...p, loraName: lora?.name || null };
  return base;
}

export function createGenerateJob({ nodeId, nodeType, params = {}, wired = {} }) {
  const def = byType(nodeType);
  if (!def) throw new Error(`Unknown node type: ${nodeType}`);

  const job = {
    id: newId('job'),
    kind: 'generate',
    nodeId,
    nodeType,
    nodeTitle: def.title,
    provider: def.provider,
    endpoint: def.endpoint,
    status: 'queued',
    progress: 0,
    estCost: def.cost || 0,
    createdAt: new Date().toISOString(),
    input: buildInferenceInput(def, params, wired),
  };
  return submit(job);
}

export function createTrainingJob({ datasetId, presetId = 'style', baseId, steps, name }) {
  const dataset = store.get('datasets', datasetId);
  if (!dataset) throw new Error('Dataset not found.');

  const preset = trainingPresets[presetId] || trainingPresets.style;
  const base = trainingBases.find((b) => b.id === (baseId || preset.base)) || trainingBases[0];
  const resolvedSteps = steps || preset.steps;
  const cost = estimateCost(base, resolvedSteps);

  const captions = (dataset.images || []).map((img) => ({
    asset: img.asset,
    caption: normaliseCaption(img.caption, dataset.trigger),
  }));

  const job = {
    id: newId('job'),
    kind: 'train',
    provider: base.provider,
    endpoint: base.endpoint,
    status: 'queued',
    progress: 0,
    datasetId,
    presetId,
    baseId: base.id,
    name: name || dataset.name || 'untitled',
    trigger: dataset.trigger,
    estCost: cost.usd,
    billableSteps: cost.billableSteps,
    createdAt: new Date().toISOString(),
    input: {
      trigger_word: dataset.trigger,
      steps: cost.billableSteps,
      learning_rate: preset.learningRate,
      rank: preset.rank,
      is_style: presetId === 'style',
      captions,
    },
  };
  return submit(job);
}

function submit(job) {
  store.put('jobs', job);
  const adapter = adapterFor(job.provider);
  Promise.resolve()
    .then(() => adapter.submit(job))
    .then((res) => {
      store.put('jobs', {
        id: job.id,
        status: res.done ? 'succeeded' : 'running',
        remoteId: res.remoteId,
        statusUrl: res.statusUrl,
        responseUrl: res.responseUrl,
        startedAt: res.startedAt || Date.now(),
        images: res.images,
        progress: res.done ? 1 : 0.05,
      });
      if (res.done) finish(job.id);
    })
    .catch((err) => {
      store.put('jobs', { id: job.id, status: 'failed', error: err.message, progress: 0 });
    });
  return store.get('jobs', job.id);
}

/** Poll a job, advancing its stored state. Safe to call repeatedly. */
export async function refreshJob(id) {
  const job = store.get('jobs', id);
  if (!job) return null;
  if (job.status === 'succeeded' || job.status === 'failed') return job;

  try {
    const res = await adapterFor(job.provider).poll(job);
    store.put('jobs', {
      id,
      status: res.status,
      progress: res.progress ?? job.progress,
      images: res.images?.length ? res.images : job.images,
      artifact: res.artifact || job.artifact,
      error: res.error,
    });
    if (res.status === 'succeeded') finish(id);
  } catch (err) {
    store.put('jobs', { id, status: 'failed', error: err.message });
  }
  return store.get('jobs', id);
}

/** Post-success side effects. Training jobs publish a LoRA. */
function finish(id) {
  const job = store.get('jobs', id);
  if (!job || job.kind !== 'train') return;
  if (store.list('loras').some((l) => l.jobId === id)) return;

  store.put('loras', {
    id: newId('lora'),
    jobId: id,
    name: job.name,
    trigger: job.trigger,
    baseId: job.baseId,
    presetId: job.presetId,
    fileUrl: job.artifact || null,
    datasetId: job.datasetId,
    steps: job.billableSteps,
    cost: job.estCost,
    createdAt: new Date().toISOString(),
    // A LoRA is only compatible with inference nodes on the same base. The
    // canvas uses this to grey out mismatched picks instead of letting someone
    // load a Flux LoRA into SDXL and wonder why the output is noise.
    compatible: job.baseId.startsWith('flux') ? ['flux-lora', 'flux-kontext'] : ['sdxl-lora'],
  });
}
