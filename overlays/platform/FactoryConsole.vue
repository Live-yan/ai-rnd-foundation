<script setup lang="ts">
import { computed, onMounted, onUnmounted, onActivated, onDeactivated, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import FactoryAPI, { type FactoryProject, type FactoryRun, type ProviderProfile, type RunEvent, type ToolchainItem } from "@/api/module_factory";

const router = useRouter();
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
  <div v-loading="busy" class="factory-page">
    <section class="hero">
      <div><span>AI SOFTWARE R&D · FASTAPIADMIN</span><h1>从需求澄清到可交付工程</h1><p>先问清楚，再规划、生成、验证和交付。每个组件都有运行阶段与真实状态。</p></div>
      <div class="hero-actions"><el-button @click="router.push('/factory-providers')">模型供应商</el-button><el-button @click="router.push('/factory-toolchain')">工具链中心</el-button><el-button type="primary" @click="createVisible = true">新建项目</el-button></div>
    </section>

    <el-alert v-if="!providers.length" title="请先到“模型供应商”配置并测试一个真实模型，再开始需求分析。" type="info" :closable="false" />
    <el-alert v-if="connectionError" :title="connectionError" type="warning" :closable="false" />
    <section class="stats">
      <el-card shadow="never"><small>项目</small><strong>{{ projects.length }}</strong></el-card>
      <el-card shadow="never"><small>模型供应商</small><strong>{{ providers.filter(x => x.enabled).length }}</strong></el-card>
      <el-card shadow="never"><small>工具链</small><strong>{{ tools.filter(x => x.configured).length }}/{{ tools.length }}</strong></el-card>
      <el-card shadow="never"><small>本次阶段</small><strong>{{ finishedStages }}/{{ stages.length }}</strong></el-card>
    </section>

    <section class="workspace">
      <el-card shadow="never" class="projects">
        <template #header><div class="section-title"><b>研发项目</b><el-button text @click="createVisible = true">＋</el-button></div></template>
        <el-scrollbar height="610px">
          <button v-for="item in projects" :key="item.id" class="project-item" :class="{ active: item.id === project?.id }" @click="chooseProject(item)">
            <span>{{ item.title.slice(0, 1) }}</span><div><b>{{ item.title }}</b><small>{{ item.clarification_status }}</small></div><el-tag size="small" :type="item.clarification_status === 'READY' ? 'success' : 'warning'">{{ item.clarification_status === 'READY' ? '已澄清' : '待确认' }}</el-tag>
          </button>
          <el-empty v-if="!projects.length" description="创建第一个研发项目" />
        </el-scrollbar>
      </el-card>

      <el-card shadow="never" class="chat">
        <template #header><div class="section-title"><div><b>需求对话</b><small>{{ project?.title || '未选择项目' }}</small></div><el-select v-model="providerId" placeholder="选择模型" style="width:240px"><el-option v-for="item in providers.filter(x => x.enabled)" :key="item.id" :value="item.id" :label="`${item.name} · ${item.model}`" /></el-select></div></template>
        <template v-if="project">
          <el-alert :type="clarificationReady ? 'success' : 'info'" :title="clarificationReady ? 'AI 已确认需求可进入规划' : '不会直接生成代码：先完成需求澄清'" :closable="false" show-icon />
          <el-scrollbar height="360px" class="messages">
            <div v-for="(message, index) in project.messages" :key="index" class="message" :class="message.role">
              <span>{{ message.role === 'assistant' ? 'AI' : '我' }}</span><div><small>{{ message.role === 'assistant' ? '需求分析 Agent' : '需求方' }}</small><p>{{ message.content }}</p><ol v-if="message.questions?.length"><li v-for="q in message.questions" :key="q">{{ q }}</li></ol></div>
            </div>
          </el-scrollbar>
          <div v-if="questions.length" class="questions"><b>还需要确认 {{ questions.length }} 个阻塞问题</b><ol><li v-for="q in questions" :key="q">{{ q }}</li></ol></div>
          <el-input v-model="answer" type="textarea" :rows="3" maxlength="16000" show-word-limit placeholder="逐项回答阻塞问题，或补充新的业务约束" />
          <div class="composer"><el-button @click="clarify">重新分析</el-button><el-button type="primary" :disabled="!answer.trim()" @click="sendAnswer">发送并继续澄清</el-button></div>
        </template>
        <el-empty v-else description="选择或创建一个项目" />
      </el-card>

      <el-card shadow="never" class="pipeline">
        <template #header><div class="section-title"><b>研发流水线</b><el-button text :disabled="!run" @click="logVisible = true">运行日志</el-button></div></template>
        <el-button :disabled="!run?.spec" @click="showAnalysis">审阅 OpenSpec / C4 / ER / 部署图</el-button>
        <div class="mode-row"><el-radio-group v-model="mode" size="small" @change="setMode"><el-radio-button value="full">完整模式</el-radio-button><el-radio-button value="core">基础模式</el-radio-button></el-radio-group><el-select v-model="sandbox" size="small" :disabled="mode === 'full'"><el-option label="CubeSandbox" value="cube" /><el-option label="Docker" value="docker" /><el-option label="静态" value="static" /></el-select><el-checkbox v-model="useSerena" :disabled="mode === 'full'">Serena</el-checkbox><el-checkbox v-model="provisionCoder" :disabled="mode === 'full'">Coder</el-checkbox></div>
        <el-alert v-if="mode === 'full' && !fullReady" type="warning" :closable="false" title="完整模式缺少组件配置；后端也会硬门禁阻止启动" />
        <div v-for="([key, name, tool], index) in stages" :key="key" class="stage" :class="stageState(key)"><span>{{ index + 1 }}</span><div><b>{{ name }}</b><small>{{ tool }}</small><em>{{ run?.stage_details?.[key]?.status || (key === 'clarify' ? project?.clarification_status : 'WAITING') }}</em></div></div>
        <el-button type="primary" size="large" class="start" :disabled="!clarificationReady || !providerId || (mode === 'full' && !fullReady)" @click="startRun">启动研发流水线</el-button>
        <el-select v-if="runs.length" :model-value="run?.id" class="history" placeholder="历史运行" @change="selectRun"><el-option v-for="item in runs" :key="item.id" :value="item.id" :label="`${item.id.slice(0, 8)} · ${item.status}`" /></el-select>
      </el-card>
    </section>

    <el-card v-if="run" shadow="never" class="run-card">
      <div class="run-head"><div><small>RUN {{ run.id.slice(0, 8) }}</small><h3>{{ run.spec?.title || project?.title }}</h3></div><div><el-button :disabled="!run.spec" @click="specVisible = true">查看规格</el-button><el-button v-if="run.checks?.coder?.url" @click="openCoder">打开 Coder</el-button><el-button v-if="run.download_available" type="success" @click="download">下载源码 ZIP</el-button></div></div>
      <el-descriptions :column="4" border size="small"><el-descriptions-item label="状态">{{ run.status }}</el-descriptions-item><el-descriptions-item label="模式">{{ run.pipeline_mode }}</el-descriptions-item><el-descriptions-item label="沙箱">{{ run.sandbox }}</el-descriptions-item><el-descriptions-item label="SHA">{{ run.artifact_sha256?.slice(0, 18) || '—' }}</el-descriptions-item></el-descriptions>
      <el-alert v-if="run.download_available" type="info" :closable="false" title="工具链结束不等于生产验收：请查看质量报告中的实际检查范围和未执行项。" />
      <el-descriptions v-if="run.checks" :column="3" size="small" border><el-descriptions-item label="全栈业务验收">{{ run.checks.full_stack }}</el-descriptions-item><el-descriptions-item label="前端构建">{{ run.checks.frontend_build }}</el-descriptions-item><el-descriptions-item label="Coder 源码">{{ run.checks.coder?.source_import || '未请求' }}</el-descriptions-item></el-descriptions>
      <el-alert v-if="run.error" type="error" :title="run.error" :closable="false" show-icon />
      <div v-if="run.status === 'AWAITING_APPROVAL'" class="approval"><div><b>人工确认门禁</b><p>检查结构化规格、OpenSpec/C4、验收标准和未支持项后再继续。</p></div><div><el-checkbox v-model="acceptLimitations">已阅读并接受未实现项</el-checkbox><el-button @click="decide(false)">拒绝</el-button><el-button type="primary" @click="decide(true)">批准并继续</el-button></div></div>
    </el-card>

    <el-dialog v-model="createVisible" title="创建研发项目" width="720px"><el-form label-position="top"><el-form-item label="项目名称"><el-input v-model="title" /></el-form-item><el-form-item label="软件需求"><el-input v-model="requirement" type="textarea" :rows="8" maxlength="16000" show-word-limit /></el-form-item><el-alert type="info" :closable="false" title="创建后先发送给真实 AI 做需求澄清；未通过 READY 门禁不会生成代码。" /></el-form><template #footer><el-button @click="createVisible = false">取消</el-button><el-button type="primary" :disabled="!providerId || !title.trim() || requirement.trim().length < 5" @click="createProject">创建并开始 AI 分析</el-button></template></el-dialog>
    <el-drawer v-model="specVisible" title="需求与数据规格审阅" size="65%">
      <h2>{{ run?.spec?.title }}</h2><p>{{ run?.spec?.summary }}</p>
      <el-card v-if="run?.clarification" shadow="never"><template #header>本次运行冻结的需求与验收标准</template><p>{{ run.clarification.understanding }}</p><ol><li v-for="item in run.clarification.acceptance_criteria" :key="item">{{ item }}</li></ol><p v-for="risk in run.clarification.risks" :key="risk">风险：{{ risk }}</p></el-card>
      <el-alert v-if="unsupported.length" type="warning" :closable="false" title="以下能力未由当前确定性生成器完成" /><ul><li v-for="item in unsupported" :key="item">{{ item }}</li></ul>
      <el-card v-for="entity in run?.spec?.entities || []" :key="entity.name" shadow="never" style="margin:12px 0"><template #header><b>{{ entity.label }}</b> · {{ entity.name }}</template><el-table :data="entity.fields" size="small"><el-table-column prop="label" label="字段" /><el-table-column prop="name" label="标识" /><el-table-column prop="kind" label="类型" /><el-table-column label="必填" width="65"><template #default="scope">{{ scope.row.required ? '是' : '否' }}</template></el-table-column><el-table-column prop="references" label="关联对象" /></el-table></el-card>
      <el-collapse><el-collapse-item title="开发者：查看原始 JSON" name="raw"><pre>{{ JSON.stringify(run?.spec, null, 2) }}</pre></el-collapse-item></el-collapse>
    </el-drawer>
    <el-drawer v-model="analysisVisible" title="规格与架构产物（真实生成内容）" size="75%">
      <el-select v-model="analysisPath" placeholder="选择产物" style="width:100%" @change="previewAnalysis"><el-option v-for="path in analysisFiles" :key="path" :value="path" :label="path" /></el-select>
      <img v-if="analysisImage" :src="analysisImage" alt="生成的架构图" style="max-width:100%;margin-top:16px" />
      <pre v-else>{{ analysisContent }}</pre>
    </el-drawer>
    <el-drawer v-model="logVisible" title="Temporal / Toolchain 运行日志" size="50%"><el-timeline><el-timeline-item v-for="event in events" :key="event.id" :timestamp="new Date(event.created_at).toLocaleString()" :type="event.level === 'error' ? 'danger' : 'primary'"><b>{{ event.stage || 'event' }} · {{ event.tool || 'platform' }}</b><p>{{ event.message }}</p></el-timeline-item></el-timeline><el-empty v-if="!events.length" description="暂无事件" /></el-drawer>
  </div>
</template>

<style scoped>
.factory-page{padding:20px;min-height:100%;background:var(--el-bg-color-page)}.hero{display:flex;justify-content:space-between;align-items:flex-end;gap:20px;padding:25px 28px;border-radius:16px;background:linear-gradient(120deg,#111a2d,#173969 55%,#245d91);color:#fff}.hero span{font-size:11px;letter-spacing:1.5px}.hero h1{margin:9px 0 6px;font-size:28px}.hero p{margin:0;color:#ffffffc9}.hero-actions{display:flex;gap:8px;white-space:nowrap}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:14px 0}.stats :deep(.el-card__body){display:grid;gap:4px}.stats small{color:var(--el-text-color-secondary)}.stats strong{font-size:22px}.workspace{display:grid;grid-template-columns:255px minmax(480px,1.2fr) minmax(350px,.9fr);gap:12px}.section-title,.run-head{display:flex;align-items:center;justify-content:space-between;gap:12px}.section-title small{display:block;margin-top:3px;color:var(--el-text-color-secondary)}.project-item{width:100%;display:grid;grid-template-columns:34px 1fr auto;gap:8px;align-items:center;padding:10px;border:1px solid transparent;border-radius:10px;background:transparent;text-align:left;color:inherit;cursor:pointer}.project-item:hover,.project-item.active{background:var(--el-fill-color-light)}.project-item.active{border-color:var(--el-color-primary-light-7)}.project-item>span{display:grid;place-items:center;width:34px;height:34px;border-radius:9px;background:var(--el-color-primary);color:#fff}.project-item>div{min-width:0}.project-item b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.project-item b,.project-item small{display:block}.project-item small{margin-top:3px;color:var(--el-text-color-secondary)}.messages{margin:10px 0}.message{display:flex;gap:9px;margin:12px 0}.message.user{flex-direction:row-reverse}.message>span{flex:0 0 32px;height:32px;display:grid;place-items:center;border-radius:9px;background:var(--el-fill-color-dark);font-size:11px}.message.assistant>span{background:var(--el-color-primary);color:#fff}.message>div{max-width:86%;padding:10px 13px;border-radius:11px;background:var(--el-fill-color-light)}.message.user>div{background:var(--el-color-primary-light-9)}.message p{white-space:pre-wrap;margin:4px 0;line-height:1.6}.message small{color:var(--el-text-color-secondary)}.questions{margin:10px 0;padding:12px;border-radius:10px;background:var(--el-color-warning-light-9)}.composer{display:flex;justify-content:flex-end;gap:8px;margin-top:8px}.mode-row{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:10px}.stage{display:grid;grid-template-columns:26px 1fr;gap:8px;min-height:45px}.stage>span{width:22px;height:22px;display:grid;place-items:center;border:2px solid var(--el-border-color);border-radius:50%;font-size:10px}.stage b{font-size:13px}.stage small{margin-left:7px;color:var(--el-text-color-secondary)}.stage em{display:block;margin-top:3px;font-size:10px;color:var(--el-text-color-placeholder);font-style:normal}.stage.ok>span{background:var(--el-color-success);border-color:var(--el-color-success);color:#fff}.stage.doing>span{border-color:var(--el-color-primary);color:var(--el-color-primary)}.stage.bad>span{background:var(--el-color-danger);border-color:var(--el-color-danger);color:#fff}.start,.history{width:100%;margin-top:8px}.run-card{margin-top:12px}.run-head h3{margin:4px 0}.approval{display:flex;justify-content:space-between;gap:16px;align-items:center;margin-top:12px;padding:13px;border-radius:10px;background:var(--el-color-warning-light-9)}.approval p{margin:4px 0;color:var(--el-text-color-secondary)}.approval>div:last-child{display:flex;align-items:center;gap:8px;flex-wrap:wrap}pre{white-space:pre-wrap;overflow-wrap:anywhere;padding:14px;border-radius:8px;background:var(--el-fill-color-light)}@media(max-width:1350px){.workspace{grid-template-columns:240px 1fr}.pipeline{grid-column:1/-1}.stats{grid-template-columns:repeat(2,1fr)}}@media(max-width:800px){.factory-page{padding:10px}.hero{flex-direction:column;align-items:flex-start}.hero-actions{flex-wrap:wrap}.stats,.workspace{grid-template-columns:1fr}.pipeline{grid-column:auto}.approval{align-items:flex-start;flex-direction:column}}
</style>
