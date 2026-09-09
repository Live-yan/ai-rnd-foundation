import { request } from "@utils";

const API_PATH = "/factory";

export type ClarificationStatus = "NEEDS_CLARIFICATION" | "WAITING_USER" | "READY";
export interface Clarification {
  ready: boolean;
  understanding: string;
  questions: string[];
  assumptions: string[];
  acceptance_criteria: string[];
  risks: string[];
  suggested_stack: string[];
}
export interface FactoryMessage {
  role: "user" | "assistant" | string;
  kind?: string;
  content: string;
  questions?: string[];
  acceptance_criteria?: string[];
  risks?: string[];
}
export interface FactoryProject {
  revision: string;
  id: string;
  title: string;
  template_id: string;
  messages: FactoryMessage[];
  clarification_status: ClarificationStatus;
  clarification: Clarification | null;
  clarification_provider_id: string | null;
  created_at: string;
  updated_at: string;
}
export interface ProviderProfile {
  id: string;
  name: string;
  provider: string;
  base_url: string;
  model: string;
  enabled: boolean;
  is_default: boolean;
  has_api_key: boolean;
  auth_status?: string;
  litellm_params?: Record<string, any>;
  credential_fields?: string[];
  api_version?: string;
  temperature: number;
  max_tokens: number;
  created_at: string;
  updated_at: string;
}
export interface ProviderInput {
  litellm_params?: Record<string, any>;
  credentials?: Record<string, string>;
  name: string;
  provider: string;
  base_url: string;
  api_key?: string;
  api_version?: string;
  model: string;
  enabled: boolean;
  is_default: boolean;
  temperature: number;
  max_tokens: number;
}
export interface ProviderCatalogModel {
  id: string;
  label: string;
}
export interface ProviderCatalogItem {
  id: string;
  name: string;
  category: string;
  description: string;
  base_url: string;
  default_base_url: string;
  requires_api_key: boolean;
  requires_base_url: boolean;
  supports_discover: boolean;
  docs: string;
  models: ProviderCatalogModel[];
  litellm_prefix: string;
  is_local: boolean;
  extra_hint: string;
  discover_path: string;
  auth_mode?: string;
}
export interface ProviderCatalog {
  categories: string[];
  providers: ProviderCatalogItem[];
  quick_start: { provider: string; model: string; name: string }[];
}
export interface DiscoverInput {
  provider: string;
  base_url: string;
  api_key?: string;
}
export interface ToolchainItem {
  id: string;
  name: string;
  role: string;
  configured: boolean;
  execution: string;
  hint: string;
}
export interface RunEvent {
  id: number;
  level: string;
  message: string;
  stage: string | null;
  tool: string | null;
  payload: Record<string, unknown> | null;
  created_at: string;
}
export interface FactoryRun {
  id: string;
  project_id: string;
  status: string;
  spec: Record<string, any> | null;
  spec_digest: string | null;
  decision: Record<string, any> | null;
  clarification?: Clarification | null;
  artifact_sha256: string | null;
  checks: Record<string, any> | null;
  stage_details: Record<string, any> | null;
  error: string | null;
  provider_id: string | null;
  provider: string;
  sandbox: string;
  pipeline_mode: "core" | "full";
  provision_coder: boolean;
  download_available: boolean;
  quality_label: string | null;
  created_at: string;
  updated_at: string;
}

export interface OAuthStatus {
  status: string;
  verification_url?: string;
  user_code?: string;
  expires_at?: number;
  interval: number;
}
export interface IntegrationConfig {
  id: string; docs: string; web_url: string; note: string; revision: number; editable: boolean;
  requires_restart: boolean; startup_values: Record<string, any>;
  fields: { key: string; label: string; kind: string; value: any; configured: boolean; minimum?: number; maximum?: number }[];
}

function data<T>(response: any): T {
  return response.data.data as T;
}

