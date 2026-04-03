"""
mvc/model.py
────────────
Leitura do JSON de shinies persistido pelo atuador no volume Docker.
Não escreve nada — persistência é responsabilidade do atuador_headless.py.
"""

import json
import os
from sensores import GERACOES, detectar_gen

ARQUIVO = os.environ.get("ARQUIVO", "/shinies.json")


class ShinyModel:
    def __init__(self):
        self._dados: list[dict] = []
        self._carregar()

    def _carregar(self):
        if not os.path.exists(ARQUIVO):
            self._dados = []
            return
        with open(ARQUIVO, "r", encoding="utf-8") as f:
            try:
                self._dados = json.load(f)
            except Exception:
                self._dados = []

    def recarregar(self):
        """Relê o JSON do disco — chamado pela GUI ao receber evento SHINY."""
        self._carregar()

    # ── leitura ───────────────────────────────────────────────────────────────

    def get_todos(self) -> list[dict]:
        return list(self._dados)

    def get_por_id(self, p_id: str) -> dict | None:
        for item in self._dados:
            if str(item["id"]) == str(p_id):
                return dict(item)
        return None

    def get_geracoes(self) -> dict:
        return GERACOES

    def detectar_gen(self, p_id: str) -> int:
        try:
            return detectar_gen(int(p_id))
        except (ValueError, TypeError):
            return 1

    def total(self) -> int:
        return len(self._dados)

    def libertar(self, p_id: str) -> bool:
        """Remove localmente da view — o JSON no volume não é alterado pela GUI."""
        antes = len(self._dados)
        self._dados = [d for d in self._dados if str(d["id"]) != str(p_id)]
        return len(self._dados) < antes
