#!/usr/bin/env python3
"""Servidor de chat compatible con clientes de texto y JSON.

- Mantiene compatibilidad con client_v4.py / client_v5.py (protocolo de texto).
- Acepta client.py y client_v2.py (mensajes JSON por línea).
- Handshake opcional "HELLO_V5" para clientes avanzados.
- Sistema de logging detallado para depuración de conexiones.
"""

import json
import logging
import socket
import threading
import time
import shlex

HOST = '0.0.0.0'
PORT = 55555

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)

LOGGER = logging.getLogger('server_v5')


def now_ts():
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())


clients = {}  # username -> {'conn': socket, 'protocol': 'text'|'json', 'addr': addr}
clients_lock = threading.Lock()

rooms = {'global': {'members': set(), 'password': None}}
rooms_lock = threading.Lock()
user_rooms = {}  # username -> sala activa
user_memberships = {}  # username -> set(salas en las que está unido)


class DisconnectRequested(Exception):
    """Se lanza cuando el cliente solicita desconexión voluntaria."""


def register_client(username, conn, addr, protocol):
    with clients_lock:
        if username in clients:
            return False
        clients[username] = {'conn': conn, 'protocol': protocol, 'addr': addr}
    LOGGER.info("Usuario %s registrado (%s) desde %s", username, protocol, addr)
    return True


def initialize_memberships(username):
    with rooms_lock:
        rooms.setdefault('global', {'members': set(), 'password': None})
        rooms['global']['members'].add(username)
        user_rooms[username] = 'global'
        user_memberships[username] = {'global'}


def send_line(conn, text):
    try:
        conn.sendall((text + "\n").encode('utf-8'))
        LOGGER.debug('→ %s', text)
    except Exception as exc:
        LOGGER.warning('Error enviando texto: %s', exc)
        raise


def send_json(conn, obj):
    try:
        payload = json.dumps(obj, ensure_ascii=False) + '\n'
        conn.sendall(payload.encode('utf-8'))
        LOGGER.debug('→ JSON %s', payload.strip())
    except Exception as exc:
        LOGGER.warning('Error enviando JSON: %s', exc)
        raise


def _format_json_as_text(obj):
    mtype = obj.get('type')
    if mtype == 'msg':
        return f"{obj.get('user', '??')}: {obj.get('text', '')}"
    text = obj.get('text')
    if text:
        return f"[JSON/{mtype}] {text}"
    return json.dumps(obj, ensure_ascii=False)


def broadcast_room(room, *, text=None, json_obj=None, exclude=None):
    with rooms_lock:
        members = [
            username
            for username in rooms.get(room, {}).get('members', set())
            if username != exclude and user_rooms.get(username, 'global') == room
        ]
    targets = []
    with clients_lock:
        for username in members:
            info = clients.get(username)
            if info:
                targets.append((username, info))
    text_data = (text + '\n').encode('utf-8') if text is not None else None
    json_data = (
        (json.dumps(json_obj, ensure_ascii=False) + '\n').encode('utf-8')
        if json_obj is not None
        else None
    )
    for target_username, info in targets:
        conn = info['conn']
        try:
            if info['protocol'] == 'json':
                if json_data is not None:
                    conn.sendall(json_data)
                elif text is not None:
                    fallback = {
                        'type': 'system',
                        'text': text,
                        'time': now_ts(),
                    }
                    conn.sendall(
                        (json.dumps(fallback, ensure_ascii=False) + '\n').encode('utf-8')
                    )
            else:
                if text_data is not None:
                    conn.sendall(text_data)
                elif json_obj is not None:
                    fallback_text = _format_json_as_text(json_obj)
                    conn.sendall((fallback_text + '\n').encode('utf-8'))
        except Exception as exc:
            LOGGER.warning(
                'Error difundiendo a %s (%s): %s',
                target_username,
                info['protocol'],
                exc,
            )


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
        broadcast_room(
            room,
            text=f"🔔 {username} se ha unido a la sala '{room}'.",
            json_obj={
                'type': 'system',
                'text': f"{username} se ha unido a la sala '{room}'.",
                'time': now_ts(),
            },
            exclude=username,
        )
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
    broadcast_room(
        room,
        text=f"ℹ️ {username} ha abandonado la sala '{room}'.",
        json_obj={
            'type': 'system',
            'text': f"{username} ha abandonado la sala '{room}'.",
            'time': now_ts(),
        },
        exclude=username,
    )


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
    broadcast_room(
        room,
        text=f"{username}: {text}",
        json_obj={'type': 'msg', 'user': username, 'text': text, 'time': now_ts()},
        exclude=username,
    )


