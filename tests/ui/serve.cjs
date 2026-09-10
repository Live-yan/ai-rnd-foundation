// Use Vite's own conditional exports and dependency optimizer, exactly as a
// normal frontend does. Hand-picking package.module can bypass CommonJS interop.
const fs = require('node:fs');
const {createRequire} = require('node:module');
const {pathToFileURL} = require('node:url');
const req = createRequire('/web/package.json');
(async () => {
  const {createServer} = await import(pathToFileURL(req.resolve('vite')).href);
  const {default: vue} = await import(pathToFileURL(req.resolve('@vitejs/plugin-vue')).href);
  // The input mount remains read-only. Staging under /web makes the real pinned
  // node_modules visible to the harness and to all imported production pages.
  const root = '/web/.rnd-ui';
  fs.cpSync('/checks', root, {recursive: true});
  const server = await createServer({
    configFile: false, root, cacheDir: '/tmp/rnd-vite', plugins: [vue()],
    resolve: {
      alias: [
        {find: /^@\/api\/module_factory$/, replacement: root + '/api.ts'},
        {find: '@', replacement: '/web/src'},
      ],
      dedupe: ['vue', 'vue-router', 'element-plus'],
    },
    server: {host: '0.0.0.0', port: 4173, strictPort: true, fs: {allow: ['/web']}},
    optimizeDeps: {entries: ['index.html'], include: ['vue', 'vue-router', 'element-plus']},
  });
  await server.listen();
  console.log('Actual Vue page test harness listening');
})().catch(error => {console.error(error); process.exit(1);});
