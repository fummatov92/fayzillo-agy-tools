import os
import sys
import socket
import subprocess
import shutil
from agy_tools.utils import emit_progress, emit_result

def get_sys_describe():
    return {
        "name": "sys",
        "description": "Server tizim resurslari, Rootless Docker va foydalanuvchi portlarini xavfsiz tekshirish vositasi.",
        "commands": {
            "status": "Tizim umumiy holati (CPU, RAM, Disk, Uptime)",
            "ports": "Foydalanuvchiga ajratilgan portlar holati (15800-15900)",
            "docker": "Foydalanuvchi Rootless Docker konteynerlari holati"
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
