import os
import sys
import subprocess
from agy_tools.utils import emit_progress, emit_result, safe_jail_path

DEFAULT_HANDLERS_DIR = "/home/fayzillo/Desktop/sessiya_connector/bot/handlers"

def get_bot_describe():
    return {
        "name": "bot",
        "description": "JarvisOS Telegram Bot dinamik modullari (handlers)ni boshqarish, yangi buyruq qo'shish va tekshirish vositasi.",
        "commands": {
            "list": "Botdagi barcha faol dinamik plaginlar va handlerlarni ko'rish",
            "add": "Yangi izolyatsiyalangan modulli buyruq (handler) faylini xavfsiz yaratish",
            "remove": "Modulli buyruq faylini xavfsiz o'chirish",
            "check": "Barcha handler fayllari sintaksisi va tuzilmasini tekshirish"
        }
    }

def list_handlers(handlers_dir=DEFAULT_HANDLERS_DIR):
    emit_progress("Handlers Scan", 30, "Handlerlar ro'yxati olinmoqda...")
    if not os.path.exists(handlers_dir):
        return emit_result({"handlers": [], "count": 0, "path": handlers_dir}, success=True)

    files = [f for f in os.listdir(handlers_dir) if f.endswith(".js")]
    handlers = []

    for f in sorted(files):
        full_path = os.path.join(handlers_dir, f)
        stats = os.stat(full_path)
        # Fayl ichidan name va descriptionni sodda tahlil qilish
        desc = ""
        name = f.replace(".js", "")
        cmd_type = "command"
        try:
            with open(full_path, "r", encoding="utf-8", errors="ignore") as fp:
                content = fp.read()
                for line in content.splitlines():
                    if "description:" in line:
                        desc = line.split("description:", 1)[1].strip(" '\",")
                    if "type:" in line:
                        cmd_type = line.split("type:", 1)[1].strip(" '\",")
        except Exception:
            pass

        handlers.append({
            "file": f,
            "name": name,
            "type": cmd_type,
            "description": desc,
            "size_bytes": stats.st_size,
            "modified_time": stats.st_mtime
        })

    emit_progress("Done", 100, "Handlerlar ro'yxati tayyor.")
    return emit_result({
        "handlers_dir": handlers_dir,
        "count": len(handlers),
        "handlers": handlers
    }, success=True)

def add_handler(name, cmd_type="command", description="", handlers_dir=DEFAULT_HANDLERS_DIR):
    emit_progress("Adding Handler", 30, f"Yangi handler yaratilmoqda: {name}...")
    if "/" in name or "\\" in name or ".." in name:
        raise PermissionError(f"Xavfsizlik cheklovi: Yaroqsiz handler nomi yoki path traversal aniqlandi: '{name}'")
        
    safe_name = "".join(c for c in name.replace(".js", "") if c.isalnum() or c in "_-").lower()
    if not safe_name:
        return emit_result(None, success=False, error="Yaroqsiz handler nomi.")

    os.makedirs(handlers_dir, exist_ok=True)
    target_file = safe_jail_path(os.path.join(handlers_dir, f"{safe_name}.js"), base_dir=handlers_dir)

    real_handlers_dir = os.path.realpath(handlers_dir)
    real_target_file = os.path.realpath(target_file)
    if not real_target_file.startswith(real_handlers_dir + os.sep) and real_target_file != real_handlers_dir:
        raise PermissionError(f"Xavfsizlik cheklovi: Handler fayli ruxsat etilgan papkadan tashqarida: '{target_file}'")

    if os.path.exists(target_file):
        return emit_result(None, success=False, error=f"Handler allaqachon mavjud: {safe_name}.js")

    desc_str = description or f"{safe_name} komandasi"

    template = f"""// ==========================================
// JarvisOS Modular Handler: /{safe_name}
// ==========================================

module.exports = {{
  name: '{safe_name}',
  type: '{cmd_type}',
  description: '{desc_str}',
  async execute(ctx, helpers) {{
    // Komanda mantiqi shu yerga yoziladi
    await ctx.reply('✅ /{safe_name} komandasi muvaffaqiyatli bajarildi!');
  }}
}};
"""

    with open(target_file, "w", encoding="utf-8") as f:
        f.write(template)

    # Sintaksis tekshirish
    try:
        subprocess.run(["node", "--check", target_file], check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        os.remove(target_file)
        return emit_result(None, success=False, error=f"Yaratilgan handler sintaksis tekshiruvidan o'tmadi: {e.stderr}")

    emit_progress("Done", 100, f"Handler {safe_name}.js yaratildi.")
    return emit_result({
        "name": safe_name,
        "file": f"{safe_name}.js",
        "path": target_file,
        "type": cmd_type,
        "description": desc_str
    }, success=True)

def remove_handler(name, handlers_dir=DEFAULT_HANDLERS_DIR):
    emit_progress("Removing Handler", 30, f"Handler o'chirilmoqda: {name}...")
    if "/" in name or "\\" in name or ".." in name:
        raise PermissionError(f"Xavfsizlik cheklovi: Yaroqsiz handler nomi yoki path traversal aniqlandi: '{name}'")

    safe_name = "".join(c for c in name.replace(".js", "") if c.isalnum() or c in "_-").lower()
    if not safe_name:
        return emit_result(None, success=False, error="Yaroqsiz handler nomi.")

    target_file = safe_jail_path(os.path.join(handlers_dir, f"{safe_name}.js"), base_dir=handlers_dir)

    real_handlers_dir = os.path.realpath(handlers_dir)
    real_target_file = os.path.realpath(target_file)
    if not real_target_file.startswith(real_handlers_dir + os.sep) and real_target_file != real_handlers_dir:
        raise PermissionError(f"Xavfsizlik cheklovi: Handler fayli ruxsat etilgan papkadan tashqarida: '{target_file}'")

    if not os.path.exists(target_file):
        return emit_result(None, success=False, error=f"Bunday handler fayli topilmadi: {safe_name}.js")

    os.remove(target_file)
    emit_progress("Done", 100, f"{safe_name}.js o'chirildi.")
    return emit_result({
        "deleted": safe_name,
        "file": f"{safe_name}.js"
    }, success=True)

def check_handlers(handlers_dir=DEFAULT_HANDLERS_DIR):
    emit_progress("Checking Handlers", 30, "Barcha handlerlar sintaksisi tekshirilmoqda...")
    if not os.path.exists(handlers_dir):
        return emit_result({"checks": [], "all_pass": True}, success=True)

    files = [f for f in os.listdir(handlers_dir) if f.endswith(".js")]
    checks = []
    all_pass = True

    for f in sorted(files):
        full_path = os.path.join(handlers_dir, f)
        try:
            res = subprocess.run(["node", "--check", full_path], check=True, capture_output=True, text=True)
            checks.append({"file": f, "status": "PASS", "error": None})
        except subprocess.CalledProcessError as e:
            all_pass = False
            checks.append({"file": f, "status": "FAIL", "error": e.stderr.strip()})

    emit_progress("Done", 100, "Tekshiruv yakunlandi.")
    return emit_result({
        "all_pass": all_pass,
        "count": len(checks),
        "checks": checks
    }, success=True)
