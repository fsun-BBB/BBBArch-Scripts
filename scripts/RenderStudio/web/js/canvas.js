// ---------------------------------------------------------------------------
// INFINITE CANVAS
// Pan / zoom / drag / wire. Nodes are absolutely-positioned DOM inside a
// transformed .world; wires live in a screen-space SVG whose endpoints are
// measured off the real port elements, so they never drift from the dots.
// ---------------------------------------------------------------------------
import {
  state, on, set, defByType, nodeById, addNode, removeNode, connect,
  disconnectInput, edgesInto, resolveInputs, outputValue,
} from './state.js';
import { runNode } from './runner.js';

const NODE_W = 260;
const MIN_K = 0.25;
const MAX_K = 2.5;

let viewport, world, wireGroup, zoomLabel, emptyHint;
let dragging = null; // node drag
let panning = null;
let wiring = null; // in-progress connection

export function initCanvas() {
  viewport = document.getElementById('viewport');
  world = document.getElementById('world');
  wireGroup = document.getElementById('wire-group');
  zoomLabel = document.getElementById('zoom-label');
  emptyHint = document.getElementById('empty-hint');

  viewport.addEventListener('wheel', onWheel, { passive: false });
  viewport.addEventListener('pointerdown', onViewportDown);
  window.addEventListener('pointermove', onPointerMove);
  window.addEventListener('pointerup', onPointerUp);
  window.addEventListener('keydown', onKeyDown);
  window.addEventListener('resize', drawWires);

  document.getElementById('btn-zoom-in').onclick = () => zoomBy(1.2);
  document.getElementById('btn-zoom-out').onclick = () => zoomBy(1 / 1.2);
  document.getElementById('btn-fit').onclick = fitToContent;

  on('nodes', renderNodes);
  on('edges', drawWires);
  on('selectedId', renderNodes);
  on('view', applyTransform);
  on('loras', renderNodes);

  applyTransform();
  renderNodes();
}

/* ------------------------------------------------------------- transform */

function applyTransform() {
  const { x, y, k } = state.view;
  world.style.transform = `translate(${x}px, ${y}px) scale(${k})`;
  zoomLabel.textContent = `${Math.round(k * 100)}%`;
  drawWires();
}

function zoomBy(factor, cx, cy) {
  const rect = viewport.getBoundingClientRect();
  const px = cx ?? rect.width / 2;
  const py = cy ?? rect.height / 2;
  const { x, y, k } = state.view;
  const nk = Math.min(MAX_K, Math.max(MIN_K, k * factor));
  // Keep the point under the cursor fixed while scaling.
  set({ view: { k: nk, x: px - ((px - x) * nk) / k, y: py - ((py - y) * nk) / k } });
}

function onWheel(e) {
  e.preventDefault();
  const rect = viewport.getBoundingClientRect();
  if (e.ctrlKey || e.metaKey || Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
    zoomBy(e.deltaY < 0 ? 1.12 : 1 / 1.12, e.clientX - rect.left, e.clientY - rect.top);
  } else {
    set({ view: { ...state.view, x: state.view.x - e.deltaX, y: state.view.y - e.deltaY } });
  }
}

export function fitToContent() {
  if (!state.nodes.length) return set({ view: { x: 0, y: 0, k: 1 } });
  const pad = 90;
  const xs = state.nodes.map((n) => n.x);
  const ys = state.nodes.map((n) => n.y);
  const minX = Math.min(...xs) - pad;
  const minY = Math.min(...ys) - pad;
  const maxX = Math.max(...xs) + NODE_W + pad;
  const maxY = Math.max(...ys) + 360 + pad;
  const rect = viewport.getBoundingClientRect();
  const k = Math.min(MAX_K, Math.max(MIN_K, Math.min(rect.width / (maxX - minX), rect.height / (maxY - minY))));
  set({ view: { k, x: -minX * k + (rect.width - (maxX - minX) * k) / 2, y: -minY * k + (rect.height - (maxY - minY) * k) / 2 } });
}

