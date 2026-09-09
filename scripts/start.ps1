$ErrorActionPreference = "Stop"
Write-Host "推荐在 WSL Ubuntu 终端运行 bash scripts/start.sh。"
Set-Location (Join-Path $PSScriptRoot "..")
python scripts/init_env.py
if ($LASTEXITCODE -ne 0) { throw "初始化失败。请安装 Python 或改在 WSL 运行。" }
docker compose up --build -d
if ($LASTEXITCODE -ne 0) { throw "Docker 构建或启动失败；查看输出与 docs/TROUBLESHOOTING.md。" }
Write-Host "打开 http://localhost:8000/web/，登录后访问 /web/#/factory。"
