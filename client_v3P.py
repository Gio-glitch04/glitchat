import tkinter as tk
from tkinter import font as tkFont
from datetime import datetime

# ================================================
#   Pixel Chat v3 — Interfaz estilo pixel art
# ================================================

class PixelChatUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Pixel Chat v3")
        self.configure(bg="#2E2E2E")
        self.geometry("650x500")
        self.resizable(False, False)

        # Fuente pixelada (usar "Press Start 2P" o similar)
        # Podés instalarla o descargarla de Google Fonts
        self.pixel_font = tkFont.Font(family="Press Start 2P", size=8)

        # === MARCO SUPERIOR ===
        top_frame = tk.Frame(self, bg="#2E2E2E")
        top_frame.pack(pady=5)

        self.btn_connect = self.pixel_button(top_frame, "▶ Conectar", "#4CAF50", self.connect_action)
        self.btn_connect.pack(side=tk.LEFT, padx=5)

        self.btn_save = self.pixel_button(top_frame, "💾 Guardar Servidor", "#00BFFF", self.save_action)
        self.btn_save.pack(side=tk.LEFT, padx=5)

        self.btn_create = self.pixel_button(top_frame, "✏ Crear/Unir Sala", "#FFD700", self.create_room)
        self.btn_create.pack(side=tk.LEFT, padx=5)

        self.btn_list = self.pixel_button(top_frame, "📜 Listar Salas", "#FFD700", self.list_rooms)
        self.btn_list.pack(side=tk.LEFT, padx=5)

        # === ÁREA DEL CHAT ===
        chat_container = tk.Frame(self, bg="#1E1E1E")
        chat_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.chat_canvas = tk.Canvas(chat_container, bg="#1E1E1E", highlightthickness=0)
        self.chat_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.scrollbar = tk.Scrollbar(chat_container, orient="vertical", command=self.chat_canvas.yview)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.chat_canvas.configure(yscrollcommand=self.scrollbar.set)

        self.chat_frame = tk.Frame(self.chat_canvas, bg="#1E1E1E")
        self.chat_window = self.chat_canvas.create_window((0, 0), window=self.chat_frame, anchor="nw")
        self.chat_frame.bind("<Configure>", self.on_frame_configure)
        self.chat_canvas.bind("<Configure>", self.on_canvas_configure)

        # === CAMPO DE ENTRADA ===
        entry_frame = tk.Frame(self, bg="#2E2E2E")
        entry_frame.pack(fill=tk.X, pady=5)

        self.msg_entry = tk.Entry(entry_frame, font=self.pixel_font, bg="#333333", fg="white", insertbackground="white")
        self.msg_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.msg_entry.bind("<Return>", lambda e: self.send_message())

        self.btn_send = self.pixel_button(entry_frame, "Enviar", "#4CAF50", self.send_message)
        self.btn_send.pack(side=tk.RIGHT, padx=5)

    # =====================================================
    #      FUNCIONES DE ESTILO Y EVENTOS VISUALES
    # =====================================================
    def pixel_button(self, parent, text, bg, command):
        """Crea un botón estilo pixel art"""
        return tk.Button(
            parent,
            text=text,
            bg=bg,
            fg="white",
            font=self.pixel_font,
            activebackground=bg,
            activeforeground="white",
            bd=4,
            relief="ridge",
            command=command,
            cursor="hand2"
        )

    def on_frame_configure(self, event):
        """Actualizar scroll cuando cambie el tamaño"""
        self.chat_canvas.configure(scrollregion=self.chat_canvas.bbox("all"))

    def on_canvas_configure(self, event):
        """Ajustar ancho del chat dinámicamente"""
        self.chat_canvas.itemconfig(self.chat_window, width=event.width)

    # =====================================================
    #         FUNCIONES DE MENSAJES Y ACCIONES
    # =====================================================
    def add_message(self, sender, message, is_self=False):
        """Agrega una burbuja al chat"""
        time_str = datetime.now().strftime("%H:%M")
        msg_color = "#A8E6CF" if is_self else "#FFFFFF"
        text_color = "black"
        anchor_side = "e" if is_self else "w"

        bubble_frame = tk.Frame(self.chat_frame, bg="#1E1E1E")
        bubble_frame.pack(fill=tk.X, pady=4, padx=10, anchor=anchor_side)

        bubble = tk.Label(
            bubble_frame,
            text=f"{sender}: {message}\n{time_str}",
            bg=msg_color,
            fg=text_color,
            font=self.pixel_font,
            justify=tk.LEFT,
            wraplength=400,
            padx=8,
            pady=6,
            bd=3,
            relief="ridge"
        )
        bubble.pack(anchor=anchor_side)

        self.chat_canvas.yview_moveto(1.0)

    # =====================================================
    #         ACCIONES SIMULADAS DE DEMOSTRACIÓN
    # =====================================================
    def connect_action(self):
        self.add_message("Sistema", "Conectado al servidor ✅")

    def save_action(self):
        self.add_message("Sistema", "Servidor guardado 💾")

    def create_room(self):
        self.add_message("Sistema", "Sala creada/unida ✏")

    def list_rooms(self):
        self.add_message("Sistema", "Salas disponibles 📜")

    def send_message(self):
        msg = self.msg_entry.get().strip()
        if msg:
            self.add_message("Tú", msg, is_self=True)
            # Ejemplo de respuesta simulada del servidor:
            self.after(800, lambda: self.add_message("Otro", "Mensaje recibido 👍"))
            self.msg_entry.delete(0, tk.END)

# =====================================================
#             EJECUCIÓN PRINCIPAL
# =====================================================
if __name__ == "__main__":
    app = PixelChatUI()
    app.mainloop()
