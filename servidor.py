"""
servidor.py
───────────
Backend central do sistema Shiny Detector.

Escuta UMA porta UDP (todos os sensores enviam para cá).
Aceita múltiplos atuadores via TCP.
Propaga o campo `gen` no protocolo para que o atuador diferencie sensores.

Em Docker: usa variáveis de ambiente BIND_HOST, UDP_PORT, TCP_PORT.
"""

import socket
import json
import threading
import os

UDP_PORT = int(os.environ.get("UDP_PORT", 5000))
TCP_PORT = int(os.environ.get("TCP_PORT", 6000))
HOST     = os.environ.get("BIND_HOST", "0.0.0.0")   # 0.0.0.0 para aceitar conexões externas no Docker

lock      = threading.Lock()
atuadores: list[socket.socket] = []


def registrar_atuador():
    sock_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock_tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock_tcp.bind((HOST, TCP_PORT))
    sock_tcp.listen(10)
    print(f"[Servidor] Aguardando atuadores na porta TCP:{TCP_PORT}...")

    while True:
        conn, addr = sock_tcp.accept()
        with lock:
            atuadores.append(conn)
        print(f"[Servidor] Atuador conectado: {addr} | Total: {len(atuadores)}")
        try:
            conn.send(b"Aguardando Shinies...\n")
        except Exception:
            pass


def notificar_atuadores(msg: str):
    dados = msg.encode()
    mortos = []
    with lock:
        for conn in atuadores:
            try:
                conn.send(dados)
            except Exception:
                mortos.append(conn)
        for conn in mortos:
            atuadores.remove(conn)


def escutar_sensores():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((HOST, UDP_PORT))
    print(f"[Servidor] Escutando sensores na porta UDP:{UDP_PORT}")

    while True:
        data, addr = sock.recvfrom(4096)
        try:
            pkm = json.loads(data.decode())
        except Exception:
            continue

        sensor_id = pkm.get("sensor_id", f"{addr[0]}:{addr[1]}")
        nome      = pkm.get("nome",      "?")
        p_id      = pkm.get("id",        "?")
        img       = pkm.get("link_img",  "")
        is_shiny  = pkm.get("shiny",     False)
        gen       = pkm.get("gen",       1)
        tipos     = pkm.get("tipos",     [])

        notificar_atuadores(f"APARECER|{nome}|{p_id}|{img}|{sensor_id}|{gen}|{';'.join(tipos)}\n")

        if is_shiny:
            print(f"[{sensor_id}] ✨ SHINY: {nome}!")
            notificar_atuadores(f"SHINY|{nome}|{p_id}|{img}|{sensor_id}|{gen}|{';'.join(tipos)}\n")
        else:
            print(f"[{sensor_id}] {nome}")


def iniciar_backend():
    threading.Thread(target=registrar_atuador, daemon=True).start()
    threading.Thread(target=escutar_sensores,  daemon=True).start()
    print(f"[Servidor] Rodando | UDP:{UDP_PORT} | TCP:{TCP_PORT} | HOST:{HOST}")
    threading.Event().wait()


if __name__ == "__main__":
    iniciar_backend()
