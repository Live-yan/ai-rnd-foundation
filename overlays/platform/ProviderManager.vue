<script setup lang="ts">
import { computed, onMounted, onDeactivated, onBeforeUnmount, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import FactoryAPI, { type ProviderProfile, type ProviderInput, type ProviderCatalog, type ProviderCatalogModel, type OAuthStatus } from "@/api/module_factory";
import { useEmbeddedViewport, openService } from "@/api/module_factory/embedded";
import "@/api/module_factory/embedded.css";
const { panel, panelHeight } = useEmbeddedViewport();
const router = useRouter();
const items = ref<ProviderProfile[]>([]);
const catalog = ref<ProviderCatalog>({ providers: [], categories: [], quick_start: [] });
const query = ref(""); const category = ref(""); const busy = ref(false); const editor = ref(false);
const editing = ref<ProviderProfile>(); const discovering = ref(false); const discovered = ref<ProviderCatalogModel[]>([]);
const output = ref(""); const exportNote = ref(""); const exportVisible = ref(false);
const authVisible = ref(false); const authProfile = ref<ProviderProfile>(); const auth = ref<OAuthStatus>(); const authBusy = ref(false);
let timer: ReturnType<typeof setTimeout> | undefined;
const form = reactive<ProviderInput>({name: "", provider: "openai", model: "", base_url: "", api_key: "", api_version: "", enabled: true, is_default: false, temperature: 0.1, max_tokens: 6000, litellm_params: {}, credentials: {}});
const opts = computed(() => form.litellm_params!);
const creds = computed(() => form.credentials!);
const meta = computed(() => catalog.value.providers.find(x => x.id === form.provider));
const matches = computed(() => catalog.value.providers.filter(x => !category.value || x.category === category.value));
const filtered = computed(() => items.value.filter(x => `${x.name} ${x.provider} ${x.model}`.toLowerCase().includes(query.value.toLowerCase())));
const modelOptions = computed(() => discovered.value.length ? discovered.value : meta.value?.models || []);
function label(id: string) { return catalog.value.providers.find(x => x.id === id)?.name || id; }
function error(error: any) { ElMessage.error(error?.response?.data?.msg || error?.response?.data?.detail || error?.message || "操作失败"); }
async function refresh() { items.value = await FactoryAPI.listProviders(); }
async function load() { busy.value = true; try { [items.value, catalog.value] = await Promise.all([FactoryAPI.listProviders(), FactoryAPI.providerCatalog()]); } catch(e) { error(e); } finally { busy.value = false; } }
function create() {
  editing.value = undefined; discovered.value = []; category.value = "";
  Object.assign(form, {name: "", provider: "openai", model: "", base_url: "", api_key: "", api_version: "", enabled: true, is_default: !items.value.length, temperature: 0.1, max_tokens: 6000, litellm_params: {timeout: 90, num_retries: 0, drop_params: true}, credentials: {}});
  editor.value = true;
}
function edit(item: ProviderProfile) {
  editing.value = item; discovered.value = []; category.value = "";
  Object.assign(form, {name: item.name, provider: item.provider, model: item.model, base_url: item.base_url, api_key: "", api_version: item.api_version || "", enabled: item.enabled, is_default: item.is_default, temperature: item.temperature, max_tokens: item.max_tokens, litellm_params: {...item.litellm_params}, credentials: {}});
  editor.value = true;
}
function changeProvider() { form.base_url = meta.value?.base_url || meta.value?.default_base_url || ""; form.model = ""; form.api_key = ""; form.credentials = {}; discovered.value = []; if(form.provider === "chatgpt") form.base_url = ""; }
async function discover() {
  discovering.value = true;
  try { const result = editing.value && !form.api_key && editing.value.base_url === form.base_url ? await FactoryAPI.discoverSavedProvider(editing.value.id) : await FactoryAPI.discoverProviderModels({provider: form.provider, base_url: form.base_url, api_key: form.api_key}); discovered.value = result.models; ElMessage.success(`发现 ${result.models.length} 个模型`); } catch(e) { error(e); } finally { discovering.value = false; }
}
async function save() {
  busy.value = true;
  try {
    const body: ProviderInput = {...form, name: form.name.trim(), model: form.model.trim(), litellm_params: Object.fromEntries(Object.entries(opts.value).filter(([,v]) => v !== null && v !== undefined && v !== "")), credentials: Object.fromEntries(Object.entries(creds.value).filter(([,v]) => Boolean(v)))};
    if (editing.value && !body.api_key) delete body.api_key;
    const saved = editing.value ? await FactoryAPI.updateProvider(editing.value.id, body) : await FactoryAPI.createProvider(body);
    editor.value = false; await refresh(); ElMessage.success("LiteLLM 配置已保存并用于后续模型调用");
    if (saved.provider === "chatgpt" && saved.auth_status !== "connected") await login(saved);
  } catch(e) { error(e); } finally { busy.value = false; }
}
async function test(item: ProviderProfile) { busy.value = true; try { const result = await FactoryAPI.testProvider(item.id); if(!result.ok) throw Error("模型未返回成功确认"); ElMessage.success(result.message); } catch(e) { error(e); } finally { busy.value = false; } }
async function more(command: string, item: ProviderProfile) {
  try {
    if(command === "edit") edit(item);
    if(command === "default") { await FactoryAPI.defaultProvider(item.id); await refresh(); }
    if(command === "auth") await login(item, true);
    if(command === "disconnect") { await ElMessageBox.confirm("清除平台保存的该账号令牌？不会删除项目。", "断开授权"); await FactoryAPI.oauthAction(item.id, "disconnect"); await refresh(); }
    if(command === "delete") { await ElMessageBox.confirm(`删除 ${item.name}？依赖它的未完成任务可能失败。`, "删除配置"); await FactoryAPI.deleteProvider(item.id); await refresh(); }
  } catch(e) { if(e !== "cancel" && e !== "close") error(e); }
}
async function exportYaml() { try { const value = await FactoryAPI.exportProviders(); output.value = value.yaml; exportNote.value = value.note; exportVisible.value = true; } catch(e) { error(e); } }
function downloadYaml() { const url = URL.createObjectURL(new Blob([output.value], {type: "text/yaml"})); const a = document.createElement("a"); a.href = url; a.download = "litellm-config.yaml"; a.click(); setTimeout(() => URL.revokeObjectURL(url),1000); }
async function proxyAdmin() { try { const value = await FactoryAPI.integrationConfig("litellm"); if(value.web_url) openService(value.web_url); else router.push("/factory-toolchain?tool=litellm"); } catch(e) { error(e); } }
function stopAuth() { if(timer) clearTimeout(timer); }
async function pollAuth(id: string) {
  if (!authVisible.value || authProfile.value?.id !== id) return;
  try { const value = await FactoryAPI.oauthAction(id, "poll"); if (!authVisible.value || authProfile.value?.id !== id) return; auth.value = value;
    if(value.status === "connected") { await refresh(); ElMessage.success("账号授权完成，可以选择订阅模型测试"); return; }
    if(value.status === "pending") timer = setTimeout(() => void pollAuth(id), Math.max(5,value.interval) * 1000);
  } catch(e) { error(e); }
}
async function login(item: ProviderProfile, restart = false) {
  stopAuth(); authProfile.value = item; auth.value = undefined; authVisible.value = true; authBusy.value = true;
  try { let value = await FactoryAPI.oauthStatus(item.id); if(restart || !["pending", "connected"].includes(value.status)) value = await FactoryAPI.oauthAction(item.id, "begin"); if(authProfile.value?.id !== item.id || !authVisible.value) return; auth.value = value; if(value.status === "pending") timer = setTimeout(() => void pollAuth(item.id), value.interval * 1000); } catch(e) { error(e); } finally { authBusy.value = false; }
}
watch(editor, open => { if(!open) { form.api_key = ""; form.credentials = {}; } });
watch(authVisible, open => { if(!open) { stopAuth(); auth.value = undefined; } });
onDeactivated(() => { stopAuth(); authVisible.value = false; editor.value = false; }); onBeforeUnmount(stopAuth); onMounted(load);
</script>
<template>
  <div ref="panel" v-loading="busy" class="rnd-embedded" :style="{height: panelHeight}">
    <header class="rnd-toolbar"><div><h1>模型与 LiteLLM</h1><p>{{ catalog.providers.length }} 家供应商 · API / 云平台凭据 / ChatGPT 账号</p></div><div class="rnd-actions"><el-button size="small" @click="router.push('/factory')">工作台</el-button><el-button size="small" @click="proxyAdmin">网关管理台</el-button><el-button size="small" @click="exportYaml">导出配置</el-button><el-button size="small" type="primary" @click="create">添加模型</el-button></div></header>
    <div class="filter-bar"><el-input v-model="query" placeholder="搜索配置、供应商或模型…" clearable aria-label="搜索模型配置" /><span class="rnd-muted">{{ filtered.length }} 个配置</span><el-button size="small" @click="load">刷新</el-button></div>
    <div class="rnd-note">本页保存的 litellm_params 直接用于平台 SDK 调用。独立 Proxy 的预算、负载均衡、访问密钥等在“网关管理台”配置。</div>
    <div class="rnd-scroll provider-list"><article v-for="item in filtered" :key="item.id" class="rnd-panel provider-row"><div class="provider-name"><span class="vendor-mark">{{ item.provider.slice(0,2).toUpperCase() }}</span><div><strong class="rnd-ellipsis" :title="item.name">{{ item.name }}</strong><small class="rnd-ellipsis" :title="label(item.provider)">{{ label(item.provider) }}</small></div></div><div class="model-cell"><code class="rnd-ellipsis" :title="item.model">{{ item.model }}</code><small class="rnd-ellipsis" :title="item.base_url">{{ item.base_url || '供应商默认地址' }}</small></div><div class="profile-state"><el-tag size="small" :type="item.enabled ? 'success' : 'info'">{{ item.is_default ? '默认' : item.enabled ? '启用' : '停用' }}</el-tag><small v-if="item.provider === 'chatgpt'">{{ item.auth_status === 'connected' ? '账号已连接' : '等待授权' }}</small><small v-else>{{ item.has_api_key || item.credential_fields?.length ? '凭据已保存' : '无密钥 / 本地' }}</small></div><div class="row-actions"><el-button v-if="item.provider === 'chatgpt' && item.auth_status !== 'connected'" size="small" type="primary" plain @click="login(item)">网页登录</el-button><el-button v-else size="small" @click="test(item)">连接测试</el-button><el-button size="small" @click="edit(item)">配置</el-button><el-dropdown @command="cmd => more(cmd, item)"><el-button size="small" aria-label="更多模型操作">⋯</el-button><template #dropdown><el-dropdown-menu><el-dropdown-item command="default" :disabled="!item.enabled">设为默认</el-dropdown-item><el-dropdown-item v-if="item.provider === 'chatgpt'" command="auth">重新授权</el-dropdown-item><el-dropdown-item v-if="item.provider === 'chatgpt'" command="disconnect">断开账号</el-dropdown-item><el-dropdown-item divided command="delete">删除配置</el-dropdown-item></el-dropdown-menu></template></el-dropdown></div></article><el-empty v-if="!filtered.length" :image-size="72" description="添加模型后即可开始需求分析"><el-button type="primary" @click="create">添加第一个模型</el-button></el-empty></div>
    <footer class="rnd-footer"><span class="rnd-muted">密钥加密保存，不回显；测试会真实调用供应商，可能计费。</span></footer>
    <el-drawer v-model="editor" :title="editing ? '编辑 LiteLLM 模型配置' : '添加 LiteLLM 模型'" size="min(680px, 100vw)" append-to-body class="rnd-form"><el-form label-position="top"><div class="rnd-editor-grid"><el-form-item class="wide" label="配置名称 / model_name"><el-input v-model="form.name" maxlength="80" placeholder="例如：主规划模型 / 本地测试" /></el-form-item><el-form-item v-if="!editing" label="供应商分类"><el-select v-model="category" clearable placeholder="全部分类"><el-option v-for="c in catalog.categories" :key="c" :label="c" :value="c" /></el-select></el-form-item><el-form-item label="供应商" :class="{wide: !!editing}"><el-select v-model="form.provider" filterable :disabled="!!editing" @change="changeProvider"><el-option v-for="p in matches" :key="p.id" :value="p.id" :label="p.name" /></el-select></el-form-item><div class="wide rnd-note" style="margin-bottom:12px">{{ meta?.description }} <el-link v-if="meta?.docs" type="primary" @click="openService(meta.docs)">接入文档</el-link></div>
      <div v-if="form.provider === 'openai' && !editing" class="wide rnd-note" style="margin-bottom:12px">使用 ChatGPT 订阅而不是 API 计费？<el-button size="small" text type="primary" @click="form.provider = 'chatgpt'; changeProvider()">改用 Codex 网页登录</el-button></div>
      <el-alert v-if="form.provider === 'chatgpt'" class="wide" type="info" :closable="false" title="ChatGPT / Codex 账号网页登录"><template #default>保存后获取官方设备码，在新窗口登录并确认；平台不收集你的密码。账号可用模型和额度取决于订阅/组织政策，与 API Key 计费分开。</template></el-alert>
      <el-form-item class="wide" label="模型 ID / litellm_params.model"><div class="model-input"><el-select v-model="form.model" filterable allow-create default-first-option placeholder="输入账号或供应商实际可用的模型 ID"><el-option v-for="m in modelOptions" :key="m.id" :value="m.id" :label="m.label" /></el-select><el-button v-if="meta?.supports_discover" :loading="discovering" @click="discover">发现模型</el-button></div><small class="rnd-muted">路由前缀：{{ meta?.litellm_prefix }}/ · 预置模型仅作参考，连接测试验证实际权限。</small></el-form-item>
      <el-form-item v-if="form.provider !== 'chatgpt'" class="wide" label="API Base URL"><el-input v-model="form.base_url" placeholder="留空使用供应商默认；自定义地址需管理员 origin 白名单" /></el-form-item>
      <el-form-item v-if="!['chatgpt','bedrock','vertex_ai'].includes(form.provider)" class="wide" :label="editing?.has_api_key ? 'API Key（留空保留原值）' : 'API Key'"><el-input v-model="form.api_key" type="password" show-password autocomplete="new-password" /></el-form-item>
      <el-form-item v-if="form.provider === 'azure_openai'" class="wide" label="Azure API Version"><el-input v-model="form.api_version" placeholder="部署支持的 api-version" /></el-form-item>
      <template v-if="form.provider === 'bedrock'"><el-form-item class="wide" label="AWS Region"><el-input v-model="opts.aws_region_name" placeholder="例如 us-east-1" /></el-form-item><el-form-item v-for="key in ['aws_access_key_id','aws_secret_access_key','aws_session_token']" :key="key" class="wide" :label="key + (editing?.credential_fields?.includes(key) ? '（已保存，留空保留）' : '')"><el-input v-model="creds[key]" type="password" show-password autocomplete="new-password" /></el-form-item></template>
      <template v-if="form.provider === 'vertex_ai'"><el-form-item label="Vertex Project"><el-input v-model="opts.vertex_project" /></el-form-item><el-form-item label="Vertex Location"><el-input v-model="opts.vertex_location" placeholder="us-central1" /></el-form-item><el-form-item class="wide" label="Service Account JSON（留空保留已保存凭据）"><el-input v-model="creds.vertex_credentials" type="password" show-password autocomplete="new-password" placeholder="完整 service_account JSON，不接受文件路径" /></el-form-item></template>
      <el-form-item label="Temperature"><el-input-number v-model="form.temperature" :min="0" :max="2" :step="0.1" :disabled="form.provider === 'chatgpt'" /></el-form-item><el-form-item label="Max Tokens"><el-input-number v-model="form.max_tokens" :min="256" :max="128000" :step="256" :disabled="form.provider === 'chatgpt'" /></el-form-item><div class="wide rnd-actions"><el-checkbox v-model="form.enabled">启用</el-checkbox><el-checkbox v-model="form.is_default" :disabled="!form.enabled">设为默认</el-checkbox></div></div>
      <el-collapse style="margin-top:14px"><el-collapse-item title="高级 LiteLLM 参数" name="params"><div class="rnd-editor-grid"><el-form-item label="Timeout（秒）"><el-input-number v-model="opts.timeout" :min="10" :max="180" /></el-form-item><el-form-item label="Num Retries"><el-input-number v-model="opts.num_retries" :min="0" :max="2" /></el-form-item><el-form-item label="Top P"><el-input-number v-model="opts.top_p" :min="0" :max="1" :step="0.1" /></el-form-item><el-form-item label="Reasoning Effort"><el-select v-model="opts.reasoning_effort" clearable><el-option v-for="v in ['none','minimal','low','medium','high','xhigh']" :key="v" :value="v" :label="v" /></el-select></el-form-item><el-form-item label="Frequency Penalty"><el-input-number v-model="opts.frequency_penalty" :min="-2" :max="2" :step="0.1" /></el-form-item><el-form-item label="Presence Penalty"><el-input-number v-model="opts.presence_penalty" :min="-2" :max="2" :step="0.1" /></el-form-item><el-form-item label="Seed"><el-input-number v-model="opts.seed" :min="0" :max="2147483647" /></el-form-item><el-form-item label="Organization"><el-input v-model="opts.organization" /></el-form-item><el-checkbox class="wide" v-model="opts.drop_params">Drop Params：忽略供应商不支持的可选参数</el-checkbox></div><p class="rnd-muted">平台的 JSON 输出与验收校验不会关闭。账号订阅通道不支持的 token 上限等参数不发送。</p></el-collapse-item></el-collapse></el-form><template #footer><div class="rnd-actions"><el-button @click="editor = false">取消</el-button><el-button type="primary" :loading="busy" :disabled="!form.name.trim() || !form.model.trim()" @click="save">保存{{ form.provider === 'chatgpt' ? '并授权' : '' }}</el-button></div></template></el-drawer>
    <el-dialog v-model="authVisible" title="ChatGPT / Codex 官方账号授权" width="min(520px, 94vw)" append-to-body class="rnd-form"><div v-loading="authBusy"><el-alert title="仅在 auth.openai.com 输入设备码，不在本平台输入账号密码" type="info" :closable="false" /><p>配置：{{ authProfile?.name }} · {{ auth?.status || '获取授权信息…' }}</p><template v-if="auth?.user_code"><div class="device-code">{{ auth.user_code }}</div><el-button type="primary" @click="openService(auth!.verification_url!)">打开官方登录页面</el-button><p class="rnd-muted">在新窗口登录并输入上方设备码；返回后自动检查。设备授权可能需要在账号安全设置中启用。</p></template><el-result v-if="auth?.status === 'connected'" icon="success" title="账号已连接" sub-title="可以关闭此窗口，测试你有权限使用的模型" /><el-button v-if="auth?.status === 'expired' && authProfile" @click="login(authProfile, true)">重新获取设备码</el-button></div></el-dialog>
    <el-drawer v-model="exportVisible" title="LiteLLM Proxy 配置（不含明文凭据）" size="min(780px, 100vw)" append-to-body class="rnd-form"><el-alert :title="exportNote" type="info" :closable="false" /><pre>{{ output }}</pre><template #footer><el-button type="primary" @click="downloadYaml">下载 config.yaml</el-button></template></el-drawer>
  </div>
</template>
<style scoped>
.filter-bar{display:flex;gap:10px;align-items:center;flex:none}.filter-bar .el-input{max-width:380px}.filter-bar>span{margin-left:auto;white-space:nowrap}.provider-list{display:flex;flex-direction:column;gap:8px}.provider-row{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1.2fr) 80px auto;gap:12px;align-items:center;padding:13px 14px;flex:none}.provider-name{display:flex;gap:10px;align-items:center;min-width:0}.provider-name>div{min-width:0;flex:1}.provider-name strong,.provider-name small,.model-cell code,.model-cell small{display:block;max-width:100%}.vendor-mark{flex:none;width:31px;height:31px;display:grid;place-items:center;background:var(--el-color-primary-light-9);color:var(--el-color-primary);border-radius:8px;font-size:11px;font-weight:700}.provider-row small{font-size:11px;color:var(--el-text-color-secondary);margin-top:4px}.model-cell{min-width:0}.model-cell code{font-size:12px}.profile-state{min-width:0}.profile-state small{display:block}.row-actions{display:flex;gap:5px;align-items:center;flex-wrap:wrap}.model-input{display:flex;gap:8px;width:100%;min-width:0}.model-input>.el-select{flex:1;min-width:0}.device-code{font-size:32px;font-weight:700;letter-spacing:4px;background:var(--el-fill-color-light);padding:18px;text-align:center;border-radius:10px;margin:16px 0}
@container(max-width:900px){.provider-row{grid-template-columns:minmax(0,1fr) 85px auto}.model-cell{grid-column:1/-1;grid-row:2}.profile-state{grid-column:2}.row-actions{grid-column:3;grid-row:1}}
@container(max-width:540px){.provider-row{grid-template-columns:minmax(0,1fr) auto;gap:8px}.provider-name{grid-column:1}.profile-state{grid-column:2}.row-actions{grid-column:1/-1;grid-row:3;justify-content:flex-end}.filter-bar{gap:6px}.model-input{flex-wrap:wrap}}
</style>
