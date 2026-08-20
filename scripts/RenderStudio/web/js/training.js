// ---------------------------------------------------------------------------
// THE TRAINING BOARD
//
// Left column: what you are training and what you are training it on.
// Right column: whether it can possibly work, what it will cost, and the queue.
//
// The readiness panel is the whole point. Every check on it corresponds to a
// way a LoRA silently fails: a trigger word that collides with a pretrained
// concept, one building masquerading as a firm style, captions that describe
// the look and therefore train it out, a base that will not match the
// inference node. Nothing is submitted until those clear.
// ---------------------------------------------------------------------------
import { api, imageSize } from './api.js';
import { state, set, on, uid } from './state.js';
import { esc, el, pickFiles, uploadFiles, onImageDrop, toast, debounce } from './ui.js';

let host;
const LIGHTING = ['', 'overcast', 'clear day', 'dusk', 'night', 'golden hour', 'interior'];
const VIEWS = ['', 'eye-level', 'aerial', 'detail crop', 'elevation', 'interior', 'site plan'];

export function initTraining() {
  host = document.getElementById('training');
  on('dataset', renderShell);
  on('audit', renderSide);
  on('triggerVerdict', renderVerdict);
  on('jobs', renderSide);
  bootstrap();
}

async function bootstrap() {
  try {
    const existing = await api.datasets();
    set({ dataset: existing[0] || blankDataset() });
  } catch {
    set({ dataset: blankDataset() });
  }
  refreshAudit();
  refreshJobs();
  setInterval(refreshJobs, 2500);
}

const blankDataset = () => ({
  id: uid('ds'),
  name: 'Firm House Style v1',
  trigger: '',
  presetId: 'style',
  images: [],
});

/* --------------------------------------------------------------- persistence */

const persist = debounce(async () => {
  try {
    await api.saveDataset(state.dataset);
  } catch (err) {
    toast(err.message, 'err');
  }
}, 700);

const refreshAudit = debounce(async () => {
  try {
    set({ audit: await api.audit(state.dataset, state.dataset.presetId) });
  } catch (err) {
    /* audit is advisory; a failure should not block editing */
  }
}, 300);

const refreshTrigger = debounce(async () => {
  const trigger = state.dataset.trigger;
  if (!trigger) return set({ triggerVerdict: null });
  try {
    set({ triggerVerdict: await api.validateTrigger(trigger) });
  } catch {
    /* ignore */
  }
}, 350);

async function refreshJobs() {
  try {
    const jobs = await api.jobs(20);
    const training = jobs.filter((j) => j.kind === 'train');
    // Poll anything unsettled so progress advances and finished runs publish.
    await Promise.all(training.filter((j) => j.status === 'queued' || j.status === 'running').map((j) => api.job(j.id)));
    set({ jobs: training });
    const loras = await api.loras();
    if (loras.length !== state.loras.length) set({ loras });
  } catch {
    /* offline is fine */
  }
}

function mutate(fn, { structural = false } = {}) {
  fn(state.dataset);
  persist();
  refreshAudit();
  if (structural) set({ dataset: state.dataset });
}

/* -------------------------------------------------------------------- shell */

