import socket
import json
import os
import threading
import tkinter as tk
from tkinter import ttk
import urllib.request
import base64

SERVER_IP = "127.0.0.1"
PORT = 6000
ARQUIVO = "shinies.json"


def salvar(dados):
    lista = []
    if os.path.exists(ARQUIVO):
        with open(ARQUIVO, "r") as f:
            try:
                lista = json.load(f)
            except Exception:
                lista = []
    lista.append(dados)
    with open(ARQUIVO, "w") as f:
        json.dump(lista, f, indent=4)


def carregar_historico():
    if not os.path.exists(ARQUIVO):
        return []
    with open(ARQUIVO, "r") as f:
        try:
            return json.load(f)
        except Exception:
            return []


BG      = "#0d0f14"
PANEL   = "#13161e"
CARD    = "#1a1e2a"
BORDER  = "#252a3a"
ACCENT  = "#f0c030"
ACCENT2 = "#e87030"
GREEN   = "#30e890"
RED     = "#e83050"
FG      = "#d0d8f0"
FG_DIM  = "#606888"

F_BIG  = ("Courier New", 22, "bold")
F_TIT  = ("Courier New", 11, "bold")
F_SM   = ("Courier New", 9)
F_XSM  = ("Courier New", 8)


class AtuadorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("✦ Shiny Atuador")
        self.geometry("860x660")
        self.configure(bg=BG)
        self.resizable(True, True)

        self._sock       = None
        self._connected  = False
        self._img_refs   = []
        self._card_count = 0

        self._build_ui()
        self._load_history()

    def _build_ui(self):
        hdr = tk.Frame(self, bg=BG, pady=12)
        hdr.pack(fill="x", padx=20)

        tk.Label(hdr, text="✦ SHINY", font=F_BIG, fg=ACCENT, bg=BG).pack(side="left")
        tk.Label(hdr, text=" ATUADOR", font=F_BIG, fg=FG, bg=BG).pack(side="left")

        right = tk.Frame(hdr, bg=BG)
        right.pack(side="right")

        self._dot = tk.Label(right, text="●", font=("Courier New", 18), fg=RED, bg=BG)
        self._dot.pack(side="left", padx=(0, 5))

        self._status_lbl = tk.Label(right, text="OFFLINE", font=F_TIT, fg=RED, bg=BG)
        self._status_lbl.pack(side="left", padx=(0, 14))

        self._btn = tk.Button(right, text="CONECTAR", font=F_TIT,
                              fg=BG, bg=ACCENT, activebackground=ACCENT2,
                              activeforeground=BG, relief="flat",
                              padx=14, pady=4, cursor="hand2", command=self._toggle)
        self._btn.pack(side="left")

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", padx=20)

        info = tk.Frame(self, bg=BG)
        info.pack(fill="x", padx=24, pady=6)

        tk.Label(info, text="CAPTURAS:", font=F_SM, fg=FG_DIM, bg=BG).pack(side="left")
        self._count_lbl = tk.Label(info, text="0", font=F_TIT, fg=ACCENT, bg=BG)
        self._count_lbl.pack(side="left", padx=(4, 20))

        tk.Label(info, text="ÚLTIMO:", font=F_SM, fg=FG_DIM, bg=BG).pack(side="left")
        self._last_lbl = tk.Label(info, text="—", font=F_TIT, fg=FG, bg=BG)
        self._last_lbl.pack(side="left", padx=4)

        wrap = tk.Frame(self, bg=BG)
        wrap.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        self._canvas = tk.Canvas(wrap, bg=BG, highlightthickness=0, bd=0)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self._grid = tk.Frame(self._canvas, bg=BG)
        self._win  = self._canvas.create_window((0, 0), window=self._grid, anchor="nw")

        self._grid.bind("<Configure>",
                        lambda _e: self._canvas.configure(
                            scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>",
                          lambda e: self._canvas.itemconfig(self._win, width=e.width))

        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self._canvas.bind(seq, self._scroll)

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")
        log_wrap = tk.Frame(self, bg=PANEL, height=84)
        log_wrap.pack(fill="x")
        log_wrap.pack_propagate(False)

        tk.Label(log_wrap, text="LOG", font=F_XSM, fg=FG_DIM, bg=PANEL).pack(
            anchor="w", padx=14, pady=(5, 0))

        self._log = tk.Text(log_wrap, bg=PANEL, fg=FG_DIM, font=("Courier New", 8),
                            bd=0, state="disabled", wrap="word",
                            selectbackground=BORDER)
        self._log.pack(fill="both", expand=True, padx=14, pady=(0, 8))

    def _scroll(self, e):
        if e.num == 4:
            self._canvas.yview_scroll(-1, "units")
        elif e.num == 5:
            self._canvas.yview_scroll(1, "units")
        else:
            self._canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

    def _log_msg(self, msg):
        self._log.configure(state="normal")
        self._log.insert("end", msg + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _load_history(self):
        for item in carregar_historico():
            self._add_card(item["nome"], item["id"], item["imagem"])

    def _add_card(self, nome, p_id, img_url):
        idx = self._card_count
        col = idx % 4
        row = idx // 4
        self._card_count += 1

        card = tk.Frame(self._grid, bg=CARD,
                        highlightthickness=1, highlightbackground=BORDER,
                        padx=8, pady=8)
        card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")
        self._grid.columnconfigure(col, weight=1)

        img_lbl = tk.Label(card, text="◈", font=("Courier New", 30),
                           fg=BORDER, bg=CARD, width=8, height=4)
        img_lbl.pack()

        tk.Label(card, text=nome.upper(), font=F_TIT,
                 fg=ACCENT, bg=CARD, wraplength=130).pack(pady=(4, 0))
        tk.Label(card, text=f"#{p_id}", font=F_SM, fg=FG_DIM, bg=CARD).pack()
        tk.Label(card, text="✦ SHINY", font=("Courier New", 8, "bold"),
                 fg=ACCENT2, bg=CARD).pack(pady=(2, 0))

        self._count_lbl.configure(text=str(self._card_count))
        self._last_lbl.configure(text=nome.upper())

        threading.Thread(target=self._fetch_img,
                         args=(img_url, img_lbl), daemon=True).start()

    def _fetch_img(self, url, label):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                raw = r.read()

            b64 = base64.b64encode(raw).decode()
            photo = tk.PhotoImage(data=b64)

            w, h = photo.width(), photo.height()
            factor = max(1, max(w, h) // 96)
            if factor > 1:
                photo = photo.subsample(factor, factor)

            self._img_refs.append(photo)
            self.after(0, lambda p=photo: label.configure(
                image=p, text="", width=96, height=96))
        except Exception as ex:
            self.after(0, lambda: label.configure(
                text="✕", font=("Courier New", 24), fg=RED))
            self.after(0, lambda msg=str(ex): self._log_msg(f"[IMG] {msg}"))

    def _toggle(self):
        if self._connected:
            self._disconnect()
        else:
            self._btn.configure(state="disabled", text="…")
            threading.Thread(target=self._run_socket, daemon=True).start()

    def _disconnect(self):
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        self._set_online(False)

    def _set_online(self, ok):
        self._connected = ok
        if ok:
            self._dot.configure(fg=GREEN)
            self._status_lbl.configure(text="ONLINE", fg=GREEN)
            self._btn.configure(state="normal", text="DESCONECTAR",
                                bg=RED, fg="white")
        else:
            self._dot.configure(fg=RED)
            self._status_lbl.configure(text="OFFLINE", fg=RED)
            self._btn.configure(state="normal", text="CONECTAR",
                                bg=ACCENT, fg=BG)

    def _run_socket(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self._sock.connect((SERVER_IP, PORT))
            self.after(0, lambda: self._set_online(True))
            self.after(0, lambda: self._log_msg(f"[OK] Conectado em {SERVER_IP}:{PORT}"))

            while True:
                msg = self._sock.recv(1024).decode()
                if not msg:
                    break
                partes = msg.strip().split("|")
                if len(partes) == 3:
                    nome, p_id, img = partes
                    salvar({"nome": nome, "id": p_id, "imagem": img})
                    self.after(0, lambda n=nome: self._log_msg(f"[★] {n}!"))
                    self.after(0, lambda n=nome, i=p_id, u=img:
                               self._add_card(n, i, u))

        except ConnectionResetError:
            self.after(0, lambda: self._log_msg("[ERR] Conexão perdida."))
        except Exception as e:
            self.after(0, lambda msg=str(e): self._log_msg(f"[ERR] {msg}"))
        finally:
            self.after(0, lambda: self._set_online(False))

    def on_close(self):
        self._disconnect()
        self.destroy()


if __name__ == "__main__":
    app = AtuadorApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()