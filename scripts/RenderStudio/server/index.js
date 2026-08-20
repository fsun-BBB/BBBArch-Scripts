import express from 'express';
import { join } from 'node:path';
import { config, ROOT } from './config.js';
import { router } from './routes.js';

const app = express();

// Renders and datasets are large; 64mb covers a batch of 4K reference images.
app.use(express.json({ limit: '64mb' }));

app.use('/api', router);
app.use('/assets', express.static(config.assetDir, { maxAge: '1h' }));
app.use('/', express.static(join(ROOT, 'web')));

app.use((err, req, res, next) => {
  console.error(err);
  res.status(500).json({ error: err.message });
});

app.listen(config.port, () => {
  const mode = config.mock ? 'MOCK (no provider keys in use)' : 'LIVE';
  console.log('');
  console.log('  BBB Render Studio');
  console.log(`  http://localhost:${config.port}`);
  console.log(`  mode: ${mode}`);
  if (config.mock) {
    console.log('  -> copy .env.example to .env and add a key to go live');
  }
  console.log('');
});
