import socket
import threading
import sys
import socket
import threading
# imports de estilos
import tkinter as tk
from tkinter import scrolledtext, messagebox, simpledialog  # Estos siguen de tkinter
# Reemplazamos 'from tkinter import ttk' por:
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import json

# Nombre del archivo de configuración
CONFIG_FILE = 'chat_config.json'


class ClienteChat:
    def __init__(self, master, host, port, username):
        # ... (código de inicialización, socket, y conexión es el mismo) ...
        self.master = master
        self.host = host
        self.port = port
        self.nombre_usuario = username
        self.running = True
        self.mensajes_sin_leer = 0

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            self.sock.connect((self.host, self.port))
        except ConnectionRefusedError:
            messagebox.showerror("Error de Conexión",
                                 f"No se pudo conectar a {self.host}:{self.port}. Asegúrate de que el servidor esté activo.")
            self.running = False
            master.destroy()
            return

        self.crear_widgets()
        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.actualizar_titulo_ux()
        self.sock.send(self.nombre_usuario.encode('utf-8'))

        self.thread_recepcion = threading.Thread(target=self.recibir_mensajes)
        self.thread_recepcion.daemon = True
        self.thread_recepcion.start()

    def crear_widgets(self):
        # Aplicamos el fondo del tema 'superhero' (Oscuro)
        style = ttk.Style()
        style.theme_use('superhero')
        self.master.config(bg=style.lookup('TFrame', 'background'))

        # Área de Mensajes (manteniendo el fondo negro tipo chat para contraste)
        self.caja_mensajes = scrolledtext.ScrolledText(self.master, state='disabled', wrap='word',
                                                       font=('Consolas', 10), bg='#202225', fg='#FFFFFF',
                                                       insertbackground='#FFFFFF', padx=8, pady=8)
        self.caja_mensajes.pack(padx=10, pady=(10, 5), fill='both', expand=True)

        # Configuración de tags (colores tipo Discord)
        self.caja_mensajes.tag_config('server', foreground='#FEE75C', font=('Consolas', 10, 'bold'))
        self.caja_mensajes.tag_config('user', foreground='#3498DB', font=('Consolas', 10))
        self.caja_mensajes.tag_config('self', foreground='#2ECC71', font=('Consolas', 10, 'bold'))
        self.caja_mensajes.tag_config('default', foreground='#FFFFFF')

        # Frame de entrada con ttkbootstrap
        frame_entrada = ttk.Frame(self.master)
        frame_entrada.pack(padx=10, pady=(0, 10), fill='x')

        # Entrada con estilo moderno
        self.entrada_mensaje = ttk.Entry(frame_entrada, font=('Consolas', 11), bootstyle="primary")
        self.entrada_mensaje.pack(side=tk.LEFT, fill='x', expand=True, padx=(0, 5), ipady=4)
        # Usar lambda para manejar el evento y llamar al método sin argumentos de evento.
        self.entrada_mensaje.bind("<Return>", lambda event: self.enviar_mensaje())

        # Botón con estilo "success" de ttkbootstrap
        self.boton_enviar = ttk.Button(frame_entrada, text="Enviar", command=lambda: self.enviar_mensaje(),
                                       bootstyle="success")
        self.boton_enviar.pack(side=tk.RIGHT, ipadx=10, ipady=4)

    def actualizar_titulo_ux(self):
        """Actualiza el título con la IP del servidor y mensajes sin leer."""

        # Se actualiza el título para que muestre la IP del servidor
        base_titulo = f"Cliente en Servidor: {self.host}"
        if self.mensajes_sin_leer > 0:
            self.master.title(f"({self.mensajes_sin_leer}) 💬 {base_titulo}")
        else:
            self.master.title(f"{base_titulo}")

    def recibir_mensajes(self):
        """Bucle de recepción de mensajes desde el servidor."""

        while self.running:
            try:
                # Recibir el mensaje (incluido el prompt inicial del nombre)
                data = self.sock.recv(1024).decode('utf-8')

                if data:
                    self.mostrar_mensaje(data)

                    # Lógica de registro de nombre de usuario
                    if self.nombre_usuario is None and "ingresa tu nombre de usuario" in data:
                        # Este es el prompt del servidor. Pedimos el nombre al usuario
                        self.solicitar_nombre_y_enviar()

                    elif self.nombre_usuario is None:
                        # Si el servidor ya nos aceptó (el nombre ya fue enviado)
                        # El primer mensaje real que recibamos (después del envío) indica que fue aceptado                    self.nombre_usuario = self.nombre_temporal
                        del self.nombre_temporal
                        self.actualizar_titulo_ux()

                else:
                    # Conexión cerrada por el servidor
                    raise ConnectionResetError

            except (ConnectionResetError, OSError):
                if self.running:
                    self.mostrar_mensaje("[Servidor] Has sido desconectado o el servidor ha caído.")
                    messagebox.showerror("Desconexión", "Conexión con el servidor perdida.")
                self.cerrar_conexion()
                break

    def mostrar_mensaje(self, mensaje, tag='default'):
        """Inserta un mensaje con etiquetas de estilo."""
        self.caja_mensajes.config(state='normal')

        # Determinar el tag basado en el contenido si no se especificó
        if tag == 'default':
            if mensaje.startswith('[Servidor]'):
                tag = 'server'
            elif self.nombre_usuario and mensaje.startswith(f"<{self.nombre_usuario}>"):
                # No debería pasar si usamos la lógica de envío optimizada, pero es un fallback
                tag = 'self'
            elif mensaje.startswith('<') and '>' in mensaje:
                tag = 'user'
            else:
                tag = 'default'  # Mensajes de error o info

        self.caja_mensajes.insert(tk.END, mensaje, tag)
        self.caja_mensajes.config(state='disabled')
        self.caja_mensajes.see(tk.END)

        # Lógica de mensajes sin leer
        if not self.master.focus_displayof() and tag not in ('self'):  # Ignoramos los mensajes propios
            self.mensajes_sin_leer += 1
            self.actualizar_titulo_ux()

    def cerrar_conexion(self):
        self.running = False
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()

    def enviar_mensaje(self):
        """Obtiene el mensaje, maneja comandos y lo envía."""
        if not self.nombre_usuario: return
        mensaje = self.entrada_mensaje.get()
        self.entrada_mensaje.delete(0, tk.END)
        if not mensaje: return

        # Manejo de comandos (CORRECCIÓN /quitar)
        if mensaje.strip().lower() == '/quitar':
            # Solo preguntar y cerrar si el usuario confirma.
            if messagebox.askokcancel("Salir del Chat", "¿Estás seguro de que quieres desconectarte?"):
                self.sock.send('/quitar'.encode('utf-8'))
                self.cerrar_conexion()  # Cierra el socket y destruye la ventana.
            return

        if mensaje.strip().lower() == '/listar':
            self.sock.send('/listar'.encode('utf-8'))
            return

        try:
            self.sock.send(mensaje.encode('utf-8'))
            self.mostrar_mensaje(f"<{self.nombre_usuario}> {mensaje}\n", tag='self')
        except:
            self.mostrar_mensaje("[ERROR] Fallo al enviar el mensaje. Desconectando.", tag='server')
            self.cerrar_conexion()

    def on_closing(self):
        """Maneja el cierre de la ventana, asegurando el cierre del socket."""
        # Se mantiene la lógica de on_closing, ya que '/quitar' ahora maneja su propia confirmación.
        if messagebox.askokcancel("Salir", "¿Estás seguro de que quieres desconectarte?"):
            try:
                if self.nombre_usuario:
                    self.sock.send('/quitar'.encode('utf-8'))
            except:
                pass
            finally:
                self.cerrar_conexion()
                self.master.destroy()


