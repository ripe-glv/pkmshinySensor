"""
mvc/model.py
────────────
Responsável pelos dados: leitura, escrita e consulta do JSON de shinies.
Não sabe nada de UI, rede ou sockets.

Importa GERACOES de atuador/sensores.py (fonte única de verdade).
"""

import json
import os
from sensores import GERACOES, detectar_gen

ARQUIVO = "shinies.json"


class ShinyModel:
    def __init__(self):
        self._dados: list[dict] = []
        self._carregar()

    # ── persistência ──────────────────────────────────────────────────────────
    def _carregar(self):
        if not os.path.exists(ARQUIVO):
            self._dados = []
            return
        with open(ARQUIVO, "r", encoding="utf-8") as f:
            try:
                self._dados = json.load(f)
            except Exception:
                self._dados = []

    def _salvar(self):
        with open(ARQUIVO, "w", encoding="utf-8") as f:
            json.dump(self._dados, f, indent=4, ensure_ascii=False)

    # ── escrita ───────────────────────────────────────────────────────────────
    def adicionar(self, nome: str, p_id: str, imagem: str, tipos: list[str]) -> dict:
        item = {
            "nome": nome, "id": p_id, "imagem": imagem,
            "tipos": tipos, "altura": "", "peso": "", "descricao": "",
            "hp": "", "ataque": "", "defesa": "",
            "ataque_esp": "", "defesa_esp": "", "velocidade": "",
            "movimentos": [],
        }
        self._dados.append(item)
        self._salvar()
        return item

    def atualizar_detalhes(self, p_id: str, detalhes: dict) -> bool:
        for item in self._dados:
            if str(item["id"]) == str(p_id):
                item.update(detalhes)
                self._salvar()
                return True
        return False

    def libertar(self, p_id: str) -> bool:
        antes = len(self._dados)
        self._dados = [d for d in self._dados if str(d["id"]) != str(p_id)]
        if len(self._dados) < antes:
            self._salvar()
            return True
        return False

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

    def get_tipos(self, p_id: str) -> list[str]:
        item = self.get_por_id(p_id)
        if item is not None:
            return item.get("tipos", [])
        return []

    def total(self) -> int:
        return len(self._dados)
