"""
atuador_headless.py
────────────────────
Atuador headless para Docker.
Conecta ao servidor TCP, recebe eventos SHINY e persiste no JSON do volume.

Variáveis de ambiente:
  SERVER_HOST  — hostname/IP do servidor  (padrão: servidor)
  TCP_PORT     — porta TCP do servidor    (padrão: 6000)
  ARQUIVO      — caminho do JSON          (padrão: /data/shinies.json)
"""

import json
import os
import socket
import threading
import time
import urllib.request

SERVER_HOST = os.environ.get("SERVER_HOST", "servidor")
TCP_PORT    = int(os.environ.get("TCP_PORT", 6000))
ARQUIVO     = os.environ.get("ARQUIVO", "/shinies.json")

API_BASE_URL = "https://pokeapi.co/api/v2/pokemon/"

_lock = threading.Lock()


# ── persistência ──────────────────────────────────────────────────────────────

def _carregar() -> list[dict]:
    os.makedirs(os.path.dirname(ARQUIVO), exist_ok=True)
    if not os.path.exists(ARQUIVO):
        return []
    with open(ARQUIVO, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return []


def _salvar(dados: list[dict]):
    os.makedirs(os.path.dirname(ARQUIVO), exist_ok=True)
    with open(ARQUIVO, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)


def _ja_existe(p_id: str) -> bool:
    dados = _carregar()
    return any(str(d["id"]) == str(p_id) for d in dados)


def _registrar_shiny(nome: str, p_id: str, img: str, gen: int, sensor_id: str):
    with _lock:
        if _ja_existe(p_id):
            print(f"[Atuador] #{p_id} já registrado, ignorando.")
            return

        detalhes = _buscar_detalhes(int(p_id))

        item = {
            "nome":       nome,
            "id":         p_id,
            "imagem":     img,
            "gen":        gen,
            "sensor_id":  sensor_id,
            "tipos":      detalhes.get("tipos",      []),
            "altura":     detalhes.get("altura",     ""),
            "peso":       detalhes.get("peso",       ""),
            "descricao":  detalhes.get("descricao",  ""),
            "hp":         detalhes.get("hp",         ""),
            "ataque":     detalhes.get("ataque",     ""),
            "defesa":     detalhes.get("defesa",     ""),
            "ataque_esp": detalhes.get("ataque_esp", ""),
            "defesa_esp": detalhes.get("defesa_esp", ""),
            "velocidade": detalhes.get("velocidade", ""),
            "movimentos": detalhes.get("movimentos", []),
        }

        dados = _carregar()
        dados.append(item)
        _salvar(dados)
        print(f"[Atuador] ✨ Salvo: {nome} (#{p_id}) Gen {gen} — {sensor_id}")


# ── PokeAPI ───────────────────────────────────────────────────────────────────

def _buscar_detalhes(p_id: int) -> dict:
    """Busca dados completos do Pokémon na PokeAPI."""
    try:
        req = urllib.request.Request(
            f"{API_BASE_URL}{p_id}",
            headers={"User-Agent": "ShinyDetector/1.0"}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())

        stats = {s["stat"]["name"]: s["base_stat"] for s in data.get("stats", [])}

        return {
            "tipos":      [t["type"]["name"] for t in data.get("types", [])],
            "altura":     f'{data.get("height", 0) / 10:.1f}m',
            "peso":       f'{data.get("weight", 0) / 10:.1f}kg',
            "hp":         stats.get("hp",              ""),
            "ataque":     stats.get("attack",          ""),
            "defesa":     stats.get("defense",         ""),
            "ataque_esp": stats.get("special-attack",  ""),
            "defesa_esp": stats.get("special-defense", ""),
            "velocidade": stats.get("speed",           ""),
            "movimentos": [m["move"]["name"] for m in data.get("moves", [])[:20]],
            "descricao":  "",  # species endpoint separado — opcional
        }
    except Exception as e:
        print(f"[Atuador] ⚠ PokeAPI falhou para #{p_id}: {e}")
        return {}


# ── TCP loop ──────────────────────────────────────────────────────────────────

def loop():
    print(f"[Atuador] Conectando ao servidor {SERVER_HOST}:{TCP_PORT}...")
    while True:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((SERVER_HOST, TCP_PORT))
            print(f"[Atuador] ✅ Conectado!")

            buffer = ""
            while True:
                chunk = sock.recv(4096).decode(errors="replace")
                if not chunk:
                    break
                buffer += chunk
                while "\n" in buffer:
                    linha, buffer = buffer.split("\n", 1)
                    linha = linha.strip()
                    if not linha:
                        continue
                    partes = linha.split("|")
                    if len(partes) < 5:
                        continue

                    tipo, nome, p_id, img, sensor_id = partes[:5]
                    gen = int(partes[5]) if len(partes) > 5 else 1

                    if tipo == "APARECER":
                        print(f"[Atuador] 👀 {nome} (#{p_id}) Gen {gen} — {sensor_id}")

                    elif tipo == "SHINY":
                        print(f"[Atuador] ✨ SHINY! {nome} (#{p_id}) Gen {gen} — {sensor_id}")
                        threading.Thread(
                            target=_registrar_shiny,
                            args=(nome, p_id, img, gen, sensor_id),
                            daemon=True
                        ).start()

        except Exception as e:
            print(f"[Atuador] ❌ {e} — reconectando em 3s...")
            time.sleep(3)
        finally:
            try:
                sock.close()
            except Exception:
                pass


if __name__ == "__main__":
    loop()
