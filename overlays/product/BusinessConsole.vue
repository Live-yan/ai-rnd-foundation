<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { Auth } from '@utils/auth';
type Field = {name: string; label: string; kind: string; required: boolean; references?: string};
type Entity = {name: string; label: string; fields: Field[]};
type Spec = {title: string; summary: string; entities: Entity[]; unsupported_features: string[]};
type Row = Record<string, unknown> & { id: number };
const spec = ref<Spec | null>(null);
const selected = ref('');
const entity = computed(() => spec.value?.entities.find(e => e.name === selected.value));
const rows = ref<Row[]>([]);
const total = ref(0); const offset = ref(0); const limit = 50; const query = ref('');
const draft = ref<Record<string, unknown>>({});
const editing = ref<number | null>(null); const error = ref(''); const busy = ref(false);
async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const token = Auth.getAccessToken();
  if (!token) throw new Error('请先登录 FastapiAdmin，再进入 /web/#/business');
  const result = await fetch((import.meta.env.VITE_APP_BASE_API || '/api/v1').replace(/\/$/, '') + '/business-api' + path, { method,
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!result.ok) throw new Error(`HTTP ${result.status}: ${(await result.text()).slice(0, 1200)}`);
  return await result.json() as T;
}
async function guard(fn: () => Promise<void>) {
  busy.value = true; error.value = '';
  try { await fn(); } catch(e) { error.value = e instanceof Error ? e.message : String(e); }
  finally { busy.value = false; }
}
function reset() {
  editing.value = null;
  draft.value = Object.fromEntries((entity.value?.fields || []).map(f => [f.name, f.kind === 'boolean' ? false : '']));
}
async function load() {
  if (!selected.value) return;
  const result = await api<{items: Row[]; total: number}>(`/${selected.value}?offset=${offset.value}&limit=${limit}&q=${encodeURIComponent(query.value)}`);
  rows.value = result.items; total.value = result.total;
}
async function choose(name: string) {
  selected.value = name; offset.value = 0; query.value = ''; reset(); await guard(load);
}
function edit(row: Row) {
  editing.value = row.id;
  draft.value = Object.fromEntries((entity.value?.fields || []).map(f => [f.name, row[f.name]]));
}
function payload() {
  const data: Record<string,unknown> = {};
  for (const f of entity.value?.fields || []) {
    const value = draft.value[f.name];
    if (value === '' || value === null || value === undefined) {
      if (f.required) throw new Error(`${f.label} 为必填项`);
      data[f.name] = null; continue;
    }
    if (['number','integer','reference'].includes(f.kind)) {
      const n = Number(value);
      if (!Number.isFinite(n)) throw new Error(`${f.label} 必须是有限数值`);
      data[f.name] = n;
    } else if (f.kind === 'boolean') { data[f.name] = Boolean(value); }
    else { data[f.name] = value; }
  }
  return data;
}
async function save() {
  await guard(async () => {
    await api(`/${selected.value}` + (editing.value === null ? '' : `/${editing.value}`), editing.value === null ? 'POST' : 'PATCH', payload());
    reset(); await load();
  });
}
async function remove(row: Row) {
  if (!window.confirm(`确认删除 ID=${row.id}？父记录存在子记录时会拒绝删除。`)) return;
  await guard(async () => { await api(`/${selected.value}/${row.id}`, 'DELETE'); await load(); });
}
async function page(delta: number) { offset.value = Math.max(0, offset.value + delta * limit); await guard(load); }
function textValue(value: unknown): string {
  return typeof value === 'string' || typeof value === 'number' ? String(value) : '';
}
function setText(name: string, event: Event) {
  const target = event.target;
  if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement) {
    draft.value[name] = target.value;
  }
}
function inputType(kind: string) {
  if (kind === 'date') return 'date'; if (kind === 'datetime') return 'datetime-local';
  if (['number','integer','reference'].includes(kind)) return 'number'; return 'text';
}
onMounted(async () => { await guard(async () => {
  spec.value = await api<Spec>('/schema'); selected.value = spec.value.entities[0]?.name || ''; reset(); await load();
}); });
</script>
<template>
  <main class="business"><a href="#/home">← 管理后台</a><h1>{{ spec?.title || '业务工作台' }}</h1><p>{{ spec?.summary }}</p>
    <details v-if="spec?.unsupported_features.length"><summary>本次交付边界</summary><p v-for="s in spec.unsupported_features" :key="s">{{ s }}</p></details>
    <p v-if="error" role="alert" class="error">{{ error }}</p>
    <nav><button v-for="e in spec?.entities" :key="e.name" :disabled="busy" @click="choose(e.name)">{{ e.label }}</button></nav>
    <div class="grid"><section><h2>{{ editing === null ? '新增' : `编辑 #${editing}` }}{{ entity?.label }}</h2>
      <form @submit.prevent="save"><label v-for="f in entity?.fields" :key="f.name">{{ f.label }} {{ f.required ? '*' : '' }}
        <input v-if="f.kind === 'boolean'" v-model="draft[f.name]" type="checkbox" />
        <textarea v-else-if="f.kind === 'text'" :value="textValue(draft[f.name])" @input="setText(f.name, $event)" :required="f.required" rows="3" />
        <input v-else :value="textValue(draft[f.name])" @input="setText(f.name, $event)" :type="inputType(f.kind)" :required="f.required" :step="f.kind === 'number' ? 'any' : '1'" />
        <small v-if="f.kind === 'reference'">填写 {{ f.references }} 列表中的 ID；只能引用自己创建的记录。</small>
      </label><button :disabled="busy" type="submit">保存</button><button type="button" @click="reset">清空</button></form>
    </section><section><h2>{{ entity?.label }}列表 · {{ total }} 条</h2>
      <form @submit.prevent="offset = 0; guard(load)"><input v-model="query" placeholder="按文字字段搜索" /><button :disabled="busy">查询</button></form>
      <div class="table"><table><thead><tr><th>ID</th><th v-for="f in entity?.fields" :key="f.name">{{ f.label }}</th><th>操作</th></tr></thead>
        <tbody><tr v-for="row in rows" :key="row.id"><td>{{ row.id }}</td><td v-for="f in entity?.fields" :key="f.name">{{ row[f.name] }}</td>
          <td><button :disabled="busy" @click="edit(row)">编辑</button><button :disabled="busy" @click="remove(row)">删除</button></td></tr></tbody></table></div>
      <p v-if="!rows.length">暂无记录。先在左侧创建一条。</p>
      <button :disabled="busy || offset === 0" @click="page(-1)">上一页</button><button :disabled="busy || offset + limit >= total" @click="page(1)">下一页</button>
    </section></div>
  </main>
</template>
<style scoped>
.business{padding:32px;min-height:100vh;background:#f5f7fa;color:#17283a;font-family:system-ui,sans-serif}.grid{display:grid;grid-template-columns:minmax(250px,340px) 1fr;gap:24px}section{background:#fff;padding:24px;border-radius:12px;min-width:0}label{display:block;margin-bottom:16px}input:not([type=checkbox]),textarea{display:block;width:100%;box-sizing:border-box;padding:10px;border:1px solid #bcc8d6;border-radius:6px;margin-top:7px;font:inherit}button{border:0;background:#265579;color:#fff;padding:9px 13px;margin:6px;border-radius:6px;cursor:pointer}button:disabled{opacity:.4;cursor:default}small{display:block;color:#526478;margin-top:6px}.table{overflow-x:auto}table{border-collapse:collapse;width:100%;margin-top:15px}td,th{text-align:left;border-bottom:1px solid #ddd;padding:10px;white-space:pre-wrap;min-width:80px}.error{white-space:pre-wrap;background:#ffede6;padding:16px;color:#842913}details{padding:12px;border:1px solid #ccd9e8}nav{margin:16px 0}@media(max-width:900px){.grid{grid-template-columns:1fr}.business{padding:16px}}
</style>
