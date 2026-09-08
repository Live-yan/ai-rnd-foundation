#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 scripts/init_env.py
docker compose version
docker compose up --build -d
printf '\nOpen http://localhost:8000/web/ and log in, then /web/#/factory\n'
printf 'See docs/START_HERE.md for first-login and diagnosis instructions.\n'
