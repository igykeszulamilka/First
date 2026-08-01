#!/usr/bin/env bash
cd "$(dirname "$0")"
command -v node >/dev/null || { echo "Node.js kell"; exit 1; }
[[ -d node_modules ]] || npm install
exec node server.js
