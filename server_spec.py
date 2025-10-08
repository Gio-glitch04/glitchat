#!/usr/bin/env python3
"""Servidor de información del sistema.

Este servidor acepta conexiones TCP y responde a comandos de texto
terminados en "\n". Al conectarse, el cliente recibe la lista de comandos
soportados. Cada comando devuelve información sobre el estado del sistema
(hostname, CPU, memoria, disco, etc.).
"""

import os
import platform
import socket
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from shutil import disk_usage

HOST = "0.0.0.0"
PORT = 56000
ENCODING = "utf-8"
BUFFER_SIZE = 4096


class CommandError(Exception):
    """Se lanza cuando el comando no puede ejecutarse."""


def send_text(conn: socket.socket, text: str) -> None:
    """Enviar texto al cliente asegurando codificación UTF-8."""
    if not text.endswith("\n"):
        text += "\n"
    conn.sendall(text.encode(ENCODING, errors="replace"))


def read_os_release() -> dict:
    data = {}
    path = Path("/etc/os-release")
    if not path.exists():
        return data
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if value and value[0] in {'"', "'"} and value[-1] == value[0]:
                value = value[1:-1]
            data[key] = value
    except Exception:
        return {}
    return data


def gather_cpu_info() -> str:
    lines = []
    lines.append(f"Hostname: {platform.node()}")
    lines.append(f"Arquitectura: {platform.machine()}")
    cpu_count = os.cpu_count()
    if cpu_count is not None:
        lines.append(f"Procesadores lógicos: {cpu_count}")
    # Buscar modelo en /proc/cpuinfo (Linux)
    cpuinfo_path = Path("/proc/cpuinfo")
    if cpuinfo_path.exists():
        models = []
        frequencies = []
        try:
            for entry in cpuinfo_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if entry.lower().startswith("model name"):
                    models.append(entry.split(":", 1)[1].strip())
                elif entry.lower().startswith("cpu mhz"):
                    frequencies.append(entry.split(":", 1)[1].strip())
        except Exception:
            models = []
            frequencies = []
        if models:
            unique_models = sorted(set(models))
            lines.append("Modelo(s):")
            for model in unique_models:
                lines.append(f"  - {model}")
        if frequencies:
            try:
                avg_freq = sum(float(f) for f in frequencies) / len(frequencies)
                lines.append(f"Frecuencia promedio: {avg_freq:.2f} MHz")
            except Exception:
                pass
    try:
        uname = os.uname()
        lines.append(f"Kernel: {uname.sysname} {uname.release} ({uname.version})")
    except AttributeError:
        lines.append(f"Sistema operativo: {platform.platform()}")
    return "\n".join(lines)


def gather_memory_info() -> str:
    meminfo_path = Path("/proc/meminfo")
    if not meminfo_path.exists():
        raise CommandError("/proc/meminfo no disponible en este sistema.")
    info = {}
    for line in meminfo_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        info[key.strip()] = value.strip()
    def parse_kb(key: str) -> float:
        value = info.get(key)
        if not value:
            return 0.0
        parts = value.split()
        try:
            amount = float(parts[0])
        except (ValueError, IndexError):
            return 0.0
        unit = parts[1] if len(parts) > 1 else "kB"
        if unit.lower() == "kb":
            amount *= 1024.0
        return amount
    total = parse_kb("MemTotal")
    free = parse_kb("MemFree")
    available = parse_kb("MemAvailable")
    buffers = parse_kb("Buffers")
    cached = parse_kb("Cached")
    swap_total = parse_kb("SwapTotal")
    swap_free = parse_kb("SwapFree")
    def format_bytes(num: float) -> str:
        for suffix in ("B", "KiB", "MiB", "GiB", "TiB"):
            if num < 1024.0:
                return f"{num:.2f} {suffix}"
            num /= 1024.0
        return f"{num:.2f} PiB"
    lines = [
        "Memoria física:",
        f"  Total: {format_bytes(total)}",
        f"  Disponible: {format_bytes(available)}",
        f"  Libre: {format_bytes(free)}",
        f"  Buffers: {format_bytes(buffers)}",
        f"  Caché: {format_bytes(cached)}",
        "Memoria swap:",
        f"  Total: {format_bytes(swap_total)}",
        f"  Libre: {format_bytes(swap_free)}",
    ]
    return "\n".join(lines)


