// ---------------------------------------------------------------------------
// THE MODEL CATALOG
//
// Every node type on the canvas is declared here as data. Adding a model to
// the platform means adding an entry to this file - no UI code changes. The
// frontend fetches this over /api/models and builds nodes, ports, and the
// inspector panel from it.
//
// `params` entries drive the inspector widgets. `guard` blocks encode the
// house rules: Flux Dev wants guidance 2.5-4, LoRA weight above ~1.2 destroys
// the base model, ControlNet at 1.0 suppresses style. The inspector shows a
// warning whenever a value leaves the sane band.
// ---------------------------------------------------------------------------

const PROMPT_IN = { id: 'prompt', label: 'Input Prompt', kind: 'text' };
const IMAGE_IN = { id: 'image', label: 'Input Image', kind: 'image' };
const EXTRA_IN = { id: 'refs', label: 'Other Images', kind: 'image', multi: true };
const IMAGE_OUT = { id: 'image', label: 'Image', kind: 'image' };

export const catalog = [
  // ----------------------------------------------------------------- inputs
  {
    type: 'image-upload',
    title: 'Image Uploader',
    category: 'input',
    provider: 'local',
    accent: '#4f8cff',
    blurb: 'White model, channel image, Enscape frame, or reference photo.',
    cost: 0,
    inputs: [],
    outputs: [IMAGE_OUT],
    params: [{ id: 'asset', label: 'Image', type: 'image' }],
  },
  {
    type: 'text',
    title: 'Prompt',
    category: 'input',
    provider: 'local',
    accent: '#8b7bff',
    blurb: 'Plain text. Describe what the building IS, not how it should look.',
    cost: 0,
    inputs: [],
    outputs: [{ id: 'text', label: 'Text', kind: 'text' }],
    params: [{ id: 'value', label: 'Prompt', type: 'textarea', default: '' }],
  },

  // -------------------------------------------------------- image -> render
  {
    type: 'flux-lora',
    title: 'Flux Dev + Firm LoRA',
    category: 'model',
    provider: 'fal',
    endpoint: 'fal-ai/flux-control-lora-canny',
    blurb: 'House style transfer. ControlNet holds geometry, the LoRA supplies the look.',
    accent: '#3d5afe',
    cost: 0.035,
    inputs: [PROMPT_IN, IMAGE_IN, EXTRA_IN],
    outputs: [IMAGE_OUT],
    params: [
      {
        id: 'control',
        label: 'Structure Lock',
        type: 'select',
        default: 'depth',
        options: [
          { value: 'depth', label: 'Depth - white / clay models' },
          { value: 'canny', label: 'Canny Lines - channel & line images' },
          { value: 'img2img', label: 'Img2Img - Enscape with lighting' },
        ],
        help: 'Depth reads massing on untextured geometry; Canny needs real edges.',
      },
      {
        id: 'controlScale',
        label: 'Structure Strength',
        type: 'range',
        min: 0,
        max: 1,
        step: 0.05,
        default: 0.8,
        guard: {
          min: 0.5,
          max: 0.9,
          warn: 'Above 0.9 the geometry is locked so hard the style LoRA cannot express itself. Below 0.5 the building drifts.',
        },
      },
      { id: 'lora', label: 'Firm Style LoRA', type: 'lora', default: null },
      {
        id: 'loraWeight',
        label: 'LoRA Weight',
        type: 'range',
        min: 0,
        max: 2,
        step: 0.05,
        default: 0.85,
        guard: {
          min: 0.5,
          max: 1.2,
          warn: 'Past ~1.2 the adapter overpowers the base model and output collapses into unrelated imagery. Set 0.00 to A/B test whether the LoRA loads at all.',
        },
      },
      {
        id: 'guidance',
        label: 'Guidance Scale',
        type: 'range',
        min: 1,
        max: 20,
        step: 0.1,
        default: 3.5,
        guard: {
          min: 2,
          max: 5,
          warn: 'Flux Dev is guidance-distilled. Usable range is 2.5-4.0; high values burn the image and suppress ControlNet.',
        },
      },
      { id: 'steps', label: 'Steps', type: 'range', min: 8, max: 50, step: 1, default: 28 },
      { id: 'seed', label: 'Seed', type: 'seed', default: null },
    ],
  },
  {
    type: 'nano-banana',
    title: 'Nano Banana Pro',
    category: 'model',
    provider: 'gemini',
    endpoint: 'gemini-3-pro-image-preview',
    blurb: 'Best instruction-following and legible text. No LoRA support.',
    accent: '#f5b400',
    cost: 0.134,
    inputs: [PROMPT_IN, IMAGE_IN, EXTRA_IN],
    outputs: [IMAGE_OUT],
    params: [
      {
        id: 'resolution',
        label: 'Resolution',
        type: 'select',
        default: '2k',
        options: [
          { value: '1k', label: '1K - $0.039' },
          { value: '2k', label: '2K - $0.134' },
          { value: '4k', label: '4K - $0.24' },
        ],
      },
      {
        id: 'aspect',
        label: 'Aspect Ratio',
        type: 'select',
        default: '16:9',
        options: ['16:9', '3:2', '4:3', '1:1', '9:16'].map((v) => ({ value: v, label: v })),
      },
      { id: 'seed', label: 'Seed', type: 'seed', default: null },
    ],
  },
  {
    type: 'flux-kontext',
    title: 'Flux Kontext',
    category: 'model',
    provider: 'fal',
    endpoint: 'fal-ai/flux-pro/kontext',
    blurb: 'Targeted edits in plain language. Keeps whatever you did not mention.',
    accent: '#00b8a9',
    cost: 0.04,
    inputs: [PROMPT_IN, IMAGE_IN],
    outputs: [IMAGE_OUT],
    params: [
      { id: 'guidance', label: 'Guidance Scale', type: 'range', min: 1, max: 10, step: 0.1, default: 3.5 },
      { id: 'seed', label: 'Seed', type: 'seed', default: null },
    ],
  },
  {
    type: 'sdxl-lora',
    title: 'SDXL + LoRA',
    category: 'model',
    provider: 'replicate',
    endpoint: 'stability-ai/sdxl',
    blurb: 'Cheap bulk iteration. Weaker prompt adherence than Flux.',
    accent: '#7c4dff',
    cost: 0.004,
    inputs: [PROMPT_IN, IMAGE_IN],
    outputs: [IMAGE_OUT],
    params: [
      { id: 'lora', label: 'Firm Style LoRA', type: 'lora', default: null },
      {
        id: 'loraWeight',
        label: 'LoRA Weight',
        type: 'range',
        min: 0,
        max: 2,
        step: 0.05,
        default: 0.8,
        guard: { min: 0.4, max: 1.2, warn: 'Same rule as Flux: past 1.2 the adapter dominates and output degrades.' },
      },
      { id: 'guidance', label: 'CFG Scale', type: 'range', min: 1, max: 15, step: 0.5, default: 7 },
      { id: 'strength', label: 'Denoise Strength', type: 'range', min: 0, max: 1, step: 0.05, default: 0.65 },
      { id: 'seed', label: 'Seed', type: 'seed', default: null },
    ],
  },

  // -------------------------------------------------------------- utilities
  {
    type: 'preprocess',
    title: 'Structure Extract',
    category: 'process',
    provider: 'local',
    blurb: 'Preview the depth or edge map your model will actually receive.',
    accent: '#6b7a8f',
    cost: 0,
    inputs: [IMAGE_IN],
    outputs: [{ id: 'image', label: 'Control Map', kind: 'image' }],
    params: [
      {
        id: 'mode',
        label: 'Mode',
        type: 'select',
        default: 'depth',
        options: [
          { value: 'depth', label: 'Depth' },
          { value: 'canny', label: 'Canny Edges' },
          { value: 'normal', label: 'Normals' },
        ],
      },
      { id: 'low', label: 'Canny Low', type: 'range', min: 0, max: 255, step: 1, default: 100 },
      { id: 'high', label: 'Canny High', type: 'range', min: 0, max: 255, step: 1, default: 200 },
    ],
  },
  {
    type: 'upscale',
    title: 'Upscale 4K',
    category: 'process',
    provider: 'fal',
    endpoint: 'fal-ai/clarity-upscaler',
    blurb: 'Print-resolution pass for boards and large-format output.',
    accent: '#00897b',
    cost: 0.05,
    inputs: [IMAGE_IN],
    outputs: [IMAGE_OUT],
    params: [
      {
        id: 'scale',
        label: 'Scale',
        type: 'select',
        default: '2',
        options: [2, 3, 4].map((v) => ({ value: String(v), label: v + 'x' })),
      },
      {
        id: 'creativity',
        label: 'Creativity',
        type: 'range',
        min: 0,
        max: 1,
        step: 0.05,
        default: 0.2,
        guard: { max: 0.4, warn: 'High creativity invents detail. On a client deliverable that means inventing architecture.' },
      },
    ],
  },
  {
    type: 'compare',
    title: 'Compare',
    category: 'output',
    provider: 'local',
    blurb: 'Side-by-side A/B. Wire two variants in to judge settings honestly.',
    accent: '#546e7a',
    cost: 0,
    inputs: [
      { id: 'a', label: 'A', kind: 'image' },
      { id: 'b', label: 'B', kind: 'image' },
    ],
    outputs: [],
    params: [],
  },
];

