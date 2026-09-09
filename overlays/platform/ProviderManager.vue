<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import FactoryAPI, { type ProviderInput, type ProviderProfile } from "@/api/module_factory";

const router = useRouter();
const items = ref<ProviderProfile[]>([]);
const busy = ref(false);
const drawer = ref(false);
const editing = ref<ProviderProfile | null>(null);
const testing = ref<string | null>(null);
const kinds = [
  ["openai", "OpenAI", "GPT / o-series / compatible OpenAI models"],
  ["anthropic", "Anthropic", "Claude models"],
  ["azure_openai", "Azure OpenAI", "Azure deployment names"],
  ["google", "Google Gemini", "Gemini via LiteLLM"],
  ["deepseek", "DeepSeek", "DeepSeek API"],
  ["groq", "Groq", "Groq-hosted models"],
  ["openrouter", "OpenRouter", "OpenRouter multi-model gateway"],
  ["ollama", "Ollama", "Local models, usually host.docker.internal"],
  ["mistral", "Mistral", "Mistral API"],
  ["xai", "xAI", "Grok models"],
  ["litellm_proxy", "LiteLLM Proxy", "Your own LiteLLM gateway / model aliases"],
  ["custom_openai", "Custom OpenAI-compatible", "Any verified OpenAI-compatible endpoint"],
] as const;
const presets: Record<string, string> = {
  deepseek: "https://api.deepseek.com/v1",
  groq: "https://api.groq.com/openai/v1",
  openrouter: "https://openrouter.ai/api/v1",
  ollama: "http://host.docker.internal:11434",
};
const form = reactive<ProviderInput>({
  name: "", provider: "openai", base_url: "", api_key: "", model: "",
  enabled: true, is_default: false, temperature: 0.1, max_tokens: 6000, api_version: "",
});
const enabledCount = computed(() => items.value.filter((item) => item.enabled).length);
const defaultItem = computed(() => items.value.find((item) => item.is_default));

async function refresh() {
  busy.value = true;
  try { items.value = await FactoryAPI.listProviders(); }
  finally { busy.value = false; }
}
function openCreate() {
  editing.value = null;
  Object.assign(form, { name: "", provider: "openai", base_url: "", api_key: "", model: "", enabled: true, is_default: items.value.length === 0, temperature: 0.1, max_tokens: 6000, api_version: "" });
  drawer.value = true;
}
function openEdit(item: ProviderProfile) {
  editing.value = item;
  Object.assign(form, { name: item.name, provider: item.provider, base_url: item.base_url, api_key: "", model: item.model, enabled: item.enabled, is_default: item.is_default, temperature: item.temperature, max_tokens: item.max_tokens, api_version: item.api_version || "" });
  drawer.value = true;
}
function providerChanged(value: string) {
  if (!editing.value) form.base_url = presets[value] || "";
}
async function save() {
  if (!form.name.trim() || !form.model.trim()) return;
  busy.value = true;
  try {
    if (editing.value) {
      const body: Partial<ProviderInput> = { ...form };
      if (!form.api_key) delete body.api_key;
      await FactoryAPI.updateProvider(editing.value.id, body);
    } else {
      await FactoryAPI.createProvider({ ...form });
    }
    drawer.value = false;
    await refresh();
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.msg || error?.response?.data?.detail || error?.message || String(error));
  } finally { busy.value = false; }
}
async function test(item: ProviderProfile) {
  testing.value = item.id;
  try {
    const result = await FactoryAPI.testProvider(item.id);
    if (!result.ok) throw new Error("模型测试没有返回成功确认");
    ElMessage.success(result.message || "模型已返回响应");
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.msg || error?.response?.data?.detail || error?.message || String(error));
  } finally { testing.value = null; }
}
async function setDefault(item: ProviderProfile) {
  await FactoryAPI.defaultProvider(item.id); await refresh();
}
async function remove(item: ProviderProfile) {
  try {
    await ElMessageBox.confirm(`删除模型配置“${item.name}”？尚未完成规划的任务可能因此失败。`, "删除模型供应商", { type: "warning" });
    await FactoryAPI.deleteProvider(item.id); await refresh();
  } catch (error) {
    if (error !== "cancel" && error !== "close") ElMessage.error("删除未完成，请检查权限或网络状态");
  }
}

watch(drawer, (open) => { if (!open) form.api_key = ""; });
onMounted(refresh);
</script>

