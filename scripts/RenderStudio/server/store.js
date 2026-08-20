// Flat-file JSON store. A firm-internal tool with a handful of users does not
// need Postgres; swapping this module for a real DB later touches nothing else.
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { config } from './config.js';

mkdirSync(config.assetDir, { recursive: true });

const files = {
  graphs: join(config.dataDir, 'graphs.json'),
  loras: join(config.dataDir, 'loras.json'),
  jobs: join(config.dataDir, 'jobs.json'),
  datasets: join(config.dataDir, 'datasets.json'),
};

function read(name) {
  const path = files[name];
  if (!existsSync(path)) return [];
  try {
    return JSON.parse(readFileSync(path, 'utf8'));
  } catch {
    return [];
  }
}

function write(name, rows) {
  writeFileSync(files[name], JSON.stringify(rows, null, 2));
  return rows;
}

export const store = {
  list: (name) => read(name),

  get(name, id) {
    return read(name).find((r) => r.id === id) || null;
  },

  put(name, row) {
    const rows = read(name);
    const i = rows.findIndex((r) => r.id === row.id);
    if (i === -1) rows.push(row);
    else rows[i] = { ...rows[i], ...row };
    write(name, rows);
    return this.get(name, row.id);
  },

  remove(name, id) {
    write(name, read(name).filter((r) => r.id !== id));
  },
};

let counter = 0;
export const newId = (prefix) =>
  `${prefix}_${Date.now().toString(36)}${(counter++).toString(36)}${Math.random()
    .toString(36)
    .slice(2, 6)}`;
