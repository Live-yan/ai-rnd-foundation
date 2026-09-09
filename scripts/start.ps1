param(
    [switch]$Fresh,
    [switch]$NewEnv
)

$ErrorActionPreference = "Stop"
Write-Host "推荐在 WSL Ubuntu 终端运行 ./scripts/start.sh；PowerShell 保持相同 Fresh 语义。"
Set-Location (Join-Path $PSScriptRoot "..")

if ($NewEnv -and -not $Fresh) {
    throw "-NewEnv 只能与 -Fresh 一起使用。"
}

if ($Fresh) {
    if ($NewEnv) {
        python scripts/reset_local.py --new-env
    } else {
        python scripts/reset_local.py
    }
    if ($LASTEXITCODE -ne 0) { throw "本地 Fresh 重置失败；没有继续启动。" }
}

python scripts/init_env.py --repair-data
if ($LASTEXITCODE -ne 0) { throw "初始化失败。请安装 Python 或改在 WSL 运行。" }

docker compose config --quiet
if ($LASTEXITCODE -ne 0) { throw "Compose 配置校验失败。" }

docker compose up --build -d
if ($LASTEXITCODE -ne 0) { throw "Docker 构建或启动失败；查看输出与 docs/TROUBLESHOOTING.md。" }
Write-Host "打开 http://localhost:8000/api/v1/web/，登录后访问 /api/v1/web/#/factory。"
