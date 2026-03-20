import socket
import json
import tkinter as tk
from tkinter import scrolledtext
import threading
import urllib.request
import io
import os
from PIL import Image, ImageTk

# Configurações
SERVER_IP = "127.0.0.1"
PORT = 6000
ARQUIVO_JSON = "shinies_capturados.json"

class AtuadorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Pokémon Collector - Atuador")
        self.root.geometry("450x650")
        self.root.configure(bg="#e0e0e0")

        # --- Menu Fixo (Sempre Disponível) ---
        self.menu_frame = tk.Frame(root, bg="#333", height=50)
        self.menu_frame.pack(side="top", fill="x")
        
        tk.Button(self.menu_frame, text="Monitor Real-Time", command=self.mostrar_tela_captura, bg="#555", fg="white").pack(side="left", padx=10, pady=5)
        tk.Button(self.menu_frame, text="Ver Coleção (Histórico)", command=self.mostrar_tela_historico, bg="#555", fg="white").pack(side="left", padx=10, pady=5)
        tk.Button(self.menu_frame, text="Limpar Tudo", command=self.limpar_dados, bg="#a33", fg="white").pack(side="right", padx=10, pady=5)

        # --- Container Principal para Alternar Telas ---
        self.container = tk.Frame(root, bg="#f0f0f0")
        self.container.pack(fill="both", expand=True)

        # Inicializa as Telas
        self.setup_tela_captura()
        self.setup_tela_historico()

        # Mostra a tela inicial
        self.mostrar_tela_captura()

        # Thread de Rede
        threading.Thread(target=self.conectar_rede, daemon=True).start()

    def setup_tela_captura(self):
        self.frame_captura = tk.Frame(self.container, bg="#f0f0f0")
        tk.Label(self.frame_captura, text="Aguardando Shinies...", font=("Arial", 14, "bold"), bg="#f0f0f0").pack(pady=10)
        
        self.canvas_img = tk.Label(self.frame_captura, bg="white", width=200, height=200, relief="solid")
        self.canvas_img.pack(pady=10)

        self.pkm_label = tk.Label(self.frame_captura, text="Status: Desconectado", font=("Arial", 11), bg="#f0f0f0")
        self.pkm_label.pack(pady=5)

        self.log_area = scrolledtext.ScrolledText(self.frame_captura, width=45, height=12)
        self.log_area.pack(pady=10)

    def setup_tela_historico(self):
        self.frame_historico = tk.Frame(self.container, bg="white")
        self.canvas_scroll = tk.Canvas(self.frame_historico, bg="white")
        self.scrollbar = tk.Scrollbar(self.frame_historico, orient="vertical", command=self.canvas_scroll.yview)
        self.scrollable_frame = tk.Frame(self.canvas_scroll, bg="white")

        self.scrollable_frame.bind("<Configure>", lambda e: self.canvas_scroll.configure(scrollregion=self.canvas_scroll.bbox("all")))
        self.canvas_scroll.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas_scroll.configure(yscrollcommand=self.scrollbar.set)

    def mostrar_tela_captura(self):
        self.frame_historico.pack_forget()
        self.frame_captura.pack(fill="both", expand=True)

    def mostrar_tela_historico(self):
        self.frame_captura.pack_forget()
        self.frame_historico.pack(fill="both", expand=True)
        self.canvas_scroll.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.atualizar_galeria()

    def atualizar_galeria(self):
        # Limpa galeria antiga
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        self.galeria_fotos = []
        if os.path.exists(ARQUIVO_JSON):
            with open(ARQUIVO_JSON, "r") as f:
                dados = json.load(f)
                for i, pkm in enumerate(dados):
                    card = tk.Frame(self.scrollable_frame, bg="#fff", bd=1, relief="ridge")
                    card.grid(row=i//3, column=i%3, padx=5, pady=5)
                    
                    foto = self.baixar_imagem(pkm['url'], size=(90, 90))
                    if foto:
                        tk.Label(card, image=foto, bg="#fff").pack()
                        self.galeria_fotos.append(foto)
                    tk.Label(card, text=pkm['nome'], font=("Arial", 8), bg="#fff").pack()

    def limpar_dados(self):
        if os.path.exists(ARQUIVO_JSON):
            os.remove(ARQUIVO_JSON)
        self.mostrar_tela_captura()
        self.log_area.delete('1.0', tk.END)
        self.log_area.insert(tk.END, "Histórico limpo!\n")

    def baixar_imagem(self, url, size=(180, 180)):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=2) as resp:
                img = Image.open(io.BytesIO(resp.read())).resize(size, Image.LANCZOS)
                return ImageTk.PhotoImage(img)
        except: return None

    def atualizar_ui_captura(self, nome, id_pkm, url):
        foto = self.baixar_imagem(url)
        if foto:
            self.canvas_img.config(image=foto)
            self.canvas_img.image = foto
        self.pkm_label.config(text=f"✨ {nome.upper()} CAPTURADO! ✨", fg="#b8860b")
        self.log_area.insert(tk.END, f"[SISTEMA] {nome} salvo no JSON.\n")
        self.log_area.see(tk.END)
        
        # Salva no JSON
        historico = []
        if os.path.exists(ARQUIVO_JSON):
            with open(ARQUIVO_JSON, "r") as f:
                try: historico = json.load(f)
                except: pass
        historico.append({"nome": nome, "id": id_pkm, "url": url})
        with open(ARQUIVO_JSON, "w") as f:
            json.dump(historico, f, indent=4)

    def conectar_rede(self):
        cliente = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            cliente.connect((SERVER_IP, PORT))
            self.root.after(0, lambda: self.log_area.insert(tk.END, "Conectado ao Backend!\n"))
            while True:
                msg = cliente.recv(1024).decode()
                if not msg: break
                nome, p_id, url = msg.strip().split("|")
                self.root.after(0, self.atualizar_ui_captura, nome, p_id, url)
        except Exception as e:
            self.root.after(0, lambda: self.log_area.insert(tk.END, f"❌ Erro: {e}\n"))

if __name__ == "__main__":
    root = tk.Tk()
    app = AtuadorApp(root)
    root.mainloop()