workspace "AI Software R&D Foundation" "Local-first bounded software factory" {
  model {
    user = person "Developer" "Submits requirements and approves generated specifications"
    platform = softwareSystem "AI R&D Platform" "Source generation, verification and delivery" {
      web = container "Web Console" "Original FastapiAdmin shell plus factory UI" "Vue 3"
      api = container "Control API" "Authentication, projects, runs and approvals" "FastAPI" {
        auth = component "Authentication adapter" "Reuses upstream identity and session" "FastapiAdmin"
        control = component "Factory API" "Owner-scoped request and download endpoints" "Python"
        repo = component "Repository" "Transactions and outbox" "SQLAlchemy"
        control -> auth "Requires identity"
        control -> repo "Persists project and run data"
      }
      worker = container "Workflow Worker" "LangGraph planner, trusted generator, verifier and packager" "Python / Temporal SDK"
      temporal = container "Temporal" "Durable workflow history and approval waiting" "Temporal dev service"
      pg = container "Platform database" "Admin and rnd_ tables, including transactional outbox" "PostgreSQL"
      redis = container "Session cache" "Upstream authentication and caching" "Redis"
      artifacts = container "Artifact store" "Immutable run folders and ZIP files" "Local filesystem"
      gateway = container "Model gateway" "Optional model routing" "LiteLLM"
      mcp = container "Scoped MCP proxy" "Optional read-only template symbols" "ToolHive / Serena"
    }
    modelProvider = softwareSystem "Model provider" "Local Ollama or approved remote model"
    cube = softwareSystem "CubeSandbox" "Optional private Linux KVM execution service"
    coder = softwareSystem "Coder" "Optional persistent human IDE workspace"
    user -> web "Uses"
    web -> api "Calls" "HTTP / JSON"
    api -> pg "Reads and writes" "SQL"
    api -> redis "Authenticates sessions" "Redis protocol"
    repo -> pg "Writes outbox transactionally" "SQL"
    worker -> pg "Dispatches outbox and updates projections" "SQL"
    worker -> temporal "Registers workflows and activities" "gRPC"
    worker -> gateway "Requests structured plans" "OpenAI-compatible HTTP"
    gateway -> modelProvider "Routes requests"
    worker -> mcp "Reads template symbols" "MCP"
    worker -> cube "Runs optional fixed source checks" "E2B-compatible SDK"
    worker -> artifacts "Writes validated source packages"
    api -> artifacts "Downloads after ownership and SHA verification"
    api -> coder "Creates optional administrator workspace" "REST"
    user -> coder "Manually imports ZIP and develops"
  }
  views {
    systemContext platform "C1" {
      include *
      autoLayout lr
    }
    container platform "C2" {
      include *
      autoLayout lr
    }
    component api "C3" {
      include *
      autoLayout lr
    }
  }
}
