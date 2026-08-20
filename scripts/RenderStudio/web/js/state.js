// ---------------------------------------------------------------------------
// APP STATE
// A single observable store. Views subscribe to the keys they care about and
// re-render on change; nothing reaches into another view's DOM.
// ---------------------------------------------------------------------------

const listeners = new Map(); // key -> Set<fn>

export const state = {
  // catalog, loaded once from /api/models
  nodeDefs: [],
  trainingBases: [],
  trainingPresets: {},
  providers: [],
  mock: true,

  // canvas
  graphId: null,
  graphName: 'Untitled board',
  nodes: [],
  edges: [], // { id, from: {node, port}, to: {node, port}, kind }
  selectedId: null,
  view: { x: 0, y: 0, k: 1 },

  // training
  dataset: null,
  audit: null,
  triggerVerdict: null,
  jobs: [],

  loras: [],
  sessionCost: 0,
};

export function on(key, fn) {
  if (!listeners.has(key)) listeners.set(key, new Set());
  listeners.get(key).add(fn);
  return () => listeners.get(key).delete(fn);
}

export function emit(...keys) {
  for (const key of keys) for (const fn of listeners.get(key) || []) fn(state);
}

export function set(patch, ...alsoEmit) {
  Object.assign(state, patch);
  emit(...Object.keys(patch), ...alsoEmit);
}

export const defByType = (type) => state.nodeDefs.find((d) => d.type === type) || null;
export const nodeById = (id) => state.nodes.find((n) => n.id === id) || null;

let seq = 0;
export const uid = (p) => `${p}${Date.now().toString(36)}${(seq++).toString(36)}`;

/** Default params for a node type, straight off the catalog. */
export function defaultParams(def) {
  const out = {};
  for (const p of def.params || []) out[p.id] = p.default ?? null;
  return out;
}

export function addNode(type, x, y) {
  const def = defByType(type);
  if (!def) return null;
  const node = {
    id: uid('n'),
    type,
    x: Math.round(x),
    y: Math.round(y),
    params: defaultParams(def),
    status: 'idle',
    result: null,
    error: null,
    jobId: null,
  };
  state.nodes.push(node);
  emit('nodes');
  return node;
}

export function removeNode(id) {
  state.nodes = state.nodes.filter((n) => n.id !== id);
  state.edges = state.edges.filter((e) => e.from.node !== id && e.to.node !== id);
  if (state.selectedId === id) state.selectedId = null;
  emit('nodes', 'edges', 'selectedId');
}

export function updateNode(id, patch) {
  const node = nodeById(id);
  if (!node) return;
  Object.assign(node, patch);
  emit('nodes');
}

export function setParam(id, key, value) {
  const node = nodeById(id);
  if (!node) return;
  node.params = { ...node.params, [key]: value };
  emit('nodes');
}

/**
 * Connect two ports. Inputs accept one edge unless the port is `multi`, so a
 * re-connect silently replaces the old wire rather than stacking invisible ones.
 */
export function connect(from, to) {
  const fromDef = defByType(nodeById(from.node)?.type);
  const toDef = defByType(nodeById(to.node)?.type);
  if (!fromDef || !toDef || from.node === to.node) return null;

  const outPort = fromDef.outputs.find((p) => p.id === from.port);
  const inPort = toDef.inputs.find((p) => p.id === to.port);
  if (!outPort || !inPort || outPort.kind !== inPort.kind) return null;

  if (!inPort.multi) state.edges = state.edges.filter((e) => !(e.to.node === to.node && e.to.port === to.port));
  if (state.edges.some((e) => e.from.node === from.node && e.from.port === from.port && e.to.node === to.node && e.to.port === to.port)) {
    return null;
  }

  const edge = { id: uid('e'), from, to, kind: inPort.kind };
  state.edges.push(edge);
  emit('edges');
  return edge;
}

export function disconnectInput(nodeId, port) {
  state.edges = state.edges.filter((e) => !(e.to.node === nodeId && e.to.port === port));
  emit('edges');
}

export const edgesInto = (nodeId) => state.edges.filter((e) => e.to.node === nodeId);
export const edgesOutOf = (nodeId) => state.edges.filter((e) => e.from.node === nodeId);

/**
 * Resolve what a node's input ports currently carry, by walking upstream.
 * Text nodes contribute their literal value; everything else contributes its
 * last render (falling back to an uploaded asset).
 */
export function resolveInputs(nodeId) {
  const wired = { prompt: '', image: null, refs: [] };
  for (const edge of edgesInto(nodeId)) {
    const src = nodeById(edge.from.node);
    if (!src) continue;
    const value = outputValue(src);
    if (!value) continue;
    if (edge.kind === 'text') {
      wired.prompt = wired.prompt ? `${wired.prompt}\n${value}` : value;
    } else if (edge.to.port === 'refs') {
      wired.refs.push(value);
    } else {
      wired[edge.to.port] = value;
    }
  }
  return wired;
}

export function outputValue(node) {
  const def = defByType(node.type);
  if (!def) return null;
  if (def.type === 'text') return node.params.value || '';
  if (def.type === 'image-upload') return node.params.asset || null;
  return node.result?.image || null;
}

/** Nodes in dependency order, so "Run board" never runs a node before its input. */
export function topoOrder() {
  const indegree = new Map(state.nodes.map((n) => [n.id, 0]));
  for (const e of state.edges) indegree.set(e.to.node, (indegree.get(e.to.node) || 0) + 1);

  const queue = state.nodes.filter((n) => !indegree.get(n.id)).map((n) => n.id);
  const order = [];
  const seen = new Set();
  while (queue.length) {
    const id = queue.shift();
    if (seen.has(id)) continue;
    seen.add(id);
    order.push(id);
    for (const e of edgesOutOf(id)) {
      indegree.set(e.to.node, indegree.get(e.to.node) - 1);
      if (indegree.get(e.to.node) === 0) queue.push(e.to.node);
    }
  }
  // Any node left out sits in a cycle; append so it is at least attempted.
  for (const n of state.nodes) if (!seen.has(n.id)) order.push(n.id);
  return order.map(nodeById).filter(Boolean);
}

export function serializeGraph() {
  return {
    id: state.graphId,
    name: state.graphName,
    nodes: state.nodes.map(({ id, type, x, y, params, result }) => ({ id, type, x, y, params, result })),
    edges: state.edges,
    view: state.view,
  };
}

export function loadGraph(graph) {
  set({
    graphId: graph.id || null,
    graphName: graph.name || 'Untitled board',
    nodes: (graph.nodes || []).map((n) => ({ status: 'idle', error: null, jobId: null, result: null, ...n })),
    edges: graph.edges || [],
    view: graph.view || { x: 0, y: 0, k: 1 },
    selectedId: null,
  });
}
