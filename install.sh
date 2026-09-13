#!/usr/bin/env bash
# ==========================================================
# fayzillo-agy-tools Universal Installer
# ==========================================================
set -e

INSTALL_DIR="$HOME/.local/bin"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🚀 [1/3] fayzillo-agy-tools o'rnatilmoqda..."
echo "📂 Manba katalogi: $SOURCE_DIR"

# 1. Tizim talablarini tekshirish
if ! command -v python3 &> /dev/null; then
    echo "❌ Xato: python3 topilmadi. Iltimos Python 3.10+ o'rnating."
    exit 1
fi

if ! command -v ffmpeg &> /dev/null; then
    echo "⚠️ Ogohlantirish: ffmpeg topilmadi. Video/Audio tahlili uchun 'sudo apt install ffmpeg' tavsiya etiladi."
fi

# 2. Python bog'liqliklarini o'rnatish
echo "📦 [2/3] Python kutubxonalari tekshirilmoqda..."
if [ -f "$SOURCE_DIR/requirements.txt" ]; then
    python3 -m pip install --break-system-packages --quiet -r "$SOURCE_DIR/requirements.txt" 2>/dev/null || \
    python3 -m pip install --user --quiet -r "$SOURCE_DIR/requirements.txt" 2>/dev/null || \
    python3 -m pip install -r "$SOURCE_DIR/requirements.txt"
fi

# 3. ~/.local/bin/agy-tool skriptini yaratish
echo "⚙️ [3/3] Global CLI binarini ulash (~/.local/bin/agy-tool)..."
mkdir -p "$INSTALL_DIR"
chmod +x "$SOURCE_DIR/bin/agy-tool"

cat << EOF > "$INSTALL_DIR/agy-tool"
#!/usr/bin/env bash
exec "$SOURCE_DIR/bin/agy-tool" "\$@"
EOF

chmod +x "$INSTALL_DIR/agy-tool"

# PATH tekshiruvi
if [[ ":\$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo "ℹ️ Eslatma: ~/.local/bin sizning PATH muhitingizga qo'shilishi kerak:"
    echo '   export PATH="\$HOME/.local/bin:\$PATH"'
fi

echo "=========================================================="
echo "✅ fayzillo-agy-tools v1.5.0 muvaffaqiyatli o'rnatildi!"
echo "Tekshirish: agy-tool --describe"
echo "=========================================================="
