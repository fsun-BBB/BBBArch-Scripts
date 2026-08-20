// Reads .env by hand so the project stays dependency-light. Only KEY=value
// lines matter; everything else is ignored.
import { readFileSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

export const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');

function loadEnvFile() {
  const path = join(ROOT, '.env');
  if (!existsSync(path)) return;
  for (const line of readFileSync(path, 'utf8').split(/\r?\n/)) {
    const m = /^\s*([A-Z0-9_]+)\s*=\s*(.*)$/.exec(line);
    if (!m) continue;
    const value = m[2].trim().replace(/^["']|["']$/g, '');
    if (process.env[m[1]] === undefined) process.env[m[1]] = value;
  }
}
loadEnvFile();

const keys = {
  fal: process.env.FAL_KEY || '',
  replicate: process.env.REPLICATE_API_TOKEN || '',
  gemini: process.env.GEMINI_API_KEY || '',
  huggingface: process.env.HF_TOKEN || '',
};

// Mock unless explicitly disabled AND at least one key is present. This makes
// "npm start" on a fresh clone always work instead of erroring on auth.
const anyKey = Object.values(keys).some(Boolean);
export const config = {
  port: Number(process.env.PORT || 5178),
  mock: process.env.MOCK_MODE === '1' || !anyKey,
  keys,
  dataDir: join(ROOT, 'data'),
  assetDir: join(ROOT, 'data', 'assets'),
};

export const hasKey = (provider) => Boolean(keys[provider]);
