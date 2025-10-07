#!/usr/bin/env python3
"""
server.py
Servidor de chat simple basado en sockets.
Protocolo: JSON por línea (cada mensaje termina en '\n')
Campos principales: type, user, text, time
"""

import socket
import threading
import json
import time

HOST = '0.0.0.0'  # escuchar en todas las interfaces
PORT = 50000      # puerto (puedes cambiarlo)

# Diccionario: username -> (conn, addr)
clients = {}
clients_lock = threading.Lock()

def now_ts():
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())

def send_json(conn, obj):
    try:
        data = (json.dumps(obj, ensure_ascii=False) + '\n').encode('utf-8')
        conn.sendall(data)
    except Exception:
        raise

def broadcast(obj, exclude_conn=None):
    """Enviar obj (dict) a todos los clientes excepto exclude_conn"""
    to_remove = []
    data = (json.dumps(obj, ensure_ascii=False) + '\n').encode('utf-8')
    with clients_lock:
        for user, (conn, addr) in list(clients.items()):
            if conn == exclude_conn:
                continue
            try:
                conn.sendall(data)
            except Exception:
                # marcar para remover
                to_remove.append(user)
        # limpiar desconectados
        for u in to_remove:
            print(f"[SERVER] Removiendo cliente por fallo: {u}")
            try:
                clients[u][0].close()
            except Exception:
                pass
            clients.pop(u, None)
            # anunciar que el usuario se fue
            broadcast({'type':'system', 'text': f'{u} se ha desconectado (forzado).', 'time': now_ts()})

def handle_client(conn, addr):
    """
    Rutina por cliente.
    Espera primer mensaje: join con {"type":"join","user":"nombre"}.
    Luego procesa mensajes.
    """
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
                # permitimos timeouts para chequear shutdown / etc.
                pass
            except ConnectionResetError:
                raise
            # procesar líneas completas
            while '\n' in buf:
                line, buf = buf.split('\n', 1)
                if not line.strip():
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    send_json(conn, {'type':'system', 'text':'Mensaje mal formado.' , 'time': now_ts()})
                    continue

                mtype = msg.get('type')
                if mtype == 'join':
                    # registro
                    requested = msg.get('user', '').strip()
                    if not requested:
                        send_json(conn, {'type':'system','text':'Nombre de usuario inválido.','time':now_ts()})
                        conn.close()
                        return
                    with clients_lock:
                        if requested in clients:
                            # usuario ya existe
                            send_json(conn, {'type':'system','text':'Nombre de usuario en uso.','time':now_ts()})
                            conn.close()
                            return
                        username = requested
                        clients[username] = (conn, addr)
                        print(f"[SERVER] {username} se unió desde {addr}")
                    # confirmar y anunciar
                    send_json(conn, {'type':'system','text':f'Bienvenido {username}!', 'time': now_ts()})
                    broadcast({'type':'system','text':f'{username} se ha unido al chat.', 'time': now_ts()}, exclude_conn=conn)
                elif mtype == 'msg':
                    text = msg.get('text', '')
                    if text.startswith('/listar'):
                        # enviar lista de usuarios
                        with clients_lock:
                            lista = list(clients.keys())
                        send_json(conn, {'type':'list_response','users': lista, 'time': now_ts()})
                    elif text.startswith('/quitar'):
                        # quitar cliente voluntariamente
                        send_json(conn, {'type':'system','text':'Desconectando...','time': now_ts()})
                        raise ConnectionResetError("cliente solicitó desconexión")
                    else:
                        # mensaje normal: re-enviar a todos
                        broadcast({'type':'msg','user': username, 'text': text, 'time': now_ts()}, exclude_conn=None)
                else:
                    send_json(conn, {'type':'system','text':'Tipo de mensaje desconocido.','time': now_ts()})
    except (ConnectionResetError, BrokenPipeError):
        # desconexión
        pass
    except Exception as e:
        print(f"[SERVER] Error con cliente {addr}: {e}")
    finally:
        # limpiar
        if username:
            with clients_lock:
                if username in clients:
                    try:
                        clients[username][0].close()
                    except Exception:
                        pass
                    clients.pop(username, None)
            print(f"[SERVER] {username} desconectado.")
            broadcast({'type':'system','text':f'{username} se ha desconectado.', 'time': now_ts()})
        else:
            try:
                conn.close()
            except Exception:
                pass

def accept_loop(server_sock):
    print(f"[SERVER] Escuchando en {HOST}:{PORT}")
    while True:
        try:
            conn, addr = server_sock.accept()
            print(f"[SERVER] Conexión desde {addr}")
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
        s.listen(100)
        accept_loop(s)

if __name__ == '__main__':
    main()
