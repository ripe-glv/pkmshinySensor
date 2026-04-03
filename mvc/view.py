"""
mvc/view.py
───────────
Interface gráfica do Shiny Atuador.

- Página SENSORES: cards de gerações com botões ATIVAR/DESATIVAR reais
- Monitor ao vivo por sensor ativo com múltiplos sensores simultâneos
- Cache de imagens + semáforo para evitar sobrecarga com 4+ sensores
"""

import tkinter as tk
from tkinter import ttk, messagebox
import urllib.request
import base64
import threading

# ── paleta ────────────────────────────────────────────────────────────────────
BG      = "#0d0f14"
PANEL   = "#12151f"
SIDEBAR = "#0f1219"
CARD    = "#1a1e2a"
BORDER  = "#252a3a"
ACCENT  = "#f0c030"
ACCENT2 = "#e87030"
GREEN   = "#30e890"
RED     = "#e83050"
FG      = "#d0d8f0"
FG_DIM  = "#606888"
SEL     = "#1e2438"

F_BIG = ("Courier New", 20, "bold")
F_TIT = ("Courier New", 11, "bold")
F_MED = ("Courier New", 10)
F_SM  = ("Courier New", 9)
F_XSM = ("Courier New", 8)

GEN_CORES = {
    1: "#e05050", 2: "#c0a030", 3: "#30b060",
    4: "#4080e0", 5: "#9060c0", 6: "#d06080",
    7: "#30b0b0", 8: "#8080c0", 9: "#e08030",
}
GEN_NOMES = {
    1: "Kanto",  2: "Johto",  3: "Hoenn",
    4: "Sinnoh", 5: "Unova",  6: "Kalos",
    7: "Alola",  8: "Galar",  9: "Paldea",
}
TYPE_CORES = {
    "fire": "#e05030",    "water": "#3090e0",   "grass": "#30b050",
    "electric": "#e0c030","psychic": "#d04090", "ice": "#60c0e0",
    "dragon": "#6040e0",  "dark": "#605060",    "fairy": "#e080b0",
    "normal": "#a0a090",  "fighting": "#c03020","flying": "#8090e0",
    "poison": "#a040c0",  "ground": "#d0b050",  "rock": "#b0a040",
    "bug": "#a0b020",     "ghost": "#705090",   "steel": "#b0b0c0",
}

# Limita downloads simultâneos de imagem (evita trava com 4+ sensores)