def parse_command(line):
    try:
        return shlex.split(line)
    except ValueError:
        return []


def handle_json_payload(username, conn, line):
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        LOGGER.warning('JSON inválido recibido de %s: %s', username, line)
        send_json(
            conn,
            {'type': 'system', 'text': 'JSON inválido recibido.', 'time': now_ts()},
        )
        return

    mtype = msg.get('type')
    if mtype == 'msg':
        text = msg.get('text', '')
        if text.startswith('/listar'):
            with clients_lock:
                users = list(clients.keys())
            send_json(
                conn,
                {
                    'type': 'list_response',
                    'users': users,
                    'time': now_ts(),
                },
            )
        elif text.startswith('/quitar'):
            send_json(
                conn,
                {'type': 'system', 'text': 'Desconectando...', 'time': now_ts()},
            )
            raise DisconnectRequested()
        elif text.startswith('/'):
            send_json(
                conn,
                {
                    'type': 'system',
                    'text': 'Comando no soportado en modo JSON.',
                    'time': now_ts(),
                },
            )
        else:
            handle_message(username, text)
    elif mtype == 'join':
        send_json(
            conn,
            {
                'type': 'system',
                'text': 'Ya estás conectado.',
                'time': now_ts(),
            },
        )
    elif mtype == 'system':
        LOGGER.debug('Mensaje system recibido de %s ignorado: %s', username, msg)
    else:
        send_json(
            conn,
            {
                'type': 'system',
                'text': 'Tipo de mensaje desconocido.',
                'time': now_ts(),
            },
        )


def parse_client_handshake_line(line):
    info = {}
    parts = line.split()
    if not parts:
        return info
    for token in parts[1:]:
        if '=' in token:
            key, value = token.split('=', 1)
            info[key.lower()] = value
    return info


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
        info = clients.pop(username, None)
    if info and info.get('conn'):
        try:
            info['conn'].close()
        except Exception:
            pass
    LOGGER.info('Usuario %s limpiado y desconectado', username)
    for room in rooms_to_notify:
        broadcast_room(
            room,
            text=f"ℹ️ {username} se ha desconectado de la sala '{room}'.",
            json_obj={
                'type': 'system',
                'text': f"{username} se ha desconectado de la sala '{room}'.",
                'time': now_ts(),
            },
            exclude=username,
        )