export const FactoryAPI = {
  async exportProviders() { return data<{yaml: string; environment_variables: string[]; note: string}>(await request({ url: `${API_PATH}/providers/export`, method: "post" })); },
  async oauthStatus(id: string) { return data<OAuthStatus>(await request({ url: `${API_PATH}/providers/${id}/oauth`, method: "get" })); },
  async oauthAction(id: string, action: "begin" | "poll" | "disconnect") { return data<OAuthStatus>(await request({ url: `${API_PATH}/providers/${id}/oauth/${action}`, method: "post", timeout: 60000 })); },
  async discoverSavedProvider(id: string) { return data<{models: ProviderCatalogModel[]}>(await request({ url: `${API_PATH}/providers/${id}/discover`, method: "post", timeout: 60000 })); },
  async integrationConfig(id: string) { return data<IntegrationConfig>(await request({ url: `${API_PATH}/toolchain/${id}/config`, method: "get" })); },
  async saveIntegration(id: string, revision: number, values: Record<string, any>) { return data<IntegrationConfig>(await request({ url: `${API_PATH}/toolchain/${id}/config`, method: "put", data: {expected_revision: revision, values} })); },
  async resetIntegration(id: string, revision: number) { return data<IntegrationConfig>(await request({ url: `${API_PATH}/toolchain/${id}/config`, method: "delete", params: {revision} })); },
  async probeIntegration(id: string) { return data<{status: string; message: string}>(await request({ url: `${API_PATH}/toolchain/${id}/probe`, method: "post", timeout: 60000 })); },
  async health() {
    return data<Record<string, any>>(await request({ url: `${API_PATH}/health`, method: "get" }));
  },
  async listProjects() {
    return data<FactoryProject[]>(await request({ url: `${API_PATH}/projects`, method: "get" }));
  },
  async getProject(id: string) {
    return data<FactoryProject>(await request({ url: `${API_PATH}/projects/${id}`, method: "get" }));
  },
  async createProject(body: { title: string; requirement: string; template_id?: string }) {
    return data<FactoryProject>(await request({ url: `${API_PATH}/projects`, method: "post", data: body }));
  },
  async addMessage(id: string, content: string) {
    return data<FactoryProject>(await request({ url: `${API_PATH}/projects/${id}/messages`, method: "post", data: { content } }));
  },
  async clarify(id: string, providerId?: string | null) {
    return data<FactoryProject>(await request({
      url: `${API_PATH}/projects/${id}/clarify`, method: "post", timeout: 410000, data: { provider_id: providerId || null },
    }));
  },
  async listProviders() {
    return data<ProviderProfile[]>(await request({ url: `${API_PATH}/providers`, method: "get" }));
  },
  async providerCatalog() {
    return data<ProviderCatalog>(await request({ url: `${API_PATH}/providers/catalog`, method: "get" }));
  },
  async discoverProviderModels(body: DiscoverInput) {
    return data<{ models: ProviderCatalogModel[] }>(await request({
      url: `${API_PATH}/providers/discover`, method: "post", timeout: 60000, data: body,
    }));
  },
  async createProvider(body: ProviderInput) {
    return data<ProviderProfile>(await request({ url: `${API_PATH}/providers`, method: "post", data: body }));
  },
  async updateProvider(id: string, body: Partial<ProviderInput>) {
    return data<ProviderProfile>(await request({ url: `${API_PATH}/providers/${id}`, method: "put", data: body }));
  },
  async deleteProvider(id: string) {
    await request({ url: `${API_PATH}/providers/${id}`, method: "delete" });
  },
  async defaultProvider(id: string) {
    return data<ProviderProfile>(await request({ url: `${API_PATH}/providers/${id}/default`, method: "post" }));
  },
  async testProvider(id: string) {
    return data<{ ok: boolean; message: string }>(await request({
      url: `${API_PATH}/providers/${id}/test`, method: "post", timeout: 120000,
    }));
  },
  async toolchain() {
    return data<ToolchainItem[]>(await request({ url: `${API_PATH}/toolchain`, method: "get" }));
  },
  async listRuns(projectId: string) {
    return data<FactoryRun[]>(await request({ url: `${API_PATH}/projects/${projectId}/runs`, method: "get" }));
  },
  async getRun(id: string) {
    return data<FactoryRun>(await request({ url: `${API_PATH}/runs/${id}`, method: "get" }));
  },
  async startRun(projectId: string, body: Record<string, unknown>) {
    return data<FactoryRun>(await request({ url: `${API_PATH}/projects/${projectId}/runs`, method: "post", data: body }));
  },
  async decide(id: string, body: Record<string, unknown>) {
    return data<FactoryRun>(await request({ url: `${API_PATH}/runs/${id}/decision`, method: "post", data: body }));
  },
  async events(id: string, after = 0) {
    return data<RunEvent[]>(await request({ url: `${API_PATH}/runs/${id}/events`, method: "get", params: { after } }));
  },
  async analysisFiles(id: string) {
    return data<string[]>(await request({ url: `${API_PATH}/runs/${id}/analysis`, method: "get" }));
  },
  async analysisFile(id: string, path: string) {
    const response = await request({ url: `${API_PATH}/runs/${id}/analysis/file`, method: "get", params: { path }, responseType: "blob" });
    return response.data as Blob;
  },
  async download(id: string) {
    const response = await request({ url: `${API_PATH}/runs/${id}/download`, method: "get", responseType: "blob" });
    return response.data as Blob;
  },
  async provisionCoder(id: string) {
    return data<Record<string, any>>(await request({ url: `${API_PATH}/runs/${id}/coder`, method: "post" }));
  },
};

export default FactoryAPI;
