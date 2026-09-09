import { createApp, defineComponent, h } from "vue";
import { createRouter, createWebHashHistory, RouterView } from "vue-router";
import ElementPlus from "element-plus";
import "element-plus/dist/index.css";
import FactoryConsole from "/web/src/views/factory/FactoryConsole.vue";
import ProviderManager from "/web/src/views/factory-providers/ProviderManager.vue";
import ToolchainCenter from "/web/src/views/factory-toolchain/ToolchainCenter.vue";
import "./shell.css";
const router = createRouter({history: createWebHashHistory(), routes: [
  {path: "/factory", component: FactoryConsole}, {path: "/factory-providers", component: ProviderManager},
  {path: "/factory-toolchain", component: ToolchainCenter}, {path: "/", redirect: "/factory"}
]});
const app = createApp(defineComponent({setup: () => () => h("div", {class: "test-shell"}, [
  h("aside", [h("b", "FastapiAdmin"), h("p", "研发工作台"), h("p", "模型供应商"), h("p", "工具链配置")]),
  h("main", [h("header", "嵌入布局回归测试 · API 夹具（非真实账号）"), h("section", {id:"app-content"}, h(RouterView))])
])}));
(window as any).__errors = [];
app.config.errorHandler = (error) => { (window as any).__errors.push(String(error)); };
app.use(ElementPlus).use(router).mount("#app");