def handle_client(conn, addr):
    buffer = ''
    username = None
    pending_lines = []
    pending_json_lines = []
    handshake_username = None
    protocol = None
    handshake_sent = False
    LOGGER.info('Conexión entrante de %s', addr)
    registered = False
    try:
        conn.settimeout(1.0)

        while username is None:
            try:
                data = conn.recv(4096)
                if not data:
                    raise ConnectionResetError()
                decoded = data.decode('utf-8', errors='replace')
                buffer += decoded
                LOGGER.debug('Datos iniciales desde %s: %r', addr, decoded)
            except socket.timeout:
                if not handshake_sent:
                    LOGGER.debug('Timeout inicial desde %s: enviando HELLO_V5', addr)
                    send_line(conn, "HELLO_V5 features=rooms,public_rooms,sidebar,json")
                    send_line(conn, "Ingresa tu nombre (NOMBRE):")
                    handshake_sent = True
                    protocol = 'text'
                    conn.settimeout(0.5)
                continue

            while '\n' in buffer and username is None:
                line, buffer = buffer.split('\n', 1)
                line = line.strip('\r')
                if not line:
                    continue
                LOGGER.debug('Línea inicial de %s: %s', addr, line)
                if line.startswith('{'):
                    try:
                        msg = json.loads(line)
                    except json.JSONDecodeError:
                        LOGGER.warning('JSON inicial inválido desde %s: %s', addr, line)
                        if protocol == 'json':
                            continue
                    else:
                        if msg.get('type') == 'join':
                            candidate = msg.get('user', '').strip()
                            if not candidate:
                                send_json(
                                    conn,
                                    {
                                        'type': 'system',
                                        'text': 'Nombre de usuario inválido.',
                                        'time': now_ts(),
                                    },
                                )
                                return
                            username = candidate
                            protocol = 'json'
                            continue
                        else:
                            LOGGER.warning('Mensaje inicial JSON inesperado de %s: %s', addr, msg)
                            continue
                if line.upper().startswith('CLIENT_V5'):
                    protocol = 'text'
                    info = parse_client_handshake_line(line)
                    candidate = info.get('username')
                    if candidate:
                        username = candidate.strip()
                        handshake_username = username
                else:
                    protocol = protocol or 'text'
                    username = line.strip()

        if not username:
            LOGGER.warning('Nombre inválido recibido desde %s', addr)
            if protocol == 'json':
                send_json(
                    conn,
                    {'type': 'system', 'text': 'Nombre inválido.', 'time': now_ts()},
                )
            else:
                send_line(conn, 'Nombre inválido. Cerrando.')
            return

        conn.settimeout(0.5)

        if not register_client(username, conn, addr, protocol or 'text'):
            LOGGER.warning('Nombre %s en uso para %s', username, addr)
            if protocol == 'json':
                send_json(
                    conn,
                    {'type': 'system', 'text': 'Nombre en uso.', 'time': now_ts()},
                )
            else:
                send_line(conn, 'Nombre en uso. Intenta con otro.')
            return

        initialize_memberships(username)
        registered = True

        if protocol == 'json':
            send_json(
                conn,
                {'type': 'system', 'text': f'Bienvenido {username}!', 'time': now_ts()},
            )
        else:
            send_line(conn, f"✅ Bienvenido {username}. Estás en 'global'.")

        broadcast_room(
            'global',
            text=f"ℹ️ {username} se ha unido al chat global.",
            json_obj={
                'type': 'system',
                'text': f'{username} se ha unido al chat.',
                'time': now_ts(),
            },
            exclude=username,
        )

        # procesar datos pendientes acumulados durante el handshake
        if protocol == 'text':
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                line = line.strip('\r')
                if not line:
                    continue
                pending_lines.append(line)
            for pending in pending_lines:
                if not pending:
                    continue
                if handshake_username and pending.strip() == handshake_username:
                    handshake_username = None
                    continue
                if pending.startswith('/'):
                    handle_command(username, conn, pending)
                else:
                    handle_message(username, pending)
        else:
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                line = line.strip('\r')
                if line:
                    pending_json_lines.append(line)
            for pending in pending_json_lines:
                handle_json_payload(username, conn, pending)

        while True:
            if '\n' not in buffer:
                try:
                    data = conn.recv(4096)
                    if not data:
                        raise ConnectionResetError()
                    decoded = data.decode('utf-8', errors='replace')
                    buffer += decoded
                    LOGGER.debug('Datos recibidos de %s (%s): %r', username, protocol, decoded)
                except socket.timeout:
                    continue

            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                line = line.strip('\r')
                if not line:
                    continue
                if protocol == 'json':
                    handle_json_payload(username, conn, line)
                else:
                    if handshake_username and line.strip() == handshake_username:
                        handshake_username = None
                        continue
                    if line.startswith('/'):
                        handle_command(username, conn, line)
                    else:
                        handle_message(username, line)
    except DisconnectRequested:
        LOGGER.info('Desconexión solicitada por %s', username or addr)
    except (ConnectionResetError, BrokenPipeError):
        LOGGER.info('Conexión perdida con %s', username or addr)
    except Exception as exc:
        LOGGER.exception('Error manejando a %s: %s', username or addr, exc)
    finally:
        if registered and username:
            cleanup_user(username)
        try:
            conn.close()
        except Exception:
            pass


def accept_loop(server_sock):
    LOGGER.info('Escuchando en %s:%s', HOST, PORT)
    while True:
        try:
            conn, addr = server_sock.accept()
            LOGGER.info('Conexión aceptada de %s', addr)
            thread = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            thread.start()
        except KeyboardInterrupt:
            LOGGER.info('Detenido por KeyboardInterrupt')
            break
        except Exception as exc:
            LOGGER.exception('Error en accept(): %s', exc)
            break


def main():
    LOGGER.info('Arrancando server_v5 en %s:%s', HOST, PORT)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen(200)
        accept_loop(s)


if __name__ == '__main__':
    main()
