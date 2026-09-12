import os
import sys
import socket
import subprocess
import shutil
from agy_tools.utils import emit_progress, emit_result

from datetime import datetime, timezone
import json
from agy_tools.logger import get_logger

def get_sys_describe():
    return {
        "name": "sys",
        "description": "Server tizim resurslari, Rootless Docker, portlar va audit loglarini boshqarish vositasi.",
        "commands": {
            "status": "Tizim umumiy holati (CPU, RAM, Disk, Uptime)",
            "ports": "Foydalanuvchiga ajratilgan portlar holati (15800-15900)",
            "docker": "Foydalanuvchi Rootless Docker konteynerlari holati",
            "last-run": "Oxirgi bajarilgan buyruq va audit natijasi tafsilotlari",
            "logs": "Tizimdagi barcha bajarilgan operatsiyalar audit jurnali"
        }
    }

def check_port(ip: str, port: int, timeout: float = 0.5) -> bool:
    """Check if a TCP port is open and listening."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        res = sock.connect_ex((ip, port))
        sock.close()
        return res == 0
    except Exception:
        return False

def run_sys_ports(args):
    """Scan ports in the user designated range (15800 - 15900)."""
    emit_progress("Scanning Ports", 10, "Portlar oralig'i aniqlanmoqda (15800-15900)...")
    
    start_port = args.start_port if hasattr(args, 'start_port') and args.start_port else 15800
    end_port = args.end_port if hasattr(args, 'end_port') and args.end_port else 15900
    
    total = end_port - start_port + 1
    active_ports = []
    
    for i, port in enumerate(range(start_port, end_port + 1)):
        if i % 15 == 0:
            pct = 10 + int((i / total) * 80)
            emit_progress("Port Scan", pct, f"Tekshirilmoqda: {port}")
        
        if check_port("127.0.0.1", port):
            # Try to resolve process name if possible
            proc_name = ""
            try:
                cmd = f"ss -tlpn 'sport = :{port}' | grep -o 'users:(([^)]*))' | cut -d'\"' -f2"
                res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                proc_name = res.stdout.strip()
            except Exception:
                pass
            active_ports.append({
                "port": port,
                "process": proc_name if proc_name else "Unknown"
            })
            
    emit_progress("Finished", 100, "Portlar tahlili yakunlandi.")
    emit_result({
        "range": f"{start_port}-{end_port}",
        "active_count": len(active_ports),
        "active_ports": active_ports
    })

def run_sys_status(args):
    """Get system memory, disk, and load average safely."""
    emit_progress("Checking System", 30, "Disk va xotira tekshirilmoqda...")
    
    # Disk usage for /home/fayzillo
    home_stat = shutil.disk_usage(os.path.expanduser("~"))
    disk_total_gb = round(home_stat.total / (1024**3), 2)
    disk_used_gb = round(home_stat.used / (1024**3), 2)
    disk_free_gb = round(home_stat.free / (1024**3), 2)
    disk_used_pct = round((home_stat.used / home_stat.total) * 100, 1)
    
    emit_progress("Checking Memory", 70, "RAM holati olinmoqda...")
    # RAM from /proc/meminfo
    mem_total_mb = 0
    mem_avail_mb = 0
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    mem_total_mb = round(int(line.split()[1]) / 1024, 1)
                elif line.startswith("MemAvailable:"):
                    mem_avail_mb = round(int(line.split()[1]) / 1024, 1)
    except Exception:
        pass
    
    load_avg = os.getloadavg() if hasattr(os, 'getloadavg') else (0, 0, 0)
    
    emit_progress("Done", 100, "Tizim holati tayyor.")
    emit_result({
        "disk": {
            "total_gb": disk_total_gb,
            "used_gb": disk_used_gb,
            "free_gb": disk_free_gb,
            "used_pct": f"{disk_used_pct}%"
        },
        "memory": {
            "total_mb": mem_total_mb,
            "available_mb": mem_avail_mb,
            "used_pct": f"{round((1 - mem_avail_mb/mem_total_mb)*100, 1) if mem_total_mb > 0 else 0}%"
        },
        "load_avg_1_5_15": list(load_avg)
    })

def run_sys_docker(args):
    """Check user's Rootless Docker containers safely."""
    emit_progress("Checking Docker", 40, "Rootless Docker socket tekshirilmoqda...")
    docker_socket = f"/run/user/{os.getuid()}/docker.sock"
    
    cmd = f"docker ps --format '{{{{.ID}}}}|{{{{.Names}}}}|{{{{.Status}}}}|{{{{.Ports}}}}'"
    env = os.environ.copy()
    if os.path.exists(docker_socket):
        env["DOCKER_HOST"] = f"unix://{docker_socket}"
        
    try:
        res = subprocess.run(cmd, shell=True, env=env, capture_output=True, text=True)
        containers = []
        for line in res.stdout.strip().split("\n"):
            if line:
                parts = line.split("|")
                if len(parts) >= 4:
                    containers.append({
                        "id": parts[0],
                        "name": parts[1],
                        "status": parts[2],
                        "ports": parts[3]
                    })
        emit_progress("Done", 100, "Docker konteynerlar ro'yxati olindi.")
        emit_result({
            "docker_socket": docker_socket,
            "socket_active": os.path.exists(docker_socket),
            "running_count": len(containers),
            "containers": containers
        })
    except Exception as e:
        emit_result(None, success=False, error=str(e))


