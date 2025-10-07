#!/usr/bin/env python3
"""
server.py - Chat server con soporte de salas (rooms)
Protocolo: JSON por línea (cada mensaje termina en '\n')
Tipos principales:
 - join (cuando cliente se conecta): {'type':'join','user':...}
 - join_room: {'type':'join_room','room': 'nombre'}
 - leave_room: {'type':'leave_room','room': 'nombre'}
 - msg_room: {'type':'msg_room','room':'nombre','text':'...'}
 - list_rooms: {'type':'list_rooms'}
 - system messages: {'type':'system','text':..., 'time':...}
 - room_list_response: {'type':'room_list_response','rooms': {'room': [user,...], ...} }
"""

import socket
import threading
import json
import time

HOST = '0.0.0.0'
PORT = 50000

clients = {}        # username -> (conn, addr)
clients_lock = threading.Lock()

rooms = {'global': set()}       # room_name -> set(usernames)
user_rooms = {}                 # username -> set(room_name)
rooms_lock = threading.Lock()

def now_ts():
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())

def send_json(conn, obj):
    data = (json.dumps(obj, ensure_ascii=False) + '\n').encode('utf-8')
    conn.sendall(data)

def broadcast_room(room, obj, exclude_username=None):
    """Enviar obj (dict) a todos los miembros de room excepto exclude_username"""
    data = (json.dumps(obj, ensure_ascii=False) + '\n').encode('utf-8')
    with rooms_lock:
        members = list(rooms.get(room, []))
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
                # si falla, ignoramos aquí; limpieza se hace en handle_client
                pass

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
                    send_json(conn, {'type':'system','text':'Mensaje mal formado.','time': now_ts()})
                    continue

                mtype = msg.get('type')
                if mtype == 'join':
                    requested = msg.get('user','').strip()
                    if not requested:
                        send_json(conn, {'type':'system','text':'Nombre de usuario inválido.','time': now_ts()})
                        conn.close()
                        return
                    with clients_lock:
                        if requested in clients:
                            send_json(conn, {'type':'system','text':'Nombre de usuario en uso.','time': now_ts()})
                            conn.close()
                            return
                        username = requested
                        clients[username] = (conn, addr)
                    # añadir a global
                    with rooms_lock:
                        rooms.setdefault('global', set()).add(username)
                        user_rooms.setdefault(username, set()).add('global')
                    print(f"[SERVER] {username} conectado desde {addr}")
                    send_json(conn, {'type':'system','text': f'Bienvenido {username}!', 'time': now_ts()})
                    # anunciar en global (excepto al que llega)
                    broadcast_room('global', {'type':'system','text': f'{username} se ha unido al chat (global).', 'time': now_ts()}, exclude_username=username)

                elif not username:
                    send_json(conn, {'type':'system','text':'No estás registrado. Envía join primero.','time': now_ts()})
                    conn.close()
                    return

                elif mtype == 'join_room':
                    room = msg.get('room','').strip()
                    if not room:
                        send_json(conn, {'type':'system','text':'Nombre de sala inválido.','time': now_ts()})
                        continue
                    with rooms_lock:
                        rooms.setdefault(room, set()).add(username)
                        user_rooms.setdefault(username, set()).add(room)
                    send_json(conn, {'type':'system','text':f'Te has unido a la sala "{room}".','time': now_ts()})
                    broadcast_room(room, {'type':'system','text':f'{username} se ha unido a la sala "{room}".','time': now_ts()}, exclude_username=username)

                elif mtype == 'leave_room':
                    room = msg.get('room','').strip()
                    if not room:
                        send_json(conn, {'type':'system','text':'Nombre de sala inválido.','time': now_ts()})
                        continue
                    with rooms_lock:
                        if room in user_rooms.get(username, set()):
                            user_rooms[username].discard(room)
                            rooms.get(room,set()).discard(username)
                            send_json(conn, {'type':'system','text':f'Te has salido de la sala "{room}".','time': now_ts()})
                            broadcast_room(room, {'type':'system','text':f'{username} ha abandonado la sala "{room}".','time': now_ts()}, exclude_username=username)
                        else:
                            send_json(conn, {'type':'system','text':f'No estabas en la sala "{room}".','time': now_ts()})

                elif mtype == 'msg_room':
                    room = msg.get('room','').strip()
                    text = msg.get('text','')
                    if not room or room not in rooms:
                        send_json(conn, {'type':'system','text':'Sala desconocida.','time': now_ts()})
                        continue
                    # enviar solo a miembros
                    broadcast_room(room, {'type':'msg','user': username, 'text': text, 'room': room, 'time': now_ts()}, exclude_username=None)

                elif mtype == 'list_rooms':
                    # enviar lista completa de rooms y miembros
                    with rooms_lock:
                        snapshot = { r: list(members) for r,members in rooms.items() }
                    send_json(conn, {'type':'room_list_response','rooms': snapshot, 'time': now_ts()})

                elif mtype == 'msg':
                    # backward compatibility: enviar a global
                    text = msg.get('text','')
                    broadcast_room('global', {'type':'msg','user': username, 'text': text, 'room': 'global', 'time': now_ts()}, exclude_username=None)

                else:
                    send_json(conn, {'type':'system','text':'Tipo de mensaje desconocido.','time': now_ts()})
    except (ConnectionResetError, BrokenPipeError):
        pass
    except Exception as e:
        print(f"[SERVER] Error con cliente {addr}: {e}")
    finally:
        # limpiar al desconectarse
        if username:
            with clients_lock:
                clients.pop(username, None)
            with rooms_lock:
                # remover usuario de todas las salas y anunciar
                rooms_to_clean = list(user_rooms.get(username, set()))
                for r in rooms_to_clean:
                    rooms.get(r, set()).discard(username)
                    broadcast_room(r, {'type':'system','text':f'{username} se ha desconectado.', 'time': now_ts()}, exclude_username=username)
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
