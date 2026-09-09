terraform {
  required_providers {
    coder = { source = "coder/coder", version = ">= 2.5, < 3.0" }
    docker = { source = "kreuzwerker/docker", version = ">= 3.0, < 4.0" }
  }
}
# Agent bootstrap uses this URL, independently of the public browser URL.
provider "coder" { url = var.coder_agent_url }
variable "coder_agent_url" {
  type = string
  default = "http://coder:7080"
  description = "Coder URL reachable by workspace agents. The default requires the same private Compose network; use HTTPS DNS for remote provisioners."
}
provider "docker" {}
variable "workspace_image" {
  type = string
  default = "ai-rnd-coder:0.2.0"
  description = "Administrator-built image from integrations/coder/Dockerfile. Pin its verified digest."
}
variable "network_name" {
  type = string
  default = "ai-rnd_default"
  description = "Private Docker network reaching Coder and the platform API. Never mount a Docker socket in workspaces."
}
data "coder_provisioner" "me" {}
data "coder_workspace" "me" {}
data "coder_workspace_owner" "me" {}
data "coder_parameter" "source_url" {
  name = "rnd_source_url"
  type = "string"
  mutable = false
  description = "Platform source endpoint, not a general download URL."
}
data "coder_parameter" "source_token" {
  name = "rnd_source_token"
  type = "string"
  ephemeral = true
  default = ""
  description = "15-minute capability for one source ZIP, NOT an API or model key. Not needed after successful import."
}
data "coder_parameter" "source_sha256" {
  name = "rnd_source_sha256"
  type = "string"
  mutable = false
  validation { regex = "^[a-f0-9]{64}$" }
}
resource "coder_agent" "main" {
  arch = data.coder_provisioner.me.arch
  os = "linux"
  startup_script = "python3 /opt/rnd/import_source.py"
  env = {
    RND_SOURCE_URL = data.coder_parameter.source_url.value
    RND_SOURCE_TOKEN = sensitive(data.coder_parameter.source_token.value)
    RND_SOURCE_SHA256 = data.coder_parameter.source_sha256.value
  }
  metadata {
    display_name = "Imported product SHA-256"
    key = "rnd_source_sha256"
    script = "cat /home/coder/project/.rnd-source-sha256"
    interval = 5
    timeout = 1
  }
}
module "code-server" {
  count = data.coder_workspace.me.start_count
  source = "registry.coder.com/coder/code-server/coder"
  version = "~> 1.0"
  agent_id = coder_agent.main.id
  folder = "/home/coder/project"
  order = 1
}
resource "docker_volume" "home" {
  name = "rnd-${data.coder_workspace.me.id}-home"
  lifecycle { ignore_changes = all }
}
resource "docker_container" "workspace" {
  count = data.coder_workspace.me.start_count
  name = "rnd-${data.coder_workspace.me.id}"
  image = var.workspace_image
  entrypoint = ["sh", "-c", coder_agent.main.init_script]
  env = ["CODER_AGENT_TOKEN=${coder_agent.main.token}"]
  host {
    host = "host.docker.internal"
    ip = "host-gateway"
  }
  networks_advanced { name = var.network_name }
  volumes {
    container_path = "/home/coder"
    volume_name = docker_volume.home.name
    read_only = false
  }
}
