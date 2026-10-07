#!/usr/bin/env bash
# engine.db 每日备份(Task 25"备份接入"):标准库 Online Backup
# (conn.backup(),topic-digest 同款模式,备份期间引擎可继续运行),
# 保留 30 天。WAL 模式下直接 cp 数据库文件不安全(丢 -wal 内容),
# 必须经 Online Backup。脚本幂等,退出非零=备份失败(可接告警)。
set -euo pipefail

ENGINE_ROOT="${NANMU_ENGINE_ROOT:-/opt/nanmu-blog/engine}"
BACKUP_DIR="${NANMU_BACKUP_DIR:-/opt/nanmu-blog/backups}"
RETAIN_DAYS=30
STAMP="$(date +%Y%m%d-%H%M%S)"
DEST="$BACKUP_DIR/engine.db.$STAMP"

install -d -m 0750 "$BACKUP_DIR"
test -f "$ENGINE_ROOT/engine.db" || {
    echo "engine.db not found at $ENGINE_ROOT (first run before init?)" >&2
    exit 1
}

"$ENGINE_ROOT/.venv/bin/python" - "$ENGINE_ROOT/engine.db" "$DEST" <<'PY'
import sqlite3, sys

src, dest = sys.argv[1], sys.argv[2]
source = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
target = sqlite3.connect(dest)
with target:
    source.backup(target)
target.close()
source.close()
print(f"backup ok: {dest}")
PY
chmod 0640 "$DEST"

# 保留窗口外的旧备份删除(按名字排序稳定;只删本脚本命名格式的文件)
find "$BACKUP_DIR" -maxdepth 1 -type f -name 'engine.db.*' \
    -mtime "+$RETAIN_DAYS" -delete

echo "retention: kept <= ${RETAIN_DAYS}d under $BACKUP_DIR"
