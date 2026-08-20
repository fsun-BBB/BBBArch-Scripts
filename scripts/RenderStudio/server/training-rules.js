// ---------------------------------------------------------------------------
// TRAINING RULES
//
// This is the part xFigura does not have, and the reason the first LoRA
// attempt produced a cartoon fox instead of a building: nothing warned that
// the trigger word "graphic" collides with an enormous pretrained concept
// (graphic novel / graphic art / graphic illustration), that 11 images of one
// tower cannot become a style LoRA, or that captions describing the style
// train the style out.
//
// Everything here runs before a single credit is spent.
// ---------------------------------------------------------------------------
import { trainingPresets } from './providers/catalog.js';

// Tokens with strong pretrained priors in Flux / SD text encoders. A trigger
// drawn from this list will lose to the base model every time.
const POISONED_TOKENS = new Set([
  'graphic', 'graphics', 'render', 'rendering', 'architecture', 'architectural',
  'modern', 'contemporary', 'building', 'tower', 'facade', 'house', 'design',
  'style', 'photo', 'photorealistic', 'realistic', 'sketch', 'drawing', 'art',
  'artistic', 'illustration', 'concept', 'model', 'studio', 'visualization',
  'viz', 'cinematic', 'professional', 'quality', 'detailed', 'beautiful',
  'minimal', 'minimalist', 'brutalist', 'classical', 'urban', 'city', 'plan',
]);

// Words that describe the LOOK. In a style-LoRA caption these are actively
// harmful: anything you name is attributed away from the trigger token.
const STYLE_WORDS = [
  'photorealistic', 'realistic', 'high quality', 'highly detailed', 'detailed',
  'masterpiece', 'best quality', '8k', '4k', 'hdr', 'award winning',
  'beautiful lighting', 'cinematic', 'professional', 'stunning', 'sharp focus',
  'octane', 'unreal engine', 'vray', 'lumion', 'enscape', 'style of', 'trending',
];

/**
 * Validate a candidate trigger word.
 * Returns { ok, level, messages[], suggestion }
 */
export function validateTrigger(raw) {
  const word = String(raw || '').trim().toLowerCase();
  const messages = [];
  let level = 'ok';

  const fail = (msg) => {
    messages.push(msg);
    level = 'error';
  };
  const warn = (msg) => {
    messages.push(msg);
    if (level !== 'error') level = 'warn';
  };

  if (!word) {
    return { ok: false, level: 'error', messages: ['Pick a trigger word.'], suggestion: suggestTrigger() };
  }
  if (/\s/.test(word)) {
    fail('Use a single token with no spaces. Multi-word triggers split into separate embeddings and dilute.');
  }
  if (POISONED_TOKENS.has(word)) {
    fail(
      `"${word}" is a common word with a strong pretrained meaning. Flux will render its own idea of "${word}" ` +
        `and overpower your adapter. This is exactly the failure mode that produced character art from a building dataset.`
    );
  }
  if (/^[a-z]+$/.test(word) && word.length > 3 && !POISONED_TOKENS.has(word) && isDictionaryish(word)) {
    warn(`"${word}" looks like an ordinary English word. Prefer a rare string so the token starts with no prior meaning.`);
  }
  if (word.length < 4) {
    warn('Very short tokens can collide with subword fragments. 5-9 characters is the sweet spot.');
  }
  if (word.length > 16) {
    warn('Long triggers get split into several tokens, which weakens the binding.');
  }
  if (/[^a-z0-9_]/.test(word)) {
    fail('Letters, digits and underscore only.');
  }

  return {
    ok: level !== 'error',
    level,
    messages: messages.length ? messages : ['Good trigger: rare, single-token, no competing prior.'],
    suggestion: level === 'ok' ? null : suggestTrigger(),
  };
}

// Crude heuristic: real English words are mostly pronounceable alternations.
// A rare trigger like "bbbtwr" or "sksfcd" fails this test, which is the point.
function isDictionaryish(word) {
  const vowels = (word.match(/[aeiou]/g) || []).length;
  return vowels / word.length > 0.28;
}

export function suggestTrigger(seed = 'bbb') {
  const tails = ['rndr', 'styl', 'hous', 'viz', 'frm', 'look'];
  const tail = tails[Math.floor(Math.random() * tails.length)];
  const digit = Math.floor(Math.random() * 90 + 10);
  return `${seed}${tail}${digit}`;
}

/**
 * Score a dataset against the chosen preset.
 * Returns { score 0-100, ready, checks[] } where each check is
 * { id, label, state: pass|warn|fail, detail }
 */
