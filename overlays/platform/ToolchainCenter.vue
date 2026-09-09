<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import FactoryAPI, { type ToolchainItem } from "@/api/module_factory";

const router = useRouter();
const rows = ref<ToolchainItem[]>([]);
const busy = ref(false);
const configured = computed(() => rows.value.filter((item) => item.configured).length);
const groups = computed(() => [
  { title: "智能与 Agent 层", ids: ["langgraph", "litellm", "toolhive", "serena"] },
  { title: "编排与执行层", ids: ["temporal", "cube", "coder"] },
  { title: "规格与交付层", ids: ["fastapiadmin", "openspec", "diagrams", "structurizr"] },
].map((group) => ({ ...group, items: rows.value.filter((item) => group.ids.includes(item.id)) })));
async function refresh() {
  busy.value = true;
  try { rows.value = await FactoryAPI.toolchain(); } finally { busy.value = false; }
}
onMounted(refresh);
</script>

<template>
  <div v-loading="busy" class="tool-page">
    <section class="page-head"><div><el-button text @click="router.push('/factory')">← 研发工作台</el-button><h1>工具链中心</h1><p>这里区分“已配置”“运行时可达”和“本次实际执行”。运行级使用情况请回到工作台查看阶段日志与产物。</p></div><el-button @click="refresh">刷新状态</el-button></section>
    <section class="readiness"><div><span class="score">{{ configured }}/{{ rows.length }}</span><div><strong>平台组件准备度</strong><p>完整模式不会把未配置的组件静默降级。</p></div></div><el-progress :percentage="rows.length ? Math.round(configured / rows.length * 100) : 0" :stroke-width="10" /></section>
    <el-alert type="warning" show-icon :closable="false" title="configured ≠ reachable ≠ used">
      <template #default>例如填入 Serena URL 只代表配置存在；真正运行时还会执行 MCP initialize/list_tools/get_symbols_overview。Cube、Coder、Structurizr 同理，失败会让完整模式任务失败并保留错误阶段。</template>
    </el-alert>

    <section class="flow">
      <div class="flow-node"><strong>需求对话</strong><small>FastapiAdmin UI</small></div><span>→</span><div class="flow-node"><strong>澄清 / 规划</strong><small>LangGraph + LiteLLM</small></div><span>→</span><div class="flow-node"><strong>模板上下文</strong><small>ToolHive + Serena</small></div><span>→</span><div class="flow-node"><strong>规格 / 架构</strong><small>OpenSpec + C4 + diagrams</small></div><span>→</span><div class="flow-node"><strong>持久化执行</strong><small>Temporal + Cube</small></div><span>→</span><div class="flow-node"><strong>交付 / IDE</strong><small>ZIP + Coder</small></div>
    </section>

    <template v-for="group in groups" :key="group.title">
      <h2>{{ group.title }}</h2>
      <div class="tool-grid">
        <el-card v-for="item in group.items" :key="item.id" shadow="never">
          <div class="tool-card">
            <div class="tool-title"><div class="tool-icon">{{ item.name.slice(0, 2).toUpperCase() }}</div><div><strong>{{ item.name }}</strong><small>{{ item.execution }}</small></div><el-tag :type="item.configured ? 'success' : 'danger'" size="small">{{ item.configured ? '已配置' : '未配置' }}</el-tag></div>
            <p class="tool-role">{{ item.role }}</p>
            <div v-if="item.hint" class="tool-hint">{{ item.hint }}</div>
          </div>
        </el-card>
      </div>
    </template>
  </div>
</template>

<style scoped>
.tool-page{padding:20px;min-height:100%;background:var(--el-bg-color-page)}.page-head{display:flex;justify-content:space-between;align-items:flex-end;gap:20px}.page-head h1{margin:5px 0;font-size:26px}.page-head p{margin:0;color:var(--el-text-color-secondary)}.readiness{display:grid;grid-template-columns:300px 1fr;align-items:center;gap:28px;margin:16px 0;padding:20px;border-radius:12px;background:linear-gradient(120deg,var(--el-color-primary-light-9),var(--el-bg-color))}.readiness>div{display:flex;align-items:center;gap:15px}.score{font-size:34px;font-weight:750;color:var(--el-color-primary)}.readiness p{margin:4px 0 0;color:var(--el-text-color-secondary)}.flow{display:flex;align-items:center;gap:8px;overflow-x:auto;margin:16px 0;padding:15px;background:var(--el-bg-color);border:1px solid var(--el-border-color-lighter);border-radius:12px}.flow-node{min-width:145px;padding:10px;border-radius:9px;background:var(--el-fill-color-light);text-align:center}.flow-node strong,.flow-node small{display:block}.flow-node small{margin-top:4px;color:var(--el-text-color-secondary)}.tool-page h2{font-size:16px;margin:22px 0 10px}.tool-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}.tool-card{min-height:145px}.tool-title{display:flex;align-items:center;gap:10px}.tool-title>div:nth-child(2){flex:1}.tool-title strong,.tool-title small{display:block}.tool-title small{margin-top:3px;color:var(--el-text-color-secondary)}.tool-icon{width:40px;height:40px;border-radius:10px;display:grid;place-items:center;color:#fff;background:linear-gradient(135deg,#306ca8,#6b58c5);font-weight:700}.tool-role{line-height:1.6;color:var(--el-text-color-regular)}.tool-hint{padding:9px;border-radius:8px;background:var(--el-fill-color-light);font-size:12px;color:var(--el-text-color-secondary);line-height:1.5}@media(max-width:760px){.tool-page{padding:10px}.page-head{align-items:flex-start;flex-direction:column}.readiness{grid-template-columns:1fr}.flow{align-items:stretch;flex-direction:column}.flow>span{transform:rotate(90deg);align-self:center}}
</style>
