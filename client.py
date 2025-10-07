#!/usr/bin/env python3
"""
client.py
Cliente de chat con interfaz Tkinter.
Comandos:
  /listar  -> solicita lista de usuarios conectados
  /quitar  -> desconectarse
"""

import socket
import threading
import json
import time
import tkinter as tk
from tkinter import scrolledtext, messagebox, simpledialog

SERVER_HOST = '127.0.0.1'  # cambiar aquí o pedir en UI
SERVER_PORT = 50000

def now_ts():
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())

class ChatClient:
    def __init__(self, master):
        self.master = master
        master.title("Chat - Cliente")
        master.geometry("600x450")

        top_frame = tk.Frame(master)
        top_frame.pack(fill='x', padx=8, pady=6)

        tk.Label(top_frame, text="Servidor:").pack(side='left')
        self.server_entry = tk.Entry(top_frame, width=18)
        self.server_entry.pack(side='left', padx=4)
        self.server_entry.insert(0, SERVER_HOST)

        tk.Label(top_frame, text="Puerto:").pack(side='left')
        self.port_entry = tk.Entry(top_frame, width=6)
        self.port_entry.pack(side='left', padx=4)
        self.port_entry.insert(0, str(SERVER_PORT))

        tk.Label(top_frame, text="Usuario:").pack(side='left', padx=(10,0))
        self.user_entry = tk.Entry(top_frame, width=12)
        self.user_entry.pack(side='left', padx=4)

        self.connect_btn = tk.Button(top_frame, text="Conectar", command=self.connect)
        self.connect_btn.pack(side='left', padx=6)

        # area de mensajes
        self.chat_area = scrolledtext.ScrolledText(master, state='disabled', wrap='word')
        self.chat_area.pack(fill='both', expand=True, padx=8, pady=(0,6))

        bottom_frame = tk.Frame(master)
        bottom_frame.pack(fill='x', padx=8, pady=6)

        self.msg_entry = tk.Entry(bottom_frame)
        self.msg_entry.pack(side='left', fill='x', expand=True, padx=(0,6))
        self.msg_entry.bind("<Return>", lambda e: self.send_message())

        self.send_btn = tk.Button(bottom_frame, text="Enviar", command=self.send_message, state='disabled')
        self.send_btn.pack(side='right')

        # estado interno
        self.sock = None
        self.listener_thread = None
        self.running = False

        master.protocol("WM_DELETE_WINDOW", self.on_close)

    def _append(self, text):
        self.chat_area.configure(state='normal')
        self.chat_area.insert('end', text + '\n')
        self.chat_area.see('end')
        self.chat_area.configure(state='disabled')

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
            # enviar join
            join = {'type':'join','user': username}
            s.sendall((json.dumps(join, ensure_ascii=False) + '\n').encode('utf-8'))
            self.running = True
            self.listener_thread = threading.Thread(target=self.listen_loop, daemon=True)
            self.listener_thread.start()
            self.connect_btn.configure(state='disabled')
            self.send_btn.configure(state='normal')
            self._append(f"[{now_ts()}] Conectado a {server}:{port} como {username}")
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
                        self.master.after(0, lambda: self._append("[Sistema] Mensaje mal formado recibido."))
                        continue
                    self.master.after(0, lambda m=msg: self.process_message(m))
            except socket.timeout:
                continue
            except Exception:
                self.running = False
                self.master.after(0, lambda: self._append(f"[{now_ts()}] Desconectado del servidor."))
                self.master.after(0, self.disconnect_ui)
                break

    def process_message(self, msg):
        mtype = msg.get('type')
        if mtype == 'system':
            self._append(f"[{msg.get('time',now_ts())}] [Sistema] {msg.get('text')}")
        elif mtype == 'msg':
            user = msg.get('user', 'desconocido')
            text = msg.get('text', '')
            t = msg.get('time', now_ts())
        
            # ✅ No mostrar el mensaje si viene del mismo usuario (ya fue mostrado como "Tú:")
            if user == self.user_entry.get().strip():
                return
        
            self._append(f"[{t}] {user}: {text}")

        elif mtype == 'list_response':
            users = msg.get('users', [])
            t = msg.get('time', now_ts())
            self._append(f"[{t}] Usuarios conectados: {', '.join(users)}")
        else:
            self._append(f"[{now_ts()}] Mensaje desconocido: {msg}")

    def send_message(self):
        if not self.sock:
            messagebox.showwarning("No conectado", "Conéctate al servidor primero.")
            return
        text = self.msg_entry.get().strip()
        if not text:
            return
        try:
            msg = {'type':'msg','text': text}
            self.sock.sendall((json.dumps(msg, ensure_ascii=False) + '\n').encode('utf-8'))
            # mostrar localmente para feedback (opcional)
            if not text.startswith('/'):
                # no mostrar comandos locales
                self._append(f"[{now_ts()}] Tú: {text}")
        except Exception as e:
            self._append(f"[{now_ts()}] Error al enviar: {e}")
            self.running = False
            self.disconnect_ui()
        finally:
            self.msg_entry.delete(0, 'end')
            # si fue comando /quitar, cerrar UI
            if text.startswith('/quitar'):
                self.on_close()

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
        # intentar avisar con /quitar
        self.running = False
        try:
            if self.sock:
                try:
                    msg = {'type':'msg','text':'/quitar'}
                    self.sock.sendall((json.dumps(msg, ensure_ascii=False) + '\n').encode('utf-8'))
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
