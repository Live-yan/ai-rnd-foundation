<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import FactoryAPI, {
  type ProviderCatalog,
  type ProviderCatalogItem,
  type ProviderCatalogModel,
  type ProviderInput,
  type ProviderProfile,
} from "@/api/module_factory";

const router = useRouter();
const items = ref<ProviderProfile[]>([]);
const catalog = ref<ProviderCatalog | null>(null);
const busy = ref(false);
const drawer = ref(false);
const editing = ref<ProviderProfile | null>(null);
const testing = ref<string | null>(null);
const discovering = ref(false);
const search = ref("");
const categoryFilter = ref("全部");
const discovered = ref<ProviderCatalogModel[]>([]);
const modelQuery = ref("");

const form = reactive<ProviderInput>({
  name: "", provider: "openai", base_url: "", api_key: "", model: "",
  enabled: true, is_default: false, temperature: 0.1, max_tokens: 6000, api_version: "",
});

const providerOptions = computed(() => catalog.value?.providers || []);
const categories = computed(() => ["全部", ...(catalog.value?.categories || [])]);
const quickStart = computed(() => catalog.value?.quick_start || []);
const currentMeta = computed(() => providerOptions.value.find((item) => item.id === form.provider));
const enabledCount = computed(() => items.value.filter((item) => item.enabled).length);
const defaultItem = computed(() => items.value.find((item) => item.is_default));

const filteredCatalog = computed(() => {
  const q = search.value.trim().toLowerCase();
  return providerOptions.value.filter((item) => {
    if (categoryFilter.value !== "全部" && item.category !== categoryFilter.value) return false;
    if (!q) return true;
    return [item.id, item.name, item.description, item.category, ...(item.models || []).map((m) => m.id)]
      .join(" ")
      .toLowerCase()
      .includes(q);
  });
});

const filteredItems = computed(() => {
  const q = search.value.trim().toLowerCase();
  if (!q) return items.value;
  return items.value.filter((item) =>
    [item.name, item.provider, item.model, item.base_url].join(" ").toLowerCase().includes(q)
  );
});

const modelOptions = computed(() => {
  const base = discovered.value.length
    ? discovered.value
    : (currentMeta.value?.models || []);
  const q = modelQuery.value.trim().toLowerCase();
  if (!q) return base;
  return base.filter((item) => `${item.id} ${item.label}`.toLowerCase().includes(q));
});

const configuredProviders = computed(() => new Set(items.value.map((item) => item.provider)));

async function refresh() {
  busy.value = true;
  try {
    const [profiles, cat] = await Promise.all([FactoryAPI.listProviders(), FactoryAPI.providerCatalog()]);
    items.value = profiles;
    catalog.value = cat;
  } finally {
    busy.value = false;
  }
}

function displayNameFor(provider: string, model: string) {
  const meta = providerOptions.value.find((item) => item.id === provider);
  return model ? `${meta?.name || provider} · ${model}` : (meta?.name || provider);
}

function openCreate(preset?: { provider: string; model: string; name?: string }) {
  editing.value = null;
  discovered.value = [];
  modelQuery.value = "";
  const provider = preset?.provider || "openai";
  const meta = providerOptions.value.find((item) => item.id === provider);
  Object.assign(form, {
    name: preset?.name || "",
    provider,
    base_url: meta?.base_url || meta?.default_base_url || "",
    api_key: "",
    model: preset?.model || meta?.models?.[0]?.id || "",
    enabled: true,
    is_default: items.value.length === 0,
    temperature: 0.1,
    max_tokens: 6000,
    api_version: "",
  });
  drawer.value = true;
}

function openEdit(item: ProviderProfile) {
  editing.value = item;
  discovered.value = [];
  modelQuery.value = "";
  Object.assign(form, {
    name: item.name,
    provider: item.provider,
    base_url: item.base_url,
    api_key: "",
    model: item.model,
    enabled: item.enabled,
    is_default: item.is_default,
    temperature: item.temperature,
    max_tokens: item.max_tokens,
    api_version: item.api_version || "",
  });
  drawer.value = true;
}

function providerChanged(value: string) {
  discovered.value = [];
  modelQuery.value = "";
  if (editing.value) return;
  const meta = providerOptions.value.find((item) => item.id === value);
  form.base_url = meta?.base_url || meta?.default_base_url || "";
  if (!form.name || form.name === displayNameFor(form.provider, form.model)) {
    form.name = meta?.name || value;
  }
  if (!form.model || meta?.models?.some((m) => m.id === form.model)) {
    form.model = meta?.models?.[0]?.id || "";
  }
}

