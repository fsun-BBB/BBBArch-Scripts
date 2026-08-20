import express from 'express';
import { writeFileSync } from 'node:fs';
import { join, extname } from 'node:path';
import { store, newId } from './store.js';
import { config } from './config.js';
import { catalog, trainingBases, trainingPresets } from './providers/catalog.js';
import { providerStatus } from './providers/index.js';
import { createGenerateJob, createTrainingJob, refreshJob } from './jobs.js';
import { validateTrigger, suggestTrigger, auditDataset, normaliseCaption, estimateCost } from './training-rules.js';

export const router = express.Router();

const ok = (res, body) => res.json(body);
const fail = (res, err, code = 400) => res.status(code).json({ error: err.message || String(err) });
const wrap = (fn) => async (req, res) => {
  try {
    await fn(req, res);
  } catch (err) {
    fail(res, err, 400);
  }
};

// ------------------------------------------------------------------ catalog
router.get('/models', (req, res) =>
  ok(res, { nodes: catalog, trainingBases, trainingPresets, ...providerStatus() })
);

// ------------------------------------------------------------------- assets
// Images arrive as data URLs and are written to data/assets, then served back
// as plain files so the canvas is not carrying megabytes of base64 in memory.
router.post('/assets', wrap((req, res) => {
  const { dataUrl, filename } = req.body || {};
  const m = /^data:(image\/[a-z+]+);base64,(.+)$/is.exec(dataUrl || '');
  if (!m) throw new Error('Expected an image data URL.');

  const ext = { 'image/png': '.png', 'image/jpeg': '.jpg', 'image/webp': '.webp', 'image/svg+xml': '.svg' }[m[1]] || extname(filename || '') || '.png';
  const id = newId('img') + ext;
  writeFileSync(join(config.assetDir, id), Buffer.from(m[2], 'base64'));
  ok(res, { asset: `/assets/${id}`, id, originalName: filename || null });
}));

// -------------------------------------------------------------- generation
router.post('/generate', wrap((req, res) => {
  const job = createGenerateJob(req.body || {});
  ok(res, job);
}));

router.get('/jobs', (req, res) => {
  const rows = store.list('jobs').sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1));
  ok(res, rows.slice(0, Number(req.query.limit || 50)));
});

router.get('/jobs/:id', wrap(async (req, res) => {
  const job = await refreshJob(req.params.id);
  if (!job) return fail(res, new Error('No such job'), 404);
  ok(res, job);
}));

// ----------------------------------------------------------------- datasets
router.get('/datasets', (req, res) => ok(res, store.list('datasets')));

router.post('/datasets', wrap((req, res) => {
  const body = req.body || {};
  const row = {
    id: body.id || newId('ds'),
    name: body.name || 'Untitled dataset',
    trigger: body.trigger || '',
    presetId: body.presetId || 'style',
    images: body.images || [],
    updatedAt: new Date().toISOString(),
  };
  ok(res, store.put('datasets', row));
}));

router.delete('/datasets/:id', (req, res) => {
  store.remove('datasets', req.params.id);
  ok(res, { deleted: req.params.id });
});

// ------------------------------------------------------- validation & audit
router.post('/training/validate-trigger', wrap((req, res) =>
  ok(res, validateTrigger((req.body || {}).trigger))
));

router.get('/training/suggest-trigger', (req, res) =>
  ok(res, { trigger: suggestTrigger(req.query.seed || 'bbb') })
);

router.post('/training/audit', wrap((req, res) => {
  const { dataset, presetId } = req.body || {};
  ok(res, auditDataset(dataset || {}, presetId || 'style'));
}));

router.post('/training/normalise-captions', wrap((req, res) => {
  const { images = [], trigger } = req.body || {};
  ok(res, { images: images.map((i) => ({ ...i, caption: normaliseCaption(i.caption, trigger) })) });
}));

router.post('/training/estimate', wrap((req, res) => {
  const { baseId, steps, presetId } = req.body || {};
  const preset = trainingPresets[presetId] || trainingPresets.style;
  const base = trainingBases.find((b) => b.id === (baseId || preset.base)) || trainingBases[0];
  ok(res, { ...estimateCost(base, steps || preset.steps), base: base.id, label: base.label });
}));

// ----------------------------------------------------------------- training
router.post('/training/start', wrap((req, res) => {
  const { datasetId, presetId, baseId, steps, name, force } = req.body || {};
  const dataset = store.get('datasets', datasetId);
  if (!dataset) throw new Error('Dataset not found.');

  // Hard gates. `force` lets a lead override, but the block is the default so
  // nobody burns credits on a dataset that cannot succeed.
  const trig = validateTrigger(dataset.trigger);
  if (!trig.ok && !force) throw new Error(`Trigger rejected: ${trig.messages[0]}`);

  const audit = auditDataset(dataset, presetId || dataset.presetId);
  if (!audit.ready && !force) {
    const blockers = audit.checks.filter((c) => c.state === 'fail').map((c) => `${c.label}: ${c.detail}`);
    throw new Error(`Dataset not ready.\n${blockers.join('\n')}`);
  }

  ok(res, createTrainingJob({ datasetId, presetId: presetId || dataset.presetId, baseId, steps, name }));
}));

// --------------------------------------------------------------------- loras
router.get('/loras', (req, res) => ok(res, store.list('loras')));

router.delete('/loras/:id', (req, res) => {
  store.remove('loras', req.params.id);
  ok(res, { deleted: req.params.id });
});

// -------------------------------------------------------------------- graphs
router.get('/graphs', (req, res) =>
  ok(res, store.list('graphs').map(({ id, name, updatedAt }) => ({ id, name, updatedAt })))
);

router.get('/graphs/:id', (req, res) => {
  const g = store.get('graphs', req.params.id);
  return g ? ok(res, g) : fail(res, new Error('No such graph'), 404);
});

router.post('/graphs', wrap((req, res) => {
  const body = req.body || {};
  ok(res, store.put('graphs', {
    id: body.id || newId('g'),
    name: body.name || 'Untitled board',
    nodes: body.nodes || [],
    edges: body.edges || [],
    view: body.view || null,
    updatedAt: new Date().toISOString(),
  }));
}));