function renderShell() {
  const ds = state.dataset;
  if (!ds) return;
  const presets = state.trainingPresets || {};

  host.innerHTML = `
    <div class="page-head">
      <h1>Model Training</h1>
      <p>
        Train a LoRA the whole office can point at a white model, a channel image, or a rough Enscape frame.
        The readiness panel blocks the two failures that waste the most credits: a trigger word the base model
        already has strong opinions about, and a dataset that is one building pretending to be a house style.
      </p>
    </div>

    <div class="tr-grid">
      <div>
        <div class="card">
          <h3>1 · What kind of LoRA</h3>
          <p class="sub">This choice changes the dataset requirements, the hyperparameters, and the captioning rule.</p>
          <div class="preset-row">
            ${Object.entries(presets)
              .map(
                ([id, p]) => `
              <button class="preset ${ds.presetId === id ? 'is-active' : ''}" data-preset="${id}">
                <strong>${esc(p.label)}</strong>
                <span>${esc(p.goal)}</span>
                <dl>
                  <dt>images</dt><dd>${p.dataset.minImages}–${p.dataset.idealImages}</dd>
                  <dt>projects</dt><dd>${p.dataset.minProjects}+</dd>
                  <dt>rank</dt><dd>${p.rank}</dd>
                  <dt>steps</dt><dd>${p.steps}</dd>
                  <dt>lr</dt><dd>${p.learningRate}</dd>
                </dl>
              </button>`
              )
              .join('')}
          </div>
          <div class="help" style="margin-top:10px">${esc(presets[ds.presetId]?.dataset.help || '')}</div>
        </div>

        <div class="card">
          <h3>2 · Identity</h3>
          <p class="sub">The trigger is the token that summons your style at inference. It must be rare.</p>
          <div class="field">
            <label><span>Model name</span></label>
            <input type="text" id="ds-name" value="${esc(ds.name)}" />
          </div>
          <div class="field" style="margin-bottom:0">
            <label><span>Trigger word</span><span class="val">single token</span></label>
            <div class="trigger-wrap">
              <input type="text" id="ds-trigger" value="${esc(ds.trigger)}" placeholder="bbbrndr47" spellcheck="false" />
              <button class="btn btn-sm" id="btn-suggest" style="flex:0 0 auto">Suggest</button>
            </div>
            <div id="trigger-verdict"></div>
          </div>
        </div>

        <div class="card">
          <h3>3 · Dataset <span style="color:var(--text-faint);font-weight:400;text-transform:none;letter-spacing:0">
            — ${ds.images.length} image${ds.images.length === 1 ? '' : 's'}</span></h3>
          <p class="sub">
            Tag each image so the audit can tell a style set from a subject set. Captions describe the
            <em>content</em> only — anything you name is attributed away from the trigger.
          </p>
          <div class="row" style="margin-bottom:12px">
            <button class="btn btn-sm" id="btn-add">Add images</button>
            <button class="btn btn-sm" id="btn-autocaption">Draft captions</button>
            <button class="btn btn-sm" id="btn-clean">Strip style words + prefix trigger</button>
          </div>
          <div class="ds-grid" id="ds-grid"></div>
        </div>
      </div>

      <div>
        <div class="card is-sticky" id="side"></div>
      </div>
    </div>`;

  host.querySelectorAll('[data-preset]').forEach((btn) => {
    btn.onclick = () => mutate((d) => { d.presetId = btn.dataset.preset; }, { structural: true });
  });

  host.querySelector('#ds-name').oninput = (e) => mutate((d) => { d.name = e.target.value; });

  const trig = host.querySelector('#ds-trigger');
  trig.oninput = () => {
    mutate((d) => { d.trigger = trig.value.trim().toLowerCase(); });
    refreshTrigger();
  };
  host.querySelector('#btn-suggest').onclick = async () => {
    const { trigger } = await api.suggestTrigger('bbb');
    trig.value = trigger;
    mutate((d) => { d.trigger = trigger; });
    refreshTrigger();
  };

  host.querySelector('#btn-add').onclick = async () => addImages(await pickFiles({ multiple: true }));
  host.querySelector('#btn-autocaption').onclick = draftCaptions;
  host.querySelector('#btn-clean').onclick = cleanCaptions;

  renderGrid();
  renderVerdict();
  renderSide();
  refreshTrigger();
}

/* ------------------------------------------------------------------- grid */

function renderGrid() {
  const grid = host.querySelector('#ds-grid');
  if (!grid) return;
  const ds = state.dataset;

  grid.innerHTML =
    ds.images.map((img, i) => tileHtml(img, i)).join('') +
    `<button class="ds-add" id="ds-add-tile"><span class="plus">+</span><span>Add or drop images</span></button>`;

  grid.querySelectorAll('.ds-tile').forEach((tile) => {
    const i = Number(tile.dataset.index);
    tile.querySelector('.rm').onclick = () =>
      mutate((d) => { d.images.splice(i, 1); }, { structural: true });

    const caption = tile.querySelector('[data-f="caption"]');
    caption.oninput = (e) => {
      mutate((d) => { d.images[i].caption = e.target.value; });
      paintLeak(tile, e.target.value);
    };
    tile.querySelector('[data-f="project"]').oninput = (e) =>
      mutate((d) => { d.images[i].project = e.target.value; });
    tile.querySelector('[data-f="lighting"]').onchange = (e) =>
      mutate((d) => { d.images[i].lighting = e.target.value; });
    tile.querySelector('[data-f="view"]').onchange = (e) =>
      mutate((d) => { d.images[i].view = e.target.value; });
  });

  grid.querySelector('#ds-add-tile').onclick = async () => addImages(await pickFiles({ multiple: true }));
  // Drop is handled on the grid only. Binding the add-tile too would fire both
  // handlers as the event bubbles and import every file twice.
  onImageDrop(grid, addImages);
}

/** Keep the per-tile style-word warning in sync as the caption is typed. */
function paintLeak(tile, caption) {
  const leaks = styleLeaks(caption);
  tile.classList.toggle('is-bad', leaks.length > 0);
  let box = tile.querySelector('.leak');
  if (!leaks.length) return box?.remove();
  if (!box) {
    box = el('<div class="leak"></div>');
    tile.querySelector('[data-f="caption"]').after(box);
  }
  box.textContent = `Style words: ${leaks.join(', ')}. These train your style out.`;
}

function tileHtml(img, i) {
  const leaks = styleLeaks(img.caption);
  return `
    <div class="ds-tile ${leaks.length ? 'is-bad' : ''}" data-index="${i}">
      <div class="thumb" style="background-image:url('${esc(img.asset)}')">
        <button class="rm" title="Remove">×</button>
      </div>
      <div class="fields">
        <textarea data-f="caption" placeholder="mid-rise brick residential building at dusk, pedestrians, street trees">${esc(img.caption || '')}</textarea>
        ${leaks.length ? `<div class="leak">Style words: ${esc(leaks.join(', '))}. These train your style out.</div>` : ''}
        <input type="text" data-f="project" placeholder="project tag" value="${esc(img.project || '')}" />
        <div class="row">
          <select data-f="lighting">
            ${LIGHTING.map((v) => `<option value="${v}" ${v === (img.lighting || '') ? 'selected' : ''}>${v || 'lighting…'}</option>`).join('')}
          </select>
          <select data-f="view">
            ${VIEWS.map((v) => `<option value="${v}" ${v === (img.view || '') ? 'selected' : ''}>${v || 'view…'}</option>`).join('')}
          </select>
        </div>
      </div>
    </div>`;
}

// Mirrors the server list; used only for instant per-tile feedback.
const STYLE_WORDS = ['photorealistic', 'realistic', 'high quality', 'highly detailed', 'detailed', 'masterpiece', '8k', '4k', 'hdr', 'cinematic', 'professional', 'stunning', 'octane', 'unreal engine', 'vray', 'lumion', 'enscape', 'award winning', 'beautiful lighting'];
const styleLeaks = (caption) => STYLE_WORDS.filter((w) => String(caption || '').toLowerCase().includes(w));

async function addImages(files) {
  if (!files?.length) return;
  try {
    const uploaded = await uploadFiles(files);
    const sized = await Promise.all(
      uploaded.map(async (u) => ({ ...u, ...(await imageSize(u.asset)) }))
    );
    mutate((d) => {
      for (const u of sized) {
        d.images.push({
          asset: u.asset,
          name: u.name,
          caption: '',
          project: guessProject(u.name),
          lighting: '',
          view: '',
          width: u.width,
          height: u.height,
        });
      }
    }, { structural: true });
    toast(`Added ${sized.length} image${sized.length === 1 ? '' : 's'}.`, 'ok');
  } catch (err) {
    toast(err.message, 'err');
  }
}

// Filenames in practice look like "2214_TowerSt_Ext_01.jpg" — the leading job
// number is a usable project tag, which saves tagging 40 images by hand.
function guessProject(name) {
  const m = /^(\d{3,5})[_\- ]/.exec(name || '');
  return m ? m[1] : '';
}

function draftCaptions() {
  // Deliberately a skeleton, not an AI guess: a wrong auto-caption is worse
  // than a blank one, because it silently teaches the model the wrong content.
  mutate((d) => {
    for (const img of d.images) {
      if (String(img.caption || '').trim()) continue;
      const bits = [img.view, 'of a building', img.lighting ? `in ${img.lighting}` : ''].filter(Boolean);
      img.caption = bits.join(' ').replace(/\s+/g, ' ').trim();
    }
  }, { structural: true });
  toast('Skeleton captions written. Edit them — describe the actual building.', 'ok');
}

async function cleanCaptions() {
  try {
    const { images } = await api.normaliseCaptions(state.dataset.images, state.dataset.trigger);
    mutate((d) => { d.images = images; }, { structural: true });
    toast('Style words removed and trigger prefixed.', 'ok');
  } catch (err) {
    toast(err.message, 'err');
  }
}

/* ---------------------------------------------------------------- verdict */

function renderVerdict() {
  const box = host?.querySelector('#trigger-verdict');
  if (!box) return;
  const v = state.triggerVerdict;
  if (!v) {
    box.innerHTML = '';
    return;
  }
  box.innerHTML = `
    <div class="verdict ${v.level}">
      <ul>${v.messages.map((m) => `<li>${esc(m)}</li>`).join('')}</ul>
      ${v.suggestion ? `<div style="margin-top:8px">Try <code>${esc(v.suggestion)}</code> instead.</div>` : ''}
    </div>`;
}

/* -------------------------------------------------------- readiness + queue */

function renderSide() {
  const side = host?.querySelector('#side');
  if (!side) return;
  const audit = state.audit;
  const ds = state.dataset;
  const bases = state.trainingBases || [];
  const preset = state.trainingPresets?.[ds.presetId];
  const chosenBase = bases.find((b) => b.id === (ds.baseId || preset?.base)) || bases[0];
  const steps = ds.steps || preset?.steps || 1500;
  const billable = Math.max(steps, chosenBase?.minSteps || 0);
  const cost = (billable * (chosenBase?.costPerStep || 0)).toFixed(2);

  const scoreColour = !audit ? 'var(--text-faint)' : audit.score >= 80 ? 'var(--ok)' : audit.score >= 55 ? 'var(--warn)' : 'var(--bad)';

  side.innerHTML = `
    <h3>Readiness</h3>
    <p class="sub">Checked before anything is submitted.</p>

    <div class="score-ring">
      <div class="num" style="color:${scoreColour}">${audit ? audit.score : '–'}</div>
      <div class="cap">${
        audit
          ? audit.ready
            ? 'No blockers. Remaining warnings are judgement calls.'
            : 'Blocked. Fix the red items below.'
          : 'Add images to score this dataset.'
      }</div>
    </div>

    <div class="checks">
      ${(audit?.checks || [])
        .map(
          (c) => `<div class="check ${c.state}">
            <span class="icon">${c.state === 'pass' ? '✓' : c.state === 'warn' ? '!' : '×'}</span>
            <span><span class="label">${esc(c.label)}</span> — <span class="detail">${esc(c.detail)}</span></span>
          </div>`
        )
        .join('')}
    </div>

    <hr style="border:0;border-top:1px solid var(--line-soft);margin:16px 0" />

    <h3>Base model</h3>
    <div class="field">
      <select id="base-select">
        ${bases.map((b) => `<option value="${b.id}" ${b.id === chosenBase?.id ? 'selected' : ''}>${esc(b.label)}</option>`).join('')}
      </select>
      <div class="help">${esc(chosenBase?.note || '')}</div>
    </div>

    <div class="field">
      <label><span>Steps</span><span class="val">${steps}</span></label>
      <input type="range" id="steps-range" min="500" max="4000" step="100" value="${steps}" />
      <div class="help">Billed at ${billable} (provider minimum ${chosenBase?.minSteps || 0}).</div>
    </div>

    <dl class="kv">
      <dt>rank</dt><dd>${preset?.rank ?? '–'}</dd>
      <dt>learning rate</dt><dd>${preset?.learningRate ?? '–'}</dd>
      <dt>trigger</dt><dd>${esc(ds.trigger || '—')}</dd>
      <dt>estimate</dt><dd>$${cost}</dd>
    </dl>

    <button class="btn btn-primary" id="btn-train" style="width:100%;margin-top:14px"
      ${audit?.ready && ds.trigger ? '' : 'disabled'}>Start training · $${cost}</button>
    ${
      audit && !audit.ready
        ? `<button class="btn btn-sm btn-danger" id="btn-force" style="width:100%;margin-top:7px">Override blockers and train anyway</button>`
        : ''
    }

    ${
      state.jobs.length
        ? `<hr style="border:0;border-top:1px solid var(--line-soft);margin:16px 0" />
           <h3>Queue</h3>
           ${state.jobs.map(jobHtml).join('')}`
        : ''
    }`;

  side.querySelector('#base-select').onchange = (e) => {
    mutate((d) => { d.baseId = e.target.value; });
    renderSide();
  };
  side.querySelector('#steps-range').oninput = (e) => {
    state.dataset.steps = Number(e.target.value);
    persist();
    renderSide();
  };
  side.querySelector('#btn-train').onclick = () => startTraining(false);
  side.querySelector('#btn-force')?.addEventListener('click', () => startTraining(true));
}

function jobHtml(job) {
  const pct = Math.round((job.progress || 0) * 100);
  return `
    <div class="job">
      <div class="job-top">
        <span class="name">${esc(job.name || 'training')}</span>
        <span class="state ${job.status}">${job.status}</span>
      </div>
      <div class="bar"><i style="width:${job.status === 'succeeded' ? 100 : pct}%"></i></div>
      <div class="job-meta">${esc(job.trigger || '')} · ${job.billableSteps || 0} steps · $${(job.estCost || 0).toFixed(2)}${
        job.error ? ` · ${esc(job.error)}` : ''
      }</div>
    </div>`;
}

async function startTraining(force) {
  const ds = state.dataset;
  try {
    await api.saveDataset(ds);
    const job = await api.startTraining({
      datasetId: ds.id,
      presetId: ds.presetId,
      baseId: ds.baseId,
      steps: ds.steps,
      name: ds.name,
      force,
    });
    toast(`Training queued: ${job.name} (${job.billableSteps} steps, $${job.estCost.toFixed(2)}).`, 'ok');
    refreshJobs();
  } catch (err) {
    toast(err.message, 'err');
  }
}
