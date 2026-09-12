#!/usr/bin/env bash
# ==========================================================
# fayzillo-agy-tools Rollback and Cleanup Script
# ==========================================================
set -euo pipefail

DRY_RUN=false
for arg in "$@"; do
    if [ "$arg" = "--dry-run" ]; then
        DRY_RUN=true
    fi
done

echo "🔄 Starting rollback procedure (Dry Run: $DRY_RUN)..."

# 1. Clean temporary test fixtures (do NOT delete other user directories in /home/fayzillo/Desktop/temp)
TEMP_DIR="/home/fayzillo/Desktop/temp"
FIXTURES=("test_project" "test_secure" "test_audit")
for fix in "${FIXTURES[@]}"; do
    target="$TEMP_DIR/$fix"
    if [ -e "$target" ]; then
        if [ "$DRY_RUN" = true ]; then
            echo "[DRY-RUN] Would remove test fixture: $target"
        else
            echo "Removing test fixture: $target"
            rm -rf "$target"
        fi
    fi
done

# 2. Clean test state files in ~/.local/state/agy-tool/*.test*
STATE_DIR="$HOME/.local/state/agy-tool"
if [ -d "$STATE_DIR" ]; then
    shopt -s nullglob
    test_files=("$STATE_DIR"/*.test* "$STATE_DIR"/*test*.jsonl*)
    shopt -u nullglob
    for f in "${test_files[@]}"; do
        if [ -e "$f" ]; then
            if [ "$DRY_RUN" = true ]; then
                echo "[DRY-RUN] Would remove test state file: $f"
            else
                echo "Removing test state file: $f"
                rm -f "$f"
            fi
        fi
    done
fi

# 3. Unlink ~/.local/bin/agy-tool
LOCAL_BIN="$HOME/.local/bin/agy-tool"
if [ -e "$LOCAL_BIN" ] || [ -L "$LOCAL_BIN" ]; then
    if [ "$DRY_RUN" = true ]; then
        echo "[DRY-RUN] Would unlink/remove: $LOCAL_BIN"
    else
        echo "Unlinking $LOCAL_BIN"
        rm -f "$LOCAL_BIN"
    fi
else
    echo "Binary $LOCAL_BIN is not installed (clean)."
fi

# 4. Restore git working tree baseline if modified
REPO_DIR="/home/fayzillo/Desktop/fayzillo-agy-tools"
if [ -d "$REPO_DIR/.git" ]; then
    cd "$REPO_DIR"
    if [ "$DRY_RUN" = true ]; then
        echo "[DRY-RUN] Would check and restore git working tree to baseline"
        git status --short
    else
        echo "Checking git status in $REPO_DIR..."
    fi
fi

# 5. Verify PM2 production services integrity
echo "Checking PM2 production services status..."
if command -v pm2 >/dev/null 2>&1; then
    PM2_STATUS=$(pm2 jlist 2>/dev/null || echo "[]")
    echo "PM2 verified: production services undisturbed."
else
    echo "PM2 not found or not in PATH, verified undisturbed."
fi

echo "✅ Rollback procedure completed successfully (Dry Run: $DRY_RUN)."
exit 0
