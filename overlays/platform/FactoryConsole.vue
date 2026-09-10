<script setup lang="ts">
import { computed, onMounted, onUnmounted, onActivated, onDeactivated, ref, watch, nextTick } from "vue";
import { useRouter } from "vue-router";
import { useEmbeddedViewport } from "@/api/module_factory/embedded";
import "@/api/module_factory/embedded.css";
import { ElMessage } from "element-plus";
import FactoryAPI, { type FactoryTemplate, type FactoryProject, type FactoryRun, type ProviderProfile, type RunEvent, type ToolchainItem } from "@/api/module_factory";

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
const templates = ref<FactoryTemplate[]>([]);
const templateId = ref("");
const selectedTemplate = computed(() => templates.value.find(x => x.id === templateId.value));
const templateReady = computed(() => !!selectedTemplate.value && selectedTemplate.value.available !== false);
const title = ref("");
const requirement = ref("");
const answer = ref("");
const sandbox = ref<"static" | "docker">("docker");
const validationLevel = ref<"source" | "runtime">("runtime");
const useSerena = ref(false);
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
  ["sandbox", "代码与契约检查", "static / Docker"],
  ["package", "交付打包", "SHA-256"],
  ["complete", "完成", "Temporal"],
] as const;
const defaultProvider = computed(() => providers.value.find((x) => x.is_default && x.enabled) || providers.value.find((x) => x.enabled));
const clarificationReady = computed(() => project.value?.clarification_status === "READY");
const questions = computed(() => project.value?.clarification?.questions || []);
const unsupported = computed(() => (run.value?.spec?.unsupported_features || []) as string[]);
const finishedStages = computed(() => stages.filter(([key]) => stageState(key) === "ok").length);
const runActive = computed(() => !!run.value && !["READY", "FAILED", "REJECTED"].includes(run.value.status));
const operationError = ref("");
const operation = ref("");
const chatHistory = ref<HTMLElement | null>(null);
const followLatest = ref(true);
function trackScroll() {
  const node = chatHistory.value;
  if (node) followLatest.value = node.scrollHeight - node.scrollTop - node.clientHeight < 80;
}
async function scrollLatest() {
  followLatest.value = true;
  await nextTick();
  if (chatHistory.value) chatHistory.value.scrollTop = chatHistory.value.scrollHeight;
}
watch(() => [events.value.length, project.value?.messages.length, run.value?.status, busy.value], async () => {
  if (followLatest.value) await scrollLatest();
});
const questionAnswers = ref<Record<string, string>>({});
const questionChoices = computed(() => new Map((project.value?.clarification?.question_choices || []).map(choice => [choice.question, choice])));
const allRecommended = computed(() => questions.value.length > 0 && questions.value.every(q => questionChoices.value.get(q)?.recommended));
function useRecommendations() {
  if (busy.value || !allRecommended.value) return;
  for (const q of questions.value) questionAnswers.value[q] = questionChoices.value.get(q)!.recommended;
}
const runLabel = computed(() => run.value?.status === "READY"
  ? deliveryLabel(run.value.checks)
  : ({ AWAITING_APPROVAL: "等待你确认交付范围", FAILED: "生成或验收失败", REJECTED: "已拒绝范围，请修改需求", RUNNING: "正在生成与验收", PENDING: "等待开始", QUEUED: "排队中" } as Record<string, string>)[run.value?.status || ""] || (run.value ? "正在处理" : "尚未启动"));
function deliveryLabel(checks: Record<string, any> | null | undefined) {
  if (checks?.quality_level === "generated_crud_stack_verified" && checks.full_stack === "passed") return "约定的基础管理功能已通过运行验收";
  if (checks?.quality_level === "scaffold_ready") return "仅完成源码检查 · 尚未验证可运行";
  return "流程已完成 · 请查看实际验收结果";
}
async function submitQuestions() {
  if (!questions.value.every(q => questionAnswers.value[q]?.trim())) return;
  answer.value = questions.value.map((q, i) => `${i + 1}. ${q}\n回答：${questionAnswers.value[q]!.trim()}`).join("\n\n");
  await sendAnswer();
}

