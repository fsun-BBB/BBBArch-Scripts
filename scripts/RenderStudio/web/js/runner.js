// ---------------------------------------------------------------------------
// GRAPH EXECUTION
// runNode fires one node; runBoard walks the graph in dependency order so a
// downstream model always sees the upstream render rather than a stale one.
// ---------------------------------------------------------------------------
import { api, pollJob } from './api.js';
import { state, set, defByType, nodeById, updateNode, resolveInputs, topoOrder, emit } from './state.js';
import { toast } from './ui.js';

export async function runNode(id) {
  const node = nodeById(id);
  if (!node) return null;
  const def = defByType(node.type);
  if (!def || def.category === 'input' || def.type === 'compare') return null;

  const wired = resolveInputs(id);
  if (def.inputs.some((p) => p.kind === 'image' && p.id === 'image') && !wired.image && def.category === 'model') {
    updateNode(id, { status: 'idle', error: 'No input image connected.' });
    return null;
  }

  updateNode(id, { status: 'running', error: null });
  try {
    const job = await api.generate({
      nodeId: id,
      nodeType: node.type,
      params: node.params,
      wired: { prompt: wired.prompt, image: wired.image, refs: wired.refs },
    });
    updateNode(id, { jobId: job.id });

    const done = await pollJob(job.id, (j) => updateNode(id, { status: j.status }));
    if (done.status === 'failed') throw new Error(done.error || 'Job failed.');

    const image = done.images?.[0] || null;
    updateNode(id, { status: 'done', result: image ? { image } : null, error: image ? null : 'Job finished with no image.' });
    set({ sessionCost: state.sessionCost + (def.cost || 0) });
    return image;
  } catch (err) {
    updateNode(id, { status: 'error', error: err.message });
    toast(`${def.title}: ${err.message}`, 'err');
    return null;
  }
}

export async function runBoard() {
  const order = topoOrder().filter((n) => {
    const def = defByType(n.type);
    return def && (def.category === 'model' || def.category === 'process');
  });
  if (!order.length) return toast('Nothing to run — add a model node.', 'err');

  toast(`Running ${order.length} node${order.length > 1 ? 's' : ''}…`);
  for (const node of order) {
    // Sequential on purpose: each node's input is the previous node's output.
    // eslint-disable-next-line no-await-in-loop
    await runNode(node.id);
  }
  toast('Board finished.', 'ok');
  emit('nodes');
}