<template>
  <div v-loading="busy" class="provider-page">
    <section class="page-head">
      <div><el-button text @click="router.push('/factory')">← 研发工作台</el-button><h1>模型供应商</h1><p>一处配置，多阶段复用。需求澄清与结构规划统一通过 LiteLLM 调度，密钥加密落库且接口永不返回明文。</p></div>
      <el-button type="primary" @click="openCreate">新增供应商</el-button>
    </section>
    <div class="summary">
      <el-card shadow="never"><small>已配置</small><strong>{{ items.length }}</strong></el-card>
      <el-card shadow="never"><small>已启用</small><strong>{{ enabledCount }}</strong></el-card>
      <el-card shadow="never"><small>默认模型</small><strong class="model-name">{{ defaultItem ? `${defaultItem.name} / ${defaultItem.model}` : '未设置' }}</strong></el-card>
    </div>
    <el-alert type="info" show-icon :closable="false" title="供应商配置属于当前登录用户">
      <template #default>API Key 使用 FACTORY_CREDENTIAL_ENCRYPTION_KEY 派生的 Fernet 密钥加密保存；编辑时留空表示保留原密钥。模型测试会真实请求供应商，因此可能产生少量费用。</template>
    </el-alert>
    <div class="cards">
      <el-card v-for="item in items" :key="item.id" shadow="hover" class="provider-card">
        <div class="provider-top">
          <div class="provider-logo">{{ item.provider.slice(0, 2).toUpperCase() }}</div>
          <div class="provider-title"><h3>{{ item.name }}</h3><span>{{ kinds.find(k => k[0] === item.provider)?.[1] || item.provider }}</span></div>
          <el-tag v-if="item.is_default" type="success">默认</el-tag><el-tag v-else-if="item.enabled">启用</el-tag><el-tag v-else type="info">停用</el-tag>
        </div>
        <div class="provider-meta"><div><small>模型</small><strong>{{ item.model }}</strong></div><div><small>API Key</small><strong>{{ item.has_api_key ? '•••••••• 已保存' : '未保存 / 本地无需' }}</strong></div><div><small>Base URL</small><strong>{{ item.base_url || '供应商默认地址' }}</strong></div></div>
        <div class="provider-actions"><el-button :loading="testing === item.id" @click="test(item)">测试连接</el-button><el-button v-if="!item.is_default && item.enabled" @click="setDefault(item)">设为默认</el-button><el-button @click="openEdit(item)">编辑</el-button><el-button type="danger" text @click="remove(item)">删除</el-button></div>
      </el-card>
      <button class="add-card" @click="openCreate"><span>＋</span><strong>新增模型供应商</strong><small>OpenAI / Claude / Gemini / DeepSeek / Ollama…</small></button>
    </div>

    <el-drawer v-model="drawer" :title="editing ? '编辑模型供应商' : '新增模型供应商'" size="520px" destroy-on-close>
      <el-form label-position="top">
        <el-form-item label="显示名称"><el-input v-model="form.name" placeholder="例如：生产 OpenAI / 本机 Ollama" /></el-form-item>
        <el-form-item label="供应商"><el-select v-model="form.provider" style="width:100%" @change="providerChanged"><el-option v-for="kind in kinds" :key="kind[0]" :value="kind[0]" :label="kind[1]"><span>{{ kind[1] }}</span><small class="option-note">{{ kind[2] }}</small></el-option></el-select></el-form-item>
        <el-form-item v-if="form.provider === 'azure_openai'" label="Azure API Version"><el-input v-model="form.api_version" placeholder="填写 Azure 部署支持的 api-version" /></el-form-item>
        <el-form-item label="模型 ID"><el-input v-model="form.model" placeholder="填写供应商当前有效的模型 ID 或 LiteLLM alias" /></el-form-item>
        <el-form-item label="Base URL"><el-input v-model="form.base_url" placeholder="留空使用供应商默认；自定义/代理请填写完整地址" /></el-form-item>
        <el-form-item :label="editing && editing.has_api_key ? 'API Key（留空保留原值）' : 'API Key'"><el-input v-model="form.api_key" type="password" show-password autocomplete="new-password" /></el-form-item>
        <el-row :gutter="12"><el-col :span="12"><el-form-item label="Temperature"><el-input-number v-model="form.temperature" :min="0" :max="2" :step="0.1" style="width:100%" /></el-form-item></el-col><el-col :span="12"><el-form-item label="Max Tokens"><el-input-number v-model="form.max_tokens" :min="256" :max="128000" :step="256" style="width:100%" /></el-form-item></el-col></el-row>
        <el-form-item><el-checkbox v-model="form.enabled">启用此配置</el-checkbox><el-checkbox v-model="form.is_default">设为默认</el-checkbox></el-form-item>
      </el-form>
      <template #footer><el-button @click="drawer = false">取消</el-button><el-button type="primary" :disabled="!form.name.trim() || !form.model.trim()" @click="save">保存</el-button></template>
    </el-drawer>
  </div>
</template>

<style scoped>
.provider-page{padding:20px;min-height:100%;background:var(--el-bg-color-page)}.page-head{display:flex;justify-content:space-between;align-items:flex-end;gap:20px;margin-bottom:16px}.page-head h1{font-size:26px;margin:5px 0}.page-head p{margin:0;color:var(--el-text-color-secondary)}.summary{display:grid;grid-template-columns:180px 180px 1fr;gap:12px;margin-bottom:14px}.summary :deep(.el-card__body){display:grid;gap:6px}.summary small{color:var(--el-text-color-secondary)}.summary strong{font-size:24px}.summary .model-name{font-size:16px}.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:14px;margin-top:16px}.provider-card{border-radius:12px}.provider-top{display:flex;align-items:center;gap:10px}.provider-logo{width:42px;height:42px;border-radius:12px;display:grid;place-items:center;color:white;font-weight:700;background:linear-gradient(135deg,#316ca8,#704cbb)}.provider-title{flex:1}.provider-title h3{margin:0 0 3px}.provider-title span{font-size:12px;color:var(--el-text-color-secondary)}.provider-meta{display:grid;gap:10px;margin:18px 0;padding:13px;background:var(--el-fill-color-light);border-radius:9px}.provider-meta div{display:grid;grid-template-columns:75px 1fr;gap:8px}.provider-meta small{color:var(--el-text-color-secondary)}.provider-meta strong{font-size:12px;word-break:break-all}.provider-actions{display:flex;gap:7px;flex-wrap:wrap}.add-card{min-height:260px;border:1px dashed var(--el-border-color);background:var(--el-bg-color);border-radius:12px;display:grid;place-content:center;text-align:center;gap:8px;color:var(--el-text-color-secondary);cursor:pointer}.add-card:hover{border-color:var(--el-color-primary);color:var(--el-color-primary)}.add-card span{font-size:38px;font-weight:200}.option-note{float:right;margin-left:15px;color:var(--el-text-color-secondary)}@media(max-width:760px){.provider-page{padding:10px}.page-head{align-items:flex-start;flex-direction:column}.summary{grid-template-columns:1fr}.cards{grid-template-columns:1fr}}
</style>
