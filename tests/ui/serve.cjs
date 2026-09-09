const fs = require('node:fs');
const path = require('node:path');
const {createRequire} = require('node:module');
const {pathToFileURL} = require('node:url');
const req = createRequire('/web/package.json');
function moduleFile(name) {
  const pkg = JSON.parse(fs.readFileSync(`/web/node_modules/${name}/package.json`, 'utf8'));
  return path.resolve(`/web/node_modules/${name}`,pkg.module || pkg.main);
}
(async()=>{
  const {createServer} = await import(pathToFileURL(req.resolve('vite')).href);
  const {default:vue} = await import(pathToFileURL(req.resolve('@vitejs/plugin-vue')).href);
  const server=await createServer({configFile:false,root:'/checks',cacheDir:'/tmp/rnd-vite',plugins:[vue()],
    resolve:{alias:[{find:/^@\/api\/module_factory$/,replacement:'/checks/api.ts'},
      {find:'@',replacement:'/web/src'},...['vue','vue-router','element-plus'].map(name=>({find:new RegExp('^'+name+'$'),replacement:moduleFile(name)})),
      {find:'element-plus/',replacement:'/web/node_modules/element-plus/'}]},
    server:{host:'0.0.0.0',port:4173,strictPort:true,fs:{allow:['/checks','/web']}},
    optimizeDeps:{include:[]}});
  await server.listen();console.log('Actual Vue page test harness listening');
})().catch(e=>{console.error(e);process.exit(1)});