def format_elapsed(iso_ts: str) -> str:
    """Computes human-readable elapsed time string from ISO UTC timestamp."""
    try:
        ts = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = (now - ts).total_seconds()
        if diff < 0:
            diff = 0
        if diff < 60:
            return f"{int(diff)}s ago"
        elif diff < 3600:
            m = int(diff // 60)
            s = int(diff % 60)
            return f"{m}m {s}s ago"
        else:
            h = int(diff // 3600)
            m = int((diff % 3600) // 60)
            return f"{h}h {m}m ago"
    except Exception:
        return ""


def run_sys_last_run(args):
    """Show details of the last command run from audit log."""
    logger = get_logger()
    skip_meta = not getattr(args, "all", False)
    last_run = logger.get_last_run(skip_meta=skip_meta)

    fmt = getattr(args, "format", "table")
    if getattr(args, "table", False):
        fmt = "table"

    if fmt == "json":
        emit_result(last_run if last_run else {"message": "Hozircha hech qanday log yozuvi topilmadi"}, success=True)
        return

    # Table format
    print("=" * 80)
    print("                    AGY AUDIT LOGGER — LAST RUN DETAILS")
    print("=" * 80)
    if not last_run:
        print("Hozircha hech qanday log yozuvi topilmadi (~/.local/state/agy-tool/runs.jsonl bo'sh).")
        print("=" * 80)
        return

    ts_str = last_run.get("timestamp", "")
    elapsed = format_elapsed(ts_str)
    ts_display = f"{ts_str} ({elapsed})" if elapsed else ts_str

    print(f"Timestamp       : {ts_display}")
    print(f"Session ID      : {last_run.get('session_id', 'unknown')}")
    print(f"Session Path    : {last_run.get('session_path', '') or '-'}")
    print(f"Caller CWD      : {last_run.get('caller_cwd', '') or '-'}")
    print(f"Command         : {last_run.get('command', '')}")
    print(f"Arguments       : {last_run.get('args', [])}")
    print(f"Status          : {last_run.get('status', 'UNKNOWN')}")
    print(f"Duration        : {last_run.get('duration_ms', 0)} ms")
    print(f"Last Checkpoint : {last_run.get('last_checkpoint') or '-'}")
    print(f"Error Detail    : {last_run.get('error_detail') or 'None'}")
    print("=" * 80)


def run_sys_logs(args):
    """Query and inspect audit log history with filters and summary stats."""
    logger = get_logger()
    limit = getattr(args, "limit", 20) or 20
    errors_only = getattr(args, "errors_only", False)
    session_id = getattr(args, "query_session_id", None) or getattr(args, "session_id", None)
    if session_id == "unknown":
        session_id = None

    fmt = getattr(args, "format", "table")
    if getattr(args, "table", False):
        fmt = "table"

    logs = logger.get_logs(limit=limit, errors_only=errors_only, session_id=session_id)

    # Compute overall statistics from the log file
    total_in_log = 0
    all_success = 0
    all_errors = 0
    all_timeout = 0
    all_partial = 0
    if os.path.exists(logger.log_file):
        try:
            with open(logger.log_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        total_in_log += 1
                        try:
                            rec = json.loads(line)
                            st = rec.get("status")
                            if st == "SUCCESS":
                                all_success += 1
                            elif st == "ERROR":
                                all_errors += 1
                            elif st == "TIMEOUT":
                                all_timeout += 1
                            elif st == "PARTIAL":
                                all_partial += 1
                        except Exception:
                            pass
        except Exception:
            pass

    durations = [r.get("duration_ms", 0) for r in logs if isinstance(r.get("duration_ms"), (int, float))]
    avg_duration = round(sum(durations) / len(durations), 2) if durations else 0.0

    summary = {
        "total_in_log": total_in_log,
        "total_returned": len(logs),
        "success_count": all_success,
        "error_count": all_errors,
        "timeout_count": all_timeout,
        "partial_count": all_partial,
        "avg_duration_ms": avg_duration
    }

    if fmt == "json":
        emit_result({
            "summary": summary,
            "filter": {
                "limit": limit,
                "errors_only": errors_only,
                "session_id": session_id
            },
            "logs": logs
        }, success=True)
        return

    # Table format
    print("=" * 110)
    print("                                      AGY AUDIT LOGS HISTORY")
    print("=" * 110)
    print(
        f"Summary: Total Shown: {len(logs)} | In File: {total_in_log} | "
        f"Success: {all_success} | Errors: {all_errors} | Other: {all_timeout + all_partial} "
        f"(Filters: errors_only={errors_only}, session={session_id or 'all'})"
    )
    print("-" * 110)
    print(f"{'TIME (UTC)':<20} | {'STATUS':<8} | {'DURATION':<10} | {'SESSION ID':<20} | {'COMMAND':<20} | {'CHECKPOINT'}")
    print("-" * 110)

    if not logs:
        print("Hozircha hech qanday mos keluvchi audit yozuvi topilmadi.")
    else:
        for r in logs:
            ts = str(r.get("timestamp", ""))[:19].replace("T", " ")
            status = str(r.get("status", ""))[:8]
            dur = f"{r.get('duration_ms', 0):.1f} ms"
            sess = str(r.get("session_id", "unknown"))[:20]
            cmd = str(r.get("command", ""))[:20]
            chk = str(r.get("last_checkpoint") or "-")[:22]
            print(f"{ts:<20} | {status:<8} | {dur:>10} | {sess:<20} | {cmd:<20} | {chk}")
            if r.get("error_detail"):
                err_str = str(r.get("error_detail")).replace("\n", " ")[:90]
                print(f"  ↳ Error: {err_str}")

    print("=" * 110)

