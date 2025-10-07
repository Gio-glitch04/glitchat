#!/usr/bin/env python3
"""
server.py - Chat server con soporte de salas (rooms) protegidas, members, y respuestas específicas.
Protocolo: JSON por línea (cada mensaje termina en '\n')

Mensajes importantes del cliente:
 - {'type':'join','user': ...}
 - {'type':'join_room','room': ..., 'password': optional}
 - {'type':'leave_room','room': ...}
 - {'type':'msg_room','room': ..., 'text': ...}
 - {'type':'list_rooms'}
 - {'type':'msg','text': ...}  # compatibilidad -> global

Respuestas/acciones del servidor:
 - {'type':'system', 'text': ...}
 - {'type':'join_room_ok', 'room': ...}
 - {'type':'join_room_failed', 'room': ..., 'reason': 'protected'/'wrong_password'/'no_such_room'}
 - {'type':'leave_room_ok', 'room': ...}
 - {'type':'msg', 'user':..., 'room':..., 'text':..., 'time':...}
 - {'type':'room_list_response', 'rooms': {room: [users,...], ...}}  (NO incluye salas protegidas)
"""

import socket
import threading
import json
import time

HOST = '0.0.0.0'
PORT = 55555

clients = {}           # username -> (conn, addr)
clients_lock = threading.Lock()

# rooms: room_name -> {'members': set(usernames), 'password': None or 'pwd'}
rooms = {'global': {'members': set(), 'password': None}}
rooms_lock = threading.Lock()

user_rooms = {}        # username -> set(room_name)

def now_ts():
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())

def send_json(conn, obj):
    try:
        data = (json.dumps(obj, ensure_ascii=False) + '\n').encode('utf-8')
        conn.sendall(data)
    except Exception:
        # caller handles cleanup
        raise

def broadcast_room(room, obj, exclude_username=None):
    data = (json.dumps(obj, ensure_ascii=False) + '\n').encode('utf-8')
    with rooms_lock:
        members = list(rooms.get(room, {}).get('members', set()))
    with clients_lock:
        for user in members:
            if user == exclude_username:
                continue
            pair = clients.get(user)
            if not pair:
                continue
            conn = pair[0]
            try:
                conn.sendall(data)
            except Exception:
                # ignore here; cleanup happens on disconnect
                pass

def handle_join_room_request(username, conn, room, password):
    """
    Return tuple (ok:bool, reason:str)
    """
    with rooms_lock:
        info = rooms.get(room)
        if info is None:
            # create room (password may be set)
            rooms[room] = {'members': set(), 'password': password}
            info = rooms[room]
        else:
            # exists: check password
            if info.get('password') is not None:
                # protected
                if password is None:
                    return False, 'protected'  # requires password
                if password != info.get('password'):
                    return False, 'wrong_password'
            # if info.password is None and password provided: ignore (no change)
        # add member
        info['members'].add(username)
    # add to user_rooms
    with rooms_lock:
        user_rooms.setdefault(username, set()).add(room)
    return True, None

def handle_leave_room(username, room):
    with rooms_lock:
        info = rooms.get(room)
        if not info:
            return False
        info['members'].discard(username)
        user_rooms.get(username, set()).discard(room)
    return True

