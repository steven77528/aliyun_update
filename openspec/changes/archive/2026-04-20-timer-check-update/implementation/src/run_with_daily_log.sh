#!/bin/sh
set -eu

# 入口脚本仅负责转发，日志持久化由 ip_sync.py 内部处理
exec python3 /app/src/ip_sync.py "$@"
