#!/usr/bin/env bash
# ==========================================================
# fayzillo-agy-tools Universal Install Script
# ==========================================================
set -e

INSTALL_DIR="$HOME/.local/bin"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🚀 fayzillo-agy-tools o'rnatilmoqda..."

mkdir -p "$INSTALL_DIR"
mkdir -p "$HOME/.local/state/agy-tool"

# 1. Check Python 3
if ! command -v python3 &> /dev/null; then
    echo "❌ Xatolik: Python 3 topilmadi! Iltimos, python3 o'rnating."
    exit 1
fi

# 2. Check & Install Python Dependencies (if pip available)
if [ -f "$SOURCE_DIR/requirements.txt" ]; then
    echo "📦 Python bog'liqliklarini tekshirish..."
    if command -v pip3 &> /dev/null; then
        pip3 install -q -r "$SOURCE_DIR/requirements.txt" 2>/dev/null || pip install -q -r "$SOURCE_DIR/requirements.txt" 2>/dev/null || echo "⚠️ Eslatma: pip orqali o'rnatishda xatolik bo'ldi. Qo'lda 'pip install -r requirements.txt' qiling."
    fi
fi

# 3. Create .env if not exists
if [ ! -f "$SOURCE_DIR/.env" ] && [ -f "$SOURCE_DIR/.env.example" ]; then
    cp "$SOURCE_DIR/.env.example" "$SOURCE_DIR/.env"
    echo "📄 .env fayli yaratildi ($SOURCE_DIR/.env)"
fi

# 4. Make CLI executable
chmod +x "$SOURCE_DIR/bin/agy-tool"

# 5. Create launcher in ~/.local/bin/agy-tool
cat << 'LAUNCHER_EOF' > "$INSTALL_DIR/agy-tool"
#!/usr/bin/env bash
TOOL_ENTRY="$HOME/Desktop/fayzillo-agy-tools/bin/agy-tool"

if [ -f "$TOOL_ENTRY" ]; then
  exec "$TOOL_ENTRY" "$@"
else
  echo "{\"success\": false, \"error\": \"agy-tool executable topilmadi: $TOOL_ENTRY\"}" >&2
  exit 1
fi
LAUNCHER_EOF

chmod +x "$INSTALL_DIR/agy-tool"

# 6. Check system dependencies
echo "🔍 Tizim yordamchi vositalarini tekshirish:"
for cmd in ffmpeg ffprobe tesseract docker; do
    if command -v $cmd &> /dev/null; then
        echo "  ✅ $cmd: o'rnatilgan"
    else
        echo "  ⚠️ $cmd: topilmadi (ixtiyoriy media/OCR/probe modullari uchun kerak)"
    fi
done

echo ""
echo "✅ O'rnatish muvaffaqiyatli yakunlandi!"
echo "📍 Joylashuvi: $INSTALL_DIR/agy-tool"
echo "🧪 Tekshirish: agy-tool --describe"
