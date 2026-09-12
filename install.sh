#!/usr/bin/env bash
# ==========================================================
# fayzillo-agy-tools Install Script
# ==========================================================
set -e

INSTALL_DIR="$HOME/.local/bin"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🚀 fayzillo-agy-tools o'rnatilmoqda..."

mkdir -p "$INSTALL_DIR"

# Symlink or copy
chmod +x "$SOURCE_DIR/bin/agy-tool"

# Create launcher in ~/.local/bin/agy-tool
cat << 'EOF' > "$INSTALL_DIR/agy-tool"
#!/usr/bin/env bash
SCRIPT_DIR="$(dirname "$(realpath "$0")")"
# If cloned in Desktop or specific directory:
TOOL_ENTRY="$HOME/Desktop/fayzillo-agy-tools/bin/agy-tool"
if [ ! -f "$TOOL_ENTRY" ]; then
  TOOL_ENTRY="$HOME/Desktop/agy_tasks/dynamic_agy_toolsuite/work/fayzillo-agy-tools/bin/agy-tool"
fi

if [ -f "$TOOL_ENTRY" ]; then
  exec "$TOOL_ENTRY" "$@"
else
  echo '{"success": false, "error": "agy-tool executable topilmadi!"}' >&2
  exit 1
fi
EOF

chmod +x "$INSTALL_DIR/agy-tool"

echo "✅ O'rnatish muvaffaqiyatli yakunlandi!"
echo "Tekshirish: agy-tool --describe"
