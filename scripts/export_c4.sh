#!/bin/sh
# Run on host, not in the control-plane API. Explicit local Docker use; no uploaded DSL execution.
set -eu
folder="${1:-architecture}"
folder="$(cd "$folder" && pwd)"
image="structurizr/structurizr:2026.06.28-noble"
docker run --rm --user "$(id -u):$(id -g)" -v "$folder:/usr/local/structurizr" "$image" validate -workspace workspace.dsl
docker run --rm --user "$(id -u):$(id -g)" -v "$folder:/usr/local/structurizr" "$image" export -workspace workspace.dsl -format json -output exported
docker run --rm --user "$(id -u):$(id -g)" -v "$folder:/usr/local/structurizr" "$image" export -workspace workspace.dsl -format mermaid -output exported
printf 'DSL parsed and exported. See %s/exported.\n' "$folder"
