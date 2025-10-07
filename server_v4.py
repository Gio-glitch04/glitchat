#!/usr/bin/env python3
"""Servidor de chat compatible con client_v4.py (protocolo de texto)."""

import socket
import threading
import shlex

HOST = '0.0.0.0'
PORT = 55555

clients = {}  # username -> socket
clients_lock = threading.Lock()

rooms = {'global': {'members': set(), 'password': None}}
rooms_lock = threading.Lock()
user_rooms = {}  # username -> sala activa
user_memberships = {}  # username -> set(salas en las que está unido)


class DisconnectRequested(Exception):
    """Se lanza cuando el cliente solicita desconexión voluntaria."""


def send_line(conn, text):
    try:
        conn.sendall((text + "\n").encode('utf-8'))
    except Exception:
        raise


def broadcast_room(room, text, exclude=None):
    with rooms_lock:
        members = [
            username
            for username in rooms.get(room, {}).get('members', set())
            if username != exclude and user_rooms.get(username, 'global') == room
        ]
    targets = []
    with clients_lock:
        for username in members:
            conn = clients.get(username)
            if conn:
                targets.append(conn)
    data = (text + "\n").encode('utf-8')
    for conn in targets:
        try:
            conn.sendall(data)
        except Exception:
            pass


def handle_join_command(username, conn, room, password):
    room = room.strip()
    if not room:
        send_line(conn, "❌ Debes indicar un nombre de sala.")
        return
    with rooms_lock:
        info = rooms.get(room)
        already_member = False
        if info:
            already_member = username in info.get('members', set())
            stored_pwd = info.get('password')
            if not already_member and stored_pwd:
                if password is None or password != stored_pwd:
                    send_line(conn, "❌ Contraseña incorrecta.")
                    return
        else:
            rooms[room] = {'members': set(), 'password': password if password else None}
            info = rooms[room]
        info['members'].add(username)
        user_memberships.setdefault(username, set()).add(room)
        user_rooms[username] = room
    if not already_member:
        broadcast_room(room, f"🔔 {username} se ha unido a la sala '{room}'.", exclude=username)
    send_line(conn, f"✅ Te has unido a la sala '{room}'.")


def handle_leave_command(username, conn, target_room=None):
    with rooms_lock:
        current_active = user_rooms.get(username, 'global')
        memberships = user_memberships.setdefault(username, set())
        room = target_room.strip() if target_room else current_active
        if room not in memberships:
            send_line(conn, f"No estás en la sala '{room}'.")
            return
        if room == 'global':
            send_line(conn, "No puedes salir del chat global.")
            return
        rooms.setdefault(room, {'members': set(), 'password': None})
        rooms[room]['members'].discard(username)
        memberships.discard(room)
        if room == current_active:
            new_active = 'global'
            user_rooms[username] = new_active
        else:
            new_active = current_active
        rooms.setdefault('global', {'members': set(), 'password': None})
        rooms['global']['members'].add(username)
        memberships.add('global')
    send_line(conn, f"Has salido de la sala '{room}'. Sala activa: {new_active}.")
    broadcast_room(room, f"ℹ️ {username} ha abandonado la sala '{room}'.", exclude=username)


def handle_rooms_command(conn):
    with rooms_lock:
        public_rooms = [(room, len(info['members'])) for room, info in rooms.items() if not info.get('password')]
    if not public_rooms:
        send_line(conn, "Salas públicas disponibles: (ninguna)")
        return
    parts = []
    for room, count in sorted(public_rooms, key=lambda x: x[0].lower()):
        parts.append(f"{room} (vacía)" if count == 0 else room)
    send_line(conn, "Salas públicas disponibles: " + ', '.join(parts))


def handle_message(username, text):
    with rooms_lock:
        room = user_rooms.get(username, 'global')
    broadcast_room(room, f"{username}: {text}", exclude=username)


def parse_command(line):
    try:
        return shlex.split(line)
    except ValueError:
        return []


def handle_command(username, conn, line):
    parts = parse_command(line)
    if not parts:
        send_line(conn, "❌ Comando inválido.")
        return
    cmd = parts[0].lower()
    if cmd == '/join':
        if len(parts) < 2:
            send_line(conn, "Uso: /join <sala> [contraseña]")
            return
        room = parts[1]
        password = parts[2] if len(parts) > 2 else None
        handle_join_command(username, conn, room, password)
    elif cmd == '/leave':
        target = parts[1] if len(parts) > 1 else None
        handle_leave_command(username, conn, target)
    elif cmd == '/rooms':
        handle_rooms_command(conn)
    elif cmd == '/quitar':
        send_line(conn, "👋 Desconectado por solicitud.")
        raise DisconnectRequested()
    else:
        send_line(conn, "❌ Comando desconocido.")


def cleanup_user(username):
    with rooms_lock:
        memberships = user_memberships.pop(username, set())
        current = user_rooms.pop(username, None)
        rooms_to_notify = []
        for room in memberships:
            info = rooms.get(room)
            if info:
                info['members'].discard(username)
                rooms_to_notify.append(room)
    with clients_lock:
        clients.pop(username, None)
    for room in rooms_to_notify:
        broadcast_room(room, f"ℹ️ {username} se ha desconectado de la sala '{room}'.", exclude=username)


def handle_client(conn, addr):
    buffer = ''
    username = None
    try:
        send_line(conn, "Ingresa tu nombre (NOMBRE):")
        conn.settimeout(0.5)
        while '\n' not in buffer:
            data = conn.recv(4096)
            if not data:
                raise ConnectionResetError()
            buffer += data.decode('utf-8', errors='replace')
        line, buffer = buffer.split('\n', 1)
        username = line.strip()
        if not username:
            send_line(conn, "Nombre inválido. Cerrando.")
            return
        with clients_lock:
            if username in clients:
                send_line(conn, "Nombre en uso. Intenta con otro.")
                return
            clients[username] = conn
        with rooms_lock:
            rooms.setdefault('global', {'members': set(), 'password': None})
            rooms['global']['members'].add(username)
            user_rooms[username] = 'global'
            user_memberships[username] = {'global'}
        send_line(conn, f"✅ Bienvenido {username}. Estás en 'global'.")
        broadcast_room('global', f"ℹ️ {username} se ha unido al chat global.", exclude=username)

        while True:
            if '\n' not in buffer:
                try:
                    data = conn.recv(4096)
                    if not data:
                        raise ConnectionResetError()
                    buffer += data.decode('utf-8', errors='replace')
                except socket.timeout:
                    continue
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                line = line.strip('\r')
                if not line:
                    continue
                if line.startswith('/'):
                    handle_command(username, conn, line)
                else:
                    handle_message(username, line)
    except DisconnectRequested:
        pass
    except (ConnectionResetError, BrokenPipeError):
        pass
    finally:
        if username:
            cleanup_user(username)
        try:
            conn.close()
        except Exception:
            pass


def accept_loop(server_sock):
    print(f"[SERVER] Escuchando en {HOST}:{PORT}")
    while True:
        try:
            conn, addr = server_sock.accept()
            thread = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            thread.start()
        except KeyboardInterrupt:
            print("[SERVER] Detenido por KeyboardInterrupt.")
            break
        except Exception as exc:
            print(f"[SERVER] Error en accept(): {exc}")
            break


def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen(200)
        accept_loop(s)


if __name__ == '__main__':
    main()
