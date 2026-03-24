"""
mvc/controller.py
─────────────────
Liga a View ao Model e ao Atuador.
Suporta múltiplos sensores ativos simultaneamente.
"""

from mvc.model       import ShinyModel
from mvc.view        import AtuadorView
from atuador.atuador import Atuador


class AtuadorController:
    def __init__(self, model: ShinyModel, view: AtuadorView):
        self._model   = model
        self._view    = view
        self._atuador = Atuador(
            on_aparecer      = self._handle_aparecer,
            on_captura       = self._handle_captura,
            on_log           = self._log_na_ui,
            on_status        = self._handle_status,
            on_sensor_update = self._handle_sensor_update,
        )

        # liga callbacks da view aos handlers do controller
        self._view.cb_ativar_sensor    = self._handle_ativar
        self._view.cb_desativar_sensor = self._handle_desativar
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

    def _handle_ativar(self, gen: int):
        self._atuador.ativar_sensor(gen)

    def _handle_desativar(self, gen: int | None = None):
        if gen is None:
            self._atuador.desativar_todos()
        else:
            self._atuador.desativar_sensor(gen)

    def _handle_ver_detalhes(self, p_id: str):
        dados = self._model.get_por_id(p_id)
        if dados is None:
            return
        gen = self._model.detectar_gen(p_id)
        self._view.abrir_detalhes(dados, gen)

    def _handle_libertar(self, p_id: str):
        nome = (self._model.get_por_id(p_id) or {}).get("nome", p_id)
        if not self._view.confirmar_libertar(nome):
            return
        if self._model.libertar(p_id):
            self._view.remover_card(p_id)
            self._view.set_total(self._model.total())
            self._log_na_ui(f"[↩] {nome} foi libertado.")

    def _handle_fechar(self):
        self._atuador.desativar_todos()
        self._view.on_close()

    # ── callbacks do Atuador ──────────────────────────────────────────────────

    def _handle_aparecer(self, nome: str, p_id: str, img: str, gen: int, sensor_id: str):
        """Feedback visual de qualquer pokémon que aparecer (não só shinies)."""
        self._view.after(0, lambda n=nome, i=p_id, u=img, g=gen, s=sensor_id:
            self._view.atualizar_monitor_sensor(s, g, n, i, u, is_shiny=False))

    def _handle_captura(self, nome: str, p_id: str, img: str, gen: int):
        """Shiny confirmado — persiste e adiciona card."""
        sensor_id = f"sensor_gen{gen}"
        self._model.adicionar(nome, p_id, img)
        self._view.after(0, lambda n=nome, i=p_id, u=img, g=gen, s=sensor_id:
            self._view.atualizar_monitor_sensor(s, g, n, i, u, is_shiny=True))
        self._view.after(0, lambda n=nome, i=p_id, u=img, g=gen:
            self._view.adicionar_card_com_id(n, i, u, g))
        self._view.after(0, lambda: self._view.set_total(self._model.total()))

    def _handle_status(self, online: bool, texto: str):
        if online:
            self._view.after(0, lambda: self._view.set_status_online("Multi-Sensor"))
        elif not self._atuador.sensores_ativos():
            self._view.after(0, self._view.set_status_offline)

    def _handle_sensor_update(self, sensores: dict):
        """Chamado quando a lista de sensores muda."""
        self._view.after(0, lambda s=dict(sensores):
            self._view.atualizar_lista_sensores(s))

    def _log_na_ui(self, msg: str):
        self._view.after(0, lambda m=msg: self._view.log(m))