def gather_disk_usage() -> str:
    usage = disk_usage("/")
    total = usage.total
    used = usage.used
    free = usage.free
    def fmt(num: int) -> str:
        value = float(num)
        for suffix in ("B", "KiB", "MiB", "GiB", "TiB"):
            if value < 1024:
                return f"{value:.2f} {suffix}"
            value /= 1024
        return f"{value:.2f} PiB"
    lines = [
        "Uso de disco (partición raíz):",
        f"  Total: {fmt(total)}",
        f"  Usado: {fmt(used)}",
        f"  Libre: {fmt(free)}",
    ]
    try:
        df_output = subprocess.run(
            ["df", "-h"],
            check=False,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if df_output:
            lines.append("")
            lines.append("df -h:")
            lines.append(df_output)
    except FileNotFoundError:
        pass
    return "\n".join(lines)


def gather_filesystems() -> str:
    fs_path = Path("/proc/filesystems")
    if not fs_path.exists():
        raise CommandError("/proc/filesystems no disponible.")
    entries = []
    for line in fs_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        entries.append(line)
    mounts_path = Path("/proc/mounts")
    mounts_text = mounts_path.read_text(encoding="utf-8", errors="ignore") if mounts_path.exists() else ""
    lines = ["Filesystems soportados:"]
    lines.extend(f"  - {entry}" for entry in entries)
    if mounts_text:
        lines.append("")
        lines.append("Montajes activos:")
        lines.extend(f"  {m}" for m in mounts_text.splitlines())
    return "\n".join(lines)


def gather_loadavg() -> str:
    try:
        load1, load5, load15 = os.getloadavg()
    except (AttributeError, OSError):
        raise CommandError("Carga promedio no disponible en este sistema.")
    return (
        "Promedio de carga (loadavg):\n"
        f"  1 minuto:  {load1:.2f}\n"
        f"  5 minutos: {load5:.2f}\n"
        f"  15 minutos:{load15:.2f}"
    )


def gather_partitions() -> str:
    partitions_path = Path("/proc/partitions")
    if not partitions_path.exists():
        raise CommandError("/proc/partitions no disponible.")
    lines = ["Particiones detectadas:"]
    lines.extend(partitions_path.read_text(encoding="utf-8", errors="ignore").splitlines())
    return "\n".join(lines)


def gather_os_info() -> str:
    info = read_os_release()
    lines = ["Sistema operativo:"]
    if info:
        name = info.get("PRETTY_NAME") or info.get("NAME")
        if name:
            lines.append(f"  Nombre: {name}")
        version = info.get("VERSION")
        if version:
            lines.append(f"  Versión: {version}")
        lines.append("")
    lines.append(f"Plataforma: {platform.platform()}")
    lines.append(f"Python: {platform.python_version()} ({platform.python_build()[0]})")
    return "\n".join(lines)


def gather_network_info() -> str:
    dev_path = Path("/proc/net/dev")
    if not dev_path.exists():
        raise CommandError("/proc/net/dev no disponible.")
    lines = ["Interfaces de red:"]
    for line in dev_path.read_text(encoding="utf-8", errors="ignore").splitlines()[2:]:
        if ":" not in line:
            continue
        iface, data = line.split(":", 1)
        iface = iface.strip()
        parts = data.split()
        if len(parts) < 16:
            continue
        rx_bytes, rx_packets = parts[0], parts[1]
        tx_bytes, tx_packets = parts[8], parts[9]
        lines.append(
            f"  - {iface}: RX={rx_bytes} bytes ({rx_packets} paquetes) | "
            f"TX={tx_bytes} bytes ({tx_packets} paquetes)"
        )
    return "\n".join(lines)


def gather_processes() -> str:
    try:
        output = subprocess.run(
            ["ps", "-eo", "pid,ppid,comm,%cpu,%mem", "--sort=-%cpu"],
            check=False,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
    except FileNotFoundError as exc:
        raise CommandError("Comando 'ps' no disponible.") from exc
    if not output:
        return "No se pudo obtener la lista de procesos."
    header = output[0]
    top = output[1:11]
    lines = ["Procesos (top 10 por uso de CPU):", header]
    lines.extend(top)
    return "\n".join(lines)


def gather_uptime() -> str:
    uptime_path = Path("/proc/uptime")
    if not uptime_path.exists():
        raise CommandError("/proc/uptime no disponible.")
    try:
        uptime_seconds = float(uptime_path.read_text().split()[0])
    except Exception as exc:
        raise CommandError("No se pudo leer el tiempo de actividad.") from exc
    days, remainder = divmod(int(uptime_seconds), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    return (
        "Tiempo de actividad:\n"
        f"  {days} días, {hours} horas, {minutes} minutos, {seconds} segundos"
    )


def build_help_text() -> str:
    lines = ["Comandos disponibles:"]
    for name, (_, description) in sorted(COMMANDS.items()):
        lines.append(f"  {name:<7} - {description}")
    return "\n".join(lines)


COMMANDS = {
    "help": (lambda: build_help_text(), "Mostrar este mensaje de ayuda"),
    "cpu": (gather_cpu_info, "Información del procesador"),
    "mem": (gather_memory_info, "Uso de memoria"),
    "disk": (gather_disk_usage, "Uso de discos"),
    "fs": (gather_filesystems, "Filesystems y montajes"),
    "load": (gather_loadavg, "Promedio de carga"),
    "part": (gather_partitions, "Particiones detectadas"),
    "os": (gather_os_info, "Información del sistema operativo"),
    "net": (gather_network_info, "Interfaces de red"),
    "proc": (gather_processes, "Procesos en ejecución"),
    "uptime": (gather_uptime, "Tiempo desde el arranque"),
    "time": (lambda: datetime.now().strftime("Fecha y hora actual: %Y-%m-%d %H:%M:%S"),
              "Fecha y hora del servidor"),
    "quit": (lambda: "Hasta luego.", "Cerrar la conexión"),
}


WELCOME_TEXT = (
    "Bienvenido al servidor de especificaciones del sistema.\n"
    "Escriba uno de los comandos listados a continuación y presione Enter.\n"
    f"{build_help_text()}\n"
)


PROMPT = "\n> "


def handle_client(conn: socket.socket, addr) -> None:
    with conn:
        send_text(conn, WELCOME_TEXT)
        send_text(conn, "Para desconectarse utilice el comando 'quit'.")
        send_text(conn, PROMPT)
        buffer = ""
        while True:
            data = conn.recv(BUFFER_SIZE)
            if not data:
                break
            buffer += data.decode(ENCODING, errors="ignore")
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                command = line.strip().lower()
                if not command:
                    send_text(conn, PROMPT)
                    continue
                if command not in COMMANDS:
                    send_text(conn, f"Comando desconocido: {command}")
                    send_text(conn, PROMPT)
                    continue
                func, _ = COMMANDS[command]
                try:
                    result = func()
                except CommandError as exc:
                    result = f"Error: {exc}"
                except Exception as exc:
                    result = f"Error interno al ejecutar '{command}': {exc}"
                send_text(conn, result)
                if command == "quit":
                    return
                send_text(conn, PROMPT)






def accept_loop(server_sock: socket.socket) -> None:
    print(f"[SERVER] Escuchando en {HOST}:{PORT}")
    while True:
        try:
            conn, addr = server_sock.accept()
            print(f"[SERVER] Conexión desde {addr}")
            thread = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            thread.start()
        except KeyboardInterrupt:
            print("[SERVER] Terminando por KeyboardInterrupt")
            break
        except Exception as exc:
            print(f"[SERVER] Error en accept(): {exc}")
            break
    server_sock.close()


def main() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_sock:
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind((HOST, PORT))
        server_sock.listen()
        accept_loop(server_sock)


if __name__ == "__main__":
    main()
