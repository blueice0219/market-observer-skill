#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
export MONITOR_DB="$PWD/data/demo.sqlite3"
.venv/bin/python -m a_share_monitor collect --source demo --once
exec .venv/bin/python -m a_share_monitor serve
