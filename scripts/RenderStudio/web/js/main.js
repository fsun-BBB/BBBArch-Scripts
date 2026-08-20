import { api } from './api.js';
import { state, set, on, serializeGraph, loadGraph } from './state.js';
import { initCanvas, dropNode, fitToContent } from './canvas.js';
import { initInspector } from './inspector.js';
import { initTraining } from './training.js';
import { initLibrary } from './library.js';
import { runBoard } from './runner.js';
import { recipes, applyRecipe } from './recipes.js';
import { esc, toast } from './ui.js';

const CATEGORY_LABELS = { input: 'Inputs', model: 'Models', process: 'Process', output: 'Output' };

boot();

async function boot() {
  let catalog;
  try {
    catalog = await api.models();
  } catch (err) {
    document.body.innerHTML = `<div style="padding:40px;font:14px system-ui;color:#e6ebf3">
      <h1>Server not reachable</h1><p>Start it with <code>npm start</code>, then reload.</p>
      <pre style="color:#f2555a">${esc(err.message)}</pre></div>`;
    return;
  }

  set({
    nodeDefs: catalog.nodes,
    trainingBases: catalog.trainingBases,
    trainingPresets: catalog.trainingPresets,
    providers: catalog.providers,
    mock: catalog.mock,
  });

  try {
    set({ loras: await api.loras() });
  } catch {
    /* empty library is fine */
  }

  initCanvas();
  initInspector();
  initTraining();
  initLibrary();

  buildPalette();
  buildRecipes();
  wireChrome();
  paintProviderPill();
  await restoreLastGraph();
}

/* ---------------------------------------------------------------- palette */

function buildPalette() {
  const host = document.getElementById('palette-groups');
  const groups = {};
  for (const def of state.nodeDefs) (groups[def.category] ||= []).push(def);

  host.innerHTML = Object.entries(groups)
    .map(
      ([cat, defs]) => `
      <div class="palette-group">
        <h3>${CATEGORY_LABELS[cat] || cat}</h3>
        ${defs
          .map(
            (d) => `<button class="node-chip" data-type="${d.type}" title="${esc(d.blurb || '')}">
              <span class="dot" style="background:${d.accent}"></span>
              <span>${esc(d.title)}</span>
              ${d.cost ? `<span class="meta">$${d.cost.toFixed(3)}</span>` : ''}
            </button>`
          )
          .join('')}
      </div>`
    )
    .join('');

  host.querySelectorAll('[data-type]').forEach((btn) => {
    btn.onclick = () => dropNode(btn.dataset.type);
  });
}

function buildRecipes() {
  const host = document.getElementById('recipe-list');
  host.innerHTML = recipes
    .map((r) => `<button data-recipe="${r.id}"><strong>${esc(r.name)}</strong><span>${esc(r.blurb)}</span></button>`)
    .join('');
  host.querySelectorAll('[data-recipe]').forEach((btn) => {
    btn.onclick = () => {
      applyRecipe(btn.dataset.recipe);
      fitToContent();
    };
  });
}

/* ----------------------------------------------------------------- chrome */

function wireChrome() {
  document.getElementById('tabs').addEventListener('click', (e) => {
    const tab = e.target.closest('.tab');
    if (!tab) return;
    for (const t of document.querySelectorAll('.tab')) t.classList.toggle('is-active', t === tab);
    for (const v of document.querySelectorAll('.view')) v.classList.toggle('is-active', v.dataset.view === tab.dataset.view);
    if (tab.dataset.view === 'canvas') fitToContent();
  });

  document.getElementById('btn-run-all').onclick = runBoard;

  document.getElementById('btn-save').onclick = async () => {
    try {
      const saved = await api.saveGraph(serializeGraph());
      set({ graphId: saved.id });
      localStorage.setItem('bbb.lastGraph', saved.id);
      toast(`Saved "${saved.name}".`, 'ok');
    } catch (err) {
      toast(err.message, 'err');
    }
  };

  on('sessionCost', () => {
    document.getElementById('cost-value').textContent = `$${state.sessionCost.toFixed(3)}`;
  });

  // Autosave: cheap insurance against a refresh losing a wired-up board.
  let timer;
  const queueSave = () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      if (!state.nodes.length) return;
      try {
        const saved = await api.saveGraph(serializeGraph());
        set({ graphId: saved.id });
        localStorage.setItem('bbb.lastGraph', saved.id);
      } catch {
        /* ignore */
      }
    }, 2500);
  };
  on('nodes', queueSave);
  on('edges', queueSave);
}

function paintProviderPill() {
  const pill = document.getElementById('provider-pill');
  const live = state.providers.filter((p) => p.live).map((p) => p.id);
  if (state.mock) {
    pill.className = 'pill is-mock';
    pill.textContent = 'mock mode — no keys';
    pill.title = 'Every job resolves to a labelled placeholder. Add a provider key to .env and set MOCK_MODE=0 to go live.';
  } else {
    pill.className = 'pill is-live';
    pill.textContent = `live · ${live.join(', ')}`;
  }
}

async function restoreLastGraph() {
  const id = localStorage.getItem('bbb.lastGraph');
  if (id) {
    try {
      loadGraph(await api.graph(id));
      fitToContent();
      return;
    } catch {
      /* fall through to a fresh recipe */
    }
  }
  applyRecipe('white-model');
  fitToContent();
}
