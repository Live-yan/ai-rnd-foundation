# FastapiAdmin Golden Template contract

Upstream is pinned to f7f5fb61a5c918016640f6b07e053c807381b7cc. Do not silently follow master.

Keep FastapiAdmin auth, Redis sessions, Vue shell and existing system modules intact. The platform uses a separate `rnd_*` table family. Generated projects use `biz_*` tables and a separate `business_alembic_version` migration table. Never export the platform database or its secrets.

Allowed extension points: a separate ASGI factory wrapping `app.create_app()`, explicit extra router registration, one Vue route, independently-versioned migrations, and `.env.example` only. The first generator consumes a validated schema and renders deterministic code. It must not execute arbitrary model-written Python or shell on the host. All database relationships must pass cross-owner checks and real foreign-key constraints.

C4 describes the designed application structure. The ER model is generated from the exact business schema driving SQLAlchemy metadata; it excludes upstream administrative tables and does not pretend to reflect a running database. Production reflection is a separate extension.

Quality levels must be literal: source validation, isolated business contract tests, whole-stack deployment acceptance. They are not equivalent.