def handle_client(conn, addr):
    buf = ''
    username = None
    try:
        conn.settimeout(0.5)
        while True:
            try:
                data = conn.recv(4096)
                if not data:
                    raise ConnectionResetError()
                buf += data.decode('utf-8')
            except socket.timeout:
                pass
            except ConnectionResetError:
                raise
            while '\n' in buf:
                line, buf = buf.split('\n', 1)
                if not line.strip():
                    continue
                try:
                    msg = json.loads(line)
                except Exception:
                    try:
                        send_json(conn, {'type':'system','text':'Mensaje mal formado.','time':now_ts()})
                    except Exception:
                        pass
                    continue

                mtype = msg.get('type')
                if mtype == 'join':
                    requested = msg.get('user','').strip()
                    if not requested:
                        send_json(conn, {'type':'system','text':'Nombre de usuario inválido.','time':now_ts()})
                        conn.close()
                        return
                    with clients_lock:
                        if requested in clients:
                            send_json(conn, {'type':'system','text':'Nombre de usuario en uso.','time':now_ts()})
                            conn.close()
                            return
                        username = requested
                        clients[username] = (conn, addr)
                    # add to global
                    with rooms_lock:
                        rooms.setdefault('global', {'members': set(), 'password': None})
                        rooms['global']['members'].add(username)
                        user_rooms.setdefault(username, set()).add('global')
                    print(f"[SERVER] {username} conectado desde {addr}")
                    send_json(conn, {'type':'system','text': f'Bienvenido {username}!', 'time': now_ts()})
                    broadcast_room('global', {'type':'system','text': f'{username} se ha unido al chat (global).', 'time': now_ts()}, exclude_username=username)

                elif not username:
                    send_json(conn, {'type':'system','text':'No estás registrado. Envía join primero.','time': now_ts()})
                    conn.close()
                    return

                elif mtype == 'join_room':
                    room = msg.get('room','').strip()
                    password = msg.get('password') if 'password' in msg else None
                    if not room:
                        send_json(conn, {'type':'join_room_failed','room':room,'reason':'invalid_name','time':now_ts()})
                        continue
                    ok, reason = handle_join_room_request(username, conn, room, password)
                    if ok:
                        # confirm to requester
                        try:
                            send_json(conn, {'type':'join_room_ok','room':room,'time':now_ts()})
                        except Exception:
                            pass
                        # announce to room (exclude requester)
                        broadcast_room(room, {'type':'system','text': f'{username} se ha unido a la sala "{room}".', 'time': now_ts()}, exclude_username=username)
                    else:
                        # failed -> inform requester with reason
                        try:
                            send_json(conn, {'type':'join_room_failed','room':room,'reason':reason,'time':now_ts()})
                        except Exception:
                            pass

                elif mtype == 'leave_room':
                    room = msg.get('room','').strip()
                    if not room:
                        send_json(conn, {'type':'system','text':'Nombre de sala inválido.','time': now_ts()})
                        continue
                    if room == 'global':
                        send_json(conn, {'type':'system','text':'No puedes abandonar la sala global.','time': now_ts()})
                        continue
                    ok = handle_leave_room(username, room)
                    if ok:
                        try:
                            send_json(conn, {'type':'leave_room_ok','room':room,'time':now_ts()})
                        except Exception:
                            pass
                        broadcast_room(room, {'type':'system','text': f'{username} ha abandonado la sala "{room}".', 'time': now_ts()}, exclude_username=username)
                    else:
                        send_json(conn, {'type':'system','text': f'No estabas en la sala "{room}".','time': now_ts()})

                elif mtype == 'msg_room':
                    room = msg.get('room','').strip()
                    text = msg.get('text','')
                    if not room:
                        send_json(conn, {'type':'system','text':'Sala desconocida.','time': now_ts()})
                        continue
                    with rooms_lock:
                        if room not in rooms:
                            send_json(conn, {'type':'system','text':'Sala desconocida.','time': now_ts()})
                            continue
                        # only if user is member - otherwise ignore
                        if username not in rooms[room]['members']:
                            send_json(conn, {'type':'system','text':'No estás en esa sala. Únete primero.','time': now_ts()})
                            continue
                    # broadcast to members; include sender as well (client will ignore own re-broadcast)
                    broadcast_room(room, {'type':'msg','user': username, 'text': text, 'room': room, 'time': now_ts()}, exclude_username=None)

                elif mtype == 'list_rooms':
                    # build listing excluding protected rooms
                    with rooms_lock:
                        snapshot = { r: list(info['members']) for r, info in rooms.items() if info.get('password') is None }
                    try:
                        send_json(conn, {'type':'room_list_response','rooms': snapshot, 'time': now_ts()})
                    except Exception:
                        pass

                elif mtype == 'msg':
                    # backward compatibility: send to global if member
                    text = msg.get('text','')
                    with rooms_lock:
                        if username in rooms.get('global', {}).get('members', set()):
                            broadcast_room('global', {'type':'msg','user': username, 'text': text, 'room': 'global', 'time': now_ts()}, exclude_username=None)

                else:
                    try:
                        send_json(conn, {'type':'system','text':'Tipo de mensaje desconocido.','time': now_ts()})
                    except Exception:
                        pass

    except (ConnectionResetError, BrokenPipeError):
        pass
    except Exception as e:
        print(f"[SERVER] Error con cliente {addr}: {e}")
    finally:
        # cleanup
        if username:
            with clients_lock:
                clients.pop(username, None)
            with rooms_lock:
                # remove from all rooms and announce
                rooms_to_clean = list(user_rooms.get(username, set()))
                for r in rooms_to_clean:
                    rooms.get(r, {}).get('members', set()).discard(username)
                    broadcast_room(r, {'type':'system','text': f'{username} se ha desconectado.', 'time': now_ts()}, exclude_username=username)
                user_rooms.pop(username, None)
            print(f"[SERVER] {username} desconectado.")
        try:
            conn.close()
        except Exception:
            pass

def accept_loop(server_sock):
    print(f"[SERVER] Escuchando en {HOST}:{PORT}")
    while True:
        try:
            conn, addr = server_sock.accept()
            t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            t.start()
        except KeyboardInterrupt:
            print("[SERVER] Cerrando por KeyboardInterrupt.")
            server_sock.close()
            break
        except Exception as e:
            print(f"[SERVER] Error en accept(): {e}")
            break

def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen(200)
        accept_loop(s)

if __name__ == '__main__':
    main()
