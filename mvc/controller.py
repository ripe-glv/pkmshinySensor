"""
mvc/controller.py
─────────────────
Liga a View ao Model. Recebe eventos via processar() chamado pelo main_gui.py.
Ao receber SHINY, recarrega o model do disco (o atuador já salvou no volume).
"""

from mvc.model import ShinyModel
from mvc.view  import AtuadorView
import time
import threading


class AtuadorController:
    def __init__(self, model: ShinyModel, view: AtuadorView):
        self._model = model
        self._view  = view
        self.ativo  = True
        self.view   = view

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
        gen       = self._model.detectar_gen(p_id)
        tipos_raw = dados.get("tipos", [])
        tipos     = ";".join(tipos_raw) if isinstance(tipos_raw, list) else (tipos_raw or "")
        self._view.abrir_detalhes(dados, gen, tipos)

    def _handle_libertar(self, p_id: str):
        nome = (self._model.get_por_id(p_id) or {}).get("nome", p_id)
        if not self._view.confirmar_libertar(nome):
            return
        if self._model.libertar(p_id):
            self._view.remover_card(p_id)
            self._view.set_total(self._model.total())
            self._view.log(f"[↩] {nome} removido da view.")

    def _handle_fechar(self):
        self.ativo = False
        self._view.on_close()

    # ── eventos TCP (chamado pelo main_gui.py) ────────────────────────────────


    # ── eventos TCP (chamado pelo main_gui.py) ────────────────────────────────

    def processar(self, acao: str, nome: str, p_id: str, img: str, sensor_id: str, gen: int, tipos: list[str]):
        """Processa os eventos vindos do TCP."""
        
        # O APARECER e a atualização do Monitor Ao Vivo já estão sendo 
        # feitos de forma instantânea lá no main_gui.py.

        if acao == "SHINY":
            # Cria uma rotina em background para esperar o atuador_headless
            def _esperar_pokeapi_e_carregar():
                tentativas = 0
                dados = None
                
                # Tenta ler o JSON a cada 1 segundo (máximo de 10 tentativas)
                while tentativas < 10:
                    self._model.recarregar()
                    dados = self._model.get_por_id(p_id)
                    
                    if dados:
                        break # Achou! O headless terminou de salvar.
                        
                    time.sleep(1)
                    tentativas += 1

                # Se achou os dados completos, usa a imagem oficial, senão usa a do TCP
                img_final = dados["imagem"] if dados else img
                
                # Adiciona o card na View de forma segura
                self._view.after(0, lambda n=nome, i=p_id, u=img_final, g=gen:
                    self._view.adicionar_card_com_id(n, i, u, g))
                
                # Atualiza o contador de capturas
                self._view.after(0, lambda: self._view.set_total(self._model.total()))
                
                if dados:
                    self._view.after(0, lambda: self._view.log(f"[✓] Dados da PokeAPI carregados para #{p_id}"))
                else:
                    self._view.after(0, lambda: self._view.log(f"[⚠] Timeout: O atuador_headless demorou muito para o #{p_id}"))

            # Dispara a espera sem travar a interface
            threading.Thread(target=_esperar_pokeapi_e_carregar, daemon=True).start()