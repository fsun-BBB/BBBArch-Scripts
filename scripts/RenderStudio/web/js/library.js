// LoRA library: everything the office has trained, and what it is usable on.
import { api } from './api.js';
import { state, on, set } from './state.js';
import { esc, toast } from './ui.js';

let host;

export function initLibrary() {
  host = document.getElementById('library');
  on('loras', render);
  render();
}

function render() {
  const loras = state.loras || [];
  host.innerHTML = `
    <div class="page-head">
      <h1>LoRA Library</h1>
      <p>
        Every trained adapter, its trigger, and the base it is bound to. A LoRA only works on inference nodes
        built on the same base — the canvas greys out mismatches rather than letting it load and produce noise.
      </p>
    </div>
    ${
      loras.length
        ? `<div class="lora-grid">${loras.map(card).join('')}</div>`
        : `<div class="card" style="max-width:560px">
             <h3>Nothing trained yet</h3>
             <p class="sub" style="margin:0">
               Build the first one on the Model Training tab. For a firm-wide house style, gather 30–50 finished
               renders across 8+ projects — the building has to vary so that only the look is learned.
             </p>
           </div>`
    }`;

  host.querySelectorAll('[data-del]').forEach((btn) => {
    btn.onclick = async () => {
      await api.deleteLora(btn.dataset.del);
      set({ loras: await api.loras() });
      toast('Removed from library.', 'ok');
    };
  });
  host.querySelectorAll('[data-copy]').forEach((btn) => {
    btn.onclick = () => {
      navigator.clipboard?.writeText(btn.dataset.copy);
      toast(`Copied "${btn.dataset.copy}" — though the canvas injects it for you.`, 'ok');
    };
  });
}

function card(l) {
  const base = state.trainingBases?.find((b) => b.id === l.baseId);
  const preset = state.trainingPresets?.[l.presetId];
  return `
    <div class="lora-card">
      <h4>${esc(l.name)}</h4>
      <div class="trig">${esc(l.trigger || 'no trigger')}</div>
      <dl class="kv">
        <dt>type</dt><dd>${esc(preset?.label || l.presetId || '—')}</dd>
        <dt>base</dt><dd>${esc(base?.label || l.baseId)}</dd>
        <dt>steps</dt><dd>${l.steps ?? '—'}</dd>
        <dt>cost</dt><dd>$${(l.cost || 0).toFixed(2)}</dd>
        <dt>usable on</dt><dd>${(l.compatible || []).length}</dd>
      </dl>
      <div class="foot">
        <button class="btn btn-sm" data-copy="${esc(l.trigger || '')}">Copy trigger</button>
        <button class="btn btn-sm btn-danger" data-del="${l.id}">Delete</button>
      </div>
    </div>`;
}
