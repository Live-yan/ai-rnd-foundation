workspace "设备检修管理示例" "Generated architecture description" {
  model {
    user = person "User" "Authenticated application user"
    system = softwareSystem "设备检修管理示例" "FastapiAdmin-based generated product" {
      web = container "Web UI" "Forms, lists and administration" "Vue 3 / TypeScript"
      api = container "Application API" "Authentication and business endpoints" "FastAPI / Python" {
        auth = component "Authentication adapter" "Reuses upstream JWT, Redis session and live user checks" "FastapiAdmin"
        c_device = component "设备" "Typed owner-scoped CRUD" "SQLAlchemy Core"
        c_maintenance = component "检修记录" "Typed owner-scoped CRUD" "SQLAlchemy Core"
      }
      db = container "Database" "Admin and generated business data" "PostgreSQL"
      redis = container "Session cache" "Upstream sessions and caching" "Redis"
    }
    user -> web "Uses" "HTTP (local development)"
    web -> api "Calls authenticated APIs" "HTTP / JSON"
    api -> db "Reads and writes" "SQL"
    api -> redis "Validates sessions" "Redis protocol"
    auth -> db "Checks current user" "SQL"
    auth -> redis "Checks session" "Redis protocol"
    c_device -> auth "Requires identity"
    c_device -> db "CRUD biz_device" "SQL"
    c_maintenance -> auth "Requires identity"
    c_maintenance -> db "CRUD biz_maintenance" "SQL"
  }
  views {
    systemContext system "C1" {
      include *
      autoLayout lr
    }
    container system "C2" {
      include *
      autoLayout lr
    }
    component api "C3" {
      include *
      autoLayout lr
    }
  }
}