class AtuadorView(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("✦ Shiny Atuador")
        self.geometry("1100x720")
        self.minsize(860, 580)
        self.configure(bg=BG)

        # callbacks preenchidos pelo Controller
        self.cb_ativar_sensor    = lambda gen: None
        self.cb_desativar_sensor = lambda gen=None: None
        self.cb_libertar         = lambda p_id: None
        self.cb_ver_detalhes     = lambda p_id: None

        self._img_refs: list                      = []
        self._img_cache: dict[str, tk.PhotoImage] = {}   # url → PhotoImage (evita re-download)
        self._todos_cards: list[dict]             = []
        self._gen_ativos: set[int]                = set()
        self._gen_btns: dict[int, tk.Button]      = {}

        # monitor ao vivo: sensor_id → {frame, lbl_nome, lbl_img, lbl_status, img_ref, flash_job}
        self._monitor_cards: dict[str, dict] = {}

        self._build_root()

    # ═══════════════════════════════════════════════════════════════════════════
    # RAIZ
    # ═══════════════════════════════════════════════════════════════════════════
    def _build_root(self):
        self._sb = tk.Frame(self, bg=SIDEBAR, width=210)
        self._sb.pack(side="left", fill="y")
        self._sb.pack_propagate(False)

        self._area = tk.Frame(self, bg=BG)
        self._area.pack(side="left", fill="both", expand=True)

        self._build_sidebar()

        self._pages: dict[str, tk.Frame] = {}
        self._build_page_sensores()
        self._build_page_capturados()
        self._build_page_detalhes()

        self._ir_para("sensores")

    # ═══════════════════════════════════════════════════════════════════════════
    # SIDEBAR
    # ═══════════════════════════════════════════════════════════════════════════
    def _build_sidebar(self):
        sb = self._sb

        logo = tk.Frame(sb, bg=SIDEBAR, pady=18)
        logo.pack(fill="x")
        tk.Label(logo, text="✦",       font=("Courier New", 26, "bold"), fg=ACCENT,  bg=SIDEBAR).pack()
        tk.Label(logo, text="SHINY",   font=("Courier New", 13, "bold"), fg=FG,      bg=SIDEBAR).pack()
        tk.Label(logo, text="ATUADOR", font=("Courier New", 9),          fg=FG_DIM,  bg=SIDEBAR).pack()

        tk.Frame(sb, bg=BORDER, height=1).pack(fill="x", padx=16, pady=(0, 8))

        self._nav_btns: dict[str, tk.Button] = {}
        for lbl, key, icon in [("SENSORES", "sensores", "⬡"), ("CAPTURADOS", "capturados", "◈")]:
            btn = tk.Button(sb, text=f"  {icon}  {lbl}",
                            font=F_SM, fg=FG_DIM, bg=SIDEBAR,
                            activebackground=SEL, activeforeground=ACCENT,
                            relief="flat", anchor="w", padx=10, pady=10,
                            cursor="hand2",
                            command=lambda k=key: self._ir_para(k))
            btn.pack(fill="x", padx=8, pady=2)
            self._nav_btns[key] = btn

        tk.Frame(sb, bg=BORDER, height=1).pack(fill="x", padx=16, pady=8)

        tk.Label(sb, text="TOTAL SHINIES", font=F_XSM, fg=FG_DIM, bg=SIDEBAR).pack()
        self._total_num = tk.Label(sb, text="0",
                                   font=("Courier New", 28, "bold"), fg=ACCENT, bg=SIDEBAR)
        self._total_num.pack(pady=(0, 16))

        tk.Frame(sb, bg=BORDER, height=1).pack(fill="x", padx=16)
        tk.Label(sb, text="SENSORES ATIVOS", font=F_XSM, fg=FG_DIM, bg=SIDEBAR).pack(pady=(8, 2))
        self._sidebar_sensores_frame = tk.Frame(sb, bg=SIDEBAR)
        self._sidebar_sensores_frame.pack(fill="x", padx=8)
        self._sidebar_sem_sensor = tk.Label(
            self._sidebar_sensores_frame, text="nenhum",
            font=F_XSM, fg=FG_DIM, bg=SIDEBAR)
        self._sidebar_sem_sensor.pack()

        tk.Frame(sb, bg=SIDEBAR).pack(fill="both", expand=True)
        tk.Frame(sb, bg=BORDER, height=1).pack(fill="x", padx=16)
        tk.Button(sb, text="  ✕  SAIR", font=F_SM,
                  fg=RED, bg=SIDEBAR, activebackground=SEL, activeforeground=RED,
                  relief="flat", anchor="w", padx=10, pady=10, cursor="hand2",
                  command=self._confirmar_sair).pack(fill="x", padx=8, pady=8)

    def _confirmar_sair(self):
        if messagebox.askyesno("Sair", "Deseja encerrar o Atuador?", icon="warning"):
            self.on_close()

    def _ir_para(self, key: str):
        for p in self._pages.values():
            p.pack_forget()
        self._pages[key].pack(fill="both", expand=True)
        nav_key = key if key in self._nav_btns else "capturados"
        for k, btn in self._nav_btns.items():
            btn.configure(fg=ACCENT if k == nav_key else FG_DIM,
                          bg=SEL    if k == nav_key else SIDEBAR)

    # ═══════════════════════════════════════════════════════════════════════════
    # PÁGINA: SENSORES
    # ═══════════════════════════════════════════════════════════════════════════
    def _build_page_sensores(self):
        page = tk.Frame(self._area, bg=BG)
        self._pages["sensores"] = page

        # cabeçalho
        hdr = tk.Frame(page, bg=BG, pady=14)
        hdr.pack(fill="x", padx=24)
        tk.Label(hdr, text="SENSORES", font=F_BIG, fg=FG, bg=BG).pack(side="left")
        tk.Label(hdr, text=" — ative quantas gerações quiser",
                 font=F_MED, fg=FG_DIM, bg=BG).pack(side="left", pady=(6, 0))
        tk.Frame(page, bg=BORDER, height=1).pack(fill="x", padx=24)

        # barra de status global
        sbar = tk.Frame(page, bg=PANEL, pady=8)
        sbar.pack(fill="x")
        left = tk.Frame(sbar, bg=PANEL)
        left.pack(side="left", padx=24)
        self._dot = tk.Label(left, text="●", font=("Courier New", 16), fg=RED, bg=PANEL)
        self._dot.pack(side="left", padx=(0, 6))
        self._status_lbl = tk.Label(left, text="OFFLINE", font=F_TIT, fg=RED, bg=PANEL)
        self._status_lbl.pack(side="left")
        self._gen_ativa_lbl = tk.Label(left, text="", font=F_SM, fg=FG_DIM, bg=PANEL)
        self._gen_ativa_lbl.pack(side="left", padx=(8, 0))

        # log
        tk.Frame(page, bg=BORDER, height=1).pack(fill="x", side="bottom")
        log_wrap = tk.Frame(page, bg=PANEL, height=72)
        log_wrap.pack(fill="x", side="bottom")
        log_wrap.pack_propagate(False)
        tk.Label(log_wrap, text="LOG", font=F_XSM, fg=FG_DIM, bg=PANEL
                 ).pack(anchor="w", padx=16, pady=(5, 0))
        self._log = tk.Text(log_wrap, bg=PANEL, fg=FG_DIM,
                            font=("Courier New", 8), bd=0,
                            state="disabled", wrap="word",
                            selectbackground=BORDER)
        self._log.pack(fill="both", expand=True, padx=16, pady=(0, 6))

        # corpo
        corpo = tk.Frame(page, bg=BG)
        corpo.pack(fill="both", expand=True)

        # coluna esquerda — grade de gerações com botões toggle
        esq = tk.Frame(corpo, bg=BG, width=340)
        esq.pack(side="left", fill="y", padx=(12, 0), pady=10)
        esq.pack_propagate(False)

        tk.Label(esq, text="SENSORES DISPONÍVEIS", font=("Courier New", 8, "bold"),
                 fg=FG_DIM, bg=BG).pack(anchor="w", padx=8, pady=(0, 6))

        wrap_gen = tk.Frame(esq, bg=BG)
        wrap_gen.pack(fill="both", expand=True)

        for gen in range(1, 10):
            col = (gen - 1) % 3
            row = (gen - 1) // 3
            wrap_gen.columnconfigure(col, weight=1)
            cor = GEN_CORES[gen]

            card = tk.Frame(wrap_gen, bg=CARD,
                            highlightthickness=1, highlightbackground=BORDER)
            card.grid(row=row, column=col, padx=4, pady=4, sticky="nsew")

            inner = tk.Frame(card, bg=CARD, pady=8, padx=10)
            inner.pack(fill="both", expand=True)

            tk.Label(inner, text=f"GEN {gen}", font=("Courier New", 8, "bold"),
                     fg=cor, bg=CARD).pack(anchor="w")
            tk.Label(inner, text=GEN_NOMES[gen], font=F_SM, fg=FG_DIM, bg=CARD).pack(anchor="w")

            btn = tk.Button(
                inner, text="▶ ATIVAR",
                font=("Courier New", 8, "bold"),
                fg=GREEN, bg=BORDER,
                activebackground=SEL, activeforeground=GREEN,
                relief="flat", padx=4, pady=4, cursor="hand2",
                command=lambda g=gen: self._toggle_sensor(g),
            )
            btn.pack(fill="x", pady=(6, 0))
            self._gen_btns[gen] = btn

        # separador
        tk.Frame(corpo, bg=BORDER, width=1).pack(side="left", fill="y", padx=8)

        # coluna direita — monitor ao vivo
        dir_col = tk.Frame(corpo, bg=BG)
        dir_col.pack(side="left", fill="both", expand=True, pady=10, padx=(0, 12))

        tk.Label(dir_col, text="MONITOR AO VIVO", font=("Courier New", 8, "bold"),
                 fg=FG_DIM, bg=BG).pack(anchor="w", padx=8, pady=(0, 6))

        mon_wrap = tk.Frame(dir_col, bg=BG)
        mon_wrap.pack(fill="both", expand=True)

        self._mon_canvas = tk.Canvas(mon_wrap, bg=BG, highlightthickness=0, bd=0)
        mon_sb = ttk.Scrollbar(mon_wrap, orient="vertical", command=self._mon_canvas.yview)
        self._mon_canvas.configure(yscrollcommand=mon_sb.set)
        mon_sb.pack(side="right", fill="y")
        self._mon_canvas.pack(side="left", fill="both", expand=True)

        self._mon_grid = tk.Frame(self._mon_canvas, bg=BG)
        self._mon_win  = self._mon_canvas.create_window((0, 0), window=self._mon_grid, anchor="nw")
        self._mon_grid.bind("<Configure>",
            lambda _e: self._mon_canvas.configure(scrollregion=self._mon_canvas.bbox("all")))
        self._mon_canvas.bind("<Configure>",
            lambda e: self._mon_canvas.itemconfig(self._mon_win, width=e.width))

        self._mon_placeholder = tk.Label(
            self._mon_grid,
            text="Nenhum sensor ativo.\nAtive uma geração ao lado →",
            font=F_SM, fg=FG_DIM, bg=BG, justify="center")
        self._mon_placeholder.grid(row=0, column=0, pady=60, padx=20)

    # ── controle dos botões de sensor ─────────────────────────────────────────

    def _toggle_sensor(self, gen: int):
        if gen in self._gen_ativos:
            self.cb_desativar_sensor(gen)
        else:
            self.cb_ativar_sensor(gen)

    def _atualizar_botao_gen(self, gen: int, ativo: bool):
        btn = self._gen_btns.get(gen)
        if btn is None:
            return
        if ativo:
            btn.configure(text="■ DESATIVAR", fg=RED, activeforeground=RED)
        else:
            btn.configure(text="▶ ATIVAR", fg=GREEN, activeforeground=GREEN)

    # ═══════════════════════════════════════════════════════════════════════════
    # PÁGINA: CAPTURADOS
    # ═══════════════════════════════════════════════════════════════════════════
    def _build_page_capturados(self):
        page = tk.Frame(self._area, bg=BG)
        self._pages["capturados"] = page

        hdr = tk.Frame(page, bg=BG, pady=16)
        hdr.pack(fill="x", padx=24)
        tk.Label(hdr, text="CAPTURADOS", font=F_BIG, fg=FG, bg=BG).pack(side="left")

        filt = tk.Frame(hdr, bg=BG)
        filt.pack(side="right")
        tk.Label(filt, text="FILTRAR:", font=F_XSM, fg=FG_DIM, bg=BG).pack(side="left")
        self._filtro_var = tk.StringVar(value="Todos")
        cb = ttk.Combobox(filt, textvariable=self._filtro_var,
                          values=["Todos"] + [f"Gen {g}" for g in range(1, 10)],
                          state="readonly", width=9, font=F_SM)
        cb.pack(side="left", padx=(6, 0))
        cb.bind("<<ComboboxSelected>>", lambda _: self._aplicar_filtro())

        tk.Frame(page, bg=BORDER, height=1).pack(fill="x", padx=24)

        wrap = tk.Frame(page, bg=BG)
        wrap.pack(fill="both", expand=True, padx=8, pady=8)

        self._cap_canvas = tk.Canvas(wrap, bg=BG, highlightthickness=0, bd=0)
        sb2 = ttk.Scrollbar(wrap, orient="vertical", command=self._cap_canvas.yview)
        self._cap_canvas.configure(yscrollcommand=sb2.set)
        sb2.pack(side="right", fill="y")
        self._cap_canvas.pack(side="left", fill="both", expand=True)

        self._cap_grid = tk.Frame(self._cap_canvas, bg=BG)
        self._cap_win  = self._cap_canvas.create_window((0, 0), window=self._cap_grid, anchor="nw")
        self._cap_grid.bind("<Configure>",
            lambda _e: self._cap_canvas.configure(scrollregion=self._cap_canvas.bbox("all")))
        self._cap_canvas.bind("<Configure>",
            lambda e: self._cap_canvas.itemconfig(self._cap_win, width=e.width))
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self._cap_canvas.bind(seq, self._scroll_cap)

        self._empty_lbl = tk.Label(self._cap_grid,
                                   text="Nenhum shiny capturado ainda...",
                                   font=F_MED, fg=FG_DIM, bg=BG)
        self._empty_lbl.grid(row=0, column=0, pady=60)

    def _scroll_cap(self, e):
        if   e.num == 4: self._cap_canvas.yview_scroll(-1, "units")
        elif e.num == 5: self._cap_canvas.yview_scroll( 1, "units")
        else:            self._cap_canvas.yview_scroll(int(-e.delta / 120), "units")

    def _aplicar_filtro(self):
        val   = self._filtro_var.get()
        gen_f = None if val == "Todos" else int(val.split()[1])
        visiveis = []
        for entry in self._todos_cards:
            entry["frame"].grid_forget()
            if gen_f is None or entry["gen"] == gen_f:
                visiveis.append(entry["frame"])
        for i, frame in enumerate(visiveis):
            col, row = i % 4, i // 4
            frame.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")
            self._cap_grid.columnconfigure(col, weight=1)
        if visiveis:
            self._empty_lbl.grid_forget()
        else:
            self._empty_lbl.grid(row=0, column=0, pady=60)

    # ═══════════════════════════════════════════════════════════════════════════
    # PÁGINA: DETALHES
    # ═══════════════════════════════════════════════════════════════════════════
    def _build_page_detalhes(self):
        page = tk.Frame(self._area, bg=BG)
        self._pages["detalhes"] = page

        hdr = tk.Frame(page, bg=BG, pady=14)
        hdr.pack(fill="x", padx=24)
        tk.Button(hdr, text="← VOLTAR", font=F_SM,
                  fg=FG_DIM, bg=SIDEBAR,
                  activebackground=SEL, activeforeground=ACCENT,
                  relief="flat", padx=10, pady=4, cursor="hand2",
                  command=lambda: self._ir_para("capturados")
                  ).pack(side="left", padx=(0, 16))
        self._det_titulo = tk.Label(hdr, text="", font=F_BIG, fg=FG, bg=BG)
        self._det_titulo.pack(side="left")
        self._det_id_lbl = tk.Label(hdr, text="", font=F_SM, fg=FG_DIM, bg=BG)
        self._det_id_lbl.pack(side="left", padx=(8, 0), pady=(8, 0))

        tk.Frame(page, bg=BORDER, height=1).pack(fill="x", padx=24)

        topo = tk.Frame(page, bg=PANEL, pady=16)
        topo.pack(fill="x")

        img_box = tk.Frame(topo, bg=PANEL, width=140, height=140)
        img_box.pack(side="left", padx=(24, 16))
        img_box.pack_propagate(False)
        self._det_img = tk.Label(img_box, text="◈", font=("Courier New", 40), fg=BORDER, bg=PANEL)
        self._det_img.place(relx=.5, rely=.5, anchor="center")

        id_col = tk.Frame(topo, bg=PANEL)
        id_col.pack(side="left", fill="both", expand=True, padx=(0, 20))
        self._det_gen_lbl  = tk.Label(id_col, text="", font=F_SM, fg=FG_DIM, bg=PANEL)
        self._det_gen_lbl.pack(anchor="w")
        self._det_nome_lbl = tk.Label(id_col, text="", font=("Courier New", 20, "bold"), fg=FG, bg=PANEL)
        self._det_nome_lbl.pack(anchor="w")
        tk.Label(id_col, text="✦ SHINY", font=("Courier New", 9, "bold"), fg=ACCENT2, bg=PANEL
                 ).pack(anchor="w", pady=(2, 8))
        self._det_tipos_row = tk.Frame(id_col, bg=PANEL)
        self._det_tipos_row.pack(anchor="w")
        self._det_medidas   = tk.Frame(id_col, bg=PANEL)
        self._det_medidas.pack(anchor="w", pady=(10, 0))

        tk.Frame(page, bg=BORDER, height=1).pack(fill="x")

        corpo = tk.Frame(page, bg=BG)
        corpo.pack(fill="both", expand=True, padx=20, pady=14)
        corpo.columnconfigure(0, weight=2)
        corpo.columnconfigure(1, weight=3)

        esq = tk.Frame(corpo, bg=BG)
        esq.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        self._det_stats_title = tk.Label(esq, text="BASE STATS",
                                         font=("Courier New", 9, "bold"), fg=ACCENT, bg=BG)
        self._det_stats_title.pack(anchor="w", pady=(0, 8))

        self._stat_bars: dict[str, tuple] = {}
        for stat in ["HP", "ATK", "DEF", "SP.ATK", "SP.DEF", "SPD"]:
            row_f = tk.Frame(esq, bg=BG)
            row_f.pack(fill="x", pady=3)
            tk.Label(row_f, text=stat, font=F_XSM, fg=FG_DIM, bg=BG, width=7, anchor="w").pack(side="left")
            val_lbl = tk.Label(row_f, text="—", font=("Courier New", 8, "bold"), fg=FG, bg=BG, width=4, anchor="e")
            val_lbl.pack(side="left")
            bar_bg = tk.Frame(row_f, bg=BORDER, height=6)
            bar_bg.pack(side="left", fill="x", expand=True, padx=(6, 0))
            bar_bg.pack_propagate(False)
            self._stat_bars[stat] = (val_lbl, bar_bg)

        dir_col = tk.Frame(corpo, bg=BG)
        dir_col.grid(row=0, column=1, sticky="nsew")
        self._det_desc_title = tk.Label(dir_col, text="DESCRIÇÃO",
                                        font=("Courier New", 9, "bold"), fg=ACCENT, bg=BG)
        self._det_desc_title.pack(anchor="w", pady=(0, 6))
        desc_box = tk.Frame(dir_col, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        desc_box.pack(fill="x")
        self._det_desc = tk.Text(desc_box, bg=CARD, fg=FG, font=F_SM, bd=0,
                                 wrap="word", height=4, padx=10, pady=8,
                                 state="disabled", selectbackground=BORDER)
        self._det_desc.pack(fill="x")

        tk.Label(dir_col, text="MOVIMENTOS", font=("Courier New", 9, "bold"),
                 fg=ACCENT, bg=BG).pack(anchor="w", pady=(14, 6))
        mov_wrap = tk.Frame(dir_col, bg=BG)
        mov_wrap.pack(fill="both", expand=True)
        self._mov_canvas = tk.Canvas(mov_wrap, bg=BG, highlightthickness=0, bd=0, height=160)
        mov_sb = ttk.Scrollbar(mov_wrap, orient="vertical", command=self._mov_canvas.yview)
        self._mov_canvas.configure(yscrollcommand=mov_sb.set)
        mov_sb.pack(side="right", fill="y")
        self._mov_canvas.pack(side="left", fill="both", expand=True)
        self._mov_inner = tk.Frame(self._mov_canvas, bg=BG)
        self._mov_win   = self._mov_canvas.create_window((0, 0), window=self._mov_inner, anchor="nw")
        self._mov_inner.bind("<Configure>",
            lambda _e: self._mov_canvas.configure(scrollregion=self._mov_canvas.bbox("all")))
        self._mov_canvas.bind("<Configure>",
            lambda e: self._mov_canvas.itemconfig(self._mov_win, width=e.width))

    # ═══════════════════════════════════════════════════════════════════════════
    # API PÚBLICA — monitor ao vivo
    # ═══════════════════════════════════════════════════════════════════════════

    def atualizar_lista_sensores(self, sensores: dict):
        """
        Chamado pelo controller quando sensores são ativados/desativados.
        `sensores` é dict {gen: Popen}. Usa só as chaves.
        """
        gens_ativas  = set(sensores.keys())
        novas        = gens_ativas - self._gen_ativos
        removidas    = self._gen_ativos - gens_ativas
        self._gen_ativos = gens_ativas

        for g in novas:
            self._atualizar_botao_gen(g, ativo=True)
        for g in removidas:
            self._atualizar_botao_gen(g, ativo=False)

        # remove cards cujos sensores foram desativados
        for sid in [s for s in list(self._monitor_cards)
                    if self._sid_para_gen(s) in removidas]:
            self._monitor_cards.pop(sid)["frame"].destroy()

        # cria cards para gerações novas
        for gen in gens_ativas:
            sid = f"sensor_gen{gen}"
            if sid not in self._monitor_cards:
                self._criar_card_monitor(gen, sid)

        if self._monitor_cards:
            self._mon_placeholder.grid_forget()
        else:
            self._mon_placeholder.grid(row=0, column=0, pady=60, padx=20)
        self._rearranjar_monitor()

        # sidebar
        for w in self._sidebar_sensores_frame.winfo_children():
            w.destroy()
        if gens_ativas:
            for g in sorted(gens_ativas):
                tk.Label(self._sidebar_sensores_frame,
                         text=f"● Gen {g} — {GEN_NOMES[g]}",
                         font=F_XSM, fg=GEN_CORES[g], bg=SIDEBAR).pack(anchor="w")
        else:
            tk.Label(self._sidebar_sensores_frame, text="nenhum",
                     font=F_XSM, fg=FG_DIM, bg=SIDEBAR).pack()

    def _sid_para_gen(self, sensor_id: str) -> int:
        try:
            return int(sensor_id.replace("sensor_gen", ""))
        except Exception:
            return 0

    def _criar_card_monitor(self, gen: int, sensor_id: str):
        cor   = GEN_CORES[gen]
        frame = tk.Frame(self._mon_grid, bg=CARD,
                         highlightthickness=1, highlightbackground=cor,
                         padx=8, pady=8)

        top = tk.Frame(frame, bg=CARD)
        top.pack(fill="x")
        tk.Label(top, text=f"GEN {gen}", font=("Courier New", 8, "bold"),
                 fg=cor, bg=CARD).pack(side="left")
        tk.Label(top, text=GEN_NOMES[gen], font=F_XSM, fg=FG_DIM, bg=CARD
                 ).pack(side="left", padx=(4, 0))
        tk.Button(top, text="✕", font=F_XSM,
                  fg=RED, bg=CARD, activebackground=BORDER, activeforeground=RED,
                  relief="flat", cursor="hand2",
                  command=lambda g=gen: self.cb_desativar_sensor(g)
                  ).pack(side="right")

        lbl_img = tk.Label(frame, text="◈", font=("Courier New", 22),
                           fg=BORDER, bg=CARD, width=7, height=4)
        lbl_img.pack(pady=(6, 2))

        lbl_nome   = tk.Label(frame, text="aguardando...", font=F_SM, fg=FG_DIM, bg=CARD, wraplength=120)
        lbl_nome.pack()
        lbl_status = tk.Label(frame, text="", font=("Courier New", 8, "bold"), fg=FG_DIM, bg=CARD)
        lbl_status.pack(pady=(2, 0))

        self._monitor_cards[sensor_id] = {
            "frame":      frame,
            "lbl_img":    lbl_img,
            "lbl_nome":   lbl_nome,
            "lbl_status": lbl_status,
            "img_ref":    None,
            "flash_job":  None,
            "gen":        gen,
        }

    def _rearranjar_monitor(self):
        for w in self._mon_grid.winfo_children():
            if w is not self._mon_placeholder:
                w.grid_forget()
        for i, info in enumerate(self._monitor_cards.values()):
            col, row = i % 2, i // 2
            info["frame"].grid(row=row, column=col, padx=8, pady=8, sticky="nsew")
            self._mon_grid.columnconfigure(col, weight=1)

    def atualizar_monitor_sensor(
        self, sensor_id: str, gen: int, nome: str,
        p_id: str, img_url: str, is_shiny: bool
    ):
        info = self._monitor_cards.get(sensor_id)
        if info is None:
            return

        cor = GEN_CORES.get(gen, ACCENT)

        if is_shiny:
            info["lbl_nome"].configure(text=nome.upper(), fg=ACCENT)
            info["lbl_status"].configure(text="✦ SHINY!", fg=ACCENT)
            info["frame"].configure(highlightbackground=ACCENT)
            self._flash_card(sensor_id, n=6)
        else:
            if info["flash_job"]:
                self.after_cancel(info["flash_job"])
                info["flash_job"] = None
            info["lbl_nome"].configure(text=nome.capitalize(), fg=FG)
            info["lbl_status"].configure(text=f"#{p_id}  normal", fg=FG_DIM)
            info["frame"].configure(bg=CARD, highlightbackground=cor)
            for w in (info["lbl_img"], info["lbl_nome"], info["lbl_status"]):
                w.configure(bg=CARD)

        if img_url:
            if img_url in self._img_cache:
                # imagem já está em cache — aplica direto, sem nova thread
                self._apply_monitor_img(sensor_id, self._img_cache[img_url])
            else:
                threading.Thread(
                    target=self._fetch_monitor_img,
                    args=(sensor_id, img_url), daemon=True
                ).start()

    def _flash_card(self, sensor_id: str, n: int = 6):
        info = self._monitor_cards.get(sensor_id)
        if info is None:
            return
        cor = ["#2a2000", CARD][n % 2]
        info["frame"].configure(bg=cor)
        for w in (info["lbl_img"], info["lbl_nome"], info["lbl_status"]):
            w.configure(bg=cor)
        if n > 0:
            info["flash_job"] = self.after(200, self._flash_card, sensor_id, n - 1)

    def _fetch_monitor_img(self, sensor_id: str, url: str):
        # double-check: outra thread pode ter baixado enquanto esperávamos o semáforo
        if url in self._img_cache:
            self.after(0, lambda p=self._img_cache[url], s=sensor_id:
                        self._apply_monitor_img(s, p))
            return
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as r:
                raw = r.read()
            b64   = base64.b64encode(raw).decode()
            photo = tk.PhotoImage(data=b64)
            f = max(1, max(photo.width(), photo.height()) // 80)
            if f > 1:
                photo = photo.subsample(f, f)
            self._img_cache[url] = photo
            self._img_refs.append(photo)
            self.after(0, lambda p=photo, s=sensor_id: self._apply_monitor_img(s, p))
        except Exception:
            pass

    def _apply_monitor_img(self, sensor_id: str, photo):
        info = self._monitor_cards.get(sensor_id)
        if info:
            info["lbl_img"].configure(image=photo, text="", width=80, height=80)
            info["img_ref"] = photo

    # ═══════════════════════════════════════════════════════════════════════════
    # API PÚBLICA — status, cards capturados, detalhes
    # ═══════════════════════════════════════════════════════════════════════════

    def set_status_online(self, gen_nome: str):
        self._dot.configure(fg=GREEN)
        self._status_lbl.configure(text="ONLINE", fg=GREEN)
        self._gen_ativa_lbl.configure(text=f"— {gen_nome}")

    def set_status_offline(self):
        self._dot.configure(fg=RED)
        self._status_lbl.configure(text="OFFLINE", fg=RED)
        self._gen_ativa_lbl.configure(text="")

    def log(self, msg: str):
        self._log.configure(state="normal")
        self._log.insert("end", msg + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def set_total(self, n: int):
        self._total_num.configure(text=str(n))

    def adicionar_card_com_id(self, nome: str, p_id: str, img_url: str, gen: int):
        self._empty_lbl.grid_forget()
        cor   = GEN_CORES.get(gen, ACCENT)
        entry = {"gen": gen, "p_id": str(p_id), "frame": None}

        idx = len(self._todos_cards)
        col, row = idx % 4, idx // 4
        self._cap_grid.columnconfigure(col, weight=1)

        card = tk.Frame(self._cap_grid, bg=CARD,
                        highlightthickness=1, highlightbackground=BORDER,
                        padx=8, pady=8)
        card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")

        tk.Label(card, text=f"GEN {gen}", font=("Courier New", 7, "bold"),
                 fg=cor, bg=CARD).pack(anchor="e")
        img_lbl = tk.Label(card, text="◈", font=("Courier New", 28),
                           fg=BORDER, bg=CARD, width=8, height=4)
        img_lbl.pack()
        tk.Label(card, text=nome.upper(), font=F_TIT,
                 fg=ACCENT, bg=CARD, wraplength=130).pack(pady=(4, 0))
        tk.Label(card, text=f"#{p_id}", font=F_SM, fg=FG_DIM, bg=CARD).pack()
        tk.Label(card, text="✦ SHINY", font=("Courier New", 8, "bold"),
                 fg=ACCENT2, bg=CARD).pack(pady=(2, 0))

        btns = tk.Frame(card, bg=CARD)
        btns.pack(pady=(8, 0), fill="x")
        tk.Button(btns, text="◉ VER", font=F_XSM,
                  fg=ACCENT, bg=BORDER, activebackground=SEL, activeforeground=ACCENT,
                  relief="flat", padx=6, pady=3, cursor="hand2",
                  command=lambda i=p_id: self.cb_ver_detalhes(i)
                  ).pack(side="left", expand=True, fill="x", padx=(0, 2))
        tk.Button(btns, text="↩ LIB", font=F_XSM,
                  fg=RED, bg=BORDER, activebackground=SEL, activeforeground=RED,
                  relief="flat", padx=6, pady=3, cursor="hand2",
                  command=lambda i=p_id: self.cb_libertar(i)
                  ).pack(side="left", expand=True, fill="x", padx=(2, 0))

        entry["frame"] = card
        self._todos_cards.append(entry)
        self._aplicar_filtro()

        # aproveita cache se disponível
        if img_url in self._img_cache:
            photo = self._img_cache[img_url]
            img_lbl.configure(image=photo, text="", width=96, height=96)
        else:
            threading.Thread(target=self._fetch_card_img,
                             args=(img_url, img_lbl), daemon=True).start()

    def remover_card(self, p_id: str):
        for i, entry in enumerate(self._todos_cards):
            if entry["p_id"] == str(p_id):
                entry["frame"].destroy()
                self._todos_cards.pop(i)
                break
        self._aplicar_filtro()
        if not self._todos_cards:
            self._empty_lbl.grid(row=0, column=0, pady=60)

    def abrir_detalhes(self, dados: dict, gen: int, tipos: list[str]):
        cor = GEN_CORES.get(gen, ACCENT)
        self._det_titulo.configure(text=dados.get("nome", "").upper())
        self._det_id_lbl.configure(text=f"  #{dados.get('id', '')}")
        self._det_gen_lbl.configure(text=f"GEN {gen} — {GEN_NOMES.get(gen, '')}", fg=cor)
        self._det_nome_lbl.configure(text=dados.get("nome", "").upper())
        self._det_stats_title.configure(fg=cor)
        self._det_desc_title.configure(fg=cor)

        for w in self._det_tipos_row.winfo_children():
            w.destroy()
        tipos_str = dados.get("tipos", "") 
        
        if tipos_str:
            lista_tipos = tipos_str.split(";") 
            
            for t in lista_tipos:
                tc = TYPE_CORES.get(t.lower(), BORDER)
                tk.Label(self._det_tipos_row, text=t.upper(),
                         font=("Courier New", 8, "bold"), fg=BG, bg=tc, padx=6, pady=2
                         ).pack(side="left", padx=(0, 4))
        else:
            tk.Label(self._det_tipos_row, text="tipo não informado",
                     font=F_XSM, fg=FG_DIM, bg=PANEL).pack(side="left")

        for w in self._det_medidas.winfo_children():
            w.destroy()
        for lbl, val in [("ALTURA", dados.get("altura", "—")), ("PESO", dados.get("peso", "—"))]:
            blk = tk.Frame(self._det_medidas, bg=CARD,
                           highlightthickness=1, highlightbackground=BORDER, padx=10, pady=4)
            blk.pack(side="left", padx=(0, 8))
            tk.Label(blk, text=lbl, font=F_XSM, fg=FG_DIM, bg=CARD).pack()
            tk.Label(blk, text=val or "—", font=F_TIT, fg=FG, bg=CARD).pack()

        stat_keys = {
            "HP":     dados.get("hp",        "—"),
            "ATK":    dados.get("ataque",     "—"),
            "DEF":    dados.get("defesa",     "—"),
            "SP.ATK": dados.get("ataque_esp", "—"),
            "SP.DEF": dados.get("defesa_esp", "—"),
            "SPD":    dados.get("velocidade", "—"),
        }
        for stat, (val_lbl, bar_bg) in self._stat_bars.items():
            raw = stat_keys.get(stat, "—")
            val_lbl.configure(text=str(raw) if raw and raw != "—" else "—")
            for w in bar_bg.winfo_children():
                w.destroy()
            try:
                ratio   = min(1.0, int(raw) / 255)
                bar_cor = RED if ratio < 0.33 else (ACCENT if ratio < 0.66 else GREEN)
            except (ValueError, TypeError):
                ratio, bar_cor = 0, BORDER

            def _draw(bg=bar_bg, r=ratio, c=bar_cor):
                w = bg.winfo_width()
                if w < 4:
                    bg.after(50, _draw)
                    return
                tk.Frame(bg, bg=c, width=max(2, int(w * r)), height=6).place(x=0, y=0)
            bar_bg.after(80, _draw)

        self._det_desc.configure(state="normal")
        self._det_desc.delete("1.0", "end")
        self._det_desc.insert("end", dados.get("descricao", "") or "Sem descrição.")
        self._det_desc.configure(state="disabled")

        for w in self._mov_inner.winfo_children():
            w.destroy()
        movs = dados.get("movimentos", [])
        if movs:
            for mi, mov in enumerate(movs):
                tk.Label(self._mov_inner, text=mov.upper(), font=F_XSM,
                         fg=FG, bg=CARD, padx=6, pady=3,
                         highlightthickness=1, highlightbackground=BORDER
                         ).grid(row=mi // 3, column=mi % 3, padx=3, pady=3, sticky="ew")
                self._mov_inner.columnconfigure(mi % 3, weight=1)
        else:
            tk.Label(self._mov_inner, text="Movimentos não informados.",
                     font=F_SM, fg=FG_DIM, bg=BG).pack(anchor="w")

        self._det_img.configure(image="", text="◈", font=("Courier New", 40), fg=BORDER)
        img_url = dados.get("imagem", "")
        if img_url:
            threading.Thread(target=self._fetch_det_img, args=(img_url,), daemon=True).start()

        self._ir_para("detalhes")

    # ── fetch imagens ─────────────────────────────────────────────────────────

    def _fetch_card_img(self, url: str, label: tk.Label):
        if url in self._img_cache:
            photo = self._img_cache[url]
            self.after(0, lambda p=photo: label.configure(image=p, text="", width=96, height=96))
            return
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                raw = r.read()
            b64   = base64.b64encode(raw).decode()
            photo = tk.PhotoImage(data=b64)
            f = max(1, max(photo.width(), photo.height()) // 96)
            if f > 1:
                photo = photo.subsample(f, f)
            self._img_cache[url] = photo
            self._img_refs.append(photo)
            self.after(0, lambda p=photo: label.configure(image=p, text="", width=96, height=96))
        except Exception as ex:
            self.after(0, lambda: label.configure(text="✕", font=("Courier New", 22), fg=RED))
            self.after(0, lambda m=str(ex): self.log(f"[IMG] {m}"))

    def _fetch_det_img(self, url: str):
        if url in self._img_cache:
            photo = self._img_cache[url]
            self.after(0, lambda p=photo: self._det_img.configure(
                image=p, text="", width=128, height=128))
            return
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                raw = r.read()
            b64   = base64.b64encode(raw).decode()
            photo = tk.PhotoImage(data=b64)
            f = max(1, max(photo.width(), photo.height()) // 128)
            if f > 1:
                photo = photo.subsample(f, f)
            self._img_cache[url] = photo
            self._img_refs.append(photo)
            self.after(0, lambda p=photo: self._det_img.configure(
                image=p, text="", width=128, height=128))
        except Exception:
            pass

    # ── confirmações ──────────────────────────────────────────────────────────

    def confirmar_libertar(self, nome: str) -> bool:
        return messagebox.askyesno(
            "Libertar Pokémon",
            f"Tem certeza que quer libertar {nome}?\nEle será removido permanentemente.",
            icon="warning")

    def on_close(self):
        self.destroy()