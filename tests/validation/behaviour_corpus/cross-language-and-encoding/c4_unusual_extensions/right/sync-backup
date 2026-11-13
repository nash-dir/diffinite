#!/usr/bin/env bash
# sync_backup.sh - nightly incremental backup with rotation.
# Usage: sync_backup.sh <source_dir> <backup_root> [keep_days]
set -euo pipefail

SRC="${1:?source directory required}"
DEST_ROOT="${2:?backup root required}"
KEEP_DAYS="${3:-14}"
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="${DEST_ROOT}/backup.log"
LOCK_FILE="/tmp/sync_backup.lock"

log() {
    # timestamped log line to both stdout and the log file
    printf '%s [%s] %s\n' "$(date '+%F %T')" "$1" "$2" | tee -a "$LOG_FILE"
}

acquire_lock() {
    if [ -e "$LOCK_FILE" ]; then
        local pid
        pid="$(cat "$LOCK_FILE")"
        if kill -0 "$pid" 2>/dev/null; then
            log ERROR "another backup is running (pid $pid)"
            exit 2
        fi
        log WARN "stale lock from pid $pid removed"
    fi
    echo $$ > "$LOCK_FILE"
    trap 'rm -f "$LOCK_FILE"' EXIT
}

latest_snapshot() {
    find "$DEST_ROOT" -maxdepth 1 -type d -name 'snap-*' | sort | tail -n 1
}

make_snapshot() {
    local prev target
    prev="$(latest_snapshot)"
    target="${DEST_ROOT}/snap-${STAMP}"
    if [ -n "$prev" ]; then
        log INFO "incremental against $(basename "$prev")"
        rsync -a --delete --link-dest="$prev" "$SRC/" "$target/"
    else
        log INFO "first full snapshot"
        rsync -a "$SRC/" "$target/"
    fi
    du -sh "$target" | awk '{print $1}' > "$target/.size"
    log INFO "snapshot $(basename "$target") size $(cat "$target/.size")"
}

rotate_old() {
    local removed=0
    while IFS= read -r dir; do
        rm -rf -- "$dir"
        removed=$((removed + 1))
        log INFO "rotated out $(basename "$dir")"
    done < <(find "$DEST_ROOT" -maxdepth 1 -type d -name 'snap-*' -mtime "+${KEEP_DAYS}")
    log INFO "rotation removed ${removed} snapshot(s)"
}

main() {
    mkdir -p "$DEST_ROOT"
    acquire_lock
    log INFO "backup of $SRC starting"
    make_snapshot
    rotate_old
    log INFO "backup finished"
}

main "$@"
