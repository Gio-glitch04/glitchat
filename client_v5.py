#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cliente Tkinter con:
 - Historial persistente con scroll infinito (chat_history/<sala>.txt)
 - Sidebar con salas visitadas y listado de salas públicas (si el servidor las soporta)
 - Botón "Crear / Unirse a sala" con ventana única (nombre + contraseña)
 - Validación: si la sala existe y necesita contraseña, vuelve a pedir y reintenta
 - Salas públicas vacías se muestran en gris "(vacía)"
 - Combobox de servidores guardados (servers.json)
 - Sin duplicación de mensajes: "Tú:" se muestra localmente

Comparado con client_v4.py, este cliente incluye:
 - Handshake ligero con servidores que anuncian capacidades (server_v5.py)
 - Detección automática de servidores básicos (p. ej. servidor_joel.py) y desactivación
   de funciones avanzadas como la barra lateral de "Mis chats"
 - Mayor tolerancia con protocolos de texto plano sin mensajes JSON
"""

import os
import socket
import threading
import time
import json
import shlex
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog

# -------------------------
# Config
# -------------------------
SERVER_FILE = 'servers.json'
DEFAULT_HOST = '127.0.0.1'
DEFAULT_PORT = 55555          # Debe coincidir con server.py
HISTORY_DIR = 'chat_history'
LOAD_CHUNK = 100              # Líneas por “paginado” al hacer scroll arriba

# -------------------------
# Utilidades
# -------------------------
def now_ts():
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())

def ensure_history_dir(path=None):
    target = HISTORY_DIR if path is None else path
    if not os.path.exists(target):
        os.makedirs(target, exist_ok=True)


def _sanitize_name(name, fallback):
    safe_chars = []
    for char in name:
        if char.isalnum() or char in ('_', '-', '.', '@'):
            safe_chars.append(char)
        elif char.isspace():
            safe_chars.append('_')
        else:
            safe_chars.append('_')
    safe = ''.join(safe_chars).strip('_')
    return safe or fallback


def history_path(room, server_key='default'):
    ensure_history_dir()
    safe_server = _sanitize_name(server_key, 'default')
    server_dir = os.path.join(HISTORY_DIR, safe_server)
    ensure_history_dir(server_dir)
    safe_room = _sanitize_name(room, 'room')
    return os.path.join(server_dir, f"{safe_room}.txt")

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
    """Carga las últimas n líneas del archivo (si existe). Retorna (líneas, start_index)."""
    if not os.path.exists(filepath):
        return [], 0
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()
    total = len(lines)
    start = max(0, total - n)
    return lines[start:], start

def head_chunk(filepath, start_index, chunk):
    """Carga hacia atrás 'chunk' líneas antes de start_index (no inclusive)."""
    if not os.path.exists(filepath):
        return [], 0
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()
    new_start = max(0, start_index - chunk)
    return lines[new_start:start_index], new_start

def append_history_line(room, line, server_key='default'):
    """Agrega una línea al archivo de historial de la sala."""
    path = history_path(room, server_key)
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
        self.server_key = 'default'

        self.current_room = 'global'                # sala activa
        self.visited_rooms = set(['global'])        # salas visitadas (modelo: 1 sala activa a la vez)
        self.sidebar_mode = 'joined'                # 'joined' o 'public_list'
        self.public_rooms_cache = []                # [(name, empty_bool), ...]
        self.room_passwords = {}                    # sala -> contraseña recordada

        # Historial por sala (solo índices para scroll infinito)
        # room -> {'start_index': int}
        self.history_index = {}

        # Track de unión pendiente para reintentar password si hace falta
        self.pending_join_room = None
        self.pending_join_password = None

        # Capacidades del servidor detectadas via handshake o heurísticas
        self.server_caps = self._default_capabilities()
        self.sidebar_visible = True

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
        self.main_frame = main

        # Sidebar
        side = tk.Frame(main, width=240)
        side.pack(side='left', fill='y', padx=(0,8))
        self.sidebar_frame = side

        self.sidebar_title_var = tk.StringVar(value="Salas (doble clic para activar)")
        tk.Label(side, textvariable=self.sidebar_title_var).pack(anchor='w')

        self.rooms_listbox = tk.Listbox(side, width=32, height=26)
        self.rooms_listbox.pack(fill='y', expand=False)
        self.rooms_listbox.bind("<Double-Button-1>", self.on_sidebar_double_click)

        # Context menu (click derecho) para salir
        self.rooms_menu = tk.Menu(self.rooms_listbox, tearoff=0)
        self.rooms_menu.add_command(label="Salir de la sala", command=self.leave_selected_room)
        self.rooms_listbox.bind("<Button-3>", self.on_sidebar_right_click)

        # Botones para modos y crear/unir
        buttons_frame = tk.Frame(side)
        buttons_frame.pack(fill='x', pady=(6,0))
        self.btn_my_rooms = tk.Button(buttons_frame, text="Mis salas", command=self.show_joined_rooms)
        self.btn_my_rooms.pack(side='left', fill='x', expand=True, padx=(0,4))
        self.btn_public_rooms = tk.Button(buttons_frame, text="Listar públicas", command=self.request_rooms)
        self.btn_public_rooms.pack(side='left', fill='x', expand=True)

        self.btn_create_join = tk.Button(side, text="Crear / Unirse a sala", command=self.create_or_join_room)
        self.btn_create_join.pack(fill='x', pady=(6,0))

        # Panel derecho (chat)
        right = tk.Frame(main)
        right.pack(side='left', fill='both', expand=True)
        self.chat_frame = right

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

    def _default_capabilities(self):
        return {
            'supports_rooms': True,
            'supports_public_rooms': True,
            'supports_sidebar': True,
            'basic_text': False,
            'features': set(),
        }

    def _set_sidebar_visible(self, visible: bool):
        if visible and not self.sidebar_visible:
            self.sidebar_frame.pack(side='left', fill='y', padx=(0,8))
            self.sidebar_visible = True
        elif not visible and self.sidebar_visible:
            self.sidebar_frame.pack_forget()
            self.sidebar_visible = False

    def _apply_server_capabilities(self):
        caps = self.server_caps or self._default_capabilities()
        supports_rooms = caps.get('supports_rooms', True)
        supports_public_rooms = caps.get('supports_public_rooms', True)
        supports_sidebar = caps.get('supports_sidebar', True)

        self._set_sidebar_visible(supports_sidebar)

        btn_state_rooms = 'normal' if supports_rooms else 'disabled'

        self.btn_my_rooms.configure(state=btn_state_rooms)
        self.btn_create_join.configure(state=btn_state_rooms)
        self.btn_public_rooms.configure(state='normal' if supports_public_rooms else 'disabled')

        if not supports_rooms:
            self.sidebar_mode = 'joined'
            self.visited_rooms = set(['global'])
            self.public_rooms_cache = []

    # ----------------- Sidebar helpers -----------------
    def refresh_sidebar(self):
        self.rooms_listbox.delete(0, 'end')
        if self.sidebar_mode == 'joined':
            self.sidebar_title_var.set("Salas (doble clic para activar)")
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
                # self.public_rooms_cache: [(name, empty_bool), ...]
                for name, empty in sorted(self.public_rooms_cache):
                    idx = self.rooms_listbox.size()
                    self.rooms_listbox.insert('end', f"{name} (vacía)" if empty else name)
                    if empty:
                        self.rooms_listbox.itemconfig(idx, fg='gray')

    def show_joined_rooms(self):
        if not self.server_caps.get('supports_rooms', True):
            self._append_local(f"[{now_ts()}] El servidor no soporta salas múltiples.")
            return
        self.sidebar_mode = 'joined'
        self.refresh_sidebar()

    def request_rooms(self):
        if not self.server_caps.get('supports_public_rooms', True):
            self._append_local(f"[{now_ts()}] El servidor no provee listado de salas públicas.")
            return
        self.sidebar_mode = 'public_list'
        self.public_rooms_cache = []
        self.refresh_sidebar()
        self._send_raw("/rooms")

    def on_sidebar_double_click(self, event=None):
        sel = self.rooms_listbox.curselection()
        if not sel:
            return
        text = self.rooms_listbox.get(sel[0]).strip()
        if self.sidebar_mode == 'joined':
            room = text[2:] if text.startswith("• ") or text.startswith("  ") else text
            self.switch_to_room(room)
        else:
            room = text.replace("(vacía)", "").strip()
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
        if room == self.current_room:
            self._send_raw("/leave")
        else:
            self._send_raw(self._format_leave_command(room))

    # ----------------- Historial (persistente + scroll infinito) -----------------
    def load_room_history_initial(self, room):
        path = history_path(room, self.server_key)
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
        path = history_path(room, self.server_key)
        more_lines, new_start = head_chunk(path, start_idx, LOAD_CHUNK)
        if not more_lines:
            return
        # Insertar al principio
        self.chat_area.configure(state='normal')
        self.chat_area.insert('1.0', ''.join(more_lines))
        self.chat_area.configure(state='disabled')
        # Actualizar índice
        self.history_index[room]['start_index'] = new_start

    # ----------------- Conexión y escucha -----------------
    def _perform_handshake(self, sock: socket.socket, username: str):
        caps = self._default_capabilities()
        result = {
            'capabilities': caps,
            'initial_lines': [],
            'leftover': '',
            'handshake_mode': 'legacy',
        }

        try:
            sock.settimeout(2.0)
            data = sock.recv(4096)
        except socket.timeout:
            sock.sendall((username + "\n").encode('utf-8'))
            caps.update({
                'supports_rooms': False,
                'supports_public_rooms': False,
                'supports_sidebar': False,
                'basic_text': True,
                'features': set(),
            })
            result['handshake_mode'] = 'timeout_basic'
            return result

        if not data:
            raise ConnectionError("Servidor cerró la conexión durante el handshake.")

        text = data.decode('utf-8', errors='replace')
        parts = text.split('\n')
        leftover = ''
        if parts and text and not text.endswith('\n'):
            leftover = parts.pop()

        handshake_detected = False
        prompt_received = False
        features = set()
        initial_lines = []

        for raw_line in parts:
            line = raw_line.strip('\r')
            if not line:
                continue
            upper = line.upper()
            if line.startswith('HELLO_V5'):
                handshake_detected = True
                if 'features=' in line:
                    feature_str = line.split('features=', 1)[1]
                    features = set(f.strip().lower() for f in feature_str.split(',') if f.strip())
            elif 'NOMBRE' in upper and not prompt_received:
                prompt_received = True
            else:
                initial_lines.append(line)

        result['initial_lines'] = initial_lines
        result['leftover'] = leftover

        if handshake_detected:
            caps['features'] = set(features)
            caps['supports_rooms'] = 'rooms' in features or 'rooms_basic' in features or not features
            caps['supports_public_rooms'] = 'public_rooms' in features or 'rooms' in features or 'rooms_basic' in features
            caps['supports_sidebar'] = 'sidebar' in features
            caps['basic_text'] = False
            response_parts = [f"CLIENT_V5 username={username}"]
            if caps['supports_rooms']:
                response_parts.append('rooms=1')
            if caps['supports_public_rooms']:
                response_parts.append('public=1')
            if caps['supports_sidebar']:
                response_parts.append('sidebar=1')
            sock.sendall((' '.join(response_parts) + "\n").encode('utf-8'))
            result['handshake_mode'] = 'v5'
        else:
            sock.sendall((username + "\n").encode('utf-8'))
            caps['features'] = set()
            result['handshake_mode'] = 'legacy'

        return result

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

            handshake = self._perform_handshake(s, username)

            s.settimeout(1.0)

            self.sock = s
            self.username = username
            self.running = True
            self.server_key = self._build_server_key(host, port)
            self.history_index = {}
            self.room_passwords = {}
            self.pending_join_room = None
            self.pending_join_password = None
            self.public_rooms_cache = []
            self.connect_btn.configure(state='disabled')
            self.send_btn.configure(state='normal')

            # Capacidades detectadas
            caps = handshake.get('capabilities', self._default_capabilities())
            if 'features' in caps:
                caps['features'] = set(caps.get('features') or [])
            else:
                caps['features'] = set()
            self.server_caps = caps
            self._apply_server_capabilities()

            # Estado UI inicial
            self.current_room = 'global'
            self.visited_rooms = set(['global'])
            self.sidebar_mode = 'joined'
            self.active_room_var.set("Sala activa: global")
            self.load_room_history_initial('global')

            info_msg = f"[{now_ts()}] Conectado a {host}:{port} como {username}"
            if self.server_caps.get('basic_text'):
                info_msg += " (modo básico detectado, funciones avanzadas deshabilitadas)"
            self._append_local(info_msg, room='global')

            for line in handshake.get('initial_lines', []):
                if line:
                    self.process_server_line(line)

            initial_buffer = handshake.get('leftover', '') or ''

            # Iniciar hilo listener
            self.listener_thread = threading.Thread(target=self.listen_loop, args=(initial_buffer,), daemon=True)
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

    def listen_loop(self, initial_buffer=""):
        buffer = initial_buffer or ""
        try:
            while self.running and self.sock:
                try:
                    data = self.sock.recv(4096)
                    if not data:
                        raise ConnectionResetError()
                    buffer += data.decode('utf-8', errors='replace')
                    # Procesar por líneas
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
         - Listado /rooms: "Salas públicas disponibles: a, b (vacía), c"
         - Mensajes de otros: "usuario: mensaje"
         - Contraseña incorrecta: "❌ Contraseña incorrecta."
        """
        # /rooms -> lista pública
        if line.lower().startswith("salas públicas disponibles"):
            parts = line.split(':', 1)
            rooms = []
            if len(parts) == 2:
                raw = parts[1].strip()
                for token in raw.split(','):
                    token = token.strip()
                    if not token:
                        continue
                    empty = "(vacía)" in token
                    name = token.replace("(vacía)", "").strip()
                    rooms.append((name, empty))
            self.public_rooms_cache = rooms
            self.sidebar_mode = 'public_list'
            self.refresh_sidebar()
            self._append_local(f"[{now_ts()}] {line}")
            return

        # Confirmación de unión
        if "Te has unido a la sala" in line:
            room = None
            try:
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
                if self.pending_join_password is not None:
                    if self.pending_join_password:
                        self.room_passwords[room] = self.pending_join_password
                    else:
                        self.room_passwords.pop(room, None)
                self.pending_join_room = None  # unión exitosa
                self.pending_join_password = None
            self._append_local(f"[{now_ts()}] {line}", room=self.current_room)
            return

        # Confirmación de abandono de sala (volver a global)
        if "Has salido de la sala" in line and "Sala activa" in line:
            room = None
            try:
                start = line.index("'") + 1
                end = line.index("'", start)
                room = line[start:end]
            except Exception:
                room = None
            previous_room = self.current_room
            new_active = self.current_room
            try:
                fragment = line.split("Sala activa:", 1)[1]
                new_active = fragment.strip()
                if new_active.endswith('.'):
                    new_active = new_active[:-1]
                new_active = new_active.strip()
            except Exception:
                new_active = 'global'
            if not new_active:
                new_active = 'global'
            self.current_room = new_active
            self.visited_rooms.add(new_active)
            if room:
                self.visited_rooms.discard(room)
                self.history_index.pop(room, None)
            self.active_room_var.set(f"Sala activa: {new_active}")
            if previous_room != new_active:
                self.load_room_history_initial(new_active)
            self.refresh_sidebar()
            self._append_local(f"[{now_ts()}] {line}", room=new_active)
            return

        # Volver a global / no dejar salir de global
        if ("Has vuelto al chat global" in line) or ("No puedes salir del chat global" in line):
            self.current_room = 'global'
            self.visited_rooms.add('global')
            self.active_room_var.set("Sala activa: global")
            self.load_room_history_initial('global')
            self.refresh_sidebar()
            self._append_local(f"[{now_ts()}] {line}", room='global')
            return

        # Contraseña incorrecta -> pedir y reintentar
        if "❌ Contraseña incorrecta" in line:
            # Intentar usar la última sala pendiente si hay
            room = self.pending_join_room or self.current_room
            if room:
                self.room_passwords.pop(room, None)
            pwd = simpledialog.askstring("Contraseña requerida", f"Ingrese contraseña para la sala '{room}':", show="*")
            if pwd:
                self._send_raw(self._format_join_command(room, pwd))
            else:
                self._append_local(f"[{now_ts()}] No se ingresó contraseña. No se unió a '{room}'.", room=self.current_room)
            return

        # Mensaje típico "usuario: mensaje" (de otros)
        if ':' in line:
            self._append_local(f"[{now_ts()}] {line}", room=self.current_room)
            return

        # Otros textos informativos
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
            # Comandos
            if text.lower().startswith('/join'):
                try:
                    parts = shlex.split(text)
                except ValueError as err:
                    self._append_local(f"[Sistema] Error en comando /join: {err}")
                    self.msg_entry.delete(0, 'end')
                    return
                if len(parts) < 2:
                    self._append_local("[Sistema] Uso: /join <sala> [password]")
                else:
                    room = parts[1]
                    pwd = parts[2] if len(parts) > 2 else None
                    self.join_room(room, pwd)
            elif text.lower().startswith('/leave'):
                self._send_raw(text)
            elif text.lower().startswith('/rooms'):
                self.request_rooms()
            elif text.lower().startswith('/quitar'):
                self.on_close()
                return
            else:
                self._append_local("[Sistema] Comando desconocido.")
        else:
            # Mensaje normal -> se envía a la sala actual y se muestra como "Tú:"
            try:
                self.sock.sendall((text + "\n").encode('utf-8'))
                self._append_local(f"[{now_ts()}] Tú: {text}", room=self.current_room)
            except Exception as e:
                self._append_local(f"[{now_ts()}] Error al enviar: {e}", room=self.current_room)
                self.running = False
                self.disconnect_ui()

        self.msg_entry.delete(0, 'end')

    def _send_raw(self, raw: str):
        try:
            if self.sock:
                self.sock.sendall((raw + "\n").encode('utf-8'))
        except Exception as e:
            self._append_local(f"[{now_ts()}] Error al enviar comando: {e}", room=self.current_room)

    def _format_join_command(self, room, pwd=None):
        parts = ["/join", shlex.quote(room)]
        if pwd:
            parts.append(shlex.quote(pwd))
        return " ".join(parts)

    def _format_leave_command(self, room):
        return "/leave " + shlex.quote(room)

    def _build_server_key(self, host, port):
        return f"{host}:{port}"

    def join_room(self, room, pwd=None, silent=False):
        """/join room [pwd]. Guarda pending_join_room para reintento de contraseña si aplica."""
        if not room:
            return
        if not self.server_caps.get('supports_rooms', True):
            if not silent:
                self._append_local(f"[{now_ts()}] El servidor no soporta salas múltiples.")
            return
        stored_pwd = self.room_passwords.get(room)
        effective_pwd = pwd if pwd not in (None, '') else stored_pwd
        self.pending_join_room = room
        self.pending_join_password = effective_pwd
        cmd = self._format_join_command(room, effective_pwd)
        if not silent:
            self._append_local(f"[{now_ts()}] Intentando unirse a '{room}'...", room=self.current_room)
        self._send_raw(cmd)

    def switch_to_room(self, room):
        """Cambia sala activa. En este servidor, sólo hay una sala a la vez, así que es /join."""
        if room == self.current_room:
            return
        if not self.server_caps.get('supports_rooms', True):
            return
        self.join_room(room)

    # ----------------- Crear / Unirse a sala (pop-up único) -----------------
    def create_or_join_room(self):
        if not self.server_caps.get('supports_rooms', True):
            messagebox.showinfo("No disponible", "Este servidor no soporta crear ni unirse a otras salas.")
            return
        dialog = tk.Toplevel(self.master)
        dialog.title("Crear / Unirse a sala")
        dialog.transient(self.master)
        dialog.resizable(False, False)

        tk.Label(dialog, text="Nombre de la sala:").grid(row=0, column=0, padx=8, pady=(8,4), sticky="w")
        name_entry = tk.Entry(dialog, width=25)
        name_entry.grid(row=0, column=1, padx=8, pady=(8,4))

        tk.Label(dialog, text="Contraseña (opcional):").grid(row=1, column=0, padx=8, pady=4, sticky="w")
        pwd_entry = tk.Entry(dialog, width=25, show="*")
        pwd_entry.grid(row=1, column=1, padx=8, pady=4)

        def confirm():
            room = name_entry.get().strip()
            pwd = pwd_entry.get().strip()
            if not room:
                messagebox.showerror("Error", "Debes escribir un nombre para la sala.")
                return
            self.join_room(room, pwd if pwd else None)
            dialog.destroy()

        tk.Button(dialog, text="Aceptar", command=confirm).grid(row=2, column=0, columnspan=2, pady=8)

        # Centrar sobre ventana principal
        dialog.update_idletasks()
        x = self.master.winfo_x() + (self.master.winfo_width()//2 - dialog.winfo_width()//2)
        y = self.master.winfo_y() + (self.master.winfo_height()//2 - dialog.winfo_height()//2)
        dialog.geometry(f"+{x}+{y}")

        name_entry.focus_set()
        dialog.grab_set()
        dialog.wait_window()

    # ----------------- Guardado / Render de historial -----------------
    def _append_local(self, text, room=None):
        """Escribe en histórico (archivo) y muestra en pantalla si es la sala activa."""
        room = room or self.current_room
        append_history_line(room, text, self.server_key)
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
        self.server_caps = self._default_capabilities()
        self._apply_server_capabilities()

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
    ensure_history_dir()
    root = tk.Tk()
    app = ChatClient(root)
    root.mainloop()
