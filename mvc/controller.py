"""
mvc/controller.py
─────────────────
Liga a View ao Model. Recebe eventos via processar() chamado pelo main_gui.py.
Não sabe nada de sockets — a conexão TCP fica no main_gui.py.
"""

from mvc.model import ShinyModel
from mvc.view  import AtuadorView


class AtuadorController:
    def __init__(self, model: ShinyModel, view: AtuadorView):
        self._model = model
        self._view  = view
        self.ativo  = True

        # expõe view para o main_gui.py acessar
        self.view = view

        self._view.cb_ativar_sensor    = lambda gen: None
        self._view.cb_desativar_sensor = lambda gen: None
        self._view.cb_libertar         = self._handle_libertar
        self._view.cb_ver_detalhes     = self._handle_ver_detalhes
        self._view.protocol("WM_DELETE_WINDOW", self._handle_fechar)

    # ── inicialização ─────────────────────────────────────────────────────────

    def iniciar(self):
        for item in self._model.get_todos():
            gen = self._model.detectar_gen(item["id"])
            self._view.adicionar_card_com_id(item["nome"], item["id"], item["imagem"], gen)
        self._view.set_total(self._model.total())

    # ── handlers da View ──────────────────────────────────────────────────────

    def _handle_ver_detalhes(self, p_id: str):
        dados = self._model.get_por_id(p_id)
        if dados is None:
            return
        gen = self._model.detectar_gen(p_id)
        tipos = self._model.get_tipos(p_id)
        self._view.abrir_detalhes(dados, gen, tipos)

    def _handle_libertar(self, p_id: str):
        nome = (self._model.get_por_id(p_id) or {}).get("nome", p_id)
        if not self._view.confirmar_libertar(nome):
            return
        if self._model.libertar(p_id):
            self._view.remover_card(p_id)
            self._view.set_total(self._model.total())
            self._view.log(f"[↩] {nome} foi libertado.")

    def _handle_fechar(self):
        self.ativo = False
        self._view.on_close()

    # ── processamento de eventos TCP (chamado pelo main_gui.py) ───────────────

    def processar(self, linha: str):
        partes = linha.split("|")
        if len(partes) < 7:
            return

        tipo, nome, p_id, url, sensor_id, gen, tipos = partes[:7]
        gen = int(partes[5]) if len(partes) > 6 else 1
        if tipo == "APARECER":
            self._view.after(0, lambda n=nome, i=p_id, u=url, g=gen, s=sensor_id, t=tipos:
                self._view.atualizar_monitor_sensor(s, g, n, i, u, is_shiny=False))

        elif tipo == "SHINY":
            self._model.adicionar(nome, p_id, url, tipos)
            self._view.after(0, lambda n=nome, i=p_id, u=url, g=gen, s=sensor_id, t=tipos:
                self._view.atualizar_monitor_sensor(s, g, n, i, u, is_shiny=True))
            self._view.after(0, lambda n=nome, i=p_id, u=url, g=gen, t=tipos:
                self._view.adicionar_card_com_id(n, i, u, g))
            self._view.after(0, lambda: self._view.set_total(self._model.total()))
