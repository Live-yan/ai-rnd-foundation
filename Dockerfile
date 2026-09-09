# Online assembly. No private keys or .env files are copied into any image layer.
FROM python:3.12-slim-bookworm AS upstream
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY scripts/bootstrap.py scripts/bootstrap.py
COPY templates/ templates/
COPY overlays/ overlays/
RUN python scripts/bootstrap.py

FROM node:22-bookworm-slim AS frontend
WORKDIR /web
RUN npm install --global pnpm@9.15.3 @fission-ai/openspec@1.12.0
COPY --from=upstream /app/runtime/FastapiAdmin/frontend/web/ ./
RUN grep -q 'AI-RND-FRONTEND-ROUTE:factory:v2' src/router/MenuProcessor.ts && \
    grep -q '^VITE_ACCESS_MODE=mixed$' .env.production
RUN if [ -f pnpm-lock.yaml ]; then pnpm install --frozen-lockfile; else pnpm install; fi
RUN pnpm exec vite build --mode production && \
    test -s src/types/auto-imports.d.ts && test -s src/types/components.d.ts && \
    pnpm exec vue-tsc --noEmit && \
    node -e 'const h=require("fs").readFileSync("dist/index.html","utf8"); if(!h.includes("/api/v1/web/")) throw new Error("frontend assets were not built for /api/v1/web/")'

FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /uvx /usr/local/bin/
COPY --from=docker:28.3.3-cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=frontend /usr/local/bin/node /usr/local/bin/node
COPY --from=frontend /usr/local/lib/node_modules/@fission-ai/ /usr/local/lib/node_modules/@fission-ai/
RUN ln -s /usr/local/lib/node_modules/@fission-ai/openspec/bin/openspec.js /usr/local/bin/openspec
RUN apt-get update && apt-get install -y --no-install-recommends graphviz fonts-noto-cjk git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV UV_LINK_MODE=copy PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app:/app/runtime/FastapiAdmin/backend
COPY pyproject.toml .python-version alembic.ini ./
COPY factory/ factory/
COPY scripts/ scripts/
COPY templates/ templates/
COPY overlays/ overlays/
COPY migrations/ migrations/
COPY locks/ locks/
COPY --from=upstream /app/.vendor/ .vendor/
COPY --from=upstream /app/runtime/ runtime/
RUN python scripts/resolve_host.py && \
    if [ -f locks/host.uv.lock ]; then cp locks/host.uv.lock runtime/combined/uv.lock && uv sync --directory runtime/combined --frozen --no-dev; \
    else uv lock --directory runtime/combined && uv sync --directory runtime/combined --frozen --no-dev; fi
COPY --from=frontend /web/dist/ runtime/FastapiAdmin/backend/dist/
ENV PATH=/app/runtime/combined/.venv/bin:$PATH ENVIRONMENT=prod
RUN useradd --create-home --uid 10001 factory && mkdir -p /app/data && chown -R factory:factory /app
USER factory
EXPOSE 8000
ENTRYPOINT ["/bin/sh", "/app/scripts/entrypoint.sh"]
CMD ["api"]
