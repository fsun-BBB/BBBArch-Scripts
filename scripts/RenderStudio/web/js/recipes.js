// ---------------------------------------------------------------------------
// RECIPES
// Pre-wired graphs, one per input type the office actually produces. These
// exist so nobody has to remember that a white model wants Depth at 0.8 while
// an Enscape frame wants img2img at 0.6 — the recipe already knows.
// ---------------------------------------------------------------------------
import { state, set, uid, defByType, defaultParams } from './state.js';

const PROMPT = 'a mid-rise residential building, brick and bronze metal facade, ground-floor retail, street trees, pedestrians, overcast daylight, eye-level view';

export const recipes = [
  {
    id: 'white-model',
    name: 'White model → render',
    blurb: 'Clay / untextured massing. Depth lock at 0.8 so the massing survives.',
    build: () => chain({ control: 'depth', controlScale: 0.8, upscale: true }),
  },
  {
    id: 'channel',
    name: 'Channel / line image → render',
    blurb: 'Line or channel export. Canny at 0.9 — the edges are already clean.',
    build: () => chain({ control: 'canny', controlScale: 0.9, upscale: true }),
  },
  {
    id: 'enscape',
    name: 'Enscape → finished render',
    blurb: 'Already has light and material. Lower lock at 0.6 to let the style work.',
    build: () => chain({ control: 'img2img', controlScale: 0.6, upscale: true }),
  },
  {
    id: 'ab',
    name: 'A/B settings test',
    blurb: 'One input, two model nodes, a Compare. The honest way to judge a change.',
    build: () => abTest(),
  },
];

/** Uploader + prompt -> flux-lora -> optional upscale. */
function chain({ control, controlScale, upscale }) {
  const nodes = [];
  const edges = [];

  const upload = mk('image-upload', 60, 210);
  const text = mk('text', 60, 470, { value: PROMPT });
  const model = mk('flux-lora', 420, 240, { control, controlScale, lora: firstLora() });
  nodes.push(upload, text, model);

  edges.push(edge(upload, 'image', model, 'image', 'image'));
  edges.push(edge(text, 'text', model, 'prompt', 'text'));

  if (upscale) {
    const up = mk('upscale', 780, 300);
    nodes.push(up);
    edges.push(edge(model, 'image', up, 'image', 'image'));
  }
  return { nodes, edges };
}

/** Same input into two model nodes with different weights, into a Compare. */
function abTest() {
  const upload = mk('image-upload', 60, 250);
  const text = mk('text', 60, 510, { value: PROMPT });
  const a = mk('flux-lora', 420, 120, { control: 'depth', controlScale: 0.8, loraWeight: 0.6, lora: firstLora(), seed: 177121 });
  const b = mk('flux-lora', 420, 470, { control: 'depth', controlScale: 0.8, loraWeight: 1.0, lora: firstLora(), seed: 177121 });
  const cmp = mk('compare', 780, 290);

  return {
    nodes: [upload, text, a, b, cmp],
    edges: [
      edge(upload, 'image', a, 'image', 'image'),
      edge(upload, 'image', b, 'image', 'image'),
      edge(text, 'text', a, 'prompt', 'text'),
      edge(text, 'text', b, 'prompt', 'text'),
      edge(a, 'image', cmp, 'a', 'image'),
      edge(b, 'image', cmp, 'b', 'image'),
    ],
  };
}

function mk(type, x, y, params = {}) {
  const def = defByType(type);
  return {
    id: uid('n'),
    type,
    x,
    y,
    params: { ...defaultParams(def), ...params },
    status: 'idle',
    result: null,
    error: null,
    jobId: null,
  };
}

const edge = (from, fromPort, to, toPort, kind) => ({
  id: uid('e'),
  from: { node: from.id, port: fromPort },
  to: { node: to.id, port: toPort },
  kind,
});

const firstLora = () => state.loras.find((l) => l.compatible?.includes('flux-lora'))?.id || null;

export function applyRecipe(id) {
  const recipe = recipes.find((r) => r.id === id);
  if (!recipe) return;
  const { nodes, edges } = recipe.build();
  set({ nodes, edges, selectedId: null, graphName: recipe.name });
}
