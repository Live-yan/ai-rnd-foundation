# 本地测试数据重置

平台默认采用**保留数据**策略。普通启动不会删除 PostgreSQL、Redis、Temporal 数据卷，也不会重建 `.env`。

## 默认：保留现有数据

```bash
./scripts/start.sh
```

等价于初始化缺失配置后执行正常 `docker compose up --build -d`。已有 `.env`、`data/` 和 Compose named volumes 会继续使用。

## 测试阶段：数据卷全新开始

```bash
./scripts/start.sh --fresh
```

该参数是显式破坏性操作，只针对**当前 Compose 项目**：

1. 执行 `docker compose down --volumes --remove-orphans`，删除当前项目 PostgreSQL、Redis、Temporal 等 named volumes；
2. 将宿主机当前 `data/` 移到 `runtime/reset-backups/<UTC时间>/data`，而不是直接删除；
3. 创建全新的空 `data/`；
4. 保留当前 `.env` 和密钥；
5. 重新 build/up，数据库按新的空卷初始化。

因此这是最适合开发测试时“数据库从零开始，但继续使用当前配置”的模式。

## 完全从零：数据 + 密钥一起重建

```bash
./scripts/start.sh --fresh --new-env
```

除 `--fresh` 的动作外，旧 `.env` 也会被移到同一个 `runtime/reset-backups/<UTC时间>/.env`，随后 `init_env.py` 生成全新的 PostgreSQL/Redis/平台密钥。

`--new-env` 不能单独使用，必须与 `--fresh` 一起指定。

## 只预览 reset 动作

如果只想检查 reset 将执行什么，而不改变 Docker 或文件：

```bash
python3 scripts/reset_local.py --dry-run
python3 scripts/reset_local.py --dry-run --new-env
```

## 恢复误重置的宿主机 data

named volumes 被 `docker compose down --volumes` 删除后不会自动备份；这是 `--fresh` 的明确语义。宿主机 `data/` 则保存在 `runtime/reset-backups/`，可在停止平台后手工恢复。

不要在生产环境或仍有重要未备份数据库的环境使用 `--fresh`。日常停止应使用：

```bash
docker compose stop
```