function errorText(error: any) {
  return error?.response?.data?.msg || error?.response?.data?.detail || error?.message || String(error);
}
async function guarded<T>(fn: () => Promise<T>) {
  busy.value = true;
  operationError.value = "";
  try { return await fn(); }
  catch (error: any) { operationError.value = errorText(error); ElMessage.error(operationError.value); }
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
async function refreshBase() {
  [providers.value, tools.value, projects.value, templates.value] = await Promise.all([
    FactoryAPI.listProviders(), FactoryAPI.toolchain(), FactoryAPI.listProjects(), FactoryAPI.listTemplates(),
  ]);
  if (!providerId.value) providerId.value = defaultProvider.value?.id || null;
  if (!templateId.value) templateId.value = templates.value.find(x => x.available !== false)?.id || "";
}
async function chooseProject(item: FactoryProject) {
  if (busy.value) return;
  followLatest.value = true;
  const ticket = ++selection;
  run.value = null; events.value = []; runs.value = []; questionAnswers.value = {}; operation.value = "";
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
  if (busy.value || !providerId.value || !templateReady.value || !title.value.trim() || requirement.value.trim().length < 5) return;
  await guarded(async () => {
    ++selection; run.value = null; runs.value = []; events.value = []; acceptLimitations.value = false;
    project.value = await FactoryAPI.createProject({ title: title.value.trim(), requirement: requirement.value.trim(), template_id: templateId.value });
    createVisible.value = false;
    await refreshBase();
    if (!providerId.value) { ElMessage.warning("项目已创建，请先配置模型供应商。不会退回固定 Demo。"); return; }
    operation.value = "正在分析需求，等待模型返回结构化问题";
    project.value = await FactoryAPI.clarify(project.value.id, providerId.value);
    runs.value = []; run.value = null; events.value = [];
  });
}
async function clarify() {
  if (!project.value) return;
  if (runActive.value) return;
  operation.value = "正在重新分析需求";
  await guarded(async () => { project.value = await FactoryAPI.clarify(project.value!.id, providerId.value); questionAnswers.value = {}; await refreshBase(); });
}
async function sendAnswer() {
  if (!project.value || !answer.value.trim() || runActive.value) return;
  operation.value = "正在核对你的回答与验收条件";
  await guarded(async () => {
    project.value = await FactoryAPI.addMessage(project.value!.id, answer.value.trim());
    answer.value = "";
    project.value = await FactoryAPI.clarify(project.value!.id, providerId.value);
    questionAnswers.value = {};
    await refreshBase();
  });
}
async function startRun() {
  if (!project.value || !clarificationReady.value || !providerId.value || runActive.value || busy.value) return;
  operation.value = "正在提交需求快照";
  await guarded(async () => {
    run.value = await FactoryAPI.startRun(project.value!.id, {
      provider_id: providerId.value,
      expected_revision: project.value!.revision,
      pipeline_mode: "core",
      sandbox: validationLevel.value === "runtime" ? "docker" : sandbox.value,
      validation_level: validationLevel.value,
      use_serena: useSerena.value,
      provision_coder: false,
      idempotency_key: crypto.randomUUID(),
    });
    runs.value = await FactoryAPI.listRuns(project.value!.id);
    events.value = [];
  });
}
async function chooseRun(item: FactoryRun) {
  const ticket = ++selection;
  const [latest, history] = await Promise.all([FactoryAPI.getRun(item.id), FactoryAPI.events(item.id, 0)]);
  if (ticket !== selection) return;
  acceptLimitations.value = false;
  run.value = latest;
  events.value = history;
}
function selectRun(id: string) { const item = runs.value.find((x) => x.id === id); if (item) void chooseRun(item); }
async function decide(approve: boolean) {
  if (!run.value?.spec_digest || busy.value) return;
  operation.value = "正在提交你的审批决定";
  if (approve && unsupported.value.length && !acceptLimitations.value) { ElMessage.warning("请先阅读并接受当前确定性生成器未实现的能力。"); return; }
  await guarded(async () => {
    run.value = await FactoryAPI.decide(run.value!.id, {
      spec_digest: run.value!.spec_digest, approve, accept_limitations: acceptLimitations.value,
    });
  });
}
async function download() {
  if (!run.value || busy.value) return;
  operation.value = "交付包 · 正在下载已记录哈希的源码";
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
  await guarded(refreshBase);
  const first = projects.value[0];
  if (first) await chooseProject(first);
  active = true; void poll();
});
onActivated(() => { active = true; if (timer) clearTimeout(timer); void refreshBase().catch(() => {}); void poll(); });
onDeactivated(stopPolling);
onUnmounted(() => { stopPolling(); ++previewSelection; if (analysisImage.value) URL.revokeObjectURL(analysisImage.value); });
</script>

