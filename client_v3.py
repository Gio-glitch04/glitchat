#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
client.py (Tkinter)
Compatible con server.py (protocolo de texto):
 - /join <sala> [password]
 - /rooms            -> lista salas públicas (sin protegidas)
 - /leave            -> vuelve a global desde la sala actual
 - Mensaje normal    -> se difunde a la sala actual
Características:
 - Combobox de servidores guardados (servers.json)
 - Sidebar con salas (sala activa + visitadas)
 - Click derecho en sala -> salir de esa sala (si no es global)
 - /rooms: sidebar cambia a "modo listado" de salas públicas; doble clic -> /join
 - Historial persistente chat_history/<sala>.txt con timestamps
 - Scroll infinito: carga últimas 100 líneas y agrega 100 al llegar arriba
 - “Tú:” al enviar; no hay duplicado porque el server no ecoa al emisor
"""

import os
import socket
import threading
import time
import json
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog

# -------------------------
# Config
# -------------------------
SERVER_FILE = 'servers.json'
DEFAULT_HOST = '127.0.0.1'
DEFAULT_PORT = 55555           # debe coincidir con tu server.py actual
HISTORY_DIR = 'chat_history'
LOAD_CHUNK = 100               # líneas por “paginado” al hacer scroll arriba

# -------------------------
# Utilidades
# -------------------------
def now_ts():
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())

def ensure_history_dir():
    if not os.path.exists(HISTORY_DIR):
        os.makedirs(HISTORY_DIR, exist_ok=True)

def history_path(room):
    ensure_history_dir()
    safe = "".join(c for c in room if c.isalnum() or c in ('_', '-', '.'))
    return os.path.join(HISTORY_DIR, f"{safe}.txt")

def load_servers():
    if not os.path.exists(SERVER_FILE):
        return {}
    try:
        with open(SERVER_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def save_servers(data: dict):
    try:
        with open(SERVER_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Error guardando servers.json:", e)

def tail_lines(filepath, n):
    """Carga las últimas n líneas del archivo (si existe)."""
    if not os.path.exists(filepath):
        return [], 0
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()
    total = len(lines)
    start = max(0, total - n)
    return lines[start:], start

def head_chunk(filepath, start_index, chunk):
    """Carga hacia atrás 'chunk' líneas antes de start_index (no inclusive). Devuelve (nuevas_lineas, nuevo_start)."""
    if not os.path.exists(filepath):
        return [], 0
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()
    new_start = max(0, start_index - chunk)
    return lines[new_start:start_index], new_start

def append_history_line(room, line):
    path = history_path(room)
    with open(path, 'a', encoding='utf-8') as f:
        if not line.endswith('\n'):
            line += '\n'
        f.write(line)

# -------------------------
# Cliente Tkinter
# -------------------------
class ChatClient:
    def __init__(self, master):
        self.master = master
        master.title("Chat - Cliente (Tkinter)")
        master.geometry("980x560")

        # Estado interno
        self.sock = None
        self.listener_thread = None
        self.running = False
        self.username = None

        self.current_room = 'global'      # sala activa
        self.visited_rooms = set(['global'])  # salas por las que pasaste (a modo de “lista”)
        self.sidebar_mode = 'joined'      # 'joined' o 'public_list'
        self.public_rooms_cache = []      # listado de salas públicas cuando se hace /rooms

        # Historial por sala (solo índices para scroll infinito)
        # room -> {'start_index': int, 'loaded_lines': int}
        self.history_index = {}

        # ----------------- UI TOP -----------------
        top = tk.Frame(master)
        top.pack(fill='x', padx=8, pady=6)

        tk.Label(top, text="Servidor:").pack(side='left')
        self.server_entry = tk.Entry(top, width=20)
        self.server_entry.pack(side='left', padx=(4,10))
        self.server_entry.insert(0, DEFAULT_HOST)

        tk.Label(top, text="Puerto:").pack(side='left')
        self.port_entry = tk.Entry(top, width=6)
        self.port_entry.pack(side='left', padx=(4,10))
        self.port_entry.insert(0, str(DEFAULT_PORT))

        tk.Label(top, text="Usuario:").pack(side='left')
        self.user_entry = tk.Entry(top, width=14)
        self.user_entry.pack(side='left', padx=(4,10))

        self.connect_btn = tk.Button(top, text="Conectar", command=self.connect)
        self.connect_btn.pack(side='left', padx=6)

        # Combobox de servidores
        tk.Label(top, text="Recientes:").pack(side='left', padx=(12,4))
        self.servers = load_servers()
        self.combo = ttk.Combobox(top, values=list(self.servers.keys()), width=18, state='readonly')
        self.combo.pack(side='left', padx=(0,6))
        self.combo.bind("<<ComboboxSelected>>", self.on_server_selected)

        self.save_server_btn = tk.Button(top, text="Guardar servidor...", command=self.save_current_server)
        self.save_server_btn.pack(side='left', padx=6)

        # ----------------- MAIN: SIDEBAR + CHAT -----------------
        main = tk.Frame(master)
        main.pack(fill='both', expand=True, padx=8, pady=(0,6))

        # Sidebar
        side = tk.Frame(main, width=240)
        side.pack(side='left', fill='y', padx=(0,8))

        self.sidebar_title_var = tk.StringVar(value="Salas (doble clic para activar)")
        tk.Label(side, textvariable=self.sidebar_title_var).pack(anchor='w')

        self.rooms_listbox = tk.Listbox(side, width=32, height=26)
        self.rooms_listbox.pack(fill='y', expand=False)
        self.rooms_listbox.bind("<Double-Button-1>", self.on_sidebar_double_click)
        # Context menu (click derecho) para salir
        self.rooms_menu = tk.Menu(self.rooms_listbox, tearoff=0)
        self.rooms_menu.add_command(label="Salir de la sala", command=self.leave_selected_room)
        self.rooms_listbox.bind("<Button-3>", self.on_sidebar_right_click)

        # Botones para cambiar modo
        buttons_frame = tk.Frame(side)
        buttons_frame.pack(fill='x', pady=(6,0))
        tk.Button(buttons_frame, text="Mis salas", command=self.show_joined_rooms).pack(side='left', fill='x', expand=True, padx=(0,4))
        tk.Button(buttons_frame, text="Listar públicas", command=self.request_rooms).pack(side='left', fill='x', expand=True)
        tk.Button(side, text="Crear / Unirse a sala", command=self.create_or_join_room).pack(fill='x', pady=(6,0))

        # Chat area
        right = tk.Frame(main)
        right.pack(side='left', fill='both', expand=True)

        self.active_room_var = tk.StringVar(value="Sala activa: global")
        tk.Label(right, textvariable=self.active_room_var, font=('TkDefaultFont', 10, 'bold')).pack(anchor='w')

        # Text area con scroll infinito
        self.chat_area = scrolledtext.ScrolledText(right, state='disabled', wrap='word')
        self.chat_area.pack(fill='both', expand=True)

        # Conectar el callback de scroll para detectar “llegar arriba”
        self.chat_area['yscrollcommand'] = self.on_text_scroll

        # Bottom: entrada de mensaje
        bottom = tk.Frame(master)
        bottom.pack(fill='x', padx=8, pady=6)
        self.msg_entry = tk.Entry(bottom)
        self.msg_entry.pack(side='left', fill='x', expand=True, padx=(0,6))
        self.msg_entry.bind("<Return>", lambda e: self.send_message())
        self.send_btn = tk.Button(bottom, text="Enviar", command=self.send_message, state='disabled')
        self.send_btn.pack(side='right')

        # Inicializar sidebar
        self.refresh_sidebar()

        master.protocol("WM_DELETE_WINDOW", self.on_close)

    # ----------------- Sidebar helpers -----------------
    def refresh_sidebar(self):
        self.rooms_listbox.delete(0, 'end')
        if self.sidebar_mode == 'joined':
            self.sidebar_title_var.set("Salas (doble clic para activar)")
            # Orden: global primero, luego alfabético de visitadas
            items = []
            if 'global' in self.visited_rooms:
                items.append('global')
            others = sorted([r for r in self.visited_rooms if r != 'global'])
            items.extend(others)
            for r in items:
                prefix = "• " if r == self.current_room else "  "
                self.rooms_listbox.insert('end', f"{prefix}{r}")
        else:
            self.sidebar_title_var.set("Salas públicas (doble clic para unirse)")
            if not self.public_rooms_cache:
                self.rooms_listbox.insert('end', "(no hay salas públicas)")
            else:
                for r in sorted(self.public_rooms_cache):
                    self.rooms_listbox.insert('end', r)

    def show_joined_rooms(self):
        self.sidebar_mode = 'joined'
        self.refresh_sidebar()

    def request_rooms(self):
        # Cambia sidebar a modo listado público y pide al servidor
        self.sidebar_mode = 'public_list'
        self.public_rooms_cache = []
        self.refresh_sidebar()
        self._send_raw("/rooms")

    def on_sidebar_double_click(self, event=None):
        sel = self.rooms_listbox.curselection()
        if not sel:
            return
        text = self.rooms_listbox.get(sel[0]).strip()
        # Si está en modo joined, el ítem puede tener prefijo "• "
        if self.sidebar_mode == 'joined':
            room = text[2:] if text.startswith("• ") or text.startswith("  ") else text
            self.switch_to_room(room)
        else:
            # modo public_list: doble clic -> join a esa sala
            room = text
            if room and not room.startswith("("):
                self.join_room(room)

    def on_sidebar_right_click(self, event):
        if self.sidebar_mode != 'joined':
            return
        try:
            index = self.rooms_listbox.nearest(event.y)
            self.rooms_listbox.selection_clear(0, 'end')
            self.rooms_listbox.selection_set(index)
            self.rooms_listbox.activate(index)
            text = self.rooms_listbox.get(index).strip()
            room = text[2:] if text.startswith("• ") or text.startswith("  ") else text
            # Mostrar menú contextual solo si no es global
            if room != 'global':
                self.rooms_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.rooms_menu.grab_release()

    def leave_selected_room(self):
        sel = self.rooms_listbox.curselection()
        if not sel:
            return
        text = self.rooms_listbox.get(sel[0]).strip()
        room = text[2:] if text.startswith("• ") or text.startswith("  ") else text
        if room == 'global':
            messagebox.showinfo("Info", "No podés salir de la sala global.")
            return
        # Para ajustarnos al servidor (solo sale de la sala ACTUAL), si no es la actual, vamos primero.
        if room != self.current_room:
            self.join_room(room, silent=True)
        # Ahora enviar /leave (volverá a global)
        self._send_raw("/leave")

    # ----------------- Historial (persistente + scroll infinito) -----------------
    def load_room_history_initial(self, room):
        path = history_path(room)
        lines, start_idx = tail_lines(path, LOAD_CHUNK)
        self.history_index[room] = {'start_index': start_idx}
        self.chat_area.configure(state='normal')
        self.chat_area.delete('1.0', 'end')
        for ln in lines:
            self.chat_area.insert('end', ln)
        self.chat_area.see('end')
        self.chat_area.configure(state='disabled')

    def on_text_scroll(self, first, last):
        """Callback de yscrollcommand. 'first' y 'last' son fracciones (0.0 - 1.0)."""
        try:
            first_f = float(first)
        except Exception:
            first_f = 0.0
        if first_f <= 0.0:
            # Estamos arriba del todo -> cargar chunk anterior
            self.load_more_history_chunk()

    def load_more_history_chunk(self):
        room = self.current_room
        idx_info = self.history_index.get(room)
        if not idx_info:
            return
        start_idx = idx_info.get('start_index', 0)
        if start_idx == 0:
            return  # no hay más
        # Cargar chunk anterior
        path = history_path(room)
        more_lines, new_start = head_chunk(path, start_idx, LOAD_CHUNK)
        if not more_lines:
            return
        # Insertar al principio SIN mover scroll (trick: guardar posición)
        self.chat_area.configure(state='normal')
        current_view = self.chat_area.yview()
        # Insertamos al inicio
        self.chat_area.insert('1.0', ''.join(more_lines))
        # Restaurar vista para quedar “donde estábamos”
        self.chat_area.yview_moveto((len(more_lines) / max(1, self.chat_area.count('1.0', 'end', 'lines')[0])) )
        self.chat_area.configure(state='disabled')
        # Actualizar índice
        self.history_index[room]['start_index'] = new_start

    # ----------------- Conexión y escucha -----------------
    def connect(self):
        if self.sock:
            messagebox.showinfo("Info", "Ya estás conectado.")
            return
        host = self.server_entry.get().strip()
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
            s.connect((host, port))
            s.settimeout(2.0)
            # Handshake simple del server: espera "NOMBRE"
            prompt = s.recv(1024).decode('utf-8', errors='replace')
            if "NOMBRE" not in prompt.upper():
                messagebox.showwarning("Aviso", "El servidor no envió el prompt esperado. Continuando igual.")
            s.sendall((username + "\n").encode('utf-8'))

            self.sock = s
            self.username = username
            self.running = True
            self.connect_btn.configure(state='disabled')
            self.send_btn.configure(state='normal')

            # Estado UI
            self.current_room = 'global'
            self.visited_rooms = set(['global'])
            self.active_room_var.set("Sala activa: global")
            # Historial inicial de global
            self.load_room_history_initial('global')
            self._append_local(f"[{now_ts()}] Conectado a {host}:{port} como {username}", room='global')

            # Guardar servidor si se desea
            # (opcional: podríamos preguntar alias automáticamente)
            # Nada automático aquí, queda en el botón "Guardar servidor"

            # Iniciar listener
            self.listener_thread = threading.Thread(target=self.listen_loop, daemon=True)
            self.listener_thread.start()

        except Exception as e:
            messagebox.showerror("Error de conexión", f"No se pudo conectar: {e}")
            try:
                if self.sock:
                    self.sock.close()
            except Exception:
                pass
            self.sock = None
            self.running = False

    def listen_loop(self):
        buffer = ""
        try:
            while self.running and self.sock:
                try:
                    data = self.sock.recv(4096)
                    if not data:
                        raise ConnectionResetError()
                    buffer += data.decode('utf-8', errors='replace')
                    # Procesar por líneas cuando sea posible
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        line = line.strip('\r')
                        if line:
                            self.master.after(0, self.process_server_line, line)
                except socket.timeout:
                    continue
                except Exception:
                    break
        finally:
            self.running = False
            self.master.after(0, lambda: self._append_local(f"[{now_ts()}] Desconectado del servidor.", room=self.current_room))
            self.master.after(0, self.disconnect_ui)

    # ----------------- Procesamiento de líneas del servidor -----------------
    def process_server_line(self, line: str):
        """
        El servidor envía:
         - System/confirmaciones (ej: "✅ Te has unido a la sala 'x'.")
         - Listado /rooms: "Salas públicas disponibles: a, b, c"
         - Mensajes de otros: "usuario: mensaje"
        """
        # /rooms respuesta
        if line.lower().startswith("salas públicas disponibles"):
            # Extraer salas (separadas por coma)
            parts = line.split(':', 1)
            if len(parts) == 2:
                raw = parts[1].strip()
                rooms = [r.strip() for r in raw.split(',') if r.strip()]
            else:
                rooms = []
            self.public_rooms_cache = rooms
            self.sidebar_mode = 'public_list'
            self.refresh_sidebar()
            # Además mostrar en el chat activo (informativo)
            self._append_local(f"[{now_ts()}] {line}")
            return

        # Confirmaciones de unión/salida (texto del server)
        if "Te has unido a la sala" in line:
            # Parsear sala entre comillas
            room = None
            try:
                # ... 'Te has unido a la sala 'ROOM'.'
                start = line.index("'") + 1
                end = line.index("'", start)
                room = line[start:end]
            except Exception:
                pass
            if room:
                self.current_room = room
                self.visited_rooms.add(room)
                self.active_room_var.set(f"Sala activa: {room}")
                self.load_room_history_initial(room)
                self.refresh_sidebar()
            self._append_local(f"[{now_ts()}] {line}", room=self.current_room)
            return

        if ("Has vuelto al chat global" in line) or ("No puedes salir del chat global" in line):
            # Volvimos a global
            self.current_room = 'global'
            self.visited_rooms.add('global')
            self.active_room_var.set("Sala activa: global")
            self.load_room_history_initial('global')
            self.refresh_sidebar()
            self._append_local(f"[{now_ts()}] {line}", room='global')
            return

        # Mensaje típico "usuario: mensaje" (de otros)
        if ':' in line:
            # No mostrar como "Tú" porque el server no reenvía al emisor
            # Registrar con timestamp y sala actual
            self._append_local(f"[{now_ts()}] {line}", room=self.current_room)
            return

        # Fallback: sistema / info varios
        self._append_local(f"[{now_ts()}] {line}", room=self.current_room)

    # ----------------- Envío de mensajes y comandos -----------------
    def send_message(self):
        if not self.sock:
            messagebox.showwarning("No conectado", "Conéctate al servidor primero.")
            return
        text = self.msg_entry.get().strip()
        if not text:
            return

        if text.startswith('/'):
            # Comando
            if text.lower().startswith('/join'):
                # /join sala [password]
                parts = text.split()
                if len(parts) < 2:
                    self._append_local("[Sistema] Uso: /join <sala> [password]")
                else:
                    room = parts[1]
                    pwd = parts[2] if len(parts) > 2 else None
                    self.join_room(room, pwd)
            elif text.lower().startswith('/leave'):
                self._send_raw("/leave")
            elif text.lower().startswith('/rooms'):
                self.request_rooms()
            elif text.lower().startswith('/quitar'):
                self.on_close()
                return
            else:
                self._append_local("[Sistema] Comando desconocido.")
        else:
            # Mensaje normal => se envía a la sala actual
            try:
                self.sock.sendall((text + "\n").encode('utf-8'))
                # Mostrar localmente “Tú:”
                self._append_local(f"[{now_ts()}] Tú: {text}", room=self.current_room)
            except Exception as e:
                self._append_local(f"[{now_ts()}] Error al enviar: {e}", room=self.current_room)
                self.running = False
                self.disconnect_ui()

        self.msg_entry.delete(0, 'end')

    def create_or_join_room(self):
        room = simpledialog.askstring("Crear/Unir sala", "Nombre de la sala:")
        if not room:
            return
        pwd = simpledialog.askstring("Contraseña opcional", "Contraseña (déjalo vacío si es pública):", show='*')
        cmd = f"/join {room}" + (f" {pwd}" if pwd else "")
        self._send_raw(cmd)


    def _send_raw(self, raw: str):
        try:
            self.sock.sendall((raw + "\n").encode('utf-8'))
        except Exception as e:
            self._append_local(f"[{now_ts()}] Error al enviar comando: {e}", room=self.current_room)

    def join_room(self, room, pwd=None, silent=False):
        # /join room [pwd]
        if not room:
            return
        if pwd:
            cmd = f"/join {room} {pwd}"
        else:
            cmd = f"/join {room}"
        if not silent:
            self._append_local(f"[{now_ts()}] Intentando unirse a '{room}'...", room=self.current_room)
        self._send_raw(cmd)

    def switch_to_room(self, room):
        """Cambiar sala activa (si NO estás en esa sala, intenta /join sin password)."""
        if room == self.current_room:
            return
        # En el server actual, “estar” en una sala = ser tu sala ACTUAL.
        # Así que para “ver” un room visitado, debemos /join (sin pwd si es pública)
        # Si era protegida, el server pedirá contraseña (te llegará texto); no auto-prompt aquí.
        self.join_room(room)

    # ----------------- Guardado / Render de historial -----------------
    def _append_local(self, text, room=None):
        """Escribe en histórico (archivo) y muestra en pantalla si es la sala activa."""
        room = room or self.current_room
        append_history_line(room, text)
        if room == self.current_room:
            self.chat_area.configure(state='normal')
            self.chat_area.insert('end', text + '\n')
            self.chat_area.see('end')
            self.chat_area.configure(state='disabled')

    # ----------------- Servers combobox -----------------
    def on_server_selected(self, event=None):
        name = self.combo.get()
        if name in self.servers:
            info = self.servers[name]
            self.server_entry.delete(0, 'end')
            self.server_entry.insert(0, info.get('host', DEFAULT_HOST))
            self.port_entry.delete(0, 'end')
            self.port_entry.insert(0, str(info.get('port', DEFAULT_PORT)))

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
        self.combo['values'] = list(self.servers.keys())
        self.combo.set(alias)
        messagebox.showinfo("Guardado", f"Servidor guardado como '{alias}'")

    # ----------------- Limpieza / cierre -----------------
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
                    self.sock.close()
                except Exception:
                    pass
                self.sock = None
        finally:
            self.master.destroy()

# ----------------- Main -----------------
if __name__ == '__main__':
    # Asegurar carpeta de historial
    ensure_history_dir()
    root = tk.Tk()
    app = ChatClient(root)
    root.mainloop()
