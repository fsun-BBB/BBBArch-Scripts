# BBB Render Studio

An infinite node canvas for AI rendering plus a LoRA training board, for firm-wide
use. Feed it a white model, a channel image, or a rough Enscape frame; get back a
render in the office house style.

Same shape as xFigura — one canvas, node-wired pipelines, many models behind one
UI — with the parts that platform leaves to guesswork made explicit:

- **Guarded parameters.** Every slider carries a sane band from the catalog. Push
  guidance to 20 or LoRA weight to 4.0 and the inspector says what will break and
  why, inline, before you spend anything.
- **Base-compatibility enforcement.** A LoRA trained on Flux cannot be selected on
  an SDXL node. Mismatched bases load without erroring and emit garbage; the
  picker greys them out instead.
- **Automatic trigger injection.** The trigger token is prepended to the prompt at
  run time. Forgetting it is the most common reason a trained LoRA appears to do
  nothing.
- **A dataset audit that blocks bad training runs.** Trigger-word collisions,
  one-project "style" sets, and captions that describe the look are caught before
  a single credit is billed.
- **Prompt hygiene.** A node warns when its wired prompt reads like chat output
  rather than a description — conditioning on commentary produces unrelated images.

## Run it

```bash
npm install
npm start          # http://localhost:5178
```

With no `.env` the server starts in **mock mode**: the entire UI works, jobs walk
through queued → running → succeeded on a timer, and each render resolves to a
placeholder labelled with the settings actually used. Nothing is billed. Good for
demos, UI work, and training the team.

To go live, `cp .env.example .env`, add one provider key, and set `MOCK_MODE=0`.
Providers without a key silently fall back to mock, so partial configuration is fine.

## Layout

```
server/
  config.js              .env reader, mock-mode decision
  store.js               flat-file JSON persistence (swap for a DB later)
  jobs.js                one lifecycle for inference and training
  routes.js              HTTP surface
  training-rules.js      trigger validation, dataset audit, caption linting
  providers/
    catalog.js           EVERY node and training base, as data
    index.js             fal / replicate / gemini / huggingface / mock adapters
web/
  index.html
  js/
    state.js             observable store, graph model, topological ordering
    canvas.js            pan / zoom / drag / wiring
    inspector.js         settings panel, generated from the catalog
    training.js          the training board
    recipes.js           pre-wired graphs per input type
    runner.js            graph execution
    library.js           trained-LoRA library
```

### Adding a model

Append one entry to `server/providers/catalog.js`. Nodes, ports, inspector
widgets, cost display, and palette entry are all generated from it. No UI code
changes. If it needs a new provider, add an adapter to `providers/index.js`
exposing `submit(job)` and `poll(job)`.

## Provider notes

| Provider | Used for | Cost |
| --- | --- | --- |
| **fal.ai** | Flux inference, Flux LoRA training, upscaling | ~$0.035/image; training $0.0024/step, 1000-step minimum (~$2.40 floor) |
| **Replicate** | cheaper bulk SDXL passes, alternate trainer | ~$0.004–0.005/image |
| **Google Gemini** | Nano Banana Pro | $0.039 (1K) / $0.134 (2K) / $0.24 (4K); Batch API halves it |
| **Hugging Face** | model metadata, dataset + private LoRA hosting | free for hosting; inference is billed, not free |

Hugging Face is **not** a free Flux endpoint. `hf-inference` is CPU-oriented now;
HF Inference Providers route to fal/Replicate/others and bill through. Use HF for
storage and weights, not as a way to avoid inference cost.

## Training a firm-wide style LoRA

1. **Model Training → Style LoRA.**
2. Trigger word: take the **Suggest** button's output. A rare token has no
   pretrained meaning to fight. Real words — `graphic`, `render`, `modern` — lose
   to the base model's own idea of them, and the board rejects them.
3. Dataset: **30–50 finished renders across 8+ different projects.** The building
   must vary; only the look stays constant. Anything held constant across the set
   gets absorbed into the trigger, which is why a single-project set produces a
   subject LoRA no matter what you label it.
4. Tag project / lighting / view per image. The audit uses these to tell a style
   set from a subject set.
5. Captions describe **content only**. "mid-rise brick residential building at
   dusk, pedestrians" — never "photorealistic, high quality, BBB style". Whatever
   you name is attributed away from the trigger, so describing your style trains
   it out. **Strip style words + prefix trigger** does the cleanup.
6. Base: **Flux.1 Dev — Advanced**. The Fast preset is undertrained for style work.
7. Train when readiness clears. ~$8 at 2500 steps.

Pilot at ~20 images and test against 3–4 white models before scaling to 50.
If exterior and interior looks differ meaningfully, train two LoRAs — one adapter
forced to cover both averages them into something that serves neither.

## Canvas settings by input type

The recipes in the left rail set these already:

| Input | Structure Lock | Strength |
| --- | --- | --- |
| White / clay model | Depth | 0.75–0.85 |
| Channel / line image | Canny | 0.85–0.95 |
| Enscape with lighting | Img2Img | 0.55–0.70 |

Across all of them: LoRA weight **0.7–1.0**, guidance **3.0–4.0**. Leave the seed
empty while judging a settings change — a fixed seed reproduces the previous image
and makes your change look like it did nothing.

## Shortcuts

- Drag empty canvas — pan · scroll — zoom · `F` — fit
- Drag port to port — wire · drag a filled input port — detach
- `Delete` — remove selected node

Boards autosave and the last one reopens on load.
