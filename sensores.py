"""
atuador/sensores.py
───────────────────
Fonte única de verdade sobre as gerações Pokémon.
Também pode ser executado diretamente como sensor individual:

    python -m sensores <numero_da_geracao>

Em Docker: usa variáveis de ambiente SERVER_HOST e UDP_SERVER_PORT.
"""

import sys
import json
import random
import time
import socket
import urllib.request
import os

# Em Docker, SERVER_HOST aponta para o nome do serviço do servidor
HOST            = os.environ.get("SERVER_HOST", "127.0.0.1")
UDP_SERVER_PORT = int(os.environ.get("UDP_SERVER_PORT", 5000))

GERACOES: dict[int, dict] = {
    1: {"nome": "Geração I",    "regiao": "Kanto",  "range": (1,   151), "porta": 6001},
    2: {"nome": "Geração II",   "regiao": "Johto",  "range": (152, 251), "porta": 6002},
    3: {"nome": "Geração III",  "regiao": "Hoenn",  "range": (252, 386), "porta": 6003},
    4: {"nome": "Geração IV",   "regiao": "Sinnoh", "range": (387, 493), "porta": 6004},
    5: {"nome": "Geração V",    "regiao": "Unova",  "range": (494, 649), "porta": 6005},
    6: {"nome": "Geração VI",   "regiao": "Kalos",  "range": (650, 721), "porta": 6006},
    7: {"nome": "Geração VII",  "regiao": "Alola",  "range": (722, 809), "porta": 6007},
    8: {"nome": "Geração VIII", "regiao": "Galar",  "range": (810, 905), "porta": 6008},
    9: {"nome": "Geração IX",   "regiao": "Paldea", "range": (906,1025), "porta": 6009},
}

API_BASE_URL = "https://pokeapi.co/api/v2/pokemon/"


def detectar_gen(p_id: int) -> int:
    for gen, info in GERACOES.items():
        lo, hi = info["range"]
        if lo <= p_id <= hi:
            return gen
    return 9


def porta_da_gen(gen: int) -> int:
    return GERACOES[gen]["porta"]


def nome_da_gen(gen: int) -> str:
    return GERACOES[gen]["nome"]


def _buscar_pokemon(codigo: int, is_shiny: bool) -> dict | None:
    url = f"{API_BASE_URL}{codigo}"
    req = urllib.request.Request(url, headers={"User-Agent": "ShinyDetector/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            sprite = data["sprites"]["front_shiny" if is_shiny else "front_default"]
            return {"nome": data["name"], "link_img": sprite or ""}
    except Exception as e:
        print(f"[sensor] Erro na API para #{codigo}: {e}")
        return None


def rodar_sensor(gen: int):
    """Loop principal do sensor: gera pokémons da geração e envia UDP ao servidor."""
    info = GERACOES[gen]
    lo, hi = info["range"]
    sensor_id = f"sensor_gen{gen}"

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print(f"[{sensor_id}] Iniciado — {info['nome']} ({info['regiao']}) — range #{lo}-#{hi}")
    print(f"[{sensor_id}] Enviando para {HOST}:{UDP_SERVER_PORT}")

    while True:
        codigo = random.randint(lo, hi)
        is_shiny = random.random() < 0.000244140625

        pkm = _buscar_pokemon(codigo, is_shiny)
        if pkm is None:
            time.sleep(1)
            continue

        pacote = {
            "id":        codigo,
            "nome":      pkm["nome"],
            "shiny":     is_shiny,
            "link_img":  pkm["link_img"],
            "sensor_id": sensor_id,
            "gen":       gen,
        }

        sock.sendto(json.dumps(pacote).encode(), (HOST, UDP_SERVER_PORT))
        status = "*** SHINY! ***" if is_shiny else "normal"
        print(f"[{sensor_id}] #{codigo} {pkm['nome']} — {status}")

        time.sleep(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python -m sensores <geracao>  (1-9)")
        sys.exit(1)
    try:
        gen_num = int(sys.argv[1])
        assert 1 <= gen_num <= 9
    except (ValueError, AssertionError):
        print("Geração inválida. Use um número de 1 a 9.")
        sys.exit(1)

    rodar_sensor(gen_num)