async function discoverModels() {
  if (!currentMeta.value?.supports_discover) return;
  if (currentMeta.value.requires_base_url && !form.base_url.trim()) {
    ElMessage.warning("请先填写 Base URL");
    return;
  }
  if (currentMeta.value.requires_api_key && !form.api_key && !(editing.value?.has_api_key)) {
    ElMessage.warning("该供应商发现模型需要 API Key");
    return;
  }
  discovering.value = true;
  try {
    const result = await FactoryAPI.discoverProviderModels({
      provider: form.provider,
      base_url: form.base_url,
      api_key: form.api_key || undefined,
    });
    discovered.value = result.models;
    ElMessage.success(`已发现 ${result.models.length} 个模型`);
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.msg || error?.response?.data?.detail || error?.message || String(error));
  } finally {
    discovering.value = false;
  }
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
  } finally {
    busy.value = false;
  }
}

async function test(item: ProviderProfile) {
  testing.value = item.id;
  try {
    const result = await FactoryAPI.testProvider(item.id);
    if (!result.ok) throw new Error("模型测试没有返回成功确认");
    ElMessage.success(result.message || "模型已返回响应");
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.msg || error?.response?.data?.detail || error?.message || String(error));
  } finally {
    testing.value = null;
  }
}

async function setDefault(item: ProviderProfile) {
  await FactoryAPI.defaultProvider(item.id);
  await refresh();
}

async function remove(item: ProviderProfile) {
  try {
    await ElMessageBox.confirm(
      `删除模型配置“${item.name}”？尚未完成规划的任务可能因此失败。`,
      "删除模型供应商",
      { type: "warning" }
    );
    await FactoryAPI.deleteProvider(item.id);
    await refresh();
  } catch (error) {
    if (error !== "cancel" && error !== "close") ElMessage.error("删除未完成，请检查权限或网络状态");
  }
}

function providerBadge(provider: string) {
  const meta = providerOptions.value.find((item) => item.id === provider);
  return (meta?.name || provider).slice(0, 2).toUpperCase();
}

watch(drawer, (open) => {
  if (!open) form.api_key = "";
});
onMounted(refresh);
</script>

