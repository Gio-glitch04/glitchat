import socket
import threading
import sys
import tkinter as tk
from tkinter import scrolledtext, ttk

# --- Configuración del Servidor ---
HOST = '0.0.0.0'
PORT = 55555
# -----------------------------------

# Variables globales y Locks
clientes = {}
clientes_lock = threading.Lock()
server_socket = None
is_running = False


class ChatServerGUI:
    def __init__(self, master):
        self.master = master
        master.title("Servidor de Chat - Panel de Control")
        master.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Estilos para una apariencia clara
        self.style = ttk.Style(master)
        self.style.theme_use('clam')
        self.style.configure('TButton', font=('Arial', 10, 'bold'))
        self.style.configure('TLabel', font=('Arial', 10))

        self.crear_widgets()

        # Actualizar la lista de usuarios y estado cada segundo
        self.master.after(1000, self.actualizar_gui)

    def crear_widgets(self):
        # --- Frame Superior de Control ---
        control_frame = ttk.Frame(self.master, padding="10")
        control_frame.pack(fill='x')

        self.status_label = ttk.Label(control_frame, text="Estado: Detenido", foreground='red')
        self.status_label.pack(side=tk.LEFT, padx=5)

        self.boton_iniciar = ttk.Button(control_frame, text="Iniciar Servidor", command=self.iniciar_servidor_thread)
        self.boton_iniciar.pack(side=tk.LEFT, padx=5)

        self.boton_detener = ttk.Button(control_frame, text="Detener Servidor", command=self.detener_servidor,
                                        state=tk.DISABLED)
        self.boton_detener.pack(side=tk.LEFT, padx=5)

        # --- Área de Log del Servidor ---
        ttk.Label(self.master, text="Registro del Servidor:").pack(padx=10, pady=(5, 0), anchor='w')
        self.log_area = scrolledtext.ScrolledText(self.master, state='disabled', wrap='word',
                                                  font=('Consolas', 9), height=15)
        self.log_area.pack(padx=10, pady=5, fill='x')

        # --- Lista de Usuarios Conectados ---
        ttk.Label(self.master, text="Usuarios Conectados:").pack(padx=10, pady=(5, 0), anchor='w')
        self.lista_usuarios = tk.Listbox(self.master, height=6, font=('Consolas', 10))
        self.lista_usuarios.pack(padx=10, pady=(0, 10), fill='x')

    def log_message(self, mensaje):
        """Inserta un mensaje en el área de log."""
        self.log_area.config(state='normal')
        self.log_area.insert(tk.END, mensaje + '\n')
        self.log_area.config(state='disabled')
        self.log_area.see(tk.END)

    def actualizar_gui(self):
        """Actualiza el estado y la lista de usuarios en la GUI."""

        # 1. Actualizar estado y botones
        if is_running:
            self.status_label.config(text=f"Estado: Funcionando ({HOST}:{PORT})", foreground='green')
            self.boton_iniciar.config(state=tk.DISABLED)
            self.boton_detener.config(state=tk.NORMAL)
        else:
            self.status_label.config(text="Estado: Detenido", foreground='red')
            self.boton_iniciar.config(state=tk.NORMAL)
            self.boton_detener.config(state=tk.DISABLED)

        # 2. Actualizar lista de usuarios
        self.lista_usuarios.delete(0, tk.END)
        with clientes_lock:
            if clientes:
                for sock, nombre in clientes.items():
                    # Obtenemos la IP y Puerto del cliente para la lista
                    try:
                        addr = sock.getpeername()
                        self.lista_usuarios.insert(tk.END, f"{nombre} ({addr[0]}:{addr[1]})")
                    except OSError:
                        self.lista_usuarios.insert(tk.END, f"{nombre} (Desconectado o Error)")

        # Reprogramar la actualización
        self.master.after(1000, self.actualizar_gui)

    # --- Funciones de Control del Servidor ---
    def iniciar_servidor_thread(self):
        """Inicia la lógica principal del servidor en un hilo separado."""
        global is_running
        if is_running:
            self.log_message("[ERROR] El servidor ya está corriendo.")
            return

        is_running = True
        self.log_message("Intentando iniciar el servidor...")
        # Crear un hilo para la función iniciar_servidor para no bloquear la GUI
        server_thread = threading.Thread(target=self._iniciar_servidor_logica)
        server_thread.daemon = True
        server_thread.start()

    def _iniciar_servidor_logica(self):
        """Lógica de sockets del servidor (ejecutada en el hilo secundario)."""
        global server_socket, is_running

        try:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind((HOST, PORT))
            server_socket.listen()
            self.log_message(f"*** Servidor de Chat iniciado en {HOST}:{PORT} ***")
        except Exception as e:
            self.log_message(f"[FATAL] No se pudo iniciar el servidor: {e}")
            is_running = False
            return

        while is_running:
            try:
                # Establecer un timeout para que el 'accept' no bloquee indefinidamente
                # y permita al hilo verificar si is_running ha cambiado (para detenerse)
                server_socket.settimeout(1.0)
                cliente_socket, addr = server_socket.accept()

                self.log_message(f"[CONEXIÓN] Nuevo cliente pendiente desde {addr}")

                # Crear un hilo para manejar al cliente
                thread = threading.Thread(target=self.manejo_cliente, args=(cliente_socket, addr))
                thread.daemon = True
                thread.start()

            except socket.timeout:
                continue  # Continúa si el timeout ocurre (es esperado)
            except Exception as e:
                if is_running:
                    self.log_message(f"[ERROR] Error al aceptar conexión: {e}")
                break  # Sale del bucle si el servidor se ha detenido

        # Limpieza al salir del bucle
        self.log_message("Lógica del servidor apagada.")
        is_running = False

    def detener_servidor(self):
        """Detiene el bucle de aceptación y cierra el socket principal."""
        global is_running
        if not is_running:
            return

        self.log_message("Deteniendo el servidor y desconectando clientes...")
        is_running = False

        # Cerrar todas las conexiones activas primero
        with clientes_lock:
            for sock in list(clientes.keys()):
                try:
                    sock.send("[Servidor] El servidor se está apagando. Desconexión inminente.".encode('utf-8'))
                    sock.shutdown(socket.SHUT_RDWR)
                    sock.close()
                except:
                    pass
            clientes.clear()

        # Cerrar el socket principal para liberar el puerto
        if server_socket:
            try:
                server_socket.close()
            except:
                pass

    def on_closing(self):
        """Maneja el cierre de la ventana, deteniendo el servidor primero."""
        if is_running:
            # Usar after para asegurar que la UI no se bloquee mientras se detiene la red
            self.detener_servidor()
            self.master.after(500, self.master.destroy)  # Espera un poco y luego destruye la GUI
        else:
            self.master.destroy()

    # --- Funciones de Red (Adaptadas para usar el log de la GUI) ---
    def broadcast(self, mensaje, cliente_socket):
        """Envía un mensaje a todos los clientes excepto al remitente."""
        with clientes_lock:
            for cliente in clientes:
                if cliente != cliente_socket:
                    try:
                        cliente.send(mensaje)
                    except:
                        # Error de envío (posiblemente desconectado)
                        pass

    def manejo_cliente(self, cliente_socket, addr):
        """Maneja la conexión y comunicación con un único cliente (en un hilo)."""
        nombre_usuario = None

        try:
            # 1. Registro de nombre
            cliente_socket.settimeout(30.0)  # Espera un tiempo razonable por el nombre
            nombre_usuario = cliente_socket.recv(1024).decode('utf-8').strip()
            cliente_socket.settimeout(None)  # Quitar timeout para el bucle principal

            with clientes_lock:
                if nombre_usuario in clientes.values():
                    cliente_socket.send("Nombre de usuario ya en uso. Desconectando.".encode('utf-8'))
                    self.log_message(f"[FALLO] Nombre '{nombre_usuario}' duplicado. Desconectando {addr}")
                    cliente_socket.close()
                    return
                clientes[cliente_socket] = nombre_usuario

            self.log_message(f"[USUARIO] {nombre_usuario} se ha unido. ({addr[0]})")
            self.broadcast(f"[Servidor] {nombre_usuario} se ha unido al chat.\n".encode('utf-8'), cliente_socket)

        except:
            cliente_socket.close()
            return

        # 2. Bucle principal de recepción de mensajes
        while is_running:
            try:
                mensaje = cliente_socket.recv(1024).decode('utf-8')
                if not mensaje:
                    raise ConnectionResetError

                    # Manejar comandos especiales
                if mensaje.strip().lower() == '/listar':
                    with clientes_lock:
                        lista = ", ".join(clientes.values())
                        cliente_socket.send(f"[Servidor] Usuarios conectados: {lista}\n".encode('utf-8'))

                elif mensaje.strip().lower() == '/quitar':
                    raise ConnectionResetError

                else:
                    mensaje_completo = f"<{nombre_usuario}> {mensaje}\n"
                    self.log_message(f"[MENSAJE] {mensaje_completo.strip()}")
                    self.broadcast(mensaje_completo.encode('utf-8'), cliente_socket)

            except (ConnectionResetError, ConnectionAbortedError, OSError):
                # 3. Manejo de desconexión y errores
                if cliente_socket in clientes:
                    with clientes_lock:
                        del clientes[cliente_socket]

                cliente_socket.close()
                if nombre_usuario:
                    self.log_message(f"[DESCONEXIÓN] {nombre_usuario} ha abandonado el chat.")
                    self.broadcast(f"[Servidor] {nombre_usuario} ha abandonado el chat.\n".encode('utf-8'), None)
                break


if __name__ == '__main__':
    root = tk.Tk()
    app = ChatServerGUI(root)
    root.mainloop()