<template>
  <div ref="panel" :aria-busy="busy" class="rnd-embedded factory-page" :style="{ height: panelHeight }">
    <header class="rnd-toolbar">
      <div><h1>软件交付工作台 <el-tag size="small" effect="plain">{{ projects.length }} 个项目</el-tag></h1><p>选模板 → 说需求 → 确认范围 → 生成验收 → 下载启动</p></div>
      <div class="rnd-actions"><el-button size="small" @click="router.push('/factory-providers')">模型配置</el-button><el-button size="small" @click="pipelineVisible = true">高级设置与进度</el-button><el-button type="primary" size="small" @click="createVisible = true">新建项目</el-button></div>
    </header>
    <div v-if="!providers.some(x => x.enabled)" class="rnd-note" role="alert">还没有可用模型，请先<el-button link type="primary" @click="router.push('/factory-providers')">配置模型</el-button>。</div><div v-if="!templates.length" class="rnd-note" role="alert">未找到模板，请检查模板服务或联系管理员。</div>
    <div v-if="connectionError" class="rnd-note rnd-error">{{ connectionError }}</div>
    <main class="work-area">
      <aside class="rnd-panel project-list"><div class="list-title">我的项目</div><div class="rnd-scroll"><button v-for="item in projects" :key="item.id" class="project-item" :class="{ selected: project?.id === item.id }" @click="chooseProject(item)"><strong class="rnd-ellipsis">{{ item.title }}</strong><small>{{ item.clarification_status === 'READY' ? '需求已澄清' : '待分析 / 待回答' }}</small></button><el-empty v-if="!projects.length" :image-size="50" description="还没有项目" /></div></aside>
      <section class="rnd-panel conversation">
        <div class="conversation-head"><strong class="rnd-ellipsis">{{ project?.title || '选择或创建项目' }}</strong><el-select class="mobile-project" :model-value="project?.id" size="small" placeholder="切换项目" @change="id => { const p = projects.find(x => x.id === id); if (p) chooseProject(p); }"><el-option v-for="p in projects" :key="p.id" :value="p.id" :label="p.title" /></el-select></div>
        <div ref="chatHistory" class="rnd-scroll chat-history" aria-label="需求与运行对话" @scroll="trackScroll">
          <div v-if="project" class="conversation-status"><el-tag size="small" :type="clarificationReady ? 'success' : 'warning'">{{ clarificationReady ? '可进入规划' : '澄清中' }}</el-tag><span class="rnd-muted">{{ questions.length ? `${questions.length} 个问题等待回答` : '新增需求会重新经过 AI 分析' }}</span></div>
          <article v-for="(message, i) in project?.messages || []" :key="i" class="message" :class="message.role"><div class="avatar">{{ message.role === 'assistant' ? 'AI' : '我' }}</div><div class="bubble"><small>{{ message.role === 'assistant' ? '需求分析' : '需求方' }}</small><p>{{ message.content }}</p><ol v-if="message.questions?.length"><li v-for="q in message.questions" :key="q">{{ q }}</li></ol></div></article>
          <article v-if="project && questions.length && !runActive" class="message assistant">
            <div class="avatar">计划</div><div class="bubble plan-card">
              <strong>逐项确认需求</strong>
              <div class="rnd-actions"><el-button :disabled="busy || !allRecommended" @click="useRecommendations">全部采用 AI 推荐</el-button><small>会替换当前各题答案；可修改，确认后再提交。</small></div>
              <p v-if="!allRecommended" class="rnd-muted">部分问题尚无推荐选项，请点“重新分析”获取；不会自动猜测你的选择。</p>
              <fieldset v-for="(q, index) in questions" :key="q" class="question-field" :disabled="busy">
                <legend>{{ index + 1 }}. {{ q }}</legend>
                <template v-if="questionChoices.get(q)">
                  <div class="question-options" role="group" :aria-label="`第 ${index + 1} 题候选答案`">
                    <button v-for="option in questionChoices.get(q)!.options" :key="option" type="button" class="question-option" :class="{ chosen: questionAnswers[q] === option }" :aria-pressed="questionAnswers[q] === option" :disabled="busy" @click="questionAnswers[q] = option">
                      <strong v-if="option === questionChoices.get(q)!.recommended">AI 推荐 · </strong>{{ option }}
                    </button>
                  </div>
                  <p class="rnd-muted">推荐理由：{{ questionChoices.get(q)!.reason }}</p>
                </template>
                <label :for="`question-answer-${index}`">你的回答（可自由修改）</label>
                <el-input :id="`question-answer-${index}`" v-model="questionAnswers[q]" type="textarea" :autosize="{ minRows: 2, maxRows: 10 }" :aria-label="q" :disabled="busy" maxlength="4000" />
              </fieldset>
              <el-button type="primary" :disabled="busy || !providerId || !questions.every(q => questionAnswers[q]?.trim())" @click="submitQuestions">提交回答并更新计划</el-button>
            </div>
          </article>
          <article v-if="clarificationReady && !runActive" class="message assistant"><div class="avatar">计划</div><div class="bubble plan-card"><strong>需求已澄清，确认执行范围</strong><p>生成模板支持的基础管理页面和接口，复杂业务流程、库存事务和复杂权限需单独实现。下一步会列出具体交付范围，请确认后再生成。</p><ul><li v-for="criterion in project?.clarification?.acceptance_criteria || []" :key="criterion">{{ criterion }}</li></ul><div class="rnd-actions"><el-button :disabled="busy" @click="pipelineVisible = true">调整验收方式</el-button><el-button type="primary" :disabled="busy || !providerId" @click="startRun">准备交付范围</el-button></div></div></article>
          <details v-if="run" class="tool-stream" aria-label="实际工具执行事件"><summary>生成与验收进度：{{ runLabel }} · 查看真实工具日志</summary><header><strong>{{ runLabel }}</strong><small>Run {{ run.id.slice(0, 8) }} · 每 2.5 秒同步真实事件</small></header><details v-for="event in events" :key="`${run.id}-${event.id}`" class="tool-event" :class="{ 'rnd-error': event.level === 'error' }"><summary><strong>{{ event.tool || '流水线' }}</strong><span>{{ event.message }}</span><time :datetime="event.created_at">{{ new Date(event.created_at).toLocaleTimeString() }}</time></summary><p>阶段：{{ event.stage || '未指定' }} · {{ new Date(event.created_at).toLocaleString() }}</p><p>{{ event.message }}</p></details></details>
          <article v-if="run?.status === 'AWAITING_APPROVAL'" class="message assistant"><div class="avatar">审批</div><div class="bubble plan-card"><strong>请确认本次交付范围</strong><p>{{ run.spec?.summary }}</p><ul><li v-for="entity in run.spec?.entities || []" :key="entity.name"><strong>{{ entity.label || entity.name }}</strong>：{{ entity.fields.map((field: any) => field.label || field.name).join('、') }}</li></ul><ul><li v-for="criterion in run.spec?.acceptance_criteria || run.clarification?.acceptance_criteria || []" :key="criterion">{{ criterion }}</li></ul><div class="rnd-actions"><el-button @click="specVisible = true">数据结构</el-button><el-button @click="showAnalysis">规格与架构</el-button></div><template v-if="unsupported.length"><h4>以下能力不会被本次生成实现</h4><ul><li v-for="item in unsupported" :key="item">{{ item }}</li></ul><el-checkbox v-model="acceptLimitations" :disabled="busy">我接受以上未支持项，仅验收列出的交付范围</el-checkbox></template><div class="rnd-actions"><el-button :disabled="busy" @click="decide(false)">拒绝计划，返回修改需求</el-button><el-button type="primary" :disabled="busy || (!!unsupported.length && !acceptLimitations)" @click="decide(true)">确认范围，开始生成</el-button></div></div></article>
          <article v-if="run?.checks && run.status === 'READY'" class="message assistant"><div class="avatar">交付</div><div class="bubble plan-card"><strong>{{ runLabel }}</strong><p>全栈：{{ run.checks.full_stack || 'not_run' }} · 前端构建：{{ run.checks.frontend_build || 'not_run' }}<span v-if="run.checks.coder"> · 历史源码导入：{{ run.checks.coder.source_import || '未执行' }}</span></p><p>未支持业务：{{ unsupported.length }} 项。验收覆盖本次约定的基础管理功能，尚未通过生产环境验收。</p><p v-if="run.checks.quality_level === 'generated_crud_stack_verified' && run.checks.full_stack === 'passed'">下载并解压后：Windows 双击「启动.cmd」，Mac / Linux 双击「启动.command」。首次需要 Docker Desktop 和联网，请阅读包内说明。</p><p v-else>此包尚未验证可运行，请先阅读质量报告与包内说明。</p><details><summary>查看完整质量报告</summary><pre>{{ JSON.stringify(run.checks, null, 2) }}</pre></details><div class="rnd-actions"><el-button v-if="run.download_available" type="primary" :disabled="busy" @click="download">下载交付包</el-button><el-button @click="specVisible = true">查看未实现项</el-button></div></div></article>
          <p v-if="busy" role="status" class="operation-status">{{ operation || '正在执行操作，请稍候…' }}</p><p v-if="operationError || run?.error" role="alert" class="rnd-error">{{ operationError || run?.error }}</p>
          <el-empty v-if="!project" :image-size="72" description="描述目标，AI 会先提问并确认范围" />
        </div>
        <el-button v-if="!followLatest" size="small" @click="scrollLatest">查看最新进度 ↓</el-button>
        <div class="composer"><el-input v-model="answer" type="textarea" :rows="2" :disabled="!project || busy || runActive" maxlength="16000" placeholder="回答 AI 的问题，或补充需求…" aria-label="补充需求" /><div class="rnd-footer"><span class="rnd-muted">先问清楚，再生成</span><div class="rnd-actions"><el-button size="small" :disabled="!project || !providerId || busy || runActive" @click="clarify">重新分析</el-button><el-button type="primary" size="small" :disabled="!project || !providerId || !answer.trim() || busy || runActive" @click="sendAnswer">发送并分析</el-button></div></div></div>
      </section>
    </main>
    <footer class="rnd-footer run-footer"><div class="rnd-actions"><el-tag size="small" :type="run?.status === 'FAILED' ? 'danger' : run?.status === 'READY' ? 'success' : 'info'">{{ run ? runLabel : (clarificationReady ? '需求已就绪' : '尚未启动') }}</el-tag><el-button v-if="run" size="small" @click="runVisible = true">运行详情</el-button><el-button v-if="run?.status === 'AWAITING_APPROVAL'" type="warning" size="small" @click="runVisible = true">审阅并批准</el-button><el-button v-if="run?.download_available" type="success" size="small" @click="download">下载交付包</el-button></div><div class="rnd-actions"><el-tag size="small" effect="plain">{{ validationLevel === 'runtime' ? '运行验收' : '仅源码检查' }}</el-tag><el-button size="small" @click="pipelineVisible = true">运行设置</el-button><el-button size="small" type="primary" :disabled="busy || runActive || !clarificationReady || !providerId" @click="startRun">准备生成</el-button></div></footer>
    <el-drawer v-model="pipelineVisible" title="高级设置与真实进度" size="min(480px, 100vw)" append-to-body class="rnd-form"><el-form label-position="top"><el-form-item label="分析需求的模型"><el-select v-model="providerId"  aria-label="分析需求的模型" placeholder="选择模型" class="model-picker"><el-option v-for="item in providers.filter(x => x.enabled)" :key="item.id" :value="item.id" :label="`${item.name} · ${item.model}`" /></el-select></el-form-item><el-form-item label="验收方式"><el-select v-model="validationLevel" aria-label="验收方式"><el-option label="实际启动前后端并验收（推荐）" value="runtime" /><el-option label="仅检查源码（不验证可运行）" value="source" /></el-select></el-form-item><el-alert :title="validationLevel === 'runtime' ? '服务器需要 Docker 和联网能力，未通过实际运行检查不会标为可运行。' : '仅源码检查：不会启动前后端，不能证明交付包可运行。'" :type="validationLevel === 'runtime' ? 'info' : 'warning'" :closable="false" /><details><summary>工具与源码检查选项</summary><el-form-item v-if="validationLevel === 'source'" label="源码检查环境"><el-select v-model="sandbox"><el-option label="静态检查" value="static" /><el-option label="Docker" value="docker" /></el-select></el-form-item><el-checkbox v-model="useSerena">使用 Serena 模板上下文</el-checkbox><el-button @click="router.push('/factory-toolchain'); pipelineVisible = false">配置工具组件</el-button></details></el-form><div class="stages"><div v-for="([key, name, tool], i) in stages" :key="key" class="stage" :class="stageState(key)"><span>{{ i + 1 }}</span><div><strong>{{ name }}</strong><small>{{ tool }}</small><em>{{ run?.stage_details?.[key]?.status || 'WAITING' }}</em></div></div></div></el-drawer>
    <el-drawer v-model="runVisible" title="当前运行与交付" size="min(680px, 100vw)" append-to-body class="rnd-form"><template v-if="run"><el-select :model-value="run.id" @change="selectRun"><el-option v-for="item in runs" :key="item.id" :value="item.id" :label="`${item.id.slice(0, 8)} · ${item.status}`" /></el-select><h3>{{ run.spec?.title || project?.title }}</h3><div class="rnd-actions"><el-button @click="specVisible = true" :disabled="!run.spec">规格</el-button><el-button @click="showAnalysis" :disabled="!run.spec">架构与文档</el-button><el-button @click="logVisible = true">日志</el-button></div><el-alert v-if="run.error" :title="run.error" type="error" :closable="false" /><div v-if="run.status === 'AWAITING_APPROVAL'" class="approval"><p>请先审阅规格、架构和未支持项，再批准本次需求快照。</p><el-checkbox v-model="acceptLimitations">已阅读并接受未实现项</el-checkbox><div class="rnd-actions"><el-button @click="decide(false)">拒绝</el-button><el-button type="primary" :disabled="busy || (!!unsupported.length && !acceptLimitations)" @click="decide(true)">确认范围并继续</el-button></div></div><el-descriptions v-if="run.checks" :column="1" border size="small"><el-descriptions-item label="产品全栈">{{ run.checks.full_stack }}</el-descriptions-item><el-descriptions-item label="前端构建">{{ run.checks.frontend_build }}</el-descriptions-item><el-descriptions-item v-if="run.checks.coder" label="历史源码导入">{{ run.checks.coder.source_import || '未执行' }}</el-descriptions-item></el-descriptions><p class="rnd-muted">流水线完成不代表任意业务或生产安全已验收，未执行项保留在质量报告。</p></template></el-drawer>
    <el-dialog v-model="createVisible" title="选择模板，描述你的软件" width="min(680px, 94vw)" append-to-body class="rnd-form"><el-form label-position="top"><el-form-item label="1. 选择模板"><el-select v-model="templateId" aria-label="选择模板" placeholder="选择可用模板"><el-option v-for="item in templates" :key="item.id" :value="item.id" :label="`${item.name}${item.available === false ? '（未就绪）' : ''}`" :disabled="item.available === false" /></el-select><p v-for="item in templates.filter(x => x.available === false)" :key="item.id" class="rnd-muted">{{ item.name }}：{{ item.reason || item.status || '尚未安装或适配，暂不可生成' }}</p></el-form-item><p v-if="selectedTemplate">{{ selectedTemplate.description }}<span v-if="selectedTemplate.suitable_for"> 适合：{{ Array.isArray(selectedTemplate.suitable_for) ? selectedTemplate.suitable_for.join('、') : selectedTemplate.suitable_for }}</span></p><el-form-item label="2. 软件名称"><el-input v-model="title" aria-label="软件名称" placeholder="例如：门店客户管理" maxlength="100" /></el-form-item><el-form-item label="3. 你希望解决什么问题"><el-input v-model="requirement" aria-label="软件需求" type="textarea" :rows="6" maxlength="16000" show-word-limit placeholder="告诉我们谁会使用、管理什么数据、希望如何操作，以及怎样算完成。" /><el-button v-if="selectedTemplate?.example_requirement" link type="primary" @click="requirement = selectedTemplate.example_requirement || ''">填入模板示例（可修改）</el-button></el-form-item><el-alert v-if="!providerId" title="请先配置并选择模型，再分析需求。" type="warning" :closable="false" /><el-button v-if="!providerId" @click="router.push('/factory-providers')">去配置模型</el-button><el-alert title="创建后先补充关键问题，确认范围后才生成。" type="info" :closable="false" /></el-form><template #footer><el-button @click="createVisible = false">取消</el-button><el-button type="primary" :loading="busy" :disabled="busy || !templateReady || !providerId || !title.trim() || requirement.trim().length < 5" @click="createProject">创建并分析需求</el-button></template></el-dialog>
    <el-drawer v-model="specVisible" title="需求规格" size="min(760px, 100vw)" append-to-body class="rnd-form"><h3>{{ run?.spec?.title }}</h3><p>{{ run?.spec?.summary }}</p><el-alert v-if="unsupported.length" title="当前生成器未实现以下能力" type="warning" :closable="false" /><ul><li v-for="item in unsupported" :key="item">{{ item }}</li></ul><el-card v-for="entity in run?.spec?.entities || []" :key="entity.name" shadow="never"><template #header>{{ entity.label }} · {{ entity.name }}</template><el-table :data="entity.fields" size="small"><el-table-column prop="label" label="字段" /><el-table-column prop="name" label="标识" /><el-table-column prop="kind" label="类型" /></el-table></el-card><el-collapse><el-collapse-item title="原始 JSON"><pre>{{ JSON.stringify(run?.spec, null, 2) }}</pre></el-collapse-item></el-collapse></el-drawer>
    <el-drawer v-model="analysisVisible" title="真实生成的规格与架构" size="min(960px, 100vw)" append-to-body class="rnd-form"><el-select v-model="analysisPath" @change="previewAnalysis"><el-option v-for="path in analysisFiles" :key="path" :value="path" :label="path" /></el-select><img v-if="analysisImage" :src="analysisImage" alt="架构图" style="max-width:100%" /><pre v-else>{{ analysisContent }}</pre></el-drawer>
    <el-drawer v-model="logVisible" title="运行事件" size="min(640px, 100vw)" append-to-body class="rnd-form"><el-timeline><el-timeline-item v-for="event in events" :key="event.id" :timestamp="new Date(event.created_at).toLocaleString()" :type="event.level === 'error' ? 'danger' : 'primary'"><strong>{{ event.stage }} · {{ event.tool }}</strong><p>{{ event.message }}</p></el-timeline-item></el-timeline></el-drawer>
  </div>