const toWorld = (clientX, clientY) => {
  const rect = viewport.getBoundingClientRect();
  const { x, y, k } = state.view;
  return { x: (clientX - rect.left - x) / k, y: (clientY - rect.top - y) / k };
};

/** Drop a node at the centre of the current view. */
export function dropNode(type) {
  const rect = viewport.getBoundingClientRect();
  const p = toWorld(rect.left + rect.width / 2 - 130, rect.top + rect.height / 2 - 120);
  const node = addNode(type, p.x, p.y);
  if (node) set({ selectedId: node.id });
  return node;
}

/* --------------------------------------------------------------- pointer */

function onViewportDown(e) {
  const portEl = e.target.closest('.port-dot');
  if (portEl) return startWiring(e, portEl);

  const head = e.target.closest('.node-head');
  if (head && !e.target.closest('.kill')) {
    const node = nodeById(head.closest('.node').dataset.id);
    set({ selectedId: node.id });
    dragging = { id: node.id, start: toWorld(e.clientX, e.clientY), origin: { x: node.x, y: node.y } };
    return;
  }

  const nodeEl = e.target.closest('.node');
  if (nodeEl) {
    set({ selectedId: nodeEl.dataset.id });
    return;
  }

  // Empty space: pan and clear selection.
  panning = { x: e.clientX, y: e.clientY, view: { ...state.view } };
  viewport.classList.add('is-panning');
  if (state.selectedId) set({ selectedId: null });
}

function onPointerMove(e) {
  if (dragging) {
    const p = toWorld(e.clientX, e.clientY);
    const node = nodeById(dragging.id);
    if (!node) return;
    node.x = Math.round(dragging.origin.x + (p.x - dragging.start.x));
    node.y = Math.round(dragging.origin.y + (p.y - dragging.start.y));
    const el = world.querySelector(`.node[data-id="${node.id}"]`);
    if (el) {
      el.style.left = `${node.x}px`;
      el.style.top = `${node.y}px`;
    }
    drawWires();
    return;
  }
  if (panning) {
    set({ view: { ...panning.view, x: panning.view.x + (e.clientX - panning.x), y: panning.view.y + (e.clientY - panning.y) } });
    return;
  }
  if (wiring) {
    wiring.cursor = { x: e.clientX, y: e.clientY };
    drawWires();
  }
}

function onPointerUp(e) {
  if (wiring) {
    const target = document.elementFromPoint(e.clientX, e.clientY)?.closest('.port-dot');
    if (target) {
      const a = wiring.origin;
      const b = { node: target.dataset.node, port: target.dataset.port, dir: target.dataset.dir };
      const from = a.dir === 'out' ? a : b;
      const to = a.dir === 'out' ? b : a;
      if (from.dir === 'out' && to.dir === 'in') connect({ node: from.node, port: from.port }, { node: to.node, port: to.port });
    }
    wiring = null;
    drawWires();
  }
  dragging = null;
  panning = null;
  viewport.classList.remove('is-panning');
}

function startWiring(e, portEl) {
  e.stopPropagation();
  const origin = { node: portEl.dataset.node, port: portEl.dataset.port, dir: portEl.dataset.dir, kind: portEl.dataset.kindv };
  // Grabbing a filled input port detaches the existing wire instead of stacking.
  if (origin.dir === 'in') disconnectInput(origin.node, origin.port);
  wiring = { origin, cursor: { x: e.clientX, y: e.clientY } };
}

function onKeyDown(e) {
  if (e.target.matches('input, textarea, select')) return;
  if ((e.key === 'Delete' || e.key === 'Backspace') && state.selectedId) {
    e.preventDefault();
    removeNode(state.selectedId);
  }
  if (e.key === 'f' && state.nodes.length) fitToContent();
}

/* ----------------------------------------------------------------- render */

