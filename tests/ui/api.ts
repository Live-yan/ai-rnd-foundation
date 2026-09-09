// Deterministic API fixtures; the actual Vue workbench components are rendered.
const tools = ["fastapiadmin","langgraph","litellm","temporal","openspec","diagrams","structurizr","toolhive","serena","cube","coder"].map(id => ({id,name:id,role:"研发阶段中的真实职责与独立配置入口",execution:"full",configured:!['cube','coder','serena'].includes(id)}));
const catalog = [
  {id:"openai",name:"OpenAI",requires_api_key:true}, {id:"anthropic",name:"Anthropic",requires_api_key:true},
  {id:"chatgpt",name:"ChatGPT / Codex",requires_api_key:false}, {id:"bedrock",name:"Bedrock",requires_api_key:false}
].map(x=>({...x,category:"云端",models:[],docs:"https://docs.litellm.ai/docs/",base_url:"",default_base_url:"",supports_discover:false}));
const providers = Array.from({length:9},(_,i)=>({id:"p"+i,provider:i===1?"chatgpt":"openai",name:i===0?"企业研发主模型配置名称非常长时按钮仍然可见".repeat(3):"研发模型配置 "+i,model:"organization/team/model-version-with-very-long-identifier".repeat(2),base_url:"https://models.example.test/v1",enabled:true,is_default:i===0,has_api_key:true,api_version:"",temperature:.1,max_tokens:6000,litellm_params:{timeout:90},auth_status:"not_connected",credential_fields:[]}));
const projects=Array.from({length:6},(_,i)=>({id:"project-"+i,title:"设备维护研发项目 "+i,revision:"a".repeat(64),clarification_status:"WAITING_USER",clarification:{questions:["请确认设备数据的归属和验收标准"],acceptance_criteria:[]},messages:Array.from({length:12},(_,n)=>({role:n%2?"assistant":"user",content:n%2?"请先确认权限、核心实体和验收条件，再开始生成。".repeat(4):"需要设备台账、维护记录和用户数据隔离。".repeat(4),questions:[]}))}));
(window as any).__calls=[];
const api={
 async listProviders(){return providers;},async providerCatalog(){return {providers:catalog,categories:["云端"],quick_start:[]};},
 async toolchain(){return tools;},async listProjects(){return projects;},async getProject(id:string){return projects.find(p=>p.id===id);},async listRuns(){return [];},
 async integrationConfig(id:string){return {id,docs:"https://docs.litellm.ai/docs/",web_url:"",note:"配置入口合同测试；不会连接或创建外部服务。",fields:[{key:"fixture",label:"测试字段",kind:"text",value:"",configured:false}],editable:true,revision:0,requires_restart:false,startup_values:{}};},
 async saveIntegration(id:string){return this.integrationConfig(id);}, async resetIntegration(id:string){return this.integrationConfig(id);},async probeIntegration(){return {status:"requires_run",message:"必须真实联调"};},
 async oauthStatus(){await new Promise(r=>setTimeout(r,900));return {status:"not_connected",interval:5};},
 async oauthAction(id:string,action:string){(window as any).__calls.push("oauth:"+action);return {status:"pending",user_code:"TEST-ONLY",verification_url:"https://auth.openai.com/codex/device",interval:5};},
 async exportProviders(){return {yaml:"model_list: []",note:"不含凭据",environment_variables:[]};}
};
export default api;
