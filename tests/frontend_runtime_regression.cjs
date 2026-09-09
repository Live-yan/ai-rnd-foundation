// Run with Node, vue-router and typescript against an assembled frontend/web directory.
// Example: node tests/frontend_runtime_regression.cjs runtime/FastapiAdmin/frontend/web
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const ts = require('typescript');
const { createRouter, createMemoryHistory, RouterView } = require('vue-router');
const { createSSRApp, h } = require('vue');
const { renderToString } = require('vue/server-renderer');
const root = process.argv[2];
if (!root) throw new Error('Expected assembled frontend/web directory');

function loadDeclaration(relative, name, bindings = {}) {
  const source = fs.readFileSync(path.join(root, relative), 'utf8');
  const ast = ts.createSourceFile(relative, source, ts.ScriptTarget.Latest, true);
  const declaration = ast.statements.find(node => node.name?.text === name);
  assert.ok(declaration, `Missing ${name}`);
  const text = declaration.getText(ast).replace(/^export /, '');
  const js = ts.transpileModule(text, {
    compilerOptions: { target: ts.ScriptTarget.ES2020 },
  }).outputText;
  return new Function(...Object.keys(bindings), `${js}; return ${name};`)(...Object.values(bindings));
}

async function main() {
  const versionSource = fs.readFileSync(path.join(root, 'src/utils/sys/index.ts'), 'utf8');
  assert.ok(versionSource.includes('fetch(`${import.meta.env.BASE_URL}?_t=${Date.now()}`'));
  const View = { render: () => null };
  const RouteTransformer = loadDeclaration('src/router/route-loader.ts', 'RouteTransformer', {
    ROUTE_COMPONENT_LAYOUT: 'Layout',
    ROUTE_COMPONENT_NESTED_PARENT: 'ParentView',
  });
  const transformer = new RouteTransformer({ load: () => View, loadLayout: () => View });
  const router = createRouter({ history: createMemoryHistory(), routes: [] });
  const paths = ['/factory', '/factory-providers', '/factory-toolchain', '/business', '/nested/page'];
  for (const routePath of paths) {
    const name = `rnd-${routePath.slice(1)}`;
    const record = transformer.transform({ path: routePath, name, component: 'test/View', meta: {} }, 0);
    assert.equal(record.children[0].path, routePath);
    router.addRoute(record);
    await router.push(routePath);
    assert.equal(router.currentRoute.value.path, routePath);
    assert.equal(router.currentRoute.value.name, `${name}Child`);
    assert.equal(router.currentRoute.value.matched.length, 2);
    await router.push({ name });
    assert.equal(router.currentRoute.value.name, `${name}Child`);
  }
  // Exercise the real registry: production adds dynamic routes UNDER an existing Layout.
  const Layout = { render: () => h('main', [h('aside', { id: 'app-sidebar' }), h(RouterView)]) };
  const BusinessView = { render: () => h('section', { id: 'business-page' }, 'Business') };
  const routeFile = 'src/router/route-loader.ts';
  const RouteRegistry = loadDeclaration(routeFile, 'RouteRegistry', {
    RouteTransformer,
    ComponentLoader: class {
      load() { return BusinessView; }
      loadLayout() { return Layout; }
    },
    ROOT_LAYOUT_ROUTE_NAME: 'RootLayout',
    registrationName: loadDeclaration(routeFile, 'registrationName'),
    warnInvalidRouteConfig: () => {},
    IframeRouteManager: { getInstance: () => ({ clear() {} }) },
  });
  const shellRouter = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', name: 'RootLayout', component: Layout, children: [] }],
  });
  const registry = new RouteRegistry(shellRouter);
  registry.register(paths.map(routePath => ({
    path: routePath, name: `rnd-${routePath.slice(1)}`, component: 'test/View', meta: { title: 'Business' },
  })));
  for (const routePath of paths) {
    const name = `rnd-${routePath.slice(1)}`;
    await shellRouter.push(routePath);
    assert.deepEqual(shellRouter.currentRoute.value.matched.map(route => route.name), ['RootLayout', name]);
    await shellRouter.push({ name });
    assert.equal(shellRouter.currentRoute.value.path, routePath);
    const app = createSSRApp({ render: () => h(RouterView) });
    app.use(shellRouter);
    const html = await renderToString(app);
    assert.equal((html.match(/id="app-sidebar"/g) || []).length, 1, `Duplicate Layout at ${routePath}`);
    assert.equal((html.match(/id="business-page"/g) || []).length, 1);
  }
  registry.unregister();
  for (const routePath of paths) assert.equal(shellRouter.hasRoute(`rnd-${routePath.slice(1)}`), false);

  const httpEndpoint = loadDeclaration('src/utils/sse/index.ts', 'httpEndpoint', {
    window: { location: { origin: 'https://factory.example' } },
  });
  assert.equal(httpEndpoint(undefined), 'https://factory.example');
  assert.equal(httpEndpoint(''), 'https://factory.example');
  assert.equal(httpEndpoint('ws://localhost:8000'), 'http://localhost:8000');
  assert.equal(httpEndpoint('wss://factory.example'), 'https://factory.example');
  assert.equal(httpEndpoint('https://other.example'), 'https://other.example');
  console.log('PASS: standalone/shell navigation, single rendered Layout, route cleanup, SSE and polling base');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
