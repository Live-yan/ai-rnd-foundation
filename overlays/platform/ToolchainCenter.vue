<script setup lang="ts">
import { computed, onMounted, onDeactivated, onActivated, onBeforeUnmount, watch, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import FactoryAPI, { type ToolchainItem, type IntegrationConfig } from "@/api/module_factory";
import { useEmbeddedViewport, openService } from "@/api/module_factory/embedded";
import "@/api/module_factory/embedded.css";
const { panel, panelHeight } = useEmbeddedViewport();
const router = useRouter(); const route = useRoute();
const rows = ref<ToolchainItem[]>([]); const busy = ref(false); const onlyMissing = ref(false);
const drawer = ref(false); const selected = ref<IntegrationConfig>(); const draft = reactive<Record<string, any>>({});
const saving = ref(false); const checking = ref(false);
const result = ref<{status: string; message: string}>();
let selection = 0;
let active = true;
const shown = computed(() => rows.value.filter(x => !onlyMissing.value || !x.configured));
const count = computed(() => rows.value.filter(x => x.configured).length);
function error(e: any) { ElMessage.error(e?.response?.data?.msg || e?.response?.data?.detail || e?.message || "配置操作失败"); }
function populate(value: IntegrationConfig) {
  selected.value = value;
  for(const key of Object.keys(draft)) delete draft[key];
  for(const field of value.fields) draft[field.key] = field.value;
  draft.web_url = value.web_url; result.value = undefined;
}
function current(ticket: number) { return active && ticket === selection; }
async function refresh() {
  busy.value = true;
  try { const value = await FactoryAPI.toolchain(); if(active) rows.value = value; }
  catch(e) { if(active) error(e); } finally { busy.value = false; }
}
async function configure(id: string) {
  const ticket = ++selection; busy.value = true;
  try { const value = await FactoryAPI.integrationConfig(id); if(current(ticket)) { populate(value); drawer.value = true; } }
  catch(e) { if(current(ticket)) error(e); } finally { if(current(ticket)) busy.value = false; }
}
async function save() {
  if(!selected.value?.editable || saving.value) return;
  const {id, revision, fields} = selected.value; const ticket = selection;
  const values = {...draft};
  for(const field of fields) if(field.kind === "secret" && !values[field.key]) delete values[field.key];
  saving.value = true;
  try {
    const value = await FactoryAPI.saveIntegration(id, revision, values);
    if(!current(ticket)) return;
    populate(value); await refresh();
    if(current(ticket)) ElMessage.success("配置已保存，后续活动会读取；未部署的服务仍需部署");
  } catch(e) { if(current(ticket)) error(e); } finally { saving.value = false; }
}
async function reset() {
  if(!selected.value?.editable || saving.value) return;
  const {id, revision} = selected.value; const ticket = selection;
  try {
    await ElMessageBox.confirm("清除本组件保存在数据库中的覆盖值和凭据，重新使用 .env 默认值。不会删除业务数据；.env 中的凭据仍可能生效。", "恢复默认配置", {type:"warning", confirmButtonText:"确认恢复", cancelButtonText:"取消"});
  } catch { return; }
  if(!current(ticket) || saving.value) return;
  saving.value = true;
  try {
    const value = await FactoryAPI.resetIntegration(id, revision);
    if(!current(ticket)) return;
    populate(value); await refresh();
    if(current(ticket)) ElMessage.success("已恢复环境默认值，配置版本已递增");
  } catch(e) { if(current(ticket)) error(e); } finally { saving.value = false; }
}
async function test() {
  if(!selected.value?.editable || checking.value) return;
  const {id} = selected.value; const ticket = selection; checking.value = true;
  try { const value = await FactoryAPI.probeIntegration(id); if(current(ticket)) result.value = value; }
  catch(e) { if(current(ticket)) error(e); } finally { checking.value = false; }
}
watch(drawer, open => { if(!open) { ++selection; busy.value = false; for(const key of Object.keys(draft)) delete draft[key]; } });
onActivated(() => { active = true; });
onBeforeUnmount(() => { active = false; ++selection; });
onDeactivated(() => { active = false; ++selection; busy.value = false; drawer.value = false; for(const key of Object.keys(draft)) delete draft[key]; });
onMounted(async () => { await refresh(); const tool = route.query.tool; if(active && typeof tool === "string" && rows.value.some(x => x.id === tool)) await configure(tool); });
</script>
<template>
  <div ref="panel" v-loading="busy" class="rnd-embedded" :style="{height: panelHeight}">
    <header class="rnd-toolbar"><div><h1>工具链配置 <el-tag effect="plain" size="small">{{ count }}/{{ rows.length }}</el-tag></h1><p>配置、部署、连通、任务回执分别记录</p></div><div class="rnd-actions"><el-checkbox v-model="onlyMissing">只看未配置</el-checkbox><el-button size="small" @click="refresh">刷新</el-button><el-button size="small" @click="router.push('/factory')">返回工作台</el-button></div></header>
    <div class="rnd-note">每个组件可进入配置。内置库已随镜像安装；外部服务与模型授权不会凭空创建，也不会把“填了地址”算成成功执行。</div>
    <div class="rnd-scroll"><div class="tool-grid"><article v-for="item in shown" :key="item.id" class="rnd-panel tool-card"><div class="tool-heading"><span class="tool-icon">{{ item.name.slice(0,2).toUpperCase() }}</span><strong>{{ item.name }}</strong><el-tag size="small" :type="item.configured ? 'info' : 'warning'">{{ item.configured ? '配置存在' : '待配置' }}</el-tag></div><p>{{ item.role }}</p><small class="rnd-muted">{{ item.access === 'embedded' ? '内置库 / CLI · 无独立后台' : item.access === 'external' ? '外部 API / MCP · 需真实资源' : '独立控制台 · 需启动服务' }}</small><small class="rnd-muted">{{ item.hint }}</small><div class="tool-actions"><el-button size="small" type="primary" plain @click="configure(item.id)">配置 / 服务入口</el-button></div></article></div><el-empty v-if="!shown.length" :image-size="60" description="没有未配置的组件；实际运行仍需验证" /></div>
    <el-drawer v-model="drawer" :title="rows.find(x => x.id === selected?.id)?.name || '组件配置'" size="min(640px, 100vw)" append-to-body class="rnd-form"><template v-if="selected"><el-alert :title="selected.note" type="info" :closable="false" /><p class="rnd-note">{{ selected.access_note }}</p><div v-if="selected.start_command" class="console-start"><strong>连接失败时，在部署机器的项目目录执行：</strong><pre>{{ selected.start_command }}</pre><small class="rnd-muted">不删除数据；不是在浏览器中执行。启动后再点“检查已保存配置”。</small></div><div class="rnd-actions" style="margin-bottom:16px"><el-button v-if="selected.web_url" @click="openService(selected.web_url)">打开服务管理页</el-button><el-button @click="openService(selected.docs)">官方文档</el-button><el-button v-if="selected.id === 'litellm'" type="primary" @click="drawer = false; router.push('/factory-providers')">配置模型与凭据</el-button><el-button v-if="selected.id === 'toolhive'" @click="configure('serena')">配置共享 MCP 端点</el-button></div><el-alert v-if="!selected.editable" title="当前账号可查看说明；修改全局设置需要超级管理员" type="warning" :closable="false" /><el-alert v-if="selected.requires_restart" title="Temporal 启动参数在 .env 中修改，重新创建 API/worker 后生效" type="warning" :closable="false" /><el-descriptions v-if="selected.requires_restart" :column="1" border size="small"><el-descriptions-item v-for="(value,key) in selected.startup_values" :key="key" :label="key">{{ value }}</el-descriptions-item></el-descriptions><el-form label-position="top" :disabled="!selected.editable || saving"><el-form-item v-for="field in selected.fields" :key="field.key" :label="field.label + (field.kind === 'secret' && field.configured ? '（已保存，留空保留）' : '')"><el-switch v-if="field.kind === 'boolean'" v-model="draft[field.key]" /><el-input-number v-else-if="field.kind === 'number'" v-model="draft[field.key]" :min="field.minimum" :max="field.maximum" /><el-input v-else-if="field.kind === 'origins'" v-model="draft[field.key]" type="textarea" :rows="5" placeholder="https://models.example.com&#10;http://host.docker.internal:11434" /><el-input v-else v-model="draft[field.key]" :type="field.kind === 'secret' ? 'password' : 'text'" :show-password="field.kind === 'secret'" autocomplete="off" /><small class="rnd-muted">FACTORY_{{ field.key.toUpperCase() }}</small></el-form-item><el-form-item :label="selected.access === 'console' ? '浏览器管理页（必须从当前浏览器可达）' : '可选网页入口（此工具不自带管理后台，可留空）'"><el-input v-model="draft.web_url" placeholder="https://… 或本站路由；没有独立服务界面可留空" /></el-form-item></el-form><p class="rnd-muted">加密保存到 PostgreSQL，覆盖环境默认值；不会改写 .env。不要在活动执行中更换服务或凭据。</p><el-alert v-if="result" :title="result.message" :type="result.status === 'failed' ? 'error' : result.status === 'requires_run' ? 'warning' : 'success'" :closable="false" /></template><template #footer><div class="rnd-actions"><el-button :disabled="!selected?.editable || saving" @click="reset">恢复默认</el-button><el-button :disabled="!selected?.editable || saving" :loading="checking" @click="test">检查已保存配置</el-button><el-button type="primary" :disabled="!selected?.editable || saving" :loading="saving" @click="save">保存配置</el-button></div></template></el-drawer>
  </div>
</template>
<style scoped>
.console-start{margin:12px 0;padding:12px;background:var(--el-fill-color-light);border-radius:8px;font-size:12px}.console-start pre{white-space:pre-wrap;overflow-wrap:anywhere}.tool-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.tool-card{padding:14px;display:flex;flex-direction:column;gap:8px;min-width:0}.tool-heading{display:flex;gap:8px;align-items:flex-start;min-width:0}.tool-heading strong{font-size:13px;overflow-wrap:anywhere;flex:1;min-width:0}.tool-heading .el-tag{flex:none}.tool-icon{width:28px;height:28px;flex:none;font-size:10px;border-radius:7px;background:var(--el-color-primary-light-9);color:var(--el-color-primary);display:grid;place-items:center}.tool-card p{margin:0;font-size:12px;line-height:1.6;color:var(--el-text-color-regular);overflow-wrap:anywhere}.tool-actions{margin-top:auto;padding-top:4px}.tool-card small{overflow-wrap:anywhere}
@container(max-width:900px){.tool-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@container(max-width:520px){.tool-grid{grid-template-columns:minmax(0,1fr)}}
</style>