# ====================================================================
#                       VENTANA DE CONEXIÓN
# ====================================================================
class ConnectWindow:
    def __init__(self, master):
        self.master = master
        master.title("Configurar Conexión")
        # ... (Variables y métodos cargar/guardar_configuracion son iguales) ...
        self.host = tk.StringVar()
        self.port = tk.StringVar()
        self.username = tk.StringVar()
        self.connected = False
        self.cargar_configuracion()
        self.crear_widgets()

    def cargar_configuracion(self):
        # ... (código igual) ...
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                self.host.set(config.get('host', '127.0.0.1'))
                self.port.set(config.get('port', '55555'))
                self.username.set(config.get('username', 'Usuario'))
        except (FileNotFoundError, json.JSONDecodeError):
            self.host.set('127.0.0.1')
            self.port.set('55555')
            self.username.set('Usuario')

    def guardar_configuracion(self):
        # ... (código igual) ...
        config = {
            'host': self.host.get(),
            'port': self.port.get(),
            'username': self.username.get()
        }
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            messagebox.showerror("Error de Guardado", f"No se pudo guardar la configuración: {e}")

    def crear_widgets(self):
        # Usamos el estilo 'superhero' de ttkbootstrap
        style = ttk.Style()
        style.theme_use('superhero')
        self.master.config(bg=style.lookup('TFrame', 'background'))

        main_frame = ttk.Frame(self.master, padding="20")
        main_frame.pack(fill='both', expand=True)

        # Título con estilo TLabel de ttkbootstrap
        ttk.Label(main_frame, text="Configuración de Conexión", font=('Arial', 14, 'bold'),
                  bootstyle="inverse-light").grid(row=0, columnspan=2, pady=10)

        # Labels y Entradas (usando Entry de ttkbootstrap)
        ttk.Label(main_frame, text="IP del Servidor (Host):").grid(row=1, column=0, sticky='w', pady=5)
        ttk.Entry(main_frame, textvariable=self.host, width=30, bootstyle="primary").grid(row=1, column=1, pady=5)

        ttk.Label(main_frame, text="Puerto:").grid(row=2, column=0, sticky='w', pady=5)
        ttk.Entry(main_frame, textvariable=self.port, width=30, bootstyle="primary").grid(row=2, column=1, pady=5)

        ttk.Label(main_frame, text="Nombre de Usuario:").grid(row=3, column=0, sticky='w', pady=5)
        ttk.Entry(main_frame, textvariable=self.username, width=30, bootstyle="primary").grid(row=3, column=1, pady=5)

        # Botones con estilo moderno (success/secondary)
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=4, columnspan=2, pady=20)

        ttk.Button(button_frame, text="Guardar Config", command=self.guardar_configuracion,
                   bootstyle="secondary").pack(side=tk.LEFT, padx=10)
        ttk.Button(button_frame, text="Conectar", command=self.conectar,
                   bootstyle="success").pack(side=tk.LEFT, padx=10)

        # ... (El método conectar es el mismo) ...

    def conectar(self):
        # ... (validaciones y cierre son iguales) ...
        h = self.host.get()
        p = self.port.get()
        u = self.username.get().strip()

        if not (h and p and u):
            messagebox.showwarning("Error", "Todos los campos son obligatorios.")
            return
        try:
            p_int = int(p)
            if not (1024 < p_int < 65535):
                raise ValueError
        except ValueError:
            messagebox.showwarning("Error", "El puerto debe ser un número válido entre 1025 y 65535.")
            return
        if not (2 <= len(u) <= 15 and all(c.isalnum() or c in ' _-' for c in u)):
            messagebox.showwarning("Validación",
                                   "El nombre debe tener entre 2 y 15 caracteres y solo contener letras, números, espacios, guiones bajos o guiones.")
            return

        self.temp_host = h
        self.temp_port = p_int
        self.temp_username = u
        self.connected = True
        self.master.destroy()


# ====================================================================
#                      MAIN
# ====================================================================
if __name__ == '__main__':
    # Usamos ttk.Window para aplicar el tema de ttkbootstrap correctamente
    root_connect = ttk.Window(themename="superhero")
    connect_app = ConnectWindow(root_connect)
    root_connect.mainloop()

    if connect_app.connected:
        root_chat = ttk.Window(themename="superhero")
        chat_app = ClienteChat(root_chat, connect_app.temp_host, connect_app.temp_port, connect_app.temp_username)


        def reset_unread(event):
            if chat_app.running:
                chat_app.mensajes_sin_leer = 0
                chat_app.actualizar_titulo_ux()


        root_chat.bind("<FocusIn>", reset_unread)

        if chat_app.running:
            root_chat.mainloop()
