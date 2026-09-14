import os
import sys
import json
import sqlite3
import re
from datetime import datetime
from agy_tools.utils import emit_progress, emit_result, safe_jail_path
from agy_tools.modules import secure_tool

APP_DATA_DIR = os.path.expanduser("~/.gemini/antigravity-cli")
BRAIN_DIR = os.path.join(APP_DATA_DIR, "brain")
DB_PATH = os.path.join(APP_DATA_DIR, "conversation_summaries.db")

def get_brain_dir() -> str:
    return BRAIN_DIR

class SessionInspector:
    def __init__(self, brain_dir: str = None):
        self.brain_dir = brain_dir or BRAIN_DIR

    def inspect_session(self, session_id: str, limit: int = 100):
        t_path, real_id = get_transcript_path(session_id)
        if not t_path or not os.path.exists(t_path):
            return {
                "conversation_id": session_id,
                "transcript_file": None,
                "total_steps": 0,
                "total_user_turns": 0,
                "start_time": None,
                "last_time": None,
                "tool_counts": {},
                "user_turns": [],
                "last_assistant_snippet": ""
            }

        user_turns = []
        tool_counts = {}
        total_steps = 0
        start_time = None
        last_time = None
        last_assistant_response = ""

        with open(t_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                total_steps += 1
                try:
                    data = json.loads(line)
                    created_at = data.get("created_at")
                    if not start_time and created_at:
                        start_time = created_at
                    if created_at:
                        last_time = created_at

                    step_idx = data.get("step_index", total_steps)
                    step_type = data.get("type")
                    source = data.get("source")
                    content = data.get("content", "")
                    tool_calls = data.get("tool_calls", [])

                    if tool_calls:
                        for tc in tool_calls:
                            name = tc.get("name") or "unknown"
                            tool_counts[name] = tool_counts.get(name, 0) + 1

                    if step_type == "USER_INPUT" or source == "USER_EXPLICIT":
                        cleaned = clean_user_prompt(content)
                        user_turns.append({
                            "step_index": step_idx,
                            "time": created_at,
                            "text": cleaned
                        })
                    elif step_type == "PLANNER_RESPONSE" and content:
                        last_assistant_response = content
                except Exception:
                    pass

        return {
            "conversation_id": real_id,
            "transcript_file": t_path,
            "total_steps": total_steps,
            "total_user_turns": len(user_turns),
            "start_time": start_time,
            "last_time": last_time,
            "tool_counts": tool_counts,
            "user_turns": user_turns,
            "last_assistant_snippet": last_assistant_response[:400] if last_assistant_response else ""
        }

    def diff_turn(self, session_id: str, turn_index: int = -1):
        t_path, real_id = get_transcript_path(session_id)
        if not t_path or not os.path.exists(t_path):
            return {
                "error": f"Sessiya transkripti topilmadi: {session_id}"
            }

        records = []
        with open(t_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass

        user_turn_indices = []
        for i, r in enumerate(records):
            if r.get("type") == "USER_INPUT" or r.get("source") == "USER_EXPLICIT":
                user_turn_indices.append(i)

        if not user_turn_indices:
            return {"error": "Sessiyada foydalanuvchi so'rovlari topilmadi."}

        if turn_index < 0:
            target_idx = len(user_turn_indices) + turn_index
        else:
            target_idx = turn_index

        if target_idx < 0 or target_idx >= len(user_turn_indices):
            return {"error": f"Noto'g'ri turn indeksi: {turn_index}. Mavjud turnlar: 0 dan {len(user_turn_indices)-1} gacha."}

        start_rec_idx = user_turn_indices[target_idx]
        end_rec_idx = user_turn_indices[target_idx + 1] if target_idx + 1 < len(user_turn_indices) else len(records)

        turn_records = records[start_rec_idx:end_rec_idx]
        user_prompt_rec = records[start_rec_idx]
        prompt_text = clean_user_prompt(user_prompt_rec.get("content", ""))

        start_time = user_prompt_rec.get("created_at")
        last_rec = turn_records[-1] if turn_records else user_prompt_rec
        end_time = last_rec.get("created_at")

        duration_sec = 0
        if start_time and end_time:
            try:
                t1 = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                t2 = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
                duration_sec = max(0, int((t2 - t1).total_seconds()))
            except Exception:
                pass

        tool_counts = {}
        total_chars = 0
        steps_count = len(turn_records)
        last_assistant_snippet = ""

        for r in turn_records:
            content = r.get("content") or ""
            thinking = r.get("thinking") or ""
            tool_calls = r.get("tool_calls") or []
            total_chars += len(content) + len(thinking) + len(str(tool_calls))
            if tool_calls:
                for tc in tool_calls:
                    name = tc.get("name") or tc.get("function", {}).get("name") or "unknown"
                    tool_counts[name] = tool_counts.get(name, 0) + 1
            if r.get("type") == "PLANNER_RESPONSE" and content:
                last_assistant_snippet = content

        est_tokens = round(total_chars / 3.8)

        return {
            "conversation_id": real_id,
            "turn_index": target_idx,
            "total_turns": len(user_turn_indices),
            "prompt": prompt_text,
            "start_time": start_time,
            "end_time": end_time,
            "duration_seconds": duration_sec,
            "steps_in_turn": steps_count,
            "tool_counts": tool_counts,
            "total_chars": total_chars,
            "estimated_tokens": est_tokens,
            "last_assistant_snippet": last_assistant_snippet[:300] if last_assistant_snippet else ""
        }

    def list_sessions(self, limit: int = 15, search: str = None):
        sessions = []
        if os.path.exists(DB_PATH):
            try:
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                if search:
                    query = """
                        SELECT conversation_id, title, preview, step_count, last_modified_time, agent_name
                        FROM conversation_summaries
                        WHERE conversation_id LIKE ? OR title LIKE ? OR preview LIKE ?
                        ORDER BY last_modified_time DESC LIMIT ?
                    """
                    c.execute(query, (f"%{search}%", f"%{search}%", f"%{search}%", limit))
                else:
                    query = """
                        SELECT conversation_id, title, preview, step_count, last_modified_time, agent_name
                        FROM conversation_summaries
                        ORDER BY last_modified_time DESC LIMIT ?
                    """
                    c.execute(query, (limit,))
                rows = c.fetchall()
                for r in rows:
                    sessions.append({
                        "conversation_id": r[0],
                        "title": r[1] or "(Nomsiz)",
                        "preview": (r[2] or "").replace("\n", " ")[:60],
                        "step_count": r[3] or 0,
                        "last_modified": r[4] or "",
                        "agent": r[5] or "default"
                    })
                conn.close()
            except Exception:
                pass

        if not sessions and os.path.exists(self.brain_dir):
            dirs = os.listdir(self.brain_dir)
            for d in sorted(dirs, key=lambda x: os.path.getmtime(os.path.join(self.brain_dir, x)) if os.path.exists(os.path.join(self.brain_dir, x)) else 0, reverse=True)[:limit]:
                d_path = os.path.join(self.brain_dir, d)
                if os.path.isdir(d_path):
                    sessions.append({
                        "conversation_id": d,
                        "title": "(Brain Dir)",
                        "preview": "",
                        "step_count": 0,
                        "last_modified": datetime.fromtimestamp(os.path.getmtime(d_path)).isoformat(),
                        "agent": "unknown"
                    })
        return sessions


def get_session_describe():
    return {
        "name": "session",
        "description": "Antigravity (AGY) sessiyalari va transkriptlarini yuqori tezlikda tahlil qilish, qidirish va eksport qilish vositasi.",
        "commands": {
            "list": "Mavjud AGY sessiyalari ro'yxatini ko'rish (ID, sarlavha, qadamlar, oxirgi vaqt)",
            "inspect": "Ko'rsatilgan sessiyaning barcha muloqotlari, foydalanuvchi so'rovlari va tool qo'llanish statistikasini tahlil qilish",
            "query": "Sessiya transkripti ichidan kalit so'z bo'yicha tezkor qidirish",
            "export": "Sessiya muloqotini toza va xavfsiz (sirlar maskalangan) Markdown/JSON formatida saqlash"
        }
    }

def clean_user_prompt(text: str) -> str:
    """Extracts clean user prompt, removing telegram/system wrappers and metadata."""
    if not text:
        return ""
    # Extract [USER REQUEST]: if present
    match = re.search(r"\[USER REQUEST\]:\s*(.*)", text, re.DOTALL)
    cleaned = match.group(1).strip() if match else text.strip()
    cleaned = cleaned.replace("</USER_REQUEST>", "").strip()
    # Strip metadata tags
    cleaned = re.sub(r"<ADDITIONAL_METADATA>.*?</ADDITIONAL_METADATA>", "", cleaned, flags=re.DOTALL).strip()
    cleaned = re.sub(r"<SYSTEM_MESSAGE>.*?</SYSTEM_MESSAGE>", "", cleaned, flags=re.DOTALL).strip()
    return cleaned

def get_transcript_path(session_id: str) -> str:
    """Finds the transcript.jsonl or transcript_full.jsonl for a given session ID."""
    session_id = session_id.strip()
    session_brain = os.path.join(BRAIN_DIR, session_id)
    if not os.path.exists(session_brain):
        # Try finding as partial match in brain dir
        if os.path.exists(BRAIN_DIR):
            for d in os.listdir(BRAIN_DIR):
                if d.startswith(session_id) or session_id in d:
                    session_brain = os.path.join(BRAIN_DIR, d)
                    session_id = d
                    break

    t_path = os.path.join(session_brain, ".system_generated", "logs", "transcript.jsonl")
    if not os.path.exists(t_path):
        t_path_full = os.path.join(session_brain, ".system_generated", "logs", "transcript_full.jsonl")
        if os.path.exists(t_path_full):
            return t_path_full, session_id
        return None, session_id
    return t_path, session_id

def run_session_list(args):
    """List recent AGY sessions from SQLite database or brain directory."""
    emit_progress("Listing Sessions", 10, "Sessiyalar ma'lumotlar bazasi tekshirilmoqda...")
    limit = getattr(args, "limit", 15) or 15
    search = getattr(args, "search", None)
    out_format = "table" if getattr(args, "table", False) else getattr(args, "format", "table")

    sessions = []
    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            if search:
                query = """
                    SELECT conversation_id, title, preview, step_count, last_modified_time, agent_name
                    FROM conversation_summaries
                    WHERE conversation_id LIKE ? OR title LIKE ? OR preview LIKE ?
                    ORDER BY last_modified_time DESC LIMIT ?
                """
                c.execute(query, (f"%{search}%", f"%{search}%", f"%{search}%", limit))
            else:
                query = """
                    SELECT conversation_id, title, preview, step_count, last_modified_time, agent_name
                    FROM conversation_summaries
                    ORDER BY last_modified_time DESC LIMIT ?
                """
                c.execute(query, (limit,))
            rows = c.fetchall()
            for r in rows:
                sessions.append({
                    "conversation_id": r[0],
                    "title": r[1] or "(Nomsiz)",
                    "preview": (r[2] or "").replace("\n", " ")[:60],
                    "step_count": r[3] or 0,
                    "last_modified": r[4] or "",
                    "agent": r[5] or "default"
                })
            conn.close()
        except Exception as e:
            pass

    if not sessions and os.path.exists(BRAIN_DIR):
        dirs = os.listdir(BRAIN_DIR)
        for d in sorted(dirs, key=lambda x: os.path.getmtime(os.path.join(BRAIN_DIR, x)) if os.path.exists(os.path.join(BRAIN_DIR, x)) else 0, reverse=True)[:limit]:
            d_path = os.path.join(BRAIN_DIR, d)
            if os.path.isdir(d_path):
                sessions.append({
                    "conversation_id": d,
                    "title": "(Brain Dir)",
                    "preview": "",
                    "step_count": 0,
                    "last_modified": datetime.fromtimestamp(os.path.getmtime(d_path)).isoformat(),
                    "agent": "unknown"
                })

    emit_progress("Listing Sessions", 100, f"{len(sessions)} ta sessiya topildi.")

    if out_format == "json":
        emit_result({"count": len(sessions), "sessions": sessions})
        return

    # Render ASCII Table
    lines = []
    lines.append(f"{'#':<3} | {'CONVERSATION ID':<36} | {'STEPS':<6} | {'LAST MODIFIED':<19} | {'TITLE / PREVIEW'}")
    lines.append("-" * 110)
    for i, s in enumerate(sessions, 1):
        dt_str = s["last_modified"][:19] if s["last_modified"] else "N/A"
        title_prev = (s["title"] + " - " + s["preview"]).strip(" - ")[:45]
        lines.append(f"{i:<3} | {s['conversation_id']:<36} | {s['step_count']:<6} | {dt_str:<19} | {title_prev}")

    table_output = "\n".join(lines)
    print(table_output)
    emit_result({"count": len(sessions), "table": table_output, "sessions": sessions})

def run_session_inspect(args):
    """Inspects a session transcript and extracts user prompts, tool statistics, and assistant conclusions."""
    session_id = getattr(args, "session_id_arg", None) or getattr(args, "session_id", None)
    if not session_id:
        emit_result(None, success=False, error="Sessiya ID ko'rsatilmadi! Masalan: agy-tool session inspect <session_id>")
        return

    t_path, real_id = get_transcript_path(session_id)
    if not t_path or not os.path.exists(t_path):
        emit_result(None, success=False, error=f"Sessiya transkripti topilmadi: {session_id}")
        return

    emit_progress("Parsing Transcript", 15, f"{real_id} transkripti o'rganilmoqda...")

    limit = getattr(args, "limit", 10)
    show_full = getattr(args, "full", False)
    out_format = "table" if getattr(args, "table", False) else getattr(args, "format", "table")

    user_turns = []
    tool_counts = {}
    total_steps = 0
    start_time = None
    last_time = None
    last_assistant_response = ""

    with open(t_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            total_steps += 1
            try:
                data = json.loads(line)
                created_at = data.get("created_at")
                if not start_time and created_at:
                    start_time = created_at
                if created_at:
                    last_time = created_at

                step_idx = data.get("step_index", total_steps)
                step_type = data.get("type")
                source = data.get("source")
                content = data.get("content", "")
                tool_calls = data.get("tool_calls", [])

                if tool_calls:
                    for tc in tool_calls:
                        name = tc.get("name") or "unknown"
                        tool_counts[name] = tool_counts.get(name, 0) + 1

                if step_type == "USER_INPUT" or source == "USER_EXPLICIT":
                    cleaned = clean_user_prompt(content)
                    user_turns.append({
                        "step_index": step_idx,
                        "time": created_at,
                        "text": cleaned
                    })
                elif step_type == "PLANNER_RESPONSE" and content:
                    last_assistant_response = content
            except Exception:
                pass

    displayed_turns = user_turns if (show_full or limit is None) else user_turns[-limit:]

    res_data = {
        "conversation_id": real_id,
        "transcript_file": t_path,
        "total_steps": total_steps,
        "total_user_turns": len(user_turns),
        "start_time": start_time,
        "last_time": last_time,
        "tool_counts": tool_counts,
        "user_turns": displayed_turns,
        "last_assistant_snippet": last_assistant_response[:400] if last_assistant_response else ""
    }

    emit_progress("Parsing Transcript", 100, f"{len(user_turns)} ta so'rov va {total_steps} ta qadam tahlil qilindi.")

    if out_format == "json":
        emit_result(res_data)
        return

    # Table / Summary Output
    lines = []
    lines.append(f"=== SESSIYA TAHLILI: {real_id} ===")
    lines.append(f"⏱ Boshlanish: {start_time or 'N/A'} | Oxirgi: {last_time or 'N/A'}")
    lines.append(f"📊 Jami qadamlar: {total_steps} | Foydalanuvchi so'rovlari: {len(user_turns)}")
    
    if tool_counts:
        lines.append("\n🛠 Ishlatilgan vositalar (Tool calls):")
        for tool_name, count in sorted(tool_counts.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"  • {tool_name:<20}: {count} marta")

    lines.append(f"\n💬 Foydalanuvchi so'rovlari ({len(displayed_turns)}/{len(user_turns)} ko'rsatilmoqda):")
    for turn in displayed_turns:
        idx = turn.get("step_index", "?")
        t_str = turn.get("time", "")[:19]
        preview_txt = turn.get("text", "").replace("\n", " ")[:120]
        lines.append(f"  [{idx:>4}] ({t_str}): {preview_txt}")

    if last_assistant_response:
        lines.append("\n🏁 Oxirgi Javobdan Parvoza:")
        lines.append(f"  {last_assistant_response[:300].replace(chr(10), ' ')}...")

    summary_text = "\n".join(lines)
    print(summary_text)
    emit_result(res_data)

def run_session_query(args):
    """Searches for a keyword inside a session transcript."""
    session_id = getattr(args, "session_id_arg", None) or getattr(args, "session_id", None)
    query = getattr(args, "query", "")
    if not session_id or not query:
        emit_result(None, success=False, error="Sessiya ID va qidiruv so'zi talab qilinadi! Masalan: agy-tool session query <session_id> <keyword>")
        return

    t_path, real_id = get_transcript_path(session_id)
    if not t_path or not os.path.exists(t_path):
        emit_result(None, success=False, error=f"Sessiya transkripti topilmadi: {session_id}")
        return

    emit_progress("Searching Transcript", 20, f"'{query}' qidirilmoqda...")
    matches = []
    query_lower = query.lower()
    total_steps = 0

    with open(t_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            total_steps += 1
            try:
                data = json.loads(line)
                content = data.get("content", "")
                if query_lower in content.lower():
                    step_idx = data.get("step_index", total_steps)
                    step_type = data.get("type", "UNKNOWN")
                    source = data.get("source", "")
                    created_at = data.get("created_at", "")
                    # Extract small snippet around match
                    idx = content.lower().find(query_lower)
                    start = max(0, idx - 40)
                    end = min(len(content), idx + len(query) + 40)
                    snippet = content[start:end].replace("\n", " ").strip()
                    matches.append({
                        "step_index": step_idx,
                        "type": step_type,
                        "source": source,
                        "time": created_at,
                        "snippet": f"...{snippet}..."
                    })
            except Exception:
                pass

    emit_progress("Searching Transcript", 100, f"{len(matches)} ta moslik topildi.")
    out_format = getattr(args, "format", "table")
    if out_format == "json":
        emit_result({"conversation_id": real_id, "query": query, "match_count": len(matches), "matches": matches})
        return

    print(f"=== SESSIYA QIDIRUV NATIJALARI: '{query}' ({len(matches)} ta topildi) ===")
    for m in matches[:25]:
        print(f"[{m['step_index']:>4}] ({m['type']}) {m['time'][:19]}: {m['snippet']}")
    if len(matches) > 25:
        print(f"... va yana {len(matches) - 25} ta moslik mavjud.")

    emit_result({"conversation_id": real_id, "query": query, "match_count": len(matches), "matches": matches})

def run_session_export(args):
    """Exports session dialog cleanly into a sanitized Markdown or JSON file."""
    session_id = getattr(args, "session_id_arg", None) or getattr(args, "session_id", None)
    if not session_id:
        emit_result(None, success=False, error="Sessiya ID ko'rsatilmadi! Masalan: agy-tool session export <session_id>")
        return

    t_path, real_id = get_transcript_path(session_id)
    if not t_path or not os.path.exists(t_path):
        emit_result(None, success=False, error=f"Sessiya transkripti topilmadi: {session_id}")
        return

    emit_progress("Exporting Session", 20, "Transkript tozalash va formatlash boshlandi...")

    output_path = getattr(args, "output", None)
    out_fmt = getattr(args, "format", "md").lower()
    no_redact = getattr(args, "no_redact", False)

    dialogue = []
    with open(t_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            try:
                data = json.loads(line)
                step_type = data.get("type")
                source = data.get("source")
                content = data.get("content", "")
                step_idx = data.get("step_index")
                created_at = data.get("created_at")

                if step_type == "USER_INPUT" or source == "USER_EXPLICIT":
                    cleaned = clean_user_prompt(content)
                    if not no_redact:
                        cleaned, _ = secure_tool.redact_text(cleaned)
                    dialogue.append({
                        "role": "USER",
                        "step": step_idx,
                        "time": created_at,
                        "content": cleaned
                    })
                elif step_type == "PLANNER_RESPONSE" and content:
                    resp = content
                    if not no_redact:
                        resp, _ = secure_tool.redact_text(resp)
                    dialogue.append({
                        "role": "ASSISTANT",
                        "step": step_idx,
                        "time": created_at,
                        "content": resp
                    })
            except Exception:
                pass

    if not output_path:
        output_dir = os.path.expanduser("~/Desktop/agy_tasks/exports")
        os.makedirs(output_dir, exist_ok=True)
        ext = "json" if out_fmt == "json" else "md"
        output_path = os.path.join(output_dir, f"session_{real_id[:8]}.{ext}")

    safe_target = safe_jail_path(output_path)
    os.makedirs(os.path.dirname(safe_target), exist_ok=True)

    if out_fmt == "json":
        with open(safe_target, "w", encoding="utf-8") as out_f:
            json.dump({
                "conversation_id": real_id,
                "exported_at": datetime.utcnow().isoformat(),
                "dialogue_turns": len(dialogue),
                "dialogue": dialogue
            }, out_f, indent=2, ensure_ascii=False)
    else:
        with open(safe_target, "w", encoding="utf-8") as out_f:
            out_f.write(f"# 📜 Antigravity Sessiya Hisoboti: `{real_id}`\n\n")
            out_f.write(f"- **Eksport vaqti:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
            out_f.write(f"- **Jami muloqot bosqichlari:** {len(dialogue)}\n\n---\n\n")
            for item in dialogue:
                role_icon = "👤 **FOYDALANUVCHI**" if item["role"] == "USER" else "🤖 **JARVIS AI ASSISTANT**"
                t_str = item.get("time", "")[:19]
                out_f.write(f"### {role_icon} `[Qadam #{item['step']} | {t_str}]`\n\n")
                out_f.write(f"{item['content']}\n\n---\n\n")

    emit_progress("Exporting Session", 100, f"Hisobot saqlandi: {safe_target}")
    emit_result({
        "conversation_id": real_id,
        "exported_file": safe_target,
        "turns_count": len(dialogue),
        "format": out_fmt
    })


def run_session_diff(args):
    """Analyze execution time, steps and token consumption for a single turn."""
    session_id = getattr(args, "session_id_arg", None)
    if not session_id:
        emit_result(None, success=False, error="Sessiya ID ko'rsatilmadi!")
        return

    turn_idx = -1
    if hasattr(args, "turn") and args.turn is not None:
        turn_idx = args.turn - 1  # 1-indexed to 0-indexed

    out_fmt = getattr(args, "format", "table")
    emit_progress("Analyzing Turn Diff", 15, f"{session_id} sessiyasi turn tahlili boshlanmoqda...")
    
    inspector = SessionInspector()
    result = inspector.diff_turn(session_id, turn_idx)
    
    if "error" in result:
        emit_result(None, success=False, error=result["error"])
        return

    emit_progress("Analyzing Turn Diff", 100, "Turn tahlili yakunlandi.")

    if out_fmt == "table":
        m, s = divmod(result["duration_seconds"], 60)
        dur_str = f"{m}m {s}s" if m > 0 else f"{s}s"
        print(f"\n=== VAZIFA METRIKASI: {result['conversation_id']} (Turn #{result['turn_index'] + 1}/{result['total_turns']}) ===")
        print(f"💬 Prompt: \"{result['prompt'][:100]}\"")
        print(f"⏱ Vaqt: {result['start_time']} -> {result['end_time']} (Davomiyligi: {dur_str})")
        print(f"📑 Qadamlar soni (Steps): {result['steps_in_turn']} ta")
        print(f"🧠 Taxminiy token sarfi: ~{result['estimated_tokens']:,} token ({result['total_chars']:,} belgi)")
        print("\n🛠 Ishlatilgan vositalar:")
        if result["tool_counts"]:
            for k, v in sorted(result["tool_counts"].items(), key=lambda x: x[1], reverse=True):
                print(f"  • {k:<22}: {v} marta")
        else:
            print("  • (To'g'ridan-to'g'ri javob / Instrumentlar ishlatilmagan)")
        print("-" * 75)

    emit_result(result)