</template>
<style scoped>
.work-area{display:grid;grid-template-columns:190px minmax(0,1fr);gap:10px;flex:1;min-height:0;min-width:0}.project-list{display:flex;flex-direction:column;overflow:hidden}.list-title{padding:12px;font-size:12px;font-weight:600;border-bottom:1px solid var(--el-border-color-lighter)}.project-item{display:flex;flex-direction:column;gap:5px;width:100%;text-align:left;min-width:0;background:none;border:0;border-left:3px solid transparent;padding:12px 10px;cursor:pointer;color:inherit}.project-item strong{max-width:100%;font-size:13px}.project-item small{color:var(--el-text-color-secondary);font-size:11px}.project-item.selected{border-left-color:var(--el-color-primary);background:var(--el-color-primary-light-9)}.conversation{display:flex;flex-direction:column;overflow:hidden}.conversation-head{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:10px 12px;border-bottom:1px solid var(--el-border-color-lighter);flex:none}.conversation-head>strong{flex:1}.model-picker{width:220px;max-width:100%}.mobile-project{display:none}.chat-history{padding:12px 16px}.conversation-status{display:flex;gap:8px;align-items:center;margin-bottom:10px;flex-wrap:wrap}.message{display:flex;gap:8px;margin:12px 0}.message.user{flex-direction:row-reverse}.avatar{width:27px;height:27px;flex:none;border-radius:8px;background:var(--el-fill-color);font-size:11px;display:grid;place-items:center}.assistant .avatar{color:var(--el-color-primary);background:var(--el-color-primary-light-9)}.bubble{padding:10px 12px;border-radius:10px;max-width:90%;min-width:0;background:var(--el-fill-color-light);overflow-wrap:anywhere}.user .bubble{background:var(--el-color-primary-light-9)}.bubble small{font-size:11px;color:var(--el-text-color-secondary)}.bubble p{margin:4px 0 0;white-space:pre-wrap;line-height:1.65}.bubble ol{padding-left:18px;margin:8px 0 0;line-height:1.6}.composer{padding:10px 12px;border-top:1px solid var(--el-border-color-lighter);display:flex;gap:8px;flex-direction:column;flex:none}.run-footer{padding:4px 0}.approval{padding:12px;background:var(--el-color-warning-light-9);margin:14px 0;border-radius:10px}.stages{margin-top:18px}.stage{display:flex;gap:10px;padding:8px 0}.stage>span{width:24px;height:24px;flex:none;border:1px solid var(--el-border-color);border-radius:50%;display:grid;place-items:center;font-size:11px}.stage strong,.stage small,.stage em{display:block}.stage small,.stage em{font-size:12px;color:var(--el-text-color-secondary);font-style:normal;margin-top:2px}.stage.ok>span{background:var(--el-color-success-light-9);border-color:var(--el-color-success);color:var(--el-color-success)}.stage.doing>span{border-color:var(--el-color-primary);color:var(--el-color-primary)}.stage.bad>span{border-color:var(--el-color-danger);color:var(--el-color-danger)}
.question-field{min-width:0;margin:18px 0;padding:12px;border:1px solid var(--el-border-color);border-radius:8px}.question-field legend{max-width:100%;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.65;font-weight:600;padding:0 5px}.question-field label{display:block;margin:10px 0 6px;font-size:12px}.question-options{display:grid;gap:8px}.question-option{min-height:44px;width:100%;min-width:0;height:auto;text-align:left;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.6;border:1px solid var(--el-border-color);border-radius:6px;padding:10px;background:var(--el-bg-color);color:var(--el-text-color-primary);cursor:pointer;font:inherit}.question-option.chosen{border-color:var(--el-color-primary);background:var(--el-color-primary-light-9)}.question-option:focus-visible{outline:2px solid var(--el-color-primary);outline-offset:2px}.question-option:disabled{cursor:not-allowed;opacity:.6}.plan-card{width:100%}.plan-card ul{padding-left:20px;line-height:1.7}.plan-card .rnd-actions{margin-top:12px}.tool-stream{border:1px solid var(--el-border-color);border-radius:10px;padding:12px;margin:12px 0}.tool-stream header{display:flex;flex-direction:column;gap:5px;margin-bottom:10px}.tool-stream small,.tool-event time{color:var(--el-text-color-secondary)}.tool-event{padding:9px 0;border-top:1px solid var(--el-border-color-lighter)}.tool-event summary{cursor:pointer;display:flex;gap:8px;flex-wrap:wrap;align-items:baseline}.tool-event summary span{flex:1;min-width:140px}.tool-event p{white-space:pre-wrap;overflow-wrap:anywhere}.operation-status{color:var(--el-color-primary)}.plan-card pre{white-space:pre-wrap;overflow-wrap:anywhere}
.project-item:focus-visible{outline:2px solid var(--el-color-primary);outline-offset:-2px}.tool-stream>summary{cursor:pointer;padding:4px 0}.rnd-form details{margin-top:16px}.rnd-form summary{cursor:pointer;padding:10px 0}
@container(max-width:720px){.work-area{grid-template-columns:minmax(0,1fr)}.project-list{display:none}.mobile-project{display:block;width:140px;max-width:100%}.conversation-head{gap:6px}.conversation-head>strong{flex-basis:100%}.model-picker{flex:1;min-width:130px}.bubble{max-width:95%}.chat-history{padding:8px}}
</style>
