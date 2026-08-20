// ---------------------------------------------------------------------------
// INSPECTOR
// Builds the right-hand settings panel from the selected node's catalog entry.
// Widget types map 1:1 to `param.type`, so a new model with a new control just
// needs its param declared in the catalog.
// ---------------------------------------------------------------------------
import { state, on, defByType, nodeById, setParam } from './state.js';
import { esc, pickFiles, uploadFiles, onImageDrop, toast } from './ui.js';

let host;

export function initInspector() {
  host = document.getElementById('inspector');
  on('selectedId', render);
  on('nodes', renderIfSame);
  on('loras', render);
  render();
}

let lastRenderedId = null;
function renderIfSame() {
  // Avoid stomping an input the user is typing in: only re-render when the
  // selection actually changed.
  if (state.selectedId !== lastRenderedId) render();
}

function render() {
  lastRenderedId = state.selectedId;
  const node = nodeById(state.selectedId);
  if (!node) {
    host.innerHTML = '<div class="inspector-empty">Select a node to edit its settings.</div>';
    return;
  }
  const def = defByType(node.type);

  host.innerHTML = `
    <div class="insp-head">
      <span class="dot" style="background:${def.accent}"></span>
      <h2>${esc(def.title)}</h2>
    </div>
    <p class="insp-blurb">${esc(def.blurb || '')}</p>
    <div id="insp-fields"></div>
    ${
      def.provider !== 'local'
        ? `<p class="insp-blurb" style="margin-top:16px;border-top:1px solid var(--line-soft);padding-top:12px">
             provider <code>${def.provider}</code> · <code>${esc(def.endpoint || '')}</code><br>
             ~$${(def.cost || 0).toFixed(3)} per run
           </p>`
        : ''
    }`;

  const fields = host.querySelector('#insp-fields');
  for (const spec of def.params || []) fields.appendChild(buildField(node, spec));
}

