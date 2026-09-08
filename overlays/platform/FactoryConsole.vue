<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import { Auth } from '@utils/auth';

type Message = { role: string; content: string };
type Project = { id: string; title: string; messages: Message[] };
type Run = { id: string; status: string; spec: Record<string, unknown> | null; spec_digest: string;
  error: string; checks: Record<string, unknown>; download_available: boolean; provider: string; };
type EventRow = { id: number; message: string; level: string };
const title = ref('设备台账与维护记录');
const requirement = ref('我需要设备台账，记录设备名称、编号、是否启用；维护记录关联设备，记录维护日期和备注。每位用户仅管理自己的记录。');
const followup = ref('');
const project = ref<Project | null>(null);
const projects = ref<Project[]>([]);
const runs = ref<Run[]>([]);
const run = ref<Run | null>(null);
const provider = ref('demo');
const sandbox = ref('static');
const useSerena = ref(false);
const acceptLimitations = ref(false);
const busy = ref(false);
const error = ref('');
const events = ref<EventRow[]>([]);
const integration = ref<Record<string,string>>({});
let timer: ReturnType<typeof setTimeout> | undefined;
let stopped = false;

async function request<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const token = Auth.getAccessToken();
  if (!token) throw new Error('请先在 FastapiAdmin 登录页面登录，然后进入 /web/#/factory。');
  const response = await fetch('/factory-api' + path, {
    method, headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`HTTP ${response.status}: ${text.slice(0, 900)}`);
  }
  return await response.json() as T;
}
async function guarded(fn: () => Promise<void>) {
  busy.value = true; error.value = '';
  try { await fn(); } catch (e) { error.value = e instanceof Error ? e.message : String(e); }
  finally { busy.value = false; }
}
async function refreshProjects() { projects.value = await request<Project[]>('/projects'); }
async function createProject() {
  await guarded(async () => {
    project.value = await request<Project>('/projects', 'POST', {
      title: title.value, requirement: requirement.value, template_id: 'fastapiadmin-pg-v1',
    });
    run.value = null; runs.value = []; events.value = []; await refreshProjects();
  });
}
async function selectProject(p: Project) {
  await guarded(async () => {
    project.value = await request<Project>(`/projects/${p.id}`);
    runs.value = await request<Run[]>(`/projects/${p.id}/runs`);
    run.value = runs.value[0] || null; events.value = []; acceptLimitations.value = false;
  });
}
async function addMessage() {
  if (!project.value || !followup.value.trim()) return;
  await guarded(async () => {
    project.value = await request<Project>(`/projects/${project.value!.id}/messages`, 'POST', { content: followup.value });
    followup.value = '';
  });
}
async function startRun() {
  if (!project.value) return;
  await guarded(async () => {
    run.value = await request<Run>(`/projects/${project.value!.id}/runs`, 'POST', {
      provider: provider.value, sandbox: sandbox.value, use_serena: useSerena.value,
      idempotency_key: crypto.randomUUID(),
    });
    events.value = []; acceptLimitations.value = false;
    runs.value = await request<Run[]>(`/projects/${project.value!.id}/runs`);
  });
}
async function decide(approve: boolean) {
  if (!run.value) return;
  await guarded(async () => {
    run.value = await request<Run>(`/runs/${run.value!.id}/decision`, 'POST', {
      spec_digest: run.value!.spec_digest, approve, accept_limitations: acceptLimitations.value,
    });
  });
}
async function download() {
  if (!run.value) return;
  await guarded(async () => {
    const r = await fetch(`/factory-api/runs/${run.value!.id}/download`, {
      headers: { Authorization: `Bearer ${Auth.getAccessToken()}` },
    });
    if (!r.ok) throw new Error(await r.text());
    const url = URL.createObjectURL(await r.blob());
    const a = document.createElement('a'); a.href = url;
    a.download = String(run.value!.spec?.slug || 'product') + '.zip'; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
}
async function coder() {
  if (!run.value) return;
  await guarded(async () => {
    const value = await request<{url: string}>(`/runs/${run.value!.id}/coder`, 'POST');
    // Workspace provisioning and ZIP import are separate operations; no hidden upload.
    const url = new URL(value.url);
    if (!['https:', 'http:'].includes(url.protocol)) throw new Error('不支持的 Coder URL');
    window.open(url.href, '_blank', 'noopener,noreferrer');
    error.value = 'Coder 工作区已请求创建；请等待其构建完成，再手动上传本次下载的源码包。';
  });
}
async function poll() {
  try {
    const current = run.value?.id;
    if (current) {
      const result = await request<Run>(`/runs/${current}`);
      const after = events.value.at(-1)?.id || 0;
      const newEvents = await request<EventRow[]>(`/runs/${current}/events?after=${after}`);
      if (run.value?.id === current) { run.value = result; events.value.push(...newEvents); }
    }
  } catch (e) { error.value = String(e); }
  finally { if (!stopped) timer = setTimeout(poll, 2000); }
}
onMounted(async () => {
  await guarded(async () => { await refreshProjects(); integration.value = await request('/integrations'); });
  void poll();
});
onUnmounted(() => { stopped = true; if (timer) clearTimeout(timer); });
</script>

<template>
  <main class="factory-shell">
    <header><a href="#/home">← 管理后台</a><p class="eyebrow">AI SOFTWARE R&D / FOUNDATION 0.1</p>
      <h1>从需求到可检验的项目源码</h1>
      <p>FastapiAdmin · Vue3 · uv · PostgreSQL。当前生成范围：单用户归属隔离的类型化 CRUD 与父子关联。</p>
    </header>
    <p v-if="error" role="alert" class="error">{{ error }}</p>
    <div class="columns">
      <aside class="panel"><h2>项目</h2><button v-for="p in projects" :key="p.id" @click="selectProject(p)">{{ p.title }}</button>
        <h3>集成配置</h3><dl><template v-for="(value, key) in integration" :key="key"><dt>{{ key }}</dt><dd>{{ value }}</dd></template></dl>
        <small>“已配置”不等于“已连通”。外部集成需要单独验收。</small>
      </aside>
      <section class="panel"><h2>1 · 需求对话</h2>
        <label>项目名称<input v-model="title" maxlength="100" /></label>
        <label>技术模板<select><option>FastapiAdmin / Vue3 / Python / PostgreSQL</option></select></label>
        <label>第一条需求<textarea v-model="requirement" rows="5" maxlength="16000" /></label>
        <button :disabled="busy" @click="createProject">创建项目</button>
        <template v-if="project"><h3>{{ project.title }}</h3>
          <article v-for="(m, i) in project.messages" :key="i" class="message">{{ m.content }}</article>
          <textarea v-model="followup" placeholder="补充需求；每个新生成任务读取对话快照，不改动旧包。" rows="3" />
          <button :disabled="busy" @click="addMessage">添加补充说明</button>
          <h2>2 · 规划与工具</h2><label>规划模式<select v-model="provider">
            <option value="demo">固定演示：设备 + 维护记录（不解析任意需求）</option>
            <option value="litellm">真实模型：通过 LiteLLM 解读以上对话</option></select></label>
          <label>校验方式<select v-model="sandbox"><option value="static">静态检查 + 业务契约检查（不启动全栈）</option>
            <option value="docker">Docker：固定校验命令（需启用独立配置）</option>
            <option value="cube">CubeSandbox：远程沙箱校验（需预配）</option></select></label>
          <label><input v-model="useSerena" type="checkbox" /> 使用 ToolHive 管理的只读 Serena 模板上下文</label>
          <button :disabled="busy" @click="startRun">创建新的规划任务</button>
          <label v-if="runs.length">历史任务<select @change="run = runs.find(r => r.id === ($event.target as HTMLSelectElement).value) || null; events = []">
            <option v-for="r in runs" :key="r.id" :value="r.id">{{ r.id.slice(0,8) }} · {{ r.status }}</option></select></label>
        </template>
      </section>
      <section class="panel"><h2>3 · 确认、生成、下载</h2>
        <template v-if="run"><p><strong>{{ run.status }}</strong> · {{ run.id.slice(0,8) }}</p>
          <p v-if="run.provider === 'demo'" class="notice">这是固定演示结果，不是 AI 已实现了全部需求。</p>
          <pre v-if="run.spec">{{ JSON.stringify(run.spec, null, 2) }}</pre>
          <template v-if="run.status === 'AWAITING_APPROVAL'">
            <label><input v-model="acceptLimitations" type="checkbox" /> 我已阅读 unsupported_features，接受这些未实现项。</label>
            <button :disabled="busy" @click="decide(true)">确认当前规格并生成</button>
            <button :disabled="busy" @click="decide(false)">拒绝此规格</button>
          </template>
          <p v-if="run.error" class="error">{{ run.error }}</p>
          <template v-if="run.download_available"><p class="notice">源码骨架已准备好；请查看 quality.json。此状态不代表已经通过完整部署、业务验收或生产安全审计。</p>
            <button :disabled="busy" @click="download">下载项目 ZIP</button>
            <button :disabled="busy" @click="coder">创建 Coder 工作区（可选）</button>
          </template>
          <h3>检查结果</h3><pre>{{ JSON.stringify(run.checks, null, 2) }}</pre>
          <h3>事件日志</h3><p v-for="e in events" :key="e.id" class="event">{{ e.message }}</p>
        </template><p v-else>先创建项目并发起规划。任务会在后台服务中执行；关闭页面后可从项目列表恢复查看。</p>
      </section>
    </div>
  </main>
</template>

<style scoped>
.factory-shell{padding:32px;background:#f3f6fa;color:#182235;min-height:100vh;font-family:system-ui,sans-serif}
header{max-width:1500px;margin:auto auto 28px}.eyebrow{font-size:12px;letter-spacing:2px;color:#42668f}h1{font-size:32px;margin:10px 0}h2{font-size:20px}h3{font-size:16px}.columns{display:grid;grid-template-columns:230px 1fr 1.15fr;gap:20px;max-width:1500px;margin:auto}.panel{background:white;border:1px solid #dce4ee;border-radius:14px;padding:22px;min-width:0}label{display:block;margin:14px 0}input:not([type=checkbox]),textarea,select{display:block;box-sizing:border-box;width:100%;margin-top:7px;padding:10px;border:1px solid #c3cfdd;border-radius:7px;font:inherit}button{background:#204e79;color:white;border:0;border-radius:7px;padding:10px 13px;margin:6px 6px 6px 0;cursor:pointer}button:disabled{opacity:.5;cursor:wait}aside button{display:block;width:100%;text-align:left}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:420px;overflow:auto;background:#f3f6fa;padding:12px;font-size:12px}dt{font-weight:600;font-size:12px}dd{margin:0 0 10px;font-size:11px;overflow-wrap:anywhere}.error{background:#fff0e9;color:#8b2c10;padding:14px;white-space:pre-wrap}.notice{background:#eef5ff;padding:12px}.message{white-space:pre-wrap;background:#f0f5fb;padding:12px;margin:10px 0}.event{font-size:12px;border-bottom:1px solid #eee;padding-bottom:8px}@media(max-width:1100px){.columns{grid-template-columns:1fr}.factory-shell{padding:16px}}
</style>