<template>
  <div v-loading="busy" class="provider-page">
    <section class="page-head">
      <div>
        <el-button text @click="router.push('/factory')">← 研发工作台</el-button>
        <h1>模型供应商</h1>
        <p>
          通过 LiteLLM 一处接入主流云端、聚合网关与本地模型。目录内置 40+ 供应商与常用模型 ID，
          支持在线发现模型列表；密钥加密落库且接口永不返回明文。
        </p>
      </div>
      <el-button type="primary" @click="openCreate()">新增供应商</el-button>
    </section>

    <div class="summary">
      <el-card shadow="never"><small>已配置</small><strong>{{ items.length }}</strong></el-card>
      <el-card shadow="never"><small>已启用</small><strong>{{ enabledCount }}</strong></el-card>
      <el-card shadow="never">
        <small>默认模型</small>
        <strong class="model-name">
          {{ defaultItem ? `${defaultItem.name} / ${defaultItem.model}` : "未设置" }}
        </strong>
      </el-card>
      <el-card shadow="never">
        <small>可用目录</small>
        <strong>{{ providerOptions.length }} 家</strong>
      </el-card>
    </div>

    <el-alert type="info" show-icon :closable="false" title="供应商配置属于当前登录用户">
      <template #default>
        API Key 使用 FACTORY_CREDENTIAL_ENCRYPTION_KEY 派生的 Fernet 密钥加密保存；编辑时留空表示保留原密钥。
        连接测试会真实请求供应商，因此可能产生少量费用。本地/自定义端点需管理员在
        FACTORY_MODEL_ALLOWED_ORIGINS 中批准 origin。
      </template>
    </el-alert>

    <section v-if="quickStart.length" class="quick-start">
      <header>
        <h2>快速接入</h2>
        <span>点选后自动填好供应商与模型 ID，补上 Key 即可保存</span>
      </header>
      <div class="quick-row">
        <button
          v-for="preset in quickStart"
          :key="`${preset.provider}-${preset.model}`"
          type="button"
          class="quick-chip"
          @click="openCreate(preset)"
        >
          <span class="quick-logo">{{ providerBadge(preset.provider) }}</span>
          <span>
            <strong>{{ preset.name }}</strong>
            <small>{{ preset.model }}</small>
          </span>
        </button>
      </div>
    </section>

    <section class="toolbar">
      <el-input v-model="search" clearable placeholder="搜索供应商 / 模型 / 已配置项" class="search-box" />
      <el-radio-group v-model="categoryFilter" size="small">
        <el-radio-button v-for="name in categories" :key="name" :value="name">{{ name }}</el-radio-button>
      </el-radio-group>
    </section>

    <section class="catalog-grid">
      <article
        v-for="meta in filteredCatalog"
        :key="meta.id"
        class="catalog-card"
        :class="{ configured: configuredProviders.has(meta.id) }"
      >
        <div class="catalog-top">
          <div class="provider-logo">{{ providerBadge(meta.id) }}</div>
          <div class="catalog-title">
            <h3>{{ meta.name }}</h3>
            <span>{{ meta.description }}</span>
          </div>
          <el-tag v-if="configuredProviders.has(meta.id)" size="small" type="success">已接入</el-tag>
          <el-tag v-else-if="meta.is_local" size="small" type="warning">本地</el-tag>
          <el-tag v-else size="small" type="info">{{ meta.category }}</el-tag>
        </div>
        <div class="model-preview">
          <template v-if="meta.models.length">
            <el-tag v-for="model in meta.models.slice(0, 3)" :key="model.id" size="small" effect="plain">
              {{ model.id }}
            </el-tag>
            <el-tag v-if="meta.models.length > 3" size="small" type="info" effect="plain">
              +{{ meta.models.length - 3 }}
            </el-tag>
          </template>
          <small v-else class="muted">手动填写模型 ID，或使用在线发现</small>
        </div>
        <div class="catalog-actions">
          <el-button size="small" type="primary" text @click="openCreate({ provider: meta.id, model: meta.models[0]?.id || '' })">
            配置
          </el-button>
          <a v-if="meta.docs" :href="meta.docs" target="_blank" rel="noreferrer">文档</a>
        </div>
      </article>
    </section>

    <section class="configured-section">
      <header class="section-head">
        <h2>已配置供应商</h2>
        <span>{{ filteredItems.length }} 条</span>
      </header>
      <div v-if="!filteredItems.length" class="empty-state">
        还没有匹配的配置。从上方目录或快速接入卡片开始。
      </div>
      <div v-else class="cards">
        <el-card v-for="item in filteredItems" :key="item.id" shadow="hover" class="provider-card">
          <div class="provider-top">
            <div class="provider-logo">{{ providerBadge(item.provider) }}</div>
            <div class="provider-title">
              <h3>{{ item.name }}</h3>
              <span>{{ providerOptions.find((k) => k.id === item.provider)?.name || item.provider }}</span>
            </div>
            <el-tag v-if="item.is_default" type="success">默认</el-tag>
            <el-tag v-else-if="item.enabled">启用</el-tag>
            <el-tag v-else type="info">停用</el-tag>
          </div>
          <div class="provider-meta">
            <div><small>模型</small><strong>{{ item.model }}</strong></div>
            <div>
              <small>API Key</small>
              <strong>{{ item.has_api_key ? "•••••••• 已保存" : "未保存 / 本地无需" }}</strong>
            </div>
            <div><small>Base URL</small><strong>{{ item.base_url || "供应商默认地址" }}</strong></div>
          </div>
          <div class="provider-actions">
            <el-button :loading="testing === item.id" @click="test(item)">测试连接</el-button>
            <el-button v-if="!item.is_default && item.enabled" @click="setDefault(item)">设为默认</el-button>
            <el-button @click="openEdit(item)">编辑</el-button>
            <el-button type="danger" text @click="remove(item)">删除</el-button>
          </div>
        </el-card>
        <button class="add-card" @click="openCreate()">
          <span>＋</span>
          <strong>新增模型供应商</strong>
          <small>OpenAI / Claude / Gemini / DeepSeek / Ollama…</small>
        </button>
      </div>
    </section>

    <el-drawer
      v-model="drawer"
      :title="editing ? '编辑模型供应商' : '新增模型供应商'"
      size="560px"
      destroy-on-close
    >
      <el-form label-position="top">
        <el-form-item label="显示名称">
          <el-input v-model="form.name" placeholder="例如：生产 OpenAI / 本机 Ollama" />
        </el-form-item>

        <el-form-item label="供应商">
          <el-select v-model="form.provider" filterable style="width: 100%" @change="providerChanged">
            <el-option-group
              v-for="category in (catalog?.categories || [])"
              :key="category"
              :label="category"
            >
              <el-option
                v-for="meta in providerOptions.filter((p) => p.category === category)"
                :key="meta.id"
                :value="meta.id"
                :label="meta.name"
              >
                <span>{{ meta.name }}</span>
                <small class="option-note">{{ meta.description }}</small>
              </el-option>
            </el-option-group>
          </el-select>
        </el-form-item>

        <el-alert
          v-if="currentMeta?.extra_hint"
          type="warning"
          :closable="false"
          :title="currentMeta.extra_hint"
          class="hint-alert"
        />

        <el-form-item v-if="form.provider === 'azure_openai'" label="Azure API Version">
          <el-input v-model="form.api_version" placeholder="填写 Azure 部署支持的 api-version" />
        </el-form-item>

        <el-form-item label="模型 ID">
          <div class="model-field">
            <el-select
              v-model="form.model"
              filterable
              allow-create
              default-first-option
              clearable
              style="width: 100%"
              placeholder="选择常用模型，或输入自定义模型 ID"
              :filter-method="(q: string) => { modelQuery = q }"
            >
              <el-option
                v-for="model in modelOptions"
                :key="model.id"
                :value="model.id"
                :label="model.label || model.id"
              >
                <span>{{ model.id }}</span>
                <small v-if="model.label && model.label !== model.id" class="option-note">
                  {{ model.label }}
                </small>
              </el-option>
            </el-select>
            <el-button
              v-if="currentMeta?.supports_discover"
              :loading="discovering"
              @click="discoverModels"
            >
              发现模型
            </el-button>
          </div>
          <div v-if="discovered.length" class="discover-note">
            已从端点发现 {{ discovered.length }} 个模型，可直接选择。
          </div>
          <div v-else-if="currentMeta?.models?.length" class="discover-note">
            目录内置 {{ currentMeta.models.length }} 个常用模型；也可手动输入任意模型 ID。
          </div>
        </el-form-item>

        <el-form-item label="Base URL">
          <div class="model-field">
            <el-input
              v-model="form.base_url"
              :placeholder="currentMeta?.default_base_url || '留空使用供应商默认；自定义/代理请填写完整地址'"
            />
            <el-button
              v-if="currentMeta?.default_base_url && !editing"
              text
              @click="form.base_url = currentMeta.default_base_url"
            >
              用默认
            </el-button>
          </div>
        </el-form-item>

        <el-form-item
          :label="editing && editing.has_api_key ? 'API Key（留空保留原值）' : (currentMeta?.requires_api_key === false ? 'API Key（可选）' : 'API Key')"
        >
          <el-input
            v-model="form.api_key"
            type="password"
            show-password
            autocomplete="new-password"
            :placeholder="currentMeta?.requires_api_key === false ? '本地/网关可留空' : '填写供应商 API Key'"
          />
        </el-form-item>

        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="Temperature">
              <el-input-number v-model="form.temperature" :min="0" :max="2" :step="0.1" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="Max Tokens">
              <el-input-number v-model="form.max_tokens" :min="256" :max="128000" :step="256" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item>
          <el-checkbox v-model="form.enabled">启用此配置</el-checkbox>
          <el-checkbox v-model="form.is_default">设为默认</el-checkbox>
        </el-form-item>

        <div v-if="currentMeta" class="meta-foot">
          LiteLLM 前缀：<code>{{ currentMeta.litellm_prefix }}/</code>
          <template v-if="currentMeta.requires_base_url"> · 需要 Base URL</template>
          <template v-if="!currentMeta.requires_api_key"> · 可无 API Key</template>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="drawer = false">取消</el-button>
        <el-button type="primary" :disabled="!form.name.trim() || !form.model.trim()" @click="save">
          保存
        </el-button>
      </template>
    </el-drawer>
  </div>