function renderNodes() {
  emptyHint.classList.toggle('is-hidden', state.nodes.length > 0);

  const seen = new Set();
  for (const node of state.nodes) {
    seen.add(node.id);
    let el = world.querySelector(`.node[data-id="${node.id}"]`);
    if (!el) {
      el = document.createElement('div');
      el.className = 'node';
      el.dataset.id = node.id;
      world.appendChild(el);
    }
    paintNode(el, node);
  }
  for (const el of [...world.querySelectorAll('.node')]) {
    if (!seen.has(el.dataset.id)) el.remove();
  }
  requestAnimationFrame(drawWires);
}

function paintNode(el, node) {
  const def = defByType(node.type);
  if (!def) return;

  el.style.left = `${node.x}px`;
  el.style.top = `${node.y}px`;
  el.classList.toggle('is-selected', state.selectedId === node.id);
  el.classList.toggle('is-running', node.status === 'running' || node.status === 'queued');

  const filled = new Set(edgesInto(node.id).map((e) => e.to.port));
  const warnings = validate(node, def);
  const preview = previewHtml(node, def);

  el.innerHTML = `
    <div class="ports in">
      ${def.inputs
        .map(
          (p) => `<div class="port" data-kind="${p.kind}">
            <span class="port-dot ${filled.has(p.id) ? 'is-filled' : ''}"
                  data-node="${node.id}" data-port="${p.id}" data-dir="in" data-kindv="${p.kind}"></span>
            <span class="port-label">${p.label}</span>
          </div>`
        )
        .join('')}
    </div>
    <div class="ports out">
      ${def.outputs
        .map(
          (p) => `<div class="port" data-kind="${p.kind}">
            <span class="port-dot" data-node="${node.id}" data-port="${p.id}" data-dir="out" data-kindv="${p.kind}"></span>
            <span class="port-label">${p.label}</span>
          </div>`
        )
        .join('')}
    </div>

    <div class="node-head">
      <span class="dot" style="background:${def.accent}"></span>
      <span class="title">${def.title}</span>
      <button class="kill" title="Delete node">×</button>
    </div>

    <div class="node-body">
      ${preview}
      ${node.error ? `<div class="node-warn node-err">${escapeHtml(node.error)}</div>` : ''}
      ${warnings.length ? `<div class="node-warn">${warnings.map(escapeHtml).join('<br>')}</div>` : ''}
      ${
        def.category === 'model' || def.category === 'process'
          ? `<div class="node-foot">
              <button class="btn btn-sm btn-primary run" ${node.status === 'running' ? 'disabled' : ''}>
                ${node.status === 'running' || node.status === 'queued' ? 'Running…' : 'Run'}
              </button>
              <span class="cost">~$${(def.cost || 0).toFixed(3)}</span>
            </div>`
          : ''
      }
    </div>`;

  el.querySelector('.kill').onclick = (e) => {
    e.stopPropagation();
    removeNode(node.id);
  };
  const runBtn = el.querySelector('.run');
  if (runBtn) {
    runBtn.onclick = (e) => {
      e.stopPropagation();
      runNode(node.id);
    };
  }
  const upload = el.querySelector('[data-upload]');
  if (upload) upload.onclick = (e) => {
    e.stopPropagation();
    set({ selectedId: node.id });
  };
}

function previewHtml(node, def) {
  if (def.type === 'text') {
    return `<div class="node-text">${escapeHtml(node.params.value || '')}</div>`;
  }
  if (def.type === 'compare') {
    const a = state.edges.find((e) => e.to.node === node.id && e.to.port === 'a');
    const b = state.edges.find((e) => e.to.node === node.id && e.to.port === 'b');
    const src = (edge) => (edge ? outputValue(nodeById(edge.from.node)) : null);
    return `<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
      ${[src(a), src(b)]
        .map((u) => `<div class="node-preview" style="aspect-ratio:1/1">${u ? `<img src="${u}" alt="">` : 'empty'}</div>`)
        .join('')}
    </div>`;
  }

  const img = def.type === 'image-upload' ? node.params.asset : node.result?.image;
  if (node.status === 'running' || node.status === 'queued') {
    return `<div class="node-preview">${img ? `<img src="${img}" style="opacity:.35" alt="">` : ''}<div class="spinner" style="position:absolute"></div></div>`;
  }
  if (img) return `<div class="node-preview"><img src="${img}" alt=""></div>`;
  return `<div class="node-preview" data-upload>${def.type === 'image-upload' ? 'Click, then upload in the panel →' : 'No output yet'}</div>`;
}

