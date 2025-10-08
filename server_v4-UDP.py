#!/usr/bin/env python3
"""Servidor de chat compatible con el protocolo de texto de server_v4.py pero usando UDP."""

import socket
import threading
import shlex

HOST = '0.0.0.0'
PORT = 55555

udp_socket = None  # se inicializa en main()

clients = {}  # username -> address
address_users = {}  # address -> username
clients_lock = threading.Lock()

rooms = {'global': {'members': set(), 'password': None}}
rooms_lock = threading.Lock()
user_rooms = {}  # username -> sala activa
user_memberships = {}  # username -> set(salas en las que está unido)


class DisconnectRequested(Exception):
    """Se lanza cuando el cliente solicita desconexión voluntaria."""


def send_line_to_addr(addr, text):
    if udp_socket is None:
        return
    try:
        udp_socket.sendto((text + "\n").encode('utf-8'), addr)
    except Exception:
        pass


def send_line(username, text):
    with clients_lock:
        addr = clients.get(username)
    if addr:
        send_line_to_addr(addr, text)


def broadcast_room(room, text, exclude=None):
    with rooms_lock:
        members = [
            username
            for username in rooms.get(room, {}).get('members', set())
            if username != exclude and user_rooms.get(username, 'global') == room
        ]
    with clients_lock:
        targets = [clients[username] for username in members if username in clients]
    data = (text + "\n").encode('utf-8')
    for addr in targets:
        try:
            udp_socket.sendto(data, addr)
        except Exception:
            pass


def handle_join_command(username, room, password):
    room = room.strip()
    if not room:
        send_line(username, "❌ Debes indicar un nombre de sala.")
        return
    with rooms_lock:
        info = rooms.get(room)
        already_member = False
        if info:
            already_member = username in info.get('members', set())
            stored_pwd = info.get('password')
            if not already_member and stored_pwd:
                if password is None or password != stored_pwd:
                    send_line(username, "❌ Contraseña incorrecta.")
                    return
        else:
            rooms[room] = {'members': set(), 'password': password if password else None}
            info = rooms[room]
        info['members'].add(username)
        user_memberships.setdefault(username, set()).add(room)
        user_rooms[username] = room
    if not already_member:
        broadcast_room(room, f"🔔 {username} se ha unido a la sala '{room}'.", exclude=username)
    send_line(username, f"✅ Te has unido a la sala '{room}'.")


def handle_leave_command(username, target_room=None):
    with rooms_lock:
        current_active = user_rooms.get(username, 'global')
        memberships = user_memberships.setdefault(username, set())
        room = target_room.strip() if target_room else current_active
        if room not in memberships:
            send_line(username, f"No estás en la sala '{room}'.")
            return
        if room == 'global':
            send_line(username, "No puedes salir del chat global.")
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
    send_line(username, f"Has salido de la sala '{room}'. Sala activa: {new_active}.")
    broadcast_room(room, f"ℹ️ {username} ha abandonado la sala '{room}'.", exclude=username)


def handle_rooms_command(username):
    with rooms_lock:
        public_rooms = [
            (room, len(info['members']))
            for room, info in rooms.items()
            if not info.get('password')
        ]
    if not public_rooms:
        send_line(username, "Salas públicas disponibles: (ninguna)")
        return
    parts = []
    for room, count in sorted(public_rooms, key=lambda x: x[0].lower()):
        parts.append(f"{room} (vacía)" if count == 0 else room)
    send_line(username, "Salas públicas disponibles: " + ', '.join(parts))


def handle_message(username, text):
    with rooms_lock:
        room = user_rooms.get(username, 'global')
    broadcast_room(room, f"{username}: {text}", exclude=username)


def parse_command(line):
    try:
        return shlex.split(line)
    except ValueError:
        return []


def handle_command(username, line):
    parts = parse_command(line)
    if not parts:
        send_line(username, "❌ Comando inválido.")
        return
    cmd = parts[0].lower()
    if cmd == '/join':
        if len(parts) < 2:
            send_line(username, "Uso: /join <sala> [contraseña]")
            return
        room = parts[1]
        password = parts[2] if len(parts) > 2 else None
        handle_join_command(username, room, password)
    elif cmd == '/leave':
        target = parts[1] if len(parts) > 1 else None
        handle_leave_command(username, target)
    elif cmd == '/rooms':
        handle_rooms_command(username)
    elif cmd == '/quitar':
        send_line(username, "👋 Desconectado por solicitud.")
        raise DisconnectRequested()
    else:
        send_line(username, "❌ Comando desconocido.")


def cleanup_user(username):
    with rooms_lock:
        memberships = user_memberships.pop(username, set())
        user_rooms.pop(username, None)
        rooms_to_notify = []
        for room in memberships:
            info = rooms.get(room)
            if info:
                info['members'].discard(username)
                rooms_to_notify.append(room)
    with clients_lock:
        addr = clients.pop(username, None)
        if addr:
            address_users.pop(addr, None)
    for room in rooms_to_notify:
        broadcast_room(room, f"ℹ️ {username} se ha desconectado de la sala '{room}'.", exclude=username)


def register_username(addr, requested_name):
    username = requested_name.strip()
    if not username:
        send_line_to_addr(addr, "❌ Nombre inválido. Usa: HELLO <nombre>")
        return
    with clients_lock:
        if username in clients:
            send_line_to_addr(addr, "❌ Nombre en uso. Intenta con otro.")
            return
        if addr in address_users:
            current = address_users[addr]
            send_line_to_addr(addr, f"Ya estás identificado como {current}. Usa /quitar para desconectarte.")
            return
        clients[username] = addr
        address_users[addr] = username
    with rooms_lock:
        rooms.setdefault('global', {'members': set(), 'password': None})
        rooms['global']['members'].add(username)
        user_rooms[username] = 'global'
        user_memberships[username] = {'global'}
    send_line_to_addr(addr, f"✅ Bienvenido {username}. Estás en 'global'.")
    broadcast_room('global', f"ℹ️ {username} se ha unido al chat global.", exclude=username)


def process_user_line(username, line):
    line = line.strip('\r')
    if not line:
        return
    try:
        if line.startswith('/'):
            handle_command(username, line)
        else:
            handle_message(username, line)
    except DisconnectRequested:
        cleanup_user(username)


def handle_datagram(data, addr):
    message = data.decode('utf-8', errors='replace')
    lines = message.split('\n')
    with clients_lock:
        username = address_users.get(addr)
    if username is None:
        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue
            if line.upper().startswith('HELLO '):
                register_username(addr, line[6:])
            else:
                send_line_to_addr(addr, "❌ No identificado. Envía: HELLO <nombre>")
        return
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if line.upper().startswith('HELLO '):
            send_line(username, f"Ya estás conectado como {username}.")
            continue
        process_user_line(username, line)


def main():
    global udp_socket
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.bind((HOST, PORT))
    print(f"[SERVER] Escuchando (UDP) en {HOST}:{PORT}")
    try:
        while True:
            data, addr = udp_socket.recvfrom(65535)
            handle_datagram(data, addr)
    except KeyboardInterrupt:
        print("[SERVER] Detenido por KeyboardInterrupt.")
    finally:
        udp_socket.close()


if __name__ == '__main__':
    main()
