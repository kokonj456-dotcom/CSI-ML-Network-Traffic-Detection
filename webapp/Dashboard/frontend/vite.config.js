import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

const featureFiles = [
  'core/state.js', 'core/layout.js', 'features/traffic.js', 'features/monitor.js',
  'features/blocklist.js', 'features/sources.js', 'features/inspector.js',
  'features/management/state.js',
  'features/management/jobs.js',
  'features/management/page.js',
  'features/management/evaluation.js',
  'features/management/overview.js',
  'features/management/feedback.js',
  'features/management/training.js',
  'features/management/registry.js',
  'features/management/events.js',
  'app.js',
];
const runtimeId = '\0flowwatch-features';

// Keep the existing feature controllers in one module scope during the UI migration.
const featureRuntime = {
  name: 'flowwatch-feature-runtime',
  resolveId(id) {
    if (id === 'virtual:flowwatch-features') return runtimeId;
  },
  async load(id) {
    if (id !== runtimeId) return;
    const sources = await Promise.all(featureFiles.map(async file => {
      const path = fileURLToPath(new URL('./src/' + file, import.meta.url));
      this.addWatchFile(path);
      return readFile(path, 'utf8');
    }));
    return 'import { fetchModelMetadata, fetchRecentTraffic, saveAlertStatus, fetchCaptureFlows, uploadCaptureFile } from "/src/api/traffic.js";\n' +
      'import { managementRequest } from "/src/api/management.js";\n' +
      sources.join('\n') + '\nexport { startWorkspace };';
  },
};

const backend = 'http://127.0.0.1:8794';
const proxy = {
  '/api': {
    target: backend,
    changeOrigin: true,
    configure(server) {
      server.on('proxyReq', (outgoing, incoming) => {
        if (incoming.headers.origin === 'http://' + incoming.headers.host) {
          outgoing.setHeader('origin', backend);
        } else {
          outgoing.removeHeader('origin');
        }
      });
    },
  },
};
export default defineConfig({
  plugins: [featureRuntime, react()],
  server: {host: '127.0.0.1', proxy},
  preview: {host: '127.0.0.1', proxy},
});
