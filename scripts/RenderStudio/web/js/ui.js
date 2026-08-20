// Small shared helpers: toasts, element building, file pickers.
import { api, readFileAsDataUrl } from './api.js';

export function toast(message, kind = '') {
  const host = document.getElementById('toasts');
  const el = document.createElement('div');
  el.className = `toast ${kind}`;
  el.textContent = message;
  host.appendChild(el);
  setTimeout(() => {
    el.style.opacity = '0';
    el.style.transition = 'opacity .35s';
    setTimeout(() => el.remove(), 400);
  }, kind === 'err' ? 8000 : 3800);
}

export function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

export function el(html) {
  const t = document.createElement('template');
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

/** Open a native file picker. Resolves to an array of Files. */
export function pickFiles({ multiple = false, accept = 'image/*' } = {}) {
  return new Promise((resolve) => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = accept;
    input.multiple = multiple;
    input.onchange = () => resolve([...(input.files || [])]);
    input.click();
  });
}

/** Upload a batch of Files, returning served asset paths. */
export async function uploadFiles(files) {
  const out = [];
  for (const file of files) {
    if (!file.type.startsWith('image/')) continue;
    // eslint-disable-next-line no-await-in-loop
    const dataUrl = await readFileAsDataUrl(file);
    // eslint-disable-next-line no-await-in-loop
    const res = await api.uploadImage(dataUrl, file.name);
    out.push({ asset: res.asset, name: file.name });
  }
  return out;
}

/** Wire drag-and-drop image dropping onto an element. */
export function onImageDrop(element, handler) {
  const over = (e) => {
    e.preventDefault();
    element.classList.add('is-over');
  };
  const out = () => element.classList.remove('is-over');
  element.addEventListener('dragover', over);
  element.addEventListener('dragleave', out);
  element.addEventListener('drop', async (e) => {
    e.preventDefault();
    out();
    const files = [...(e.dataTransfer?.files || [])].filter((f) => f.type.startsWith('image/'));
    if (files.length) handler(files);
  });
}

export const debounce = (fn, ms = 350) => {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
};