</template>

<style scoped>
.provider-page {
  padding: 20px;
  min-height: 100%;
  background: var(--el-bg-color-page);
}
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 20px;
  margin-bottom: 16px;
}
.page-head h1 {
  font-size: 26px;
  margin: 5px 0;
}
.page-head p {
  margin: 0;
  color: var(--el-text-color-secondary);
  max-width: 760px;
}
.summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}
.summary :deep(.el-card__body) {
  display: grid;
  gap: 6px;
}
.summary small {
  color: var(--el-text-color-secondary);
}
.summary strong {
  font-size: 22px;
}
.summary .model-name {
  font-size: 15px;
  word-break: break-all;
}
.quick-start {
  margin: 16px 0 8px;
}
.quick-start header {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 10px;
}
.quick-start h2,
.configured-section h2 {
  margin: 0;
  font-size: 16px;
}
.quick-start header span,
.section-head span {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.quick-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.quick-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--el-border-color);
  background: var(--el-bg-color);
  border-radius: 10px;
  padding: 8px 12px;
  cursor: pointer;
  text-align: left;
  min-width: 170px;
}
.quick-chip:hover {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}
.quick-chip strong {
  display: block;
  font-size: 13px;
}
.quick-chip small {
  color: var(--el-text-color-secondary);
  font-size: 11px;
}
.quick-logo,
.provider-logo {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  display: grid;
  place-items: center;
  color: #fff;
  font-weight: 700;
  font-size: 12px;
  background: linear-gradient(135deg, #316ca8, #704cbb);
  flex-shrink: 0;
}
.toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
  margin: 14px 0 12px;
}
.search-box {
  max-width: 360px;
}
.catalog-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 10px;
  margin-bottom: 22px;
}
.catalog-card {
  border: 1px solid var(--el-border-color);
  background: var(--el-bg-color);
  border-radius: 12px;
  padding: 12px;
  display: grid;
  gap: 10px;
}
.catalog-card.configured {
  border-color: var(--el-color-success-light-5);
  box-shadow: inset 0 0 0 1px var(--el-color-success-light-7);
}
.catalog-top {
  display: flex;
  align-items: center;
  gap: 10px;
}
.catalog-title {
  flex: 1;
  min-width: 0;
}
.catalog-title h3 {
  margin: 0 0 2px;
  font-size: 14px;
}
.catalog-title span {
  display: block;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.model-preview {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-height: 24px;
  align-items: center;
}
.model-preview :deep(.el-tag) {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.catalog-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.catalog-actions a {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  text-decoration: none;
}
.catalog-actions a:hover {
  color: var(--el-color-primary);
}
.configured-section {
  margin-top: 8px;
}
.section-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 10px;
}
.empty-state {
  border: 1px dashed var(--el-border-color);
  border-radius: 12px;
  padding: 28px;
  text-align: center;
  color: var(--el-text-color-secondary);
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(330px, 1fr));
  gap: 14px;
}
.provider-card {
  border-radius: 12px;
}
.provider-top {
  display: flex;
  align-items: center;
  gap: 10px;
}
.provider-title {
  flex: 1;
}
.provider-title h3 {
  margin: 0 0 3px;
}
.provider-title span {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.provider-meta {
  display: grid;
  gap: 10px;
  margin: 18px 0;
  padding: 13px;
  background: var(--el-fill-color-light);
  border-radius: 9px;
}
.provider-meta div {
  display: grid;
  grid-template-columns: 75px 1fr;
  gap: 8px;
}
.provider-meta small {
  color: var(--el-text-color-secondary);
}
.provider-meta strong {
  font-size: 12px;
  word-break: break-all;
}
.provider-actions {
  display: flex;
  gap: 7px;
  flex-wrap: wrap;
}
.add-card {
  min-height: 260px;
  border: 1px dashed var(--el-border-color);
  background: var(--el-bg-color);
  border-radius: 12px;
  display: grid;
  place-content: center;
  text-align: center;
  gap: 8px;
  color: var(--el-text-color-secondary);
  cursor: pointer;
}
.add-card:hover {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}
.add-card span {
  font-size: 38px;
  font-weight: 200;
}
.option-note {
  float: right;
  margin-left: 15px;
  color: var(--el-text-color-secondary);
}
.model-field {
  display: flex;
  gap: 8px;
  width: 100%;
  align-items: flex-start;
}
.model-field :deep(.el-select),
.model-field :deep(.el-input) {
  flex: 1;
}
.discover-note {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.hint-alert {
  margin-bottom: 12px;
}
.meta-foot {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}
.meta-foot code {
  background: var(--el-fill-color-light);
  padding: 1px 5px;
  border-radius: 4px;
}
@media (max-width: 900px) {
  .summary {
    grid-template-columns: 1fr 1fr;
  }
}
@media (max-width: 760px) {
  .provider-page {
    padding: 10px;
  }
  .page-head {
    align-items: flex-start;
    flex-direction: column;
  }
  .summary {
    grid-template-columns: 1fr;
  }
  .cards,
  .catalog-grid {
    grid-template-columns: 1fr;
  }
}
</style>