/**
 * Per-node sanity checks shown right on the card. These are the mistakes that
 * silently waste money: a LoRA that cannot load on this base, a missing
 * trigger word, guidance outside the distilled range, an unwired input.
 */
function validate(node, def) {
  const out = [];
  const p = node.params || {};
  const wired = resolveInputs(node.id);

  for (const port of def.inputs) {
    if (port.id === 'refs') continue;
    const has = port.kind === 'text' ? Boolean(wired.prompt) : Boolean(wired.image);
    if (!has && def.category === 'model') out.push(`${port.label} is not connected.`);
  }

  if (wired.prompt && looksConversational(wired.prompt)) {
    out.push('The wired prompt reads like chat output, not a prompt. Conditioning on commentary produces unrelated images.');
  }

  if ('lora' in p) {
    const lora = state.loras.find((l) => l.id === p.lora);
    if (p.lora && !lora) out.push('Selected LoRA no longer exists.');
    if (lora && !lora.compatible?.includes(def.type)) {
      out.push(`"${lora.name}" was trained on ${lora.baseId} and will not work on this node. Base mismatch loads silently and outputs garbage.`);
    }
    if (lora && p.loraWeight === 0) out.push('LoRA weight is 0 — the adapter is loaded but contributes nothing (useful as an A/B baseline).');
  }

  for (const spec of def.params || []) {
    const g = spec.guard;
    const v = p[spec.id];
    if (!g || typeof v !== 'number') continue;
    if ((g.min !== undefined && v < g.min) || (g.max !== undefined && v > g.max)) {
      out.push(`${spec.label} ${v} is outside the safe band ${g.min ?? '−'}–${g.max ?? '−'}.`);
    }
  }
  return out;
}

const CHAT_MARKERS = [
  'i can do that', "i'll ", 'i will ', 'please do one of', 'here are', 'if you want',
  'let me know', 'sure,', 'as an ai', 'options:', 'you can also',
];
function looksConversational(text) {
  const t = text.toLowerCase();
  return CHAT_MARKERS.some((m) => t.includes(m)) || t.length > 700;
}

/* ------------------------------------------------------------------ wires */

function portCenter(nodeId, port, dir) {
  const el = world.querySelector(`.port-dot[data-node="${nodeId}"][data-port="${port}"][data-dir="${dir}"]`);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  const v = viewport.getBoundingClientRect();
  return { x: r.left + r.width / 2 - v.left, y: r.top + r.height / 2 - v.top };
}

function drawWires() {
  if (!wireGroup) return;
  const paths = [];

  for (const edge of state.edges) {
    const a = portCenter(edge.from.node, edge.from.port, 'out');
    const b = portCenter(edge.to.node, edge.to.port, 'in');
    if (!a || !b) continue;
    paths.push(`<path class="wire is-${edge.kind}" d="${curve(a, b)}" />`);
  }

  if (wiring) {
    const a = portCenter(wiring.origin.node, wiring.origin.port, wiring.origin.dir);
    const v = viewport.getBoundingClientRect();
    const b = { x: wiring.cursor.x - v.left, y: wiring.cursor.y - v.top };
    if (a) {
      const [s, e] = wiring.origin.dir === 'out' ? [a, b] : [b, a];
      paths.push(`<path class="wire is-${wiring.origin.kind} is-dragging" d="${curve(s, e)}" />`);
    }
  }
  wireGroup.innerHTML = paths.join('');
}

function curve(a, b) {
  const dx = Math.max(40, Math.abs(b.x - a.x) * 0.5);
  return `M ${a.x} ${a.y} C ${a.x + dx} ${a.y}, ${b.x - dx} ${b.y}, ${b.x} ${b.y}`;
}

export function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
