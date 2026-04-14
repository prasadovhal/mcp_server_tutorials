"""
MCP System Monitor Server
Monitors CPU, Memory, Storage, Network, GPU, and more.
Compatible with Python 3.14+ — zero dependency on psutil/gputil.
"""

import asyncio
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

# ─────────────────────────────────────────────
# Low-level helpers
# ─────────────────────────────────────────────

def _read_proc(path: str) -> str | None:
    """Read a /proc file safely (Linux only)."""
    try:
        return Path(path).read_text()
    except Exception:
        return None


def _run(cmd: list[str], timeout: int = 5) -> str:
    """Run a subprocess and return stripped stdout, or '' on error."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _bytes_to_human(n: int | float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} PB"


OS = platform.system()  # "Linux" | "Windows" | "Darwin"


# ─────────────────────────────────────────────
# CPU
# ─────────────────────────────────────────────

def _cpu_times_linux() -> tuple[int, int]:
    """Return (idle, total) jiffies from /proc/stat for the aggregate CPU line."""
    raw = _read_proc("/proc/stat")
    if not raw:
        return 0, 1
    for line in raw.splitlines():
        if line.startswith("cpu "):
            vals = list(map(int, line.split()[1:]))
            # user, nice, system, idle, iowait, irq, softirq, steal, ...
            idle = vals[3] + (vals[4] if len(vals) > 4 else 0)  # idle + iowait
            total = sum(vals)
            return idle, total
    return 0, 1


def get_cpu_usage() -> dict:
    if OS == "Linux":
        idle1, total1 = _cpu_times_linux()
        time.sleep(0.5)
        idle2, total2 = _cpu_times_linux()
        diff_total = total2 - total1
        diff_idle = idle2 - idle1
        usage = 100.0 * (1 - diff_idle / max(diff_total, 1))

        # Per-core count
        cpuinfo = _read_proc("/proc/cpuinfo") or ""
        core_count = cpuinfo.count("processor\t:")

        # Frequency
        freq_raw = _read_proc("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq")
        freq_mhz = int(freq_raw.strip()) / 1000 if freq_raw else None

        # Load average
        loadavg = _read_proc("/proc/loadavg") or ""
        loads = loadavg.split()[:3] if loadavg else []

        return {
            "usage_percent": round(usage, 2),
            "logical_cores": core_count,
            "frequency_mhz": round(freq_mhz, 1) if freq_mhz else "N/A",
            "load_average_1_5_15min": [float(x) for x in loads] if loads else "N/A",
        }

    elif OS == "Windows":
        out = _run(["wmic", "cpu", "get", "LoadPercentage,NumberOfLogicalProcessors,CurrentClockSpeed", "/format:csv"])
        lines = [l for l in out.splitlines() if l.strip() and "Node" not in l]
        if lines:
            parts = lines[0].split(",")
            return {
                "usage_percent": float(parts[1]) if len(parts) > 1 else "N/A",
                "logical_cores": int(parts[3]) if len(parts) > 3 else "N/A",
                "frequency_mhz": float(parts[2]) if len(parts) > 2 else "N/A",
                "load_average_1_5_15min": "N/A (Windows)",
            }

    elif OS == "Darwin":
        top_out = _run(["top", "-l", "1", "-s", "0"])
        usage = "N/A"
        for line in top_out.splitlines():
            if "CPU usage" in line:
                m = re.search(r"([\d.]+)% idle", line)
                if m:
                    usage = round(100.0 - float(m.group(1)), 2)
        cores = _run(["sysctl", "-n", "hw.logicalcpu"])
        freq = _run(["sysctl", "-n", "hw.cpufrequency"])
        return {
            "usage_percent": usage,
            "logical_cores": int(cores) if cores.isdigit() else "N/A",
            "frequency_mhz": round(int(freq) / 1e6, 1) if freq.isdigit() else "N/A",
            "load_average_1_5_15min": "N/A",
        }

    return {"error": f"Unsupported OS: {OS}"}


# ─────────────────────────────────────────────
# Memory
# ─────────────────────────────────────────────

def get_memory_usage() -> dict:
    if OS == "Linux":
        raw = _read_proc("/proc/meminfo")
        if not raw:
            return {"error": "Cannot read /proc/meminfo"}
        kv: dict[str, int] = {}
        for line in raw.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                kv[parts[0].rstrip(":")] = int(parts[1])  # kB

        total = kv.get("MemTotal", 0) * 1024
        free = kv.get("MemFree", 0) * 1024
        available = kv.get("MemAvailable", 0) * 1024
        buffers = kv.get("Buffers", 0) * 1024
        cached = kv.get("Cached", 0) * 1024
        used = total - available
        swap_total = kv.get("SwapTotal", 0) * 1024
        swap_free = kv.get("SwapFree", 0) * 1024
        swap_used = swap_total - swap_free

        return {
            "total": _bytes_to_human(total),
            "used": _bytes_to_human(used),
            "free": _bytes_to_human(free),
            "available": _bytes_to_human(available),
            "buffers": _bytes_to_human(buffers),
            "cached": _bytes_to_human(cached),
            "usage_percent": round(used / max(total, 1) * 100, 2),
            "swap_total": _bytes_to_human(swap_total),
            "swap_used": _bytes_to_human(swap_used),
            "swap_free": _bytes_to_human(swap_free),
        }

    elif OS == "Windows":
        out = _run(["wmic", "OS", "get", "TotalVisibleMemorySize,FreePhysicalMemory", "/format:csv"])
        lines = [l for l in out.splitlines() if l.strip() and "Node" not in l]
        if lines:
            parts = lines[0].split(",")
            free_kb = int(parts[1]) if len(parts) > 1 else 0
            total_kb = int(parts[2]) if len(parts) > 2 else 1
            used_kb = total_kb - free_kb
            return {
                "total": _bytes_to_human(total_kb * 1024),
                "used": _bytes_to_human(used_kb * 1024),
                "free": _bytes_to_human(free_kb * 1024),
                "usage_percent": round(used_kb / max(total_kb, 1) * 100, 2),
            }

    elif OS == "Darwin":
        vm = _run(["vm_stat"])
        page_size = 4096
        kv: dict[str, int] = {}
        for line in vm.splitlines():
            m = re.match(r"(.+?):\s+(\d+)", line)
            if m:
                kv[m.group(1).strip()] = int(m.group(2)) * page_size
        total_raw = _run(["sysctl", "-n", "hw.memsize"])
        total = int(total_raw) if total_raw.isdigit() else 0
        free = kv.get("Pages free", 0)
        used = total - free
        return {
            "total": _bytes_to_human(total),
            "used": _bytes_to_human(used),
            "free": _bytes_to_human(free),
            "usage_percent": round(used / max(total, 1) * 100, 2),
        }

    return {"error": f"Unsupported OS: {OS}"}


# ─────────────────────────────────────────────
# Storage
# ─────────────────────────────────────────────

def get_storage_info() -> dict:
    partitions: list[dict] = []

    if OS == "Linux":
        mounts_raw = _read_proc("/proc/mounts") or ""
        seen: set[str] = set()
        for line in mounts_raw.splitlines():
            parts = line.split()
            if len(parts) < 2:
                continue
            device, mount = parts[0], parts[1]
            if not device.startswith("/dev/") or mount in seen:
                continue
            seen.add(mount)
            try:
                usage = shutil.disk_usage(mount)
                partitions.append({
                    "device": device,
                    "mount": mount,
                    "filesystem": parts[2] if len(parts) > 2 else "?",
                    "total": _bytes_to_human(usage.total),
                    "used": _bytes_to_human(usage.used),
                    "free": _bytes_to_human(usage.free),
                    "usage_percent": round(usage.used / max(usage.total, 1) * 100, 2),
                })
            except PermissionError:
                pass

    elif OS == "Windows":
        import string
        for letter in string.ascii_uppercase:
            mount = f"{letter}:\\"
            if os.path.exists(mount):
                try:
                    usage = shutil.disk_usage(mount)
                    partitions.append({
                        "device": mount,
                        "mount": mount,
                        "total": _bytes_to_human(usage.total),
                        "used": _bytes_to_human(usage.used),
                        "free": _bytes_to_human(usage.free),
                        "usage_percent": round(usage.used / max(usage.total, 1) * 100, 2),
                    })
                except Exception:
                    pass

    elif OS == "Darwin":
        df_out = _run(["df", "-k"])
        for line in df_out.splitlines()[1:]:
            parts = line.split()
            if len(parts) < 6 or not parts[0].startswith("/dev/"):
                continue
            try:
                usage = shutil.disk_usage(parts[8] if len(parts) > 8 else parts[5])
                partitions.append({
                    "device": parts[0],
                    "mount": parts[8] if len(parts) > 8 else parts[5],
                    "total": _bytes_to_human(usage.total),
                    "used": _bytes_to_human(usage.used),
                    "free": _bytes_to_human(usage.free),
                    "usage_percent": round(usage.used / max(usage.total, 1) * 100, 2),
                })
            except Exception:
                pass

    return {"partitions": partitions, "count": len(partitions)}


# ─────────────────────────────────────────────
# Network
# ─────────────────────────────────────────────

def get_network_info() -> dict:
    interfaces: dict[str, Any] = {}

    if OS == "Linux":
        # Stats from /proc/net/dev
        dev_raw = _read_proc("/proc/net/dev") or ""
        for line in dev_raw.splitlines()[2:]:
            if ":" not in line:
                continue
            iface, data = line.split(":", 1)
            iface = iface.strip()
            vals = data.split()
            if len(vals) < 9:
                continue
            interfaces[iface] = {
                "bytes_recv": _bytes_to_human(int(vals[0])),
                "packets_recv": int(vals[1]),
                "bytes_sent": _bytes_to_human(int(vals[8])),
                "packets_sent": int(vals[9]),
            }

        # IP addresses from ip addr (fallback: ifconfig)
        ip_out = _run(["ip", "addr"]) or _run(["ifconfig"])
        current_iface = None
        for line in ip_out.splitlines():
            m = re.match(r"^\d+:\s+(\S+):", line)
            if m:
                current_iface = m.group(1).rstrip("@").split("@")[0]
                interfaces.setdefault(current_iface, {})
            if current_iface and "inet " in line:
                m2 = re.search(r"inet (\S+)", line)
                if m2:
                    interfaces[current_iface]["ipv4"] = m2.group(1)
            if current_iface and "inet6 " in line:
                m3 = re.search(r"inet6 (\S+)", line)
                if m3:
                    interfaces[current_iface].setdefault("ipv6", m3.group(1))

    elif OS == "Windows":
        out = _run(["ipconfig", "/all"])
        current = None
        for line in out.splitlines():
            if line and not line.startswith(" "):
                current = line.strip().rstrip(":")
                interfaces[current] = {}
            elif current and "IPv4" in line:
                m = re.search(r"([\d.]+)", line)
                if m:
                    interfaces[current]["ipv4"] = m.group(1)
            elif current and "IPv6" in line:
                m = re.search(r"([0-9a-f:]{6,})", line, re.IGNORECASE)
                if m:
                    interfaces[current]["ipv6"] = m.group(1)

    elif OS == "Darwin":
        out = _run(["ifconfig"])
        current = None
        for line in out.splitlines():
            m = re.match(r"^(\S+):", line)
            if m:
                current = m.group(1)
                interfaces.setdefault(current, {})
            if current and "inet " in line:
                m2 = re.search(r"inet (\S+)", line)
                if m2:
                    interfaces[current]["ipv4"] = m2.group(1)

    # Public IP via DNS (no HTTP needed)
    try:
        public_ip = socket.gethostbyname("myip.opendns.com")
    except Exception:
        public_ip = "unavailable"

    return {
        "hostname": socket.gethostname(),
        "public_ip": public_ip,
        "interfaces": interfaces,
    }


# ─────────────────────────────────────────────
# Network connections (active sockets)
# ─────────────────────────────────────────────

def get_network_connections() -> dict:
    connections: list[dict] = []

    if OS == "Linux":
        # Read /proc/net/tcp (IPv4 TCP connections)
        tcp_raw = _read_proc("/proc/net/tcp") or ""
        state_map = {
            "01": "ESTABLISHED", "02": "SYN_SENT", "03": "SYN_RECV",
            "04": "FIN_WAIT1", "05": "FIN_WAIT2", "06": "TIME_WAIT",
            "07": "CLOSE", "08": "CLOSE_WAIT", "09": "LAST_ACK",
            "0A": "LISTEN", "0B": "CLOSING",
        }
        for line in tcp_raw.splitlines()[1:]:
            parts = line.split()
            if len(parts) < 4:
                continue
            local_hex, remote_hex, state_hex = parts[1], parts[2], parts[3]

            def hex_to_addr(h: str) -> str:
                ip_hex, port_hex = h.split(":")
                ip = socket.inet_ntoa(bytes.fromhex(ip_hex)[::-1])
                port = int(port_hex, 16)
                return f"{ip}:{port}"

            connections.append({
                "local": hex_to_addr(local_hex),
                "remote": hex_to_addr(remote_hex),
                "state": state_map.get(state_hex.upper(), state_hex),
            })
        return {"tcp_connections": connections[:50], "total": len(connections)}

    elif OS in ("Windows", "Darwin"):
        out = _run(["netstat", "-an"])
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[0] in ("TCP", "tcp"):
                connections.append({
                    "local": parts[1],
                    "remote": parts[2],
                    "state": parts[3] if len(parts) > 3 else "",
                })
        return {"tcp_connections": connections[:50], "total": len(connections)}

    return {"error": f"Unsupported OS: {OS}"}


# ─────────────────────────────────────────────
# GPU
# ─────────────────────────────────────────────

def _nvidia_smi(query: str) -> str:
    return _run(["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"])


def get_gpu_usage() -> dict:
    # NVIDIA
    raw = _nvidia_smi("index,name,utilization.gpu,utilization.memory,memory.used,memory.total,temperature.gpu,power.draw,power.limit,fan.speed")
    if raw:
        gpus = []
        for line in raw.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 10:
                continue
            gpus.append({
                "index": parts[0],
                "name": parts[1],
                "gpu_utilization_percent": parts[2],
                "memory_utilization_percent": parts[3],
                "memory_used_mb": parts[4],
                "memory_total_mb": parts[5],
                "temperature_c": parts[6],
                "power_draw_w": parts[7],
                "power_limit_w": parts[8],
                "fan_speed_percent": parts[9],
            })
        return {"vendor": "NVIDIA", "gpus": gpus, "count": len(gpus)}

    # AMD ROCm
    rocm_out = _run(["rocm-smi", "--showuse", "--showmemuse", "--showtemp", "--csv"])
    if rocm_out:
        gpus = []
        lines = [l for l in rocm_out.splitlines() if l.strip()]
        if len(lines) > 1:
            headers = [h.strip() for h in lines[0].split(",")]
            for line in lines[1:]:
                vals = [v.strip() for v in line.split(",")]
                gpus.append(dict(zip(headers, vals)))
        return {"vendor": "AMD", "gpus": gpus, "count": len(gpus)}

    # macOS Metal
    if OS == "Darwin":
        out = _run(["system_profiler", "SPDisplaysDataType"])
        return {"vendor": "Apple Metal", "raw_info": out or "No GPU info", "note": "Live utilisation requires powermetrics (sudo)"}

    # Intel integrated (Linux — via i915 sysfs)
    intel_path = "/sys/class/drm/card0/device/gpu_busy_percent"
    intel_raw = _read_proc(intel_path)
    if intel_raw:
        return {"vendor": "Intel", "gpu_busy_percent": intel_raw.strip(), "note": "i915 sysfs"}

    return {"error": "No compatible GPU detected (tried NVIDIA, AMD ROCm, Intel i915, Apple Metal)"}


def get_gpu_info() -> dict:
    # NVIDIA detailed
    raw = _nvidia_smi("index,name,driver_version,vbios_version,pcie.link.gen.current,pcie.link.width.current,memory.total,compute_mode,ecc.mode.current")
    if raw:
        gpus = []
        for line in raw.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 9:
                continue
            gpus.append({
                "index": parts[0],
                "name": parts[1],
                "driver_version": parts[2],
                "vbios_version": parts[3],
                "pcie_gen": parts[4],
                "pcie_width": parts[5],
                "memory_total_mb": parts[6],
                "compute_mode": parts[7],
                "ecc_mode": parts[8],
            })
        return {"vendor": "NVIDIA", "gpus": gpus}

    if OS == "Darwin":
        out = _run(["system_profiler", "SPDisplaysDataType"])
        return {"vendor": "Apple", "info": out}

    if OS == "Linux":
        lspci_out = _run(["lspci"])
        gpu_lines = [l for l in lspci_out.splitlines() if re.search(r"VGA|3D|Display", l, re.I)]
        return {"detected_gpu_pci_entries": gpu_lines or ["None found — lspci may not be installed"]}

    if OS == "Windows":
        out = _run(["wmic", "path", "win32_VideoController", "get", "Name,AdapterRAM,DriverVersion,VideoProcessor", "/format:csv"])
        lines = [l for l in out.splitlines() if l.strip() and "Node" not in l]
        gpus = []
        for line in lines:
            parts = line.split(",")
            if len(parts) >= 4:
                gpus.append({
                    "adapter_ram": _bytes_to_human(int(parts[1])) if parts[1].isdigit() else parts[1],
                    "driver_version": parts[2],
                    "name": parts[3],
                    "video_processor": parts[4] if len(parts) > 4 else "N/A",
                })
        return {"vendor": "Windows WMIC", "gpus": gpus}

    return {"error": "Cannot retrieve GPU info on this platform"}


# ─────────────────────────────────────────────
# System Info
# ─────────────────────────────────────────────

def get_system_info() -> dict:
    uname = platform.uname()
    boot_time = None
    uptime_str = "N/A"

    if OS == "Linux":
        uptime_raw = _read_proc("/proc/uptime")
        if uptime_raw:
            uptime_secs = float(uptime_raw.split()[0])
            uptime_str = str(timedelta(seconds=int(uptime_secs)))
            boot_time = datetime.now() - timedelta(seconds=uptime_secs)
    elif OS == "Darwin":
        out = _run(["sysctl", "-n", "kern.boottime"])
        m = re.search(r"sec\s*=\s*(\d+)", out)
        if m:
            boot_time = datetime.fromtimestamp(int(m.group(1)))
            uptime_str = str(datetime.now() - boot_time)
    elif OS == "Windows":
        out = _run(["net", "stats", "workstation"])
        for line in out.splitlines():
            if "Statistics since" in line:
                uptime_str = line.strip()
                break

    python_info = {
        "version": sys.version,
        "implementation": platform.python_implementation(),
        "executable": sys.executable,
    }

    return {
        "os": uname.system,
        "os_release": uname.release,
        "os_version": uname.version,
        "machine": uname.machine,
        "processor": uname.processor or platform.processor(),
        "hostname": uname.node,
        "python": python_info,
        "boot_time": boot_time.isoformat() if boot_time else "N/A",
        "uptime": uptime_str,
        "current_time": datetime.now().isoformat(),
        "timezone": time.tzname,
    }


# ─────────────────────────────────────────────
# CPU Temperature
# ─────────────────────────────────────────────

def get_cpu_temperature() -> dict:
    temps: list[dict] = []

    if OS == "Linux":
        thermal_base = Path("/sys/class/thermal")
        if thermal_base.exists():
            for zone in sorted(thermal_base.iterdir()):
                if not zone.name.startswith("thermal_zone"):
                    continue
                try:
                    temp_c = int((zone / "temp").read_text().strip()) / 1000
                    zone_type = (zone / "type").read_text().strip()
                    temps.append({"zone": zone.name, "type": zone_type, "temp_c": round(temp_c, 1)})
                except Exception:
                    pass

        # Also try hwmon
        hwmon_base = Path("/sys/class/hwmon")
        if hwmon_base.exists():
            for hwmon in sorted(hwmon_base.iterdir()):
                try:
                    name = (hwmon / "name").read_text().strip()
                except Exception:
                    name = hwmon.name
                for temp_file in sorted(hwmon.glob("temp*_input")):
                    try:
                        temp_c = int(temp_file.read_text().strip()) / 1000
                        label_file = temp_file.with_name(temp_file.name.replace("_input", "_label"))
                        label = label_file.read_text().strip() if label_file.exists() else temp_file.name
                        temps.append({"sensor": name, "label": label, "temp_c": round(temp_c, 1)})
                    except Exception:
                        pass

    elif OS == "Darwin":
        out = _run(["sudo", "powermetrics", "-n", "1", "--samplers", "smc", "-i", "1"])
        for line in out.splitlines():
            m = re.search(r"(CPU die temperature|GPU die temperature|.+?temp.+?):\s*([\d.]+)", line, re.I)
            if m:
                temps.append({"sensor": m.group(1).strip(), "temp_c": float(m.group(2))})
        if not temps:
            temps.append({"note": "Run with sudo for macOS temperature data"})

    elif OS == "Windows":
        out = _run(["wmic", "/namespace:\\\\root\\wmi", "path", "MSAcpi_ThermalZoneTemperature", "get", "CurrentTemperature", "/format:csv"])
        for line in out.splitlines():
            if line.strip() and "Node" not in line:
                parts = line.split(",")
                if len(parts) > 1 and parts[1].strip().isdigit():
                    temp_c = (int(parts[1].strip()) / 10) - 273.15
                    temps.append({"sensor": "ACPI Thermal Zone", "temp_c": round(temp_c, 1)})

    return {"temperatures": temps, "count": len(temps)} if temps else {"note": "Temperature data unavailable or requires elevated permissions"}


# ─────────────────────────────────────────────
# Top Processes
# ─────────────────────────────────────────────

def get_top_processes(n: int = 10) -> dict:
    processes: list[dict] = []

    if OS == "Linux":
        # Read all pids from /proc
        pid_dirs = [p for p in Path("/proc").iterdir() if p.name.isdigit()]
        procs_raw: list[dict] = []
        for pid_dir in pid_dirs:
            try:
                stat = (pid_dir / "stat").read_text().split()
                status_lines = {
                    line.split(":")[0].strip(): line.split(":", 1)[1].strip()
                    for line in (pid_dir / "status").read_text().splitlines()
                    if ":" in line
                }
                cmd_raw = (pid_dir / "cmdline").read_bytes().replace(b"\x00", b" ").decode(errors="replace").strip()
                procs_raw.append({
                    "pid": int(stat[0]),
                    "name": stat[1].strip("()"),
                    "state": stat[2],
                    "vm_rss_kb": int(status_lines.get("VmRSS", "0 kB").split()[0]),
                    "cmdline": cmd_raw[:120],
                })
            except Exception:
                pass

        procs_raw.sort(key=lambda x: x["vm_rss_kb"], reverse=True)
        for p in procs_raw[:n]:
            p["memory"] = _bytes_to_human(p.pop("vm_rss_kb") * 1024)
            processes.append(p)

    elif OS in ("Windows", "Darwin"):
        sep = "," if OS == "Windows" else None
        if OS == "Windows":
            out = _run(["tasklist", "/fo", "csv", "/nh"])
            for line in out.splitlines()[:n]:
                parts = [p.strip('"') for p in line.split('","')]
                if len(parts) >= 5:
                    processes.append({"name": parts[0], "pid": parts[1], "memory": parts[4]})
        else:
            out = _run(["ps", "aux"])
            rows = sorted(out.splitlines()[1:], key=lambda l: float(l.split()[3]) if len(l.split()) > 3 else 0, reverse=True)
            for line in rows[:n]:
                parts = line.split(None, 10)
                if len(parts) >= 11:
                    processes.append({"user": parts[0], "pid": parts[1], "cpu_pct": parts[2], "mem_pct": parts[3], "command": parts[10][:80]})

    return {"top_processes_by_memory": processes, "count": len(processes)}


# ─────────────────────────────────────────────
# Battery
# ─────────────────────────────────────────────

def get_battery_info() -> dict:
    if OS == "Linux":
        bat_base = Path("/sys/class/power_supply")
        for entry in (bat_base.iterdir() if bat_base.exists() else []):
            if entry.name.startswith("BAT"):
                try:
                    info: dict = {}
                    for key in ("status", "capacity", "energy_now", "energy_full", "voltage_now", "technology"):
                        f = entry / key
                        if f.exists():
                            info[key] = f.read_text().strip()
                    return {"battery": info}
                except Exception:
                    pass
        return {"battery": "No battery detected (desktop or VM)"}

    elif OS == "Darwin":
        out = _run(["pmset", "-g", "batt"])
        return {"raw": out or "No battery info"}

    elif OS == "Windows":
        out = _run(["wmic", "path", "win32_battery", "get", "EstimatedChargeRemaining,BatteryStatus,Name", "/format:csv"])
        lines = [l for l in out.splitlines() if l.strip() and "Node" not in l]
        if lines:
            parts = lines[0].split(",")
            return {"charge_remaining": parts[1] if len(parts) > 1 else "N/A",
                    "status": parts[2] if len(parts) > 2 else "N/A",
                    "name": parts[3] if len(parts) > 3 else "N/A"}
        return {"battery": "No battery detected"}

    return {"error": f"Unsupported OS: {OS}"}


# ─────────────────────────────────────────────
# Users logged in
# ─────────────────────────────────────────────

def get_logged_in_users() -> dict:
    users: list[dict] = []

    if OS in ("Linux", "Darwin"):
        out = _run(["who"])
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 4:
                users.append({"user": parts[0], "tty": parts[1], "login_time": f"{parts[2]} {parts[3]}"})

    elif OS == "Windows":
        out = _run(["query", "user"])
        for line in out.splitlines()[1:]:
            parts = line.split()
            if parts:
                users.append({"user": parts[0], "session": parts[1] if len(parts) > 1 else ""})

    return {"logged_in_users": users, "count": len(users)}


# ─────────────────────────────────────────────
# Open File Descriptors / Handles
# ─────────────────────────────────────────────

def get_open_files_count() -> dict:
    if OS == "Linux":
        file_nr = _read_proc("/proc/sys/fs/file-nr")
        if file_nr:
            parts = file_nr.split()
            return {
                "open_file_descriptors": int(parts[0]),
                "max_file_descriptors": int(parts[2]) if len(parts) > 2 else "N/A",
            }
    elif OS == "Darwin":
        out = _run(["sysctl", "-n", "kern.num_files"])
        return {"open_file_descriptors": out}
    elif OS == "Windows":
        out = _run(["handle", "-s"])
        return {"note": "Requires Sysinternals Handle.exe", "raw": out[:300] if out else "Not available"}

    return {"error": "Unavailable"}


# ─────────────────────────────────────────────
# Disk I/O Statistics
# ─────────────────────────────────────────────

def get_disk_io_stats() -> dict:
    stats: list[dict] = []

    if OS == "Linux":
        diskstats = _read_proc("/proc/diskstats") or ""
        for line in diskstats.splitlines():
            parts = line.split()
            if len(parts) >= 14 and parts[2].startswith(("sd", "hd", "nvme", "mmc")):
                device = parts[2]
                reads = int(parts[5])
                writes = int(parts[9])
                read_bytes = int(parts[5]) * 512  # Assume 512 byte sectors
                write_bytes = int(parts[9]) * 512
                stats.append({
                    "device": device,
                    "reads_completed": reads,
                    "writes_completed": writes,
                    "read_bytes": _bytes_to_human(read_bytes),
                    "write_bytes": _bytes_to_human(write_bytes),
                })

    elif OS == "Darwin":
        out = _run(["iostat", "-d", "1", "1"])
        # Parse iostat output - simplified
        stats.append({"note": "iostat data available", "raw": out[:200] if out else "N/A"})

    elif OS == "Windows":
        out = _run(["wmic", "diskdrive", "get", "Name,Size", "/format:csv"])
        for line in out.splitlines()[1:]:
            if line.strip():
                parts = line.split(",")
                if len(parts) >= 2:
                    stats.append({"device": parts[1], "size": _bytes_to_human(int(parts[2])) if parts[2].isdigit() else "N/A"})

    return {"disk_io_stats": stats, "count": len(stats)} if stats else {"note": "Disk I/O stats unavailable on this platform"}


# ─────────────────────────────────────────────
# Kernel / OS Flags (Linux specific extras)
# ─────────────────────────────────────────────

def get_kernel_info() -> dict:
    info: dict[str, Any] = {}
    if OS == "Linux":
        info["kernel_version"] = _run(["uname", "-r"])
        info["kernel_arch"] = _run(["uname", "-m"])
        info["os_release"] = {}
        os_rel = _read_proc("/etc/os-release")
        if os_rel:
            for line in os_rel.splitlines():
                if "=" in line:
                    k, _, v = line.partition("=")
                    info["os_release"][k] = v.strip('"')
        info["cpu_flags"] = []
        cpuinfo = _read_proc("/proc/cpuinfo") or ""
        for line in cpuinfo.splitlines():
            if line.startswith("flags"):
                info["cpu_flags"] = line.split(":")[1].strip().split()[:30]
                break
    else:
        info["kernel"] = _run(["uname", "-a"]) or platform.version()
    return info


# ─────────────────────────────────────────────
# MCP Server setup
# ─────────────────────────────────────────────

app = Server("sysmon")

TOOLS = [
    Tool(
        name="get_cpu_usage",
        description="Get current CPU usage percentage, core count, frequency, and load averages.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="get_memory_usage",
        description="Get RAM and swap usage: total, used, free, available, cached, buffers.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="get_storage_info",
        description="List all mounted disk partitions with total, used, free, and usage percent.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="get_network_info",
        description="Get network interfaces, IP addresses (IPv4/IPv6), bytes sent/received, hostname, and public IP.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="get_network_connections",
        description="List active TCP connections with local/remote addresses and connection state.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="get_gpu_usage",
        description="Get GPU utilization, memory usage, temperature, power draw, and fan speed. Supports NVIDIA (nvidia-smi), AMD (ROCm), Intel (i915), and Apple (Metal).",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="get_gpu_info",
        description="Get detailed GPU hardware info: driver version, VBIOS, PCIe gen/width, ECC mode, memory.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="get_system_info",
        description="Get OS name, version, hostname, processor, Python version, boot time, uptime, and timezone.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="get_cpu_temperature",
        description="Read CPU (and other hardware) temperatures from thermal zones and hwmon sensors.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="get_top_processes",
        description="List top N processes sorted by memory usage.",
        inputSchema={
            "type": "object",
            "properties": {
                "n": {"type": "integer", "description": "Number of processes to return (default 10)", "default": 10}
            },
        },
    ),
    Tool(
        name="get_battery_info",
        description="Get battery charge level, status, and capacity (laptops only).",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="get_logged_in_users",
        description="List all currently logged-in users, their TTY/session, and login time.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="get_open_files_count",
        description="Get the number of open file descriptors system-wide and the system limit.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="get_kernel_info",
        description="Get kernel version, architecture, OS release details, and top CPU feature flags.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="get_disk_io_stats",
        description="Get disk I/O statistics: reads/writes completed, bytes transferred per device.",
        inputSchema={"type": "object", "properties": {}},
    ),
]


@app.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    dispatch = {
        "get_cpu_usage": lambda: get_cpu_usage(),
        "get_memory_usage": lambda: get_memory_usage(),
        "get_storage_info": lambda: get_storage_info(),
        "get_network_info": lambda: get_network_info(),
        "get_network_connections": lambda: get_network_connections(),
        "get_gpu_usage": lambda: get_gpu_usage(),
        "get_gpu_info": lambda: get_gpu_info(),
        "get_system_info": lambda: get_system_info(),
        "get_cpu_temperature": lambda: get_cpu_temperature(),
        "get_top_processes": lambda: get_top_processes(arguments.get("n", 10)),
        "get_battery_info": lambda: get_battery_info(),
        "get_logged_in_users": lambda: get_logged_in_users(),
        "get_open_files_count": lambda: get_open_files_count(),
        "get_kernel_info": lambda: get_kernel_info(),
        "get_disk_io_stats": lambda: get_disk_io_stats(),
    }

    fn = dispatch.get(name)
    if fn is None:
        return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}, indent=2))]

    try:
        # Run synchronous functions in a thread so we don't block the event loop
        result = await asyncio.get_event_loop().run_in_executor(None, fn)
    except Exception as exc:
        result = {"error": str(exc)}

    return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())