export function auditDataset(dataset, presetId) {
  const preset = trainingPresets[presetId] || trainingPresets.style;
  const req = preset.dataset;
  const images = dataset.images || [];
  const checks = [];

  const add = (id, label, state, detail) => checks.push({ id, label, state, detail });

  // --- count
  if (images.length < Math.min(6, req.minImages)) {
    add('count', 'Image count', 'fail', `${images.length} images. A LoRA cannot generalise below ~${req.minImages}.`);
  } else if (images.length < req.minImages) {
    add('count', 'Image count', 'warn', `${images.length} images. ${req.minImages} is the floor for a ${preset.label}, ${req.idealImages} is comfortable.`);
  } else {
    add('count', 'Image count', 'pass', `${images.length} images.`);
  }

  // --- project diversity: the single biggest style-LoRA failure
  const projects = new Set(images.map((i) => (i.project || '').trim().toLowerCase()).filter(Boolean));
  if (presetId === 'style') {
    if (projects.size === 0) {
      add('projects', 'Project spread', 'warn', 'No project tags. Tag each image so spread can be checked - one project means a subject LoRA, not a style LoRA.');
    } else if (projects.size < req.minProjects) {
      add(
        'projects',
        'Project spread',
        projects.size <= 2 ? 'fail' : 'warn',
        `${projects.size} project(s). A style LoRA needs ${req.minProjects}+ or it memorises the building instead of the look.`
      );
    } else {
      add('projects', 'Project spread', 'pass', `${projects.size} projects.`);
    }
  } else {
    add('projects', 'Single subject', projects.size <= 1 ? 'pass' : 'warn', projects.size <= 1 ? 'One subject, as intended.' : `${projects.size} projects tagged - a subject LoRA should cover one.`);
  }

  // --- lighting variety
  const lighting = new Set(images.map((i) => (i.lighting || '').trim().toLowerCase()).filter(Boolean));
  if (lighting.size >= 3) add('lighting', 'Lighting variety', 'pass', `${lighting.size} conditions.`);
  else if (lighting.size === 0) add('lighting', 'Lighting variety', 'warn', 'Untagged. If every image is dusk, the LoRA will only ever produce dusk.');
  else add('lighting', 'Lighting variety', lighting.size === 1 ? 'warn' : 'pass', `${lighting.size} condition(s). Aim for 2-3 so lighting stays promptable.`);

  // --- view variety
  const views = new Set(images.map((i) => (i.view || '').trim().toLowerCase()).filter(Boolean));
  add('views', 'View variety', views.size >= 3 ? 'pass' : 'warn', views.size >= 3 ? `${views.size} view types.` : 'Mix eye-level, aerial, and detail crops so scale is not baked in.');

  // --- captions
  const missing = images.filter((i) => !String(i.caption || '').trim());
  const styleLeaks = images.filter((i) => findStyleWords(i.caption).length);
  if (missing.length) {
    add('captions', 'Captions written', missing.length > images.length / 2 ? 'fail' : 'warn', `${missing.length} image(s) uncaptioned.`);
  } else {
    add('captions', 'Captions written', 'pass', 'All images captioned.');
  }
  if (styleLeaks.length) {
    add(
      'caption-style',
      'Captions describe content only',
      'fail',
      `${styleLeaks.length} caption(s) describe the LOOK (${[...new Set(styleLeaks.flatMap((i) => findStyleWords(i.caption)))].slice(0, 4).join(', ')}). ` +
        'Whatever you name is attributed away from your trigger - describing your style trains it out.'
    );
  } else {
    add('caption-style', 'Captions describe content only', 'pass', 'No style words leaking into captions.');
  }

  // --- trigger present in every caption
  const trig = String(dataset.trigger || '').trim().toLowerCase();
  if (trig) {
    const without = images.filter((i) => !String(i.caption || '').toLowerCase().includes(trig));
    add('trigger-in-caption', 'Trigger in every caption', without.length ? 'fail' : 'pass', without.length ? `${without.length} caption(s) missing "${trig}".` : `"${trig}" present throughout.`);
  }

  // --- resolution
  const small = images.filter((i) => i.width && i.width < 1024);
  add('resolution', 'Resolution', small.length ? 'warn' : 'pass', small.length ? `${small.length} image(s) under 1024px. Detail you cannot see cannot be learned.` : 'All at least 1024px.');

  const weight = { pass: 1, warn: 0.5, fail: 0 };
  const score = Math.round((checks.reduce((s, c) => s + weight[c.state], 0) / checks.length) * 100);
  return { score, ready: !checks.some((c) => c.state === 'fail'), checks, preset: { id: presetId, ...preset } };
}

export function findStyleWords(caption) {
  const text = String(caption || '').toLowerCase();
  return STYLE_WORDS.filter((w) => text.includes(w));
}

/** Strip style words and ensure the trigger leads the caption. */
export function normaliseCaption(caption, trigger) {
  let text = String(caption || '');
  for (const w of STYLE_WORDS) {
    text = text.replace(new RegExp(`\\b${w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b,?\\s*`, 'gi'), '');
  }
  text = text.replace(/\s*,\s*,+/g, ', ').replace(/^[\s,]+|[\s,]+$/g, '').trim();
  const trig = String(trigger || '').trim();
  if (trig && !text.toLowerCase().startsWith(trig.toLowerCase())) {
    text = text ? `${trig}, ${text}` : trig;
  }
  return text;
}

export function estimateCost(base, steps) {
  const billable = Math.max(steps, base.minSteps);
  return { billableSteps: billable, usd: Number((billable * base.costPerStep).toFixed(2)) };
}
