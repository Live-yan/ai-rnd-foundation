# Development workspace: same Python/Node/uv/pnpm toolchain as the product.
# Pin verified base-image digests before a controlled production deployment.
FROM node:22-bookworm-slim AS node-tools
RUN npm install --global pnpm@9.15.3
FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /uvx /usr/local/bin/
COPY --from=node-tools /usr/local/bin/node /usr/local/bin/node
COPY --from=node-tools /usr/local/lib/node_modules/npm/ /usr/local/lib/node_modules/npm/
COPY --from=node-tools /usr/local/lib/node_modules/pnpm/ /usr/local/lib/node_modules/pnpm/
RUN apt-get update && apt-get install -y --no-install-recommends git curl ca-certificates libstdc++6 unzip procps \
    && rm -rf /var/lib/apt/lists/* \
    && ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && ln -s /usr/local/lib/node_modules/pnpm/bin/pnpm.cjs /usr/local/bin/pnpm \
    && useradd --create-home --uid 1000 --shell /bin/bash coder
COPY import_source.py /opt/rnd/import_source.py
RUN chmod 0555 /opt/rnd/import_source.py
USER coder
WORKDIR /home/coder
