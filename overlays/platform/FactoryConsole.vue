<script setup lang="ts">
import { computed, onMounted, onUnmounted, onActivated, onDeactivated, ref } from "vue";
import { useRouter } from "vue-router";
import { useEmbeddedViewport } from "@/api/module_factory/embedded";
import "@/api/module_factory/embedded.css";
import { ElMessage } from "element-plus";
import FactoryAPI, { type FactoryProject, type FactoryRun, type ProviderProfile, type RunEvent, type ToolchainItem } from "@/api/module_factory";

const router = useRouter();
const { panel, panelHeight } = useEmbeddedViewport();
const pipelineVisible = ref(false);
const runVisible = ref(false);
const projects = ref<FactoryProject[]>([]);
const providers = ref<ProviderProfile[]>([]);
const tools = ref<ToolchainItem[]>([]);
const runs = ref<FactoryRun[]>([]);
const events = ref<RunEvent[]>([]);
const project = ref<FactoryProject | null>(null);
const run = ref<FactoryRun | null>(null);
const providerId = ref<string | null>(null);
const title = ref("设备台账与维护管理");
const requirement = ref("我需要一个设备台账与维护管理系统。请先分析需求，问清楚角色、数据范围、业务规则、验收条件，再开始设计和生成。");
const answer = ref("");
const mode = ref<"core" | "full">("full");
const sandbox = ref<"static" | "docker" | "cube">("cube");
const useSerena = ref(true);
const provisionCoder = ref(true);
const acceptLimitations = ref(false);
const busy = ref(false);
const createVisible = ref(false);
const specVisible = ref(false);
const logVisible = ref(false);
let timer: ReturnType<typeof setTimeout> | undefined;
let polling = false;
let active = false;
let selection = 0;
const connectionError = ref("");
const analysisVisible = ref(false);
const analysisFiles = ref<string[]>([]);
const analysisContent = ref("");
const analysisImage = ref("");
const analysisPath = ref("");
let previewSelection = 0;

const stages = [
  ["clarify", "需求澄清", "LangGraph + LiteLLM"],
  ["context", "模板理解", "ToolHive + Serena"],
  ["plan", "结构规划", "LangGraph + LiteLLM"],
  ["openspec", "规格门禁", "OpenSpec"],
  ["architecture", "架构设计", "Structurizr C4 + diagrams"],
  ["human_gate", "人工确认", "Temporal Signal"],
  ["generate", "源码生成", "FastapiAdmin Factory"],
  ["sandbox", "隔离验证", "CubeSandbox"],
  ["package", "交付打包", "SHA-256"],
  ["coder", "IDE 工作区", "Coder"],
  ["complete", "完成", "Temporal"],
] as const;
const defaultProvider = computed(() => providers.value.find((x) => x.is_default && x.enabled) || providers.value.find((x) => x.enabled));
const clarificationReady = computed(() => project.value?.clarification_status === "READY");
const questions = computed(() => project.value?.clarification?.questions || []);
const unsupported = computed(() => (run.value?.spec?.unsupported_features || []) as string[]);
const fullReady = computed(() => {
  const required = ["fastapiadmin", "langgraph", "litellm", "temporal", "openspec", "diagrams", "structurizr", "toolhive", "serena", "cube", "coder"];
  const state = new Map(tools.value.map((x) => [x.id, x.configured]));
  return required.every((id) => state.get(id));
});
const finishedStages = computed(() => stages.filter(([key]) => stageState(key) === "ok").length);

function errorText(error: any) {
  return error?.response?.data?.msg || error?.response?.data?.detail || error?.message || String(error);
}
async function guarded<T>(fn: () => Promise<T>) {
  busy.value = true;
  try { return await fn(); }
  catch (error: any) { ElMessage.error(errorText(error)); }
  finally { busy.value = false; }
}
function stageState(key: string) {
  if (key === "clarify") return run.value ? "ok" : clarificationReady.value ? "ok" : project.value ? "doing" : "wait";
  if (key === "human_gate" && run.value?.decision) return run.value.decision.approve ? "ok" : "bad";
  if (key === "human_gate" && run.value?.status === "AWAITING_APPROVAL") return "doing";
  if (key === "complete" && run.value?.status === "READY") return "ok";
  const status = String(run.value?.stage_details?.[key]?.status || "");
  if (run.value?.status === "FAILED" && status && !/READY|PLANNED|VALIDATED|GENERATED|VERIFIED|PACKAGED|SKIPPED/.test(status)) return "bad";
  if (/FAIL|ERROR/.test(status)) return "bad";
  if (/SKIPPED/.test(status) || run.value?.stage_details?.[key]?.used === false) return "skipped";
  if (/READY|PLANNED|VALIDATED|GENERATED|VERIFIED|PACKAGED|SKIPPED/.test(status)) return "ok";
  return status ? "doing" : "wait";
}
function setMode(value: string | number | boolean | undefined) {
  if (value === "full") { sandbox.value = "cube"; useSerena.value = true; provisionCoder.value = true; }
  else if (value === "core") { sandbox.value = "static"; useSerena.value = false; provisionCoder.value = false; }
}
async function refreshBase() {
  [providers.value, tools.value, projects.value] = await Promise.all([
    FactoryAPI.listProviders(), FactoryAPI.toolchain(), FactoryAPI.listProjects(),
  ]);
  if (!providerId.value) providerId.value = defaultProvider.value?.id || null;
}
async function chooseProject(item: FactoryProject) {
  const ticket = ++selection;
  run.value = null; events.value = []; runs.value = [];
  await guarded(async () => {
    const [next, history] = await Promise.all([FactoryAPI.getProject(item.id), FactoryAPI.listRuns(item.id)]);
    if (ticket !== selection) return;
    project.value = next; runs.value = history;
    const latest = history[0];
    if (latest) await chooseRun(latest);
    acceptLimitations.value = false;
  });
}
async function createProject() {
  if (!title.value.trim() || requirement.value.trim().length < 5) return;
  await guarded(async () => {
    ++selection; run.value = null; runs.value = []; events.value = []; acceptLimitations.value = false;
    project.value = await FactoryAPI.createProject({ title: title.value.trim(), requirement: requirement.value.trim() });
    createVisible.value = false;
    await refreshBase();
    if (!providerId.value) { ElMessage.warning("项目已创建，请先配置模型供应商。不会退回固定 Demo。"); return; }
    project.value = await FactoryAPI.clarify(project.value.id, providerId.value);
    runs.value = []; run.value = null; events.value = [];
  });
}
async function clarify() {
  if (!project.value) return;
  await guarded(async () => { project.value = await FactoryAPI.clarify(project.value!.id, providerId.value); await refreshBase(); });
}
async function sendAnswer() {
  if (!project.value || !answer.value.trim()) return;
  await guarded(async () => {
    project.value = await FactoryAPI.addMessage(project.value!.id, answer.value.trim());
    answer.value = "";
    project.value = await FactoryAPI.clarify(project.value!.id, providerId.value);
    await refreshBase();
  });
}
async function startRun() {
  if (!project.value || !clarificationReady.value || !providerId.value) return;
  if (mode.value === "full" && !fullReady.value) { ElMessage.warning("完整模式仍有组件未配置，请先检查工具链中心。"); return; }
  await guarded(async () => {
    run.value = await FactoryAPI.startRun(project.value!.id, {
      provider_id: providerId.value,
      expected_revision: project.value!.revision,
      pipeline_mode: mode.value,
      sandbox: sandbox.value,
      use_serena: useSerena.value,
      provision_coder: provisionCoder.value,
      idempotency_key: crypto.randomUUID(),
    });
    runs.value = await FactoryAPI.listRuns(project.value!.id);
    events.value = [];
  });
}
async function chooseRun(item: FactoryRun) {
  run.value = await FactoryAPI.getRun(item.id);
  events.value = await FactoryAPI.events(item.id, 0);
}
function selectRun(id: string) { const item = runs.value.find((x) => x.id === id); if (item) void chooseRun(item); }
async function decide(approve: boolean) {
  if (!run.value?.spec_digest) return;
  if (approve && unsupported.value.length && !acceptLimitations.value) { ElMessage.warning("请先阅读并接受当前确定性生成器未实现的能力。"); return; }
  await guarded(async () => {
    run.value = await FactoryAPI.decide(run.value!.id, {
      spec_digest: run.value!.spec_digest, approve, accept_limitations: acceptLimitations.value,
    });
  });
}
async function download() {
  if (!run.value) return;
  await guarded(async () => {
    const blob = await FactoryAPI.download(run.value!.id);
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url; link.download = `${run.value!.spec?.slug || "product"}.zip`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
}
function openCoder() {
  const url = run.value?.checks?.coder?.url;
  if (!url) return;
  const target = new URL(String(url));
  if (["https:", "http:"].includes(target.protocol)) window.open(target.href, "_blank", "noopener,noreferrer");
}
function stopPolling() {
  active = false;
  if (timer) clearTimeout(timer);
}
async function poll() {
  if (!active || polling) return;
  polling = true;
  try {
    if (run.value?.id) {
      const id = run.value.id;
      const [latest, more] = await Promise.all([FactoryAPI.getRun(id), FactoryAPI.events(id, events.value.at(-1)?.id || 0)]);
      if (active && run.value?.id === id) { run.value = latest; events.value.push(...more); connectionError.value = ""; }
    }
  } catch { connectionError.value = "运行状态同步失败；请检查网络、登录状态或服务日志。"; }
  finally { polling = false; if (active) timer = setTimeout(poll, 2500); }
}
async function showAnalysis() {
  if (!run.value) return;
  await guarded(async () => {
    analysisFiles.value = await FactoryAPI.analysisFiles(run.value!.id);
    analysisVisible.value = true;
    const first = analysisFiles.value[0];
    if (first) await previewAnalysis(first);
  });
}
async function previewAnalysis(path: string) {
  if (!run.value) return;
  const ticket = ++previewSelection;
  const id = run.value.id;
  const blob = await FactoryAPI.analysisFile(id, path);
  if (ticket !== previewSelection || run.value?.id !== id) return;
  if (analysisImage.value) URL.revokeObjectURL(analysisImage.value);
  analysisImage.value = ""; analysisPath.value = path;
  if (path.endsWith(".svg")) { analysisImage.value = URL.createObjectURL(blob); analysisContent.value = ""; }
  else analysisContent.value = await blob.text();
}
onMounted(async () => {
  await guarded(async () => { await refreshBase(); const first = projects.value[0]; if (first) await chooseProject(first); });
  active = true; void poll();
});
onActivated(() => { active = true; if (timer) clearTimeout(timer); void refreshBase().catch(() => {}); void poll(); });
onDeactivated(stopPolling);
onUnmounted(() => { stopPolling(); ++previewSelection; if (analysisImage.value) URL.revokeObjectURL(analysisImage.value); });
</script>

<template>
  <div ref="panel" v-loading="busy" class="rnd-embedded factory-page" :style="{ height: panelHeight }">
    <header class="rnd-toolbar">
      <div><h1>研发工作台 <el-tag size="small" effect="plain">{{ projects.length }} 个项目</el-tag></h1><p>澄清需求 → 审阅规格 → 验证并交付</p></div>
      <div class="rnd-actions"><el-button size="small" @click="router.push('/factory-providers')">模型配置</el-button><el-button size="small" @click="router.push('/factory-toolchain')">工具链</el-button><el-button size="small" @click="pipelineVisible = true">流程 {{ finishedStages }}/{{ stages.length }}</el-button><el-button type="primary" size="small" @click="createVisible = true">新建项目</el-button></div>
    </header>
    <div v-if="!providers.length" class="rnd-note">先配置真实模型。API 密钥与 ChatGPT/Codex 网页登录可分别管理。</div>
    <div v-if="connectionError" class="rnd-note rnd-error">{{ connectionError }}</div>
    <main class="work-area">
      <aside class="rnd-panel project-list"><div class="list-title">我的项目</div><div class="rnd-scroll"><button v-for="item in projects" :key="item.id" class="project-item" :class="{ selected: project?.id === item.id }" @click="chooseProject(item)"><strong class="rnd-ellipsis">{{ item.title }}</strong><small>{{ item.clarification_status === 'READY' ? '需求已澄清' : '待分析 / 待回答' }}</small></button><el-empty v-if="!projects.length" :image-size="50" description="还没有项目" /></div></aside>
      <section class="rnd-panel conversation">
        <div class="conversation-head"><strong class="rnd-ellipsis">{{ project?.title || '选择或创建项目' }}</strong><el-select v-model="providerId" size="small" placeholder="选择模型" class="model-picker"><el-option v-for="item in providers.filter(x => x.enabled)" :key="item.id" :value="item.id" :label="`${item.name} · ${item.model}`" /></el-select><el-select class="mobile-project" :model-value="project?.id" size="small" placeholder="切换项目" @change="id => { const p = projects.find(x => x.id === id); if (p) chooseProject(p); }"><el-option v-for="p in projects" :key="p.id" :value="p.id" :label="p.title" /></el-select></div>
        <div class="rnd-scroll chat-history" aria-label="需求对话">
          <div v-if="project" class="conversation-status"><el-tag size="small" :type="clarificationReady ? 'success' : 'warning'">{{ clarificationReady ? '可进入规划' : '澄清中' }}</el-tag><span class="rnd-muted">{{ questions.length ? `${questions.length} 个问题等待回答` : '新增需求会重新经过 AI 分析' }}</span></div>
          <article v-for="(message, i) in project?.messages || []" :key="i" class="message" :class="message.role"><div class="avatar">{{ message.role === 'assistant' ? 'AI' : '我' }}</div><div class="bubble"><small>{{ message.role === 'assistant' ? '需求分析' : '需求方' }}</small><p>{{ message.content }}</p><ol v-if="message.questions?.length"><li v-for="q in message.questions" :key="q">{{ q }}</li></ol></div></article>
          <el-empty v-if="!project" :image-size="72" description="描述目标，AI 会先提问并确认范围" />
        </div>
        <div class="composer"><el-input v-model="answer" type="textarea" :rows="2" :disabled="!project" maxlength="16000" placeholder="回答 AI 的问题，或补充需求…" aria-label="补充需求" /><div class="rnd-footer"><span class="rnd-muted">先问清楚，再生成</span><div class="rnd-actions"><el-button size="small" :disabled="!project || !providerId" @click="clarify">重新分析</el-button><el-button type="primary" size="small" :disabled="!project || !providerId || !answer.trim()" @click="sendAnswer">发送并分析</el-button></div></div></div>
      </section>
    </main>
    <footer class="rnd-footer run-footer"><div class="rnd-actions"><el-tag size="small" :type="run?.status === 'FAILED' ? 'danger' : run?.status === 'READY' ? 'success' : 'info'">{{ run?.status || (clarificationReady ? '需求已就绪' : '尚未启动') }}</el-tag><el-button v-if="run" size="small" @click="runVisible = true">运行详情</el-button><el-button v-if="run?.status === 'AWAITING_APPROVAL'" type="warning" size="small" @click="runVisible = true">审阅并批准</el-button><el-button v-if="run?.download_available" type="success" size="small" @click="download">下载源码</el-button></div><div class="rnd-actions"><el-tag size="small" effect="plain">{{ mode === 'full' ? '完整模式' : '基础模式' }}</el-tag><el-button size="small" @click="pipelineVisible = true">运行设置</el-button><el-button size="small" type="primary" :disabled="!clarificationReady || !providerId || (mode === 'full' && !fullReady)" @click="startRun">启动研发</el-button></div></footer>
    <el-drawer v-model="pipelineVisible" title="研发流水线 / 运行设置" size="min(480px, 100vw)" append-to-body class="rnd-form"><div class="rnd-actions"><el-radio-group v-model="mode" size="small" @change="setMode"><el-radio-button value="core">基础模式</el-radio-button><el-radio-button value="full">完整模式</el-radio-button></el-radio-group><el-button size="small" @click="router.push('/factory-toolchain'); pipelineVisible = false">配置组件</el-button></div><el-alert v-if="mode === 'full' && !fullReady" title="缺少完整工具链配置；不会静默跳过" type="warning" :closable="false" /><el-form label-position="top"><el-form-item label="验证环境"><el-select v-model="sandbox" :disabled="mode === 'full'"><el-option label="静态 / 契约检查" value="static" /><el-option label="Docker" value="docker" /><el-option label="CubeSandbox" value="cube" /></el-select></el-form-item><el-checkbox v-model="useSerena" :disabled="mode === 'full'">ToolHive + Serena 上下文</el-checkbox><el-checkbox v-model="provisionCoder" :disabled="mode === 'full'">Coder 源码工作区</el-checkbox></el-form><div class="stages"><div v-for="([key, name, tool], i) in stages" :key="key" class="stage" :class="stageState(key)"><span>{{ i + 1 }}</span><div><strong>{{ name }}</strong><small>{{ tool }}</small><em>{{ run?.stage_details?.[key]?.status || 'WAITING' }}</em></div></div></div></el-drawer>
    <el-drawer v-model="runVisible" title="当前运行与交付" size="min(680px, 100vw)" append-to-body class="rnd-form"><template v-if="run"><el-select :model-value="run.id" @change="selectRun"><el-option v-for="item in runs" :key="item.id" :value="item.id" :label="`${item.id.slice(0, 8)} · ${item.status}`" /></el-select><h3>{{ run.spec?.title || project?.title }}</h3><div class="rnd-actions"><el-button @click="specVisible = true" :disabled="!run.spec">规格</el-button><el-button @click="showAnalysis" :disabled="!run.spec">架构与文档</el-button><el-button @click="logVisible = true">日志</el-button><el-button v-if="run.checks?.coder?.url" @click="openCoder">打开 IDE</el-button></div><el-alert v-if="run.error" :title="run.error" type="error" :closable="false" /><div v-if="run.status === 'AWAITING_APPROVAL'" class="approval"><p>请先审阅规格、架构和未支持项，再批准本次需求快照。</p><el-checkbox v-model="acceptLimitations">已阅读并接受未实现项</el-checkbox><div class="rnd-actions"><el-button @click="decide(false)">拒绝</el-button><el-button type="primary" @click="decide(true)">批准并继续</el-button></div></div><el-descriptions v-if="run.checks" :column="1" border size="small"><el-descriptions-item label="产品全栈">{{ run.checks.full_stack }}</el-descriptions-item><el-descriptions-item label="前端构建">{{ run.checks.frontend_build }}</el-descriptions-item><el-descriptions-item label="源码导入">{{ run.checks.coder?.source_import || '未请求' }}</el-descriptions-item></el-descriptions><p class="rnd-muted">流水线完成不代表任意业务或生产安全已验收，未执行项保留在质量报告。</p></template></el-drawer>
    <el-dialog v-model="createVisible" title="新建研发项目" width="min(680px, 94vw)" append-to-body class="rnd-form"><el-form label-position="top"><el-form-item label="名称"><el-input v-model="title" maxlength="100" /></el-form-item><el-form-item label="软件需求"><el-input v-model="requirement" type="textarea" :rows="6" maxlength="16000" show-word-limit /></el-form-item><el-alert title="创建后先由真实模型分析和提问，不直接生成代码" type="info" :closable="false" /></el-form><template #footer><el-button @click="createVisible = false">取消</el-button><el-button type="primary" :disabled="!providerId || !title.trim() || requirement.trim().length < 5" @click="createProject">创建并分析</el-button></template></el-dialog>
    <el-drawer v-model="specVisible" title="需求规格" size="min(760px, 100vw)" append-to-body class="rnd-form"><h3>{{ run?.spec?.title }}</h3><p>{{ run?.spec?.summary }}</p><el-alert v-if="unsupported.length" title="当前生成器未实现以下能力" type="warning" :closable="false" /><ul><li v-for="item in unsupported" :key="item">{{ item }}</li></ul><el-card v-for="entity in run?.spec?.entities || []" :key="entity.name" shadow="never"><template #header>{{ entity.label }} · {{ entity.name }}</template><el-table :data="entity.fields" size="small"><el-table-column prop="label" label="字段" /><el-table-column prop="name" label="标识" /><el-table-column prop="kind" label="类型" /></el-table></el-card><el-collapse><el-collapse-item title="原始 JSON"><pre>{{ JSON.stringify(run?.spec, null, 2) }}</pre></el-collapse-item></el-collapse></el-drawer>
    <el-drawer v-model="analysisVisible" title="真实生成的规格与架构" size="min(960px, 100vw)" append-to-body class="rnd-form"><el-select v-model="analysisPath" @change="previewAnalysis"><el-option v-for="path in analysisFiles" :key="path" :value="path" :label="path" /></el-select><img v-if="analysisImage" :src="analysisImage" alt="架构图" style="max-width:100%" /><pre v-else>{{ analysisContent }}</pre></el-drawer>
    <el-drawer v-model="logVisible" title="运行事件" size="min(640px, 100vw)" append-to-body class="rnd-form"><el-timeline><el-timeline-item v-for="event in events" :key="event.id" :timestamp="new Date(event.created_at).toLocaleString()" :type="event.level === 'error' ? 'danger' : 'primary'"><strong>{{ event.stage }} · {{ event.tool }}</strong><p>{{ event.message }}</p></el-timeline-item></el-timeline></el-drawer>
  </div>
</template>
<style scoped>
.work-area{display:grid;grid-template-columns:190px minmax(0,1fr);gap:10px;flex:1;min-height:0;min-width:0}.project-list{display:flex;flex-direction:column;overflow:hidden}.list-title{padding:12px;font-size:12px;font-weight:600;border-bottom:1px solid var(--el-border-color-lighter)}.project-item{display:flex;flex-direction:column;gap:5px;width:100%;text-align:left;min-width:0;background:none;border:0;border-left:3px solid transparent;padding:12px 10px;cursor:pointer;color:inherit}.project-item strong{max-width:100%;font-size:13px}.project-item small{color:var(--el-text-color-secondary);font-size:11px}.project-item.selected{border-left-color:var(--el-color-primary);background:var(--el-color-primary-light-9)}.conversation{display:flex;flex-direction:column;overflow:hidden}.conversation-head{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:10px 12px;border-bottom:1px solid var(--el-border-color-lighter);flex:none}.conversation-head>strong{flex:1}.model-picker{width:220px;max-width:100%}.mobile-project{display:none}.chat-history{padding:12px 16px}.conversation-status{display:flex;gap:8px;align-items:center;margin-bottom:10px;flex-wrap:wrap}.message{display:flex;gap:8px;margin:12px 0}.message.user{flex-direction:row-reverse}.avatar{width:27px;height:27px;flex:none;border-radius:8px;background:var(--el-fill-color);font-size:11px;display:grid;place-items:center}.assistant .avatar{color:var(--el-color-primary);background:var(--el-color-primary-light-9)}.bubble{padding:10px 12px;border-radius:10px;max-width:90%;min-width:0;background:var(--el-fill-color-light);overflow-wrap:anywhere}.user .bubble{background:var(--el-color-primary-light-9)}.bubble small{font-size:11px;color:var(--el-text-color-secondary)}.bubble p{margin:4px 0 0;white-space:pre-wrap;line-height:1.65}.bubble ol{padding-left:18px;margin:8px 0 0;line-height:1.6}.composer{padding:10px 12px;border-top:1px solid var(--el-border-color-lighter);display:flex;gap:8px;flex-direction:column;flex:none}.run-footer{padding:4px 0}.approval{padding:12px;background:var(--el-color-warning-light-9);margin:14px 0;border-radius:10px}.stages{margin-top:18px}.stage{display:flex;gap:10px;padding:8px 0}.stage>span{width:24px;height:24px;flex:none;border:1px solid var(--el-border-color);border-radius:50%;display:grid;place-items:center;font-size:11px}.stage strong,.stage small,.stage em{display:block}.stage small,.stage em{font-size:12px;color:var(--el-text-color-secondary);font-style:normal;margin-top:2px}.stage.ok>span{background:var(--el-color-success-light-9);border-color:var(--el-color-success);color:var(--el-color-success)}.stage.doing>span{border-color:var(--el-color-primary);color:var(--el-color-primary)}.stage.bad>span{border-color:var(--el-color-danger);color:var(--el-color-danger)}
@container(max-width:720px){.work-area{grid-template-columns:minmax(0,1fr)}.project-list{display:none}.mobile-project{display:block;width:140px;max-width:100%}.conversation-head{gap:6px}.conversation-head>strong{flex-basis:100%}.model-picker{flex:1;min-width:130px}.bubble{max-width:95%}.chat-history{padding:8px}}
</style>
