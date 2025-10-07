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
user_rooms = {}  # username -> current room


class DisconnectRequested(Exception):
    """Se lanza cuando el cliente solicita desconexión voluntaria."""


def send_line(conn, text):
    try:
        conn.sendall((text + "\n").encode('utf-8'))
    except Exception:
        raise


def broadcast_room(room, text, exclude=None):
    with rooms_lock:
        members = list(rooms.get(room, {}).get('members', set()))
    targets = []
    with clients_lock:
        for username in members:
            if username == exclude:
                continue
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
        if info:
            stored_pwd = info.get('password')
            if stored_pwd:
                if password is None or password != stored_pwd:
                    send_line(conn, "❌ Contraseña incorrecta.")
                    return
        else:
            rooms[room] = {'members': set(), 'password': password if password else None}
    move_user_to_room(username, conn, room, success_message=f"✅ Te has unido a la sala '{room}'.")


def handle_leave_command(username, conn):
    with rooms_lock:
        current = user_rooms.get(username, 'global')
    if current == 'global':
        send_line(conn, "No puedes salir del chat global.")
        return
    move_user_to_room(username, conn, 'global', success_message='Has vuelto al chat global.')


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


def move_user_to_room(username, conn, new_room, success_message=None):
    with rooms_lock:
        current = user_rooms.get(username, 'global')
        if current == new_room:
            if success_message:
                send_line(conn, success_message)
            else:
                send_line(conn, f"ℹ️ Ya estás en la sala '{new_room}'.")
            return
        rooms.setdefault(current, {'members': set(), 'password': None})
        rooms[current]['members'].discard(username)
        rooms.setdefault(new_room, {'members': set(), 'password': None})
        rooms[new_room]['members'].add(username)
        user_rooms[username] = new_room
    if current:
        broadcast_room(current, f"ℹ️ {username} ha salido de la sala '{current}'.", exclude=username)
    if success_message:
        send_line(conn, success_message)
    else:
        send_line(conn, f"✅ Te has unido a la sala '{new_room}'.")
    broadcast_room(new_room, f"🔔 {username} se ha unido a la sala '{new_room}'.", exclude=username)


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
        handle_leave_command(username, conn)
    elif cmd == '/rooms':
        handle_rooms_command(conn)
    elif cmd == '/quitar':
        send_line(conn, "👋 Desconectado por solicitud.")
        raise DisconnectRequested()
    else:
        send_line(conn, "❌ Comando desconocido.")


def cleanup_user(username):
    with rooms_lock:
        current = user_rooms.pop(username, None)
        if current and current in rooms:
            rooms[current]['members'].discard(username)
    with clients_lock:
        clients.pop(username, None)
    if current:
        broadcast_room(current, f"ℹ️ {username} se ha desconectado de la sala '{current}'.", exclude=username)


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