export const byType = (type) => catalog.find((n) => n.type === type) || null;

// Training bases. `costPerStep` is provider list price, used for the estimate
// shown on the training board before anyone spends credits.
export const trainingBases = [
  {
    id: 'flux-dev',
    label: 'Flux.1 Dev - Fast',
    provider: 'fal',
    endpoint: 'fal-ai/flux-lora-fast-training',
    costPerStep: 0.0024,
    minSteps: 1000,
    note: 'Must match the Flux Dev inference node. A LoRA trained on another base loads without erroring and produces unrelated output.',
  },
  {
    id: 'flux-dev-quality',
    label: 'Flux.1 Dev - Advanced',
    provider: 'fal',
    endpoint: 'fal-ai/flux-lora-general-training',
    costPerStep: 0.0032,
    minSteps: 1500,
    note: 'Higher rank, more steps. The correct choice for a firm-wide style LoRA that must assert itself over Flux defaults.',
  },
  {
    id: 'sdxl',
    label: 'SDXL 1.0',
    provider: 'replicate',
    endpoint: 'lucataco/sdxl-lora-trainer',
    costPerStep: 0.0009,
    minSteps: 1200,
    note: 'Cheapest. Only usable by the SDXL inference node.',
  },
];

// Two very different jobs, two very different recipes. The training board
// switches its dataset checklist and hyperparameters off this.
export const trainingPresets = {
  style: {
    label: 'Style LoRA',
    goal: 'Teach the firm look, applied to buildings the model has never seen.',
    rank: 32,
    learningRate: 0.0001,
    steps: 2500,
    base: 'flux-dev-quality',
    dataset: {
      minImages: 25,
      idealImages: 40,
      minProjects: 8,
      captionRule: 'content',
      help: 'Building form must VARY across the set; only the look stays constant. Anything held constant becomes part of the trigger.',
    },
  },
  subject: {
    label: 'Subject LoRA',
    goal: 'Reproduce one specific building or product across new views.',
    rank: 16,
    learningRate: 0.0004,
    steps: 1400,
    base: 'flux-dev',
    dataset: {
      minImages: 10,
      idealImages: 20,
      minProjects: 1,
      captionRule: 'subject',
      help: 'One subject, many angles and lighting conditions. The opposite of a style set.',
    },
  },
};