function buildField(node, spec) {
  const value = node.params?.[spec.id];
  const wrap = document.createElement('div');
  wrap.className = 'field';

  const label = document.createElement('label');
  label.innerHTML = `<span>${esc(spec.label)}</span><span class="val" data-val></span>`;
  wrap.appendChild(label);
  const valEl = label.querySelector('[data-val]');

  const commit = (v) => {
    setParam(node.id, spec.id, v);
    paintValue(valEl, spec, v);
    paintGuard(wrap, spec, v);
  };

  switch (spec.type) {
    case 'range': {
      const input = document.createElement('input');
      input.type = 'range';
      input.min = spec.min;
      input.max = spec.max;
      input.step = spec.step;
      input.value = value ?? spec.default ?? spec.min;
      input.oninput = () => commit(Number(input.value));
      wrap.appendChild(input);
      break;
    }

    case 'select': {
      const sel = document.createElement('select');
      sel.innerHTML = (spec.options || [])
        .map((o) => `<option value="${esc(o.value)}" ${o.value === value ? 'selected' : ''}>${esc(o.label)}</option>`)
        .join('');
      sel.onchange = () => commit(sel.value);
      wrap.appendChild(sel);
      break;
    }

    case 'textarea': {
      const ta = document.createElement('textarea');
      ta.value = value || '';
      ta.placeholder = 'a 16-storey residential tower, bronze mullions, dark brick spandrels, ground-floor retail, overcast daylight, eye-level view';
      ta.oninput = () => setParam(node.id, spec.id, ta.value);
      wrap.appendChild(ta);
      wrap.appendChild(help('Describe what the building IS. Naming the style here does not help — the LoRA already carries it.'));
      break;
    }

    case 'seed': {
      const row = document.createElement('div');
      row.className = 'row';
      const input = document.createElement('input');
      input.type = 'number';
      input.placeholder = 'random';
      input.value = value ?? '';
      input.oninput = () => setParam(node.id, spec.id, input.value === '' ? null : Number(input.value));

      const dice = document.createElement('button');
      dice.className = 'btn btn-sm';
      dice.style.flex = '0 0 auto';
      dice.textContent = 'Roll';
      dice.onclick = () => {
        const v = Math.floor(Math.random() * 1e6);
        input.value = v;
        setParam(node.id, spec.id, v);
      };

      const free = document.createElement('button');
      free.className = 'btn btn-sm';
      free.style.flex = '0 0 auto';
      free.textContent = 'Clear';
      free.onclick = () => {
        input.value = '';
        setParam(node.id, spec.id, null);
      };

      row.append(input, dice, free);
      wrap.appendChild(row);
      wrap.appendChild(help('A fixed seed reproduces the same image exactly. Leave it empty while judging setting changes, or you will keep seeing the previous result.'));
      break;
    }

    case 'lora': {
      const def = defByType(node.type);
      const compatible = state.loras.filter((l) => l.compatible?.includes(def.type));
      const incompatible = state.loras.filter((l) => !l.compatible?.includes(def.type));

      const sel = document.createElement('select');
      sel.innerHTML =
        `<option value="">— none (base model only) —</option>` +
        compatible.map((l) => `<option value="${l.id}" ${l.id === value ? 'selected' : ''}>${esc(l.name)} · ${esc(l.trigger)}</option>`).join('') +
        incompatible.map((l) => `<option value="${l.id}" disabled>${esc(l.name)} — wrong base (${esc(l.baseId)})</option>`).join('');
      sel.onchange = () => commit(sel.value || null);
      wrap.appendChild(sel);

      const chosen = state.loras.find((l) => l.id === value);
      if (chosen) {
        wrap.appendChild(
          help(`Trigger "${chosen.trigger}" is injected into the prompt automatically at run time, so you do not have to remember it.`)
        );
      } else if (!state.loras.length) {
        wrap.appendChild(help('No LoRAs trained yet. Build one on the Model Training tab.'));
      }
      break;
    }

    case 'image': {
      const drop = document.createElement('div');
      drop.className = 'drop';
      drop.innerHTML = value ? `<img src="${esc(value)}" alt="">` : 'Click or drop an image<br><span style="color:var(--text-faint)">white model · channel image · Enscape frame</span>';

      const take = async (files) => {
        try {
          const [up] = await uploadFiles(files);
          if (up) commit(up.asset);
        } catch (err) {
          toast(err.message, 'err');
        }
      };
      drop.onclick = async () => take(await pickFiles({ multiple: false }));
      onImageDrop(drop, take);
      wrap.appendChild(drop);
      if (value) {
        const clear = document.createElement('button');
        clear.className = 'btn btn-sm';
        clear.style.marginTop = '7px';
        clear.textContent = 'Replace';
        clear.onclick = () => commit(null);
        wrap.appendChild(clear);
      }
      break;
    }

    default: {
      const input = document.createElement('input');
      input.type = 'text';
      input.value = value ?? '';
      input.oninput = () => setParam(node.id, spec.id, input.value);
      wrap.appendChild(input);
    }
  }

  if (spec.help) wrap.appendChild(help(spec.help));
  paintValue(valEl, spec, value);
  paintGuard(wrap, spec, value);
  return wrap;
}

function help(text) {
  const p = document.createElement('div');
  p.className = 'help';
  p.textContent = text;
  return p;
}

function paintValue(target, spec, value) {
  if (!target) return;
  if (spec.type === 'range') target.textContent = Number(value).toFixed(spec.step < 1 ? 2 : 0);
  else if (spec.type === 'seed') target.textContent = value ?? 'random';
  else target.textContent = '';
}

/** Show the house-rule warning inline the moment a value leaves the band. */
function paintGuard(wrap, spec, value) {
  wrap.querySelector('.guard')?.remove();
  const g = spec.guard;
  if (!g || typeof value !== 'number') return;

  const low = g.min !== undefined && value < g.min;
  const high = g.max !== undefined && value > g.max;
  wrap.querySelector('input[type="range"]')?.classList.toggle('out-of-band', low || high);
  if (!low && !high) return;

  const div = document.createElement('div');
  div.className = 'guard';
  div.textContent = g.warn || `Recommended range is ${g.min ?? '−'} to ${g.max ?? '−'}.`;
  wrap.appendChild(div);
}
