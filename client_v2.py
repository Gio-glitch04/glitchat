#!/usr/bin/env python3
"""
client.py - Cliente con UI Tkinter.
Mejoras:
 - Combobox de servidores recientes (servers.json)
 - Salas con historiales separados
 - Notificación de mensajes no leídos (sala (n))
 - Salas protegidas por contraseña; cliente pide clave automáticamente si es necesario
 - Evita duplicado de mensajes propios: cliente **ignora** mensajes recibidos cuyo user == self.username
"""

import socket
import threading
import json
import time
import os
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox, scrolledtext

SERVER_FILE = 'servers.json'
DEFAULT_HOST = '127.0.0.1'
DEFAULT_PORT = 50000

def now_ts():
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())

def load_servers():
    if not os.path.exists(SERVER_FILE):
        return {}
    try:
        with open(SERVER_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def save_servers(data):
    try:
        with open(SERVER_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Error guardando servers.json:", e)

class ChatClient:
    def __init__(self, master):
        self.master = master
        master.title("Chat - Cliente (Salas, contraseñas y recientes)")
        master.geometry("900x520")

        # --- top frame: server controls ---
        top = tk.Frame(master)
        top.pack(fill='x', padx=6, pady=4)

        tk.Label(top, text="Servidor:").pack(side='left')
        self.server_entry = tk.Entry(top, width=18)
        self.server_entry.pack(side='left', padx=4)
        self.server_entry.insert(0, DEFAULT_HOST)

        tk.Label(top, text="Puerto:").pack(side='left')
        self.port_entry = tk.Entry(top, width=6)
        self.port_entry.pack(side='left', padx=4)
        self.port_entry.insert(0, str(DEFAULT_PORT))

        tk.Label(top, text="Usuario:").pack(side='left', padx=(10,0))
        self.user_entry = tk.Entry(top, width=12)
        self.user_entry.pack(side='left', padx=4)

        self.connect_btn = tk.Button(top, text="Conectar", command=self.connect)
        self.connect_btn.pack(side='left', padx=6)

        # Servers combobox + save button
        tk.Label(top, text="Recientes:").pack(side='left', padx=(10,0))
        self.servers = load_servers()
        self.server_names = list(self.servers.keys())
        self.combo = ttk.Combobox(top, values=self.server_names, width=18, state='readonly')
        self.combo.pack(side='left', padx=4)
        self.combo.bind("<<ComboboxSelected>>", self.on_server_selected)

        self.save_server_btn = tk.Button(top, text="Guardar servidor...", command=self.save_current_server)
        self.save_server_btn.pack(side='left', padx=6)

        # --- main area: sidebar + chat area ---
        main = tk.Frame(master)
        main.pack(fill='both', expand=True, padx=6, pady=4)

        # Sidebar for rooms
        side = tk.Frame(main, width=220)
        side.pack(side='left', fill='y', padx=(0,6))
        tk.Label(side, text="Salas (doble clic para activar):").pack(anchor='w')
        self.rooms_listbox = tk.Listbox(side, width=30, height=24)
        self.rooms_listbox.pack(fill='y', expand=False)
        self.rooms_listbox.bind("<Double-Button-1>", self.on_room_double_click)

        # create/join room controls
        rframe = tk.Frame(side)
        rframe.pack(fill='x', pady=(6,0))
        self.new_room_entry = tk.Entry(rframe)
        self.new_room_entry.pack(side='left', fill='x', expand=True)
        tk.Button(rframe, text="Crear/Unir", command=self.create_or_join_room).pack(side='left', padx=4)
        tk.Button(side, text="Listar salas (server)", command=self.request_rooms_list).pack(fill='x', pady=(6,0))

        # Chat area
        right = tk.Frame(main)
        right.pack(side='left', fill='both', expand=True)

        # label for active room
        self.active_room_var = tk.StringVar(value='Activa: global')
        self.active_label = tk.Label(right, textvariable=self.active_room_var, font=('TkDefaultFont', 10, 'bold'))
        self.active_label.pack(anchor='w')

        self.chat_area = scrolledtext.ScrolledText(right, state='disabled', wrap='word')
        self.chat_area.pack(fill='both', expand=True)

        # bottom: message entry
        bottom = tk.Frame(master)
        bottom.pack(fill='x', padx=6, pady=6)
        self.msg_entry = tk.Entry(bottom)
        self.msg_entry.pack(side='left', fill='x', expand=True, padx=(0,6))
        self.msg_entry.bind("<Return>", lambda e: self.send_message())
        self.send_btn = tk.Button(bottom, text="Enviar", command=self.send_message, state='disabled')
        self.send_btn.pack(side='right')

        # internals
        self.sock = None
        self.listener_thread = None
        self.running = False
        self.username = None

        # per-room data
        self.joined_rooms = set()            # rooms the user is in
        self.room_histories = {}             # room -> [lines]
        self.unread_counts = {}              # room -> int
        self.active_room = 'global'

        # init: load servers into combobox
        self.refresh_combobox()

        master.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------------- UI helpers ----------------
    def _append_to_history(self, room, line):
        self.room_histories.setdefault(room, []).append(line)

    def render_active_room(self):
        # show history of active_room
        history = self.room_histories.get(self.active_room, [])
        self.chat_area.configure(state='normal')
        self.chat_area.delete('1.0', 'end')
        for l in history:
            self.chat_area.insert('end', l + '\n')
        self.chat_area.see('end')
        self.chat_area.configure(state='disabled')

    def refresh_combobox(self):
        self.server_names = list(self.servers.keys())
        self.combo['values'] = self.server_names

    def on_server_selected(self, event=None):
        name = self.combo.get()
        if name in self.servers:
            self.server_entry.delete(0,'end')
            self.server_entry.insert(0, self.servers[name]['host'])
            self.port_entry.delete(0,'end')
            self.port_entry.insert(0, str(self.servers[name]['port']))

    def save_current_server(self):
        alias = simpledialog.askstring("Guardar servidor", "Alias para este servidor:")
        if not alias:
            return
        host = self.server_entry.get().strip()
        try:
            port = int(self.port_entry.get().strip())
        except ValueError:
            messagebox.showerror("Error", "Puerto inválido.")
            return
        self.servers[alias] = {'host': host, 'port': port}
        save_servers(self.servers)
        self.refresh_combobox()
        self.combo.set(alias)
        messagebox.showinfo("Guardado", f"Servidor guardado como '{alias}'")

    def update_rooms_listbox(self):
        # reconstruct listbox with unread counts (format: room (n) if n>0)
        self.rooms_listbox.delete(0, 'end')
        # prefer global first if present
        rooms_sorted = []
        if 'global' in self.joined_rooms:
            rooms_sorted.append('global')
        others = sorted(r for r in self.joined_rooms if r != 'global')
        rooms_sorted.extend(others)
        for r in rooms_sorted:
            n = self.unread_counts.get(r, 0)
            display = f"{r} ({n})" if n > 0 else r
            self.rooms_listbox.insert('end', display)

    def on_room_double_click(self, event=None):
        sel = self.rooms_listbox.curselection()
        if not sel:
            return
        display = self.rooms_listbox.get(sel[0])
        # extract room name (strip trailing " (n)" if exists)
        if ' (' in display:
            room = display.split(' (',1)[0]
        else:
            room = display
        self.set_active_room(room)

    def set_active_room(self, room):
        if room not in self.joined_rooms:
            messagebox.showwarning("No estás unido", f"No estás en la sala '{room}'. Únete primero.")
            return
        self.active_room = room
        self.active_room_var.set(f"Activa: {room}")
        # clear unread counter for room
        if self.unread_counts.get(room, 0) > 0:
            self.unread_counts[room] = 0
            self.update_rooms_listbox()
        # render history
        self.render_active_room()

    # ---------------- Networking ----------------
    def connect(self):
        if self.sock:
            messagebox.showinfo("Info", "Ya estás conectado.")
            return
        server = self.server_entry.get().strip()
        try:
            port = int(self.port_entry.get().strip())
        except ValueError:
            messagebox.showerror("Error", "Puerto inválido.")
            return
        username = self.user_entry.get().strip()
        if not username:
            messagebox.showerror("Error", "Ingrese un nombre de usuario.")
            return

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((server, port))
            s.settimeout(0.5)
            self.sock = s
            self.username = username
            # send join
            join = {'type':'join','user': username}
            s.sendall((json.dumps(join, ensure_ascii=False) + '\n').encode('utf-8'))
            self.running = True
            self.listener_thread = threading.Thread(target=self.listen_loop, daemon=True)
            self.listener_thread.start()
            self.connect_btn.configure(state='disabled')
            self.send_btn.configure(state='normal')
            # initial room setup: we'll assume server adds to global
            self.joined_rooms = set(['global'])
            self.room_histories = {'global': []}
            self.unread_counts = {'global': 0}
            self.active_room = 'global'
            self.active_room_var.set(f"Activa: global")
            self.update_rooms_listbox()
            # local feedback
            self._append_local(f"[{now_ts()}] Conectado a {server}:{port} como {username}")
        except Exception as e:
            messagebox.showerror("Error de conexión", f"No se pudo conectar: {e}")
            if self.sock:
                try:
                    self.sock.close()
                except Exception:
                    pass
                self.sock = None

    def listen_loop(self):
        buf = ''
        while self.running and self.sock:
            try:
                data = self.sock.recv(4096)
                if not data:
                    raise ConnectionResetError()
                buf += data.decode('utf-8')
                while '\n' in buf:
                    line, buf = buf.split('\n', 1)
                    if not line.strip():
                        continue
                    try:
                        msg = json.loads(line)
                    except json.JSONDecodeError:
                        self.master.after(0, lambda: self._append_local("[Sistema] Mensaje mal formado recibido."))
                        continue
                    self.master.after(0, lambda m=msg: self.process_message(m))
            except socket.timeout:
                continue
            except Exception:
                self.running = False
                self.master.after(0, lambda: self._append_local(f"[{now_ts()}] Desconectado del servidor."))
                self.master.after(0, self.disconnect_ui)
                break

    # ---------------- Message processing ----------------
    def _append_local(self, text, room=None):
        # append line into room history (or active room if None)
        target = room if room else self.active_room
        self._append_to_history(target, text)
        # if target is active room, render; else increment unread
        if target == self.active_room:
            self.render_active_room()
        else:
            self.unread_counts[target] = self.unread_counts.get(target, 0) + 1
            self.update_rooms_listbox()

    def process_message(self, msg):
        mtype = msg.get('type')
        if mtype == 'system':
            text = f"[{msg.get('time', now_ts())}] [Sistema] {msg.get('text')}"
            # system messages: if include 'room' field use it, else put in active/global
            room = msg.get('room', None)
            if room:
                self._append_local(text, room=room)
            else:
                # put in active room (or global)
                self._append_local(text, room=self.active_room)
        elif mtype == 'msg':
            user = msg.get('user','desconocido')
            room = msg.get('room','global')
            text = msg.get('text','')
            t = msg.get('time', now_ts())
            # avoid duplicate: if message from myself, ignore (we already showed "Tú:")
            if user == self.username:
                return
            line = f"[{t}] [{room}] {user}: {text}"
            # if user is in the client joined_rooms for that room, append; else ignore
            # (server should only send to members, but this is safe)
            if room in self.joined_rooms:
                self._append_local(line, room=room)
        elif mtype == 'join_ok':
            room = msg.get('room')
            # server confirmed join - we already optimistically added, but ensure structures are present
            self.joined_rooms.add(room)
            self.room_histories.setdefault(room, [])
            self.unread_counts.setdefault(room, 0)
            self.update_rooms_listbox()
            self._append_local(f"[{msg.get('time', now_ts())}] [Sistema] Te has unido a '{room}'.", room=room)
        elif mtype == 'join_denied':
            room = msg.get('room')
            reason = msg.get('reason', '')
            # reason can be 'password_required' or 'wrong_password'
            # trigger password prompt automatically (B behavior) unless already tried
            self.master.after(0, lambda: self.handle_join_denied(room, reason))
        elif mtype == 'room_list_response':
            rooms = msg.get('rooms', {})
            t = msg.get('time', now_ts())
            # present rooms (these are public only)
            self._append_local(f"[{t}] Salas públicas disponibles:")
            for r, members in rooms.items():
                self._append_local(f"  - {r} ({len(members)}): {', '.join(members)}")
        else:
            self._append_local(f"[{now_ts()}] Mensaje desconocido: {msg}")

    def handle_join_denied(self, room, reason):
        # Called in main thread via after()
        # We'll prompt the user for password once
        if reason == 'password_required':
            pw = simpledialog.askstring("Contraseña requerida", f'La sala "{room}" está protegida. Ingresa la contraseña:', show='*')
            if not pw:
                self._append_local(f"[{now_ts()}] [Sistema] No ingresaste contraseña para '{room}'.")
                return
            # try again with provided password (include in join_room)
            try:
                self.sock.sendall((json.dumps({'type':'join_room','room': room, 'password': pw}) + '\n').encode('utf-8'))
            except Exception as e:
                self._append_local(f"[{now_ts()}] [Sistema] Error al enviar contraseña: {e}")
        elif reason == 'wrong_password':
            pw = simpledialog.askstring("Contraseña incorrecta", f'Contraseña incorrecta para "{room}". Reingresá la contraseña:', show='*')
            if not pw:
                self._append_local(f"[{now_ts()}] [Sistema] No ingresaste contraseña para '{room}'.")
                return
            try:
                self.sock.sendall((json.dumps({'type':'join_room','room': room, 'password': pw}) + '\n').encode('utf-8'))
            except Exception as e:
                self._append_local(f"[{now_ts()}] [Sistema] Error al reenviar contraseña: {e}")
        else:
            self._append_local(f"[{now_ts()}] [Sistema] No se pudo unir a '{room}': {reason}")

    # ---------------- Sending ----------------
    def send_message(self):
        if not self.sock:
            messagebox.showwarning("No conectado", "Conéctate al servidor primero.")
            return
        text = self.msg_entry.get().strip()
        if not text:
            return

        # commands
        if text.startswith('/'):
            parts = text.split(' ',2)
            cmd = parts[0].lower()
            if cmd == '/join':
                # supports: /join room [password]
                if len(parts) < 2 or not parts[1].strip():
                    self._append_local("[Sistema] Uso: /join <sala> [password]")
                else:
                    room = parts[1].strip()
                    pw = None
                    if len(parts) > 2:
                        pw = parts[2].strip()
                    try:
                        self.sock.sendall((json.dumps({'type':'join_room','room': room, 'password': pw}) + '\n').encode('utf-8'))
                        # optimistically add room (will be confirmed by join_ok)
                        self.joined_rooms.add(room)
                        self.room_histories.setdefault(room, [])
                        self.unread_counts.setdefault(room, 0)
                        self.update_rooms_listbox()
                        # If password was provided treat as active immediately
                        if pw:
                            self.set_active_room(room)
                    except Exception as e:
                        self._append_local(f"[Sistema] Error al unirse: {e}")
            elif cmd == '/leave':
                room = parts[1].strip() if len(parts) > 1 and parts[1].strip() else self.active_room
                if room == 'global':
                    self._append_local("[Sistema] No puedes abandonar la sala global.")
                else:
                    try:
                        self.sock.sendall((json.dumps({'type':'leave_room','room': room}) + '\n').encode('utf-8'))
                        # update local
                        self.joined_rooms.discard(room)
                        self.room_histories.pop(room, None)
                        self.unread_counts.pop(room, None)
                        if self.active_room == room:
                            self.set_active_room('global')
                        else:
                            self.update_rooms_listbox()
                    except Exception as e:
                        self._append_local(f"[Sistema] Error al salir: {e}")
            elif cmd == '/rooms':
                try:
                    self.sock.sendall((json.dumps({'type':'list_rooms'}) + '\n').encode('utf-8'))
                except Exception as e:
                    self._append_local(f"[Sistema] Error solicitando lista de salas: {e}")
            elif cmd == '/quitar':
                try:
                    # optionally notify server
                    self.sock.sendall((json.dumps({'type':'leave_room','room': self.active_room}) + '\n').encode('utf-8'))
                except Exception:
                    pass
                self.on_close()
                return
            else:
                self._append_local("[Sistema] Comando desconocido.")
        else:
            # send msg_room
            msg = {'type':'msg_room','room': self.active_room, 'text': text}
            try:
                self.sock.sendall((json.dumps(msg, ensure_ascii=False) + '\n').encode('utf-8'))
                # show local "Tú:" only (prevent duplicate when server echoes)
                line = f"[{now_ts()}] [{self.active_room}] Tú: {text}"
                self._append_local(line, room=self.active_room)
            except Exception as e:
                self._append_local(f"[{now_ts()}] Error al enviar: {e}")
                self.running = False
                self.disconnect_ui()

        self.msg_entry.delete(0, 'end')

    def create_or_join_room(self):
        room = self.new_room_entry.get().strip()
        if not room:
            messagebox.showwarning("Nombre vacío", "Ingrese el nombre de la sala.")
            return
        # Ask for optional password when creating via UI
        pw = simpledialog.askstring("Contraseña (opcional)", f"Ingresá contraseña para '{room}' (dejar vacío para pública):", show='*')
        try:
            self.sock.sendall((json.dumps({'type':'join_room','room': room, 'password': pw if pw else None}) + '\n').encode('utf-8'))
            # optimistic update
            self.joined_rooms.add(room)
            self.room_histories.setdefault(room, [])
            self.unread_counts.setdefault(room, 0)
            self.update_rooms_listbox()
            if pw:
                self.set_active_room(room)
            self.new_room_entry.delete(0,'end')
        except Exception as e:
            self._append_local(f"[Sistema] Error al crear/unir: {e}")

    def request_rooms_list(self):
        try:
            self.sock.sendall((json.dumps({'type':'list_rooms'}) + '\n').encode('utf-8'))
        except Exception as e:
            self._append_local(f"[Sistema] Error solicitando salas: {e}")

    def disconnect_ui(self):
        self.connect_btn.configure(state='normal')
        self.send_btn.configure(state='disabled')
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def on_close(self):
        self.running = False
        try:
            if self.sock:
                try:
                    self.sock.sendall((json.dumps({'type':'leave_room','room': self.active_room}) + '\n').encode('utf-8'))
                except Exception:
                    pass
                try:
                    self.sock.close()
                except Exception:
                    pass
                self.sock = None
        finally:
            self.master.destroy()

if __name__ == '__main__':
    root = tk.Tk()
    app = ChatClient(root)
    root.mainloop()
