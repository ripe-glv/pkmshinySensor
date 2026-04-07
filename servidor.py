"""
servidor.py
───────────
Backend central do sistema Shiny Detector.

Escuta UMA porta UDP (todos os sensores enviam para cá).
Aceita múltiplos atuadores via TCP.
Propaga o campo `gen` no protocolo para que o atuador diferencie sensores.

NOVO: Suporte ao Gerenciador de Sensores.
  - Clientes que se identificam com "GERENCIADOR_SENSORES" são registrados
    numa lista separada.
  - Mensagens CMD|... enviadas pela GUI (atuadores) são encaminhadas ao
    gerenciador, e as respostas (STATUS_SENSORES|...) são repassadas de
    volta para todos os atuadores.

Em Docker: usa variáveis de ambiente BIND_HOST, UDP_PORT, TCP_PORT.
"""

import socket
import json
import threading
import os

UDP_PORT = int(os.environ.get("UDP_PORT", 5000))
TCP_PORT = int(os.environ.get("TCP_PORT", 6000))
HOST     = os.environ.get("BIND_HOST", "0.0.0.0")

lock         = threading.Lock()
atuadores:    list[socket.socket] = []
gerenciadores: list[socket.socket] = []


# ── helpers de envio ──────────────────────────────────────────────────────────

def _enviar_lista(lista: list[socket.socket], msg: str) -> list[socket.socket]:
    """Envia msg para cada socket da lista. Retorna sockets mortos."""
    dados  = msg.encode()
    mortos = []
    for conn in lista:
        try:
            conn.sendall(dados)
        except Exception:
            mortos.append(conn)
    return mortos


def notificar_atuadores(msg: str):
    with lock:
        mortos = _enviar_lista(atuadores, msg)
        for c in mortos:
            atuadores.remove(c)


def _encaminhar_para_gerenciador(msg: str):
    """Encaminha um CMD ao gerenciador (apenas envia, sem travar)."""
    with lock:
        germs = list(gerenciadores)

    if not germs:
        notificar_atuadores("ERRO|SEM_GERENCIADOR\n")
        return

    for conn in germs:
        try:
            conn.sendall(msg.encode())
        except Exception as e:
            print(f"[Servidor] Erro ao enviar para gerenciador: {e}")
            with lock:
                if conn in gerenciadores:
                    gerenciadores.remove(conn)

# ── registro de clientes TCP ───────────────────────────────────────────────────

def _tratar_cliente(conn: socket.socket, addr):
    """
    Lida com um cliente TCP recém-conectado.
    - Se mandar "GERENCIADOR_SENSORES" → registra como gerenciador
    - Caso contrário → registra como atuador normal e escuta CMDs
    """
    try:
        # Tenta ler identificação (até 1 segundo)
        conn.settimeout(1.0)
        ident = b""
        try:
            ident = conn.recv(256)
        except socket.timeout:
            pass
        conn.settimeout(None)

        ident_str = ident.decode(errors="replace").strip()

        if ident_str == "GERENCIADOR_SENSORES":
            with lock:
                gerenciadores.append(conn)
            print(f"[Servidor] Gerenciador de sensores conectado: {addr}")
            
            # Aqui é o ÚNICO lugar que lê os dados do Gerenciador.
            # Tudo que ele responder (STATUS, OK, ERRO), repassamos para a GUI.
            conn.settimeout(None)
            buf = ""
            while True:
                try:
                    chunk = conn.recv(4096).decode(errors="replace")
                    if not chunk:
                        break
                    buf += chunk
                    while "\n" in buf:
                        linha, buf = buf.split("\n", 1)
                        linha = linha.strip()
                        if linha:
                            # Faz o broadcast direto para todos os Atuadores (GUI)
                            notificar_atuadores(linha + "\n")
                except Exception:
                    break

            with lock:
                if conn in gerenciadores:
                    gerenciadores.remove(conn)
            print(f"[Servidor] Gerenciador desconectado: {addr}")
            return

        # Atuador normal
        with lock:
            atuadores.append(conn)
        print(f"[Servidor] Atuador conectado: {addr} | Total: {len(atuadores)}")

        try:
            conn.sendall(b"Aguardando Shinies...\n")
            # Se havia identificação que não é GERENCIADOR, pode ser uma msg normal
            if ident_str:
                _processar_msg_atuador(ident_str, conn)
        except Exception:
            pass

        # Escuta mensagens do atuador (CMDs de controle de sensores)
        buf = ""
        while True:
            try:
                chunk = conn.recv(4096).decode(errors="replace")
                if not chunk:
                    break
                buf += chunk
                while "\n" in buf:
                    linha, buf = buf.split("\n", 1)
                    linha = linha.strip()
                    if linha:
                        _processar_msg_atuador(linha, conn)
            except Exception:
                break

    except Exception as e:
        print(f"[Servidor] Erro cliente {addr}: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass
        with lock:
            if conn in atuadores:
                atuadores.remove(conn)
        print(f"[Servidor] Cliente desconectado: {addr}")


def _processar_msg_atuador(linha: str, _conn: socket.socket):
    """Processa mensagem enviada por um atuador ao servidor."""
    if linha.startswith("CMD|"):
        print(f"[Servidor] CMD recebido → encaminhando ao gerenciador: {linha}")
        threading.Thread(
            target=_encaminhar_para_gerenciador,
            args=(linha + "\n",),
            daemon=True,
        ).start()


def registrar_clientes():
    sock_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock_tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock_tcp.bind((HOST, TCP_PORT))
    sock_tcp.listen(10)
    print(f"[Servidor] Aguardando clientes na porta TCP:{TCP_PORT}...")

    while True:
        conn, addr = sock_tcp.accept()
        threading.Thread(target=_tratar_cliente, args=(conn, addr), daemon=True).start()


# ── escuta de sensores UDP ────────────────────────────────────────────────────

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

        notificar_atuadores(
            f"APARECER|{nome}|{p_id}|{img}|{sensor_id}|{gen}|{';'.join(tipos)}\n"
        )

        if is_shiny:
            print(f"[{sensor_id}] ✨ SHINY: {nome}!")
            notificar_atuadores(
                f"SHINY|{nome}|{p_id}|{img}|{sensor_id}|{gen}|{';'.join(tipos)}\n"
            )
        else:
            print(f"[{sensor_id}] {nome}")


# ── main ──────────────────────────────────────────────────────────────────────

def iniciar_backend():
    threading.Thread(target=registrar_clientes, daemon=True).start()
    threading.Thread(target=escutar_sensores,   daemon=True).start()
    print(f"[Servidor] Rodando | UDP:{UDP_PORT} | TCP:{TCP_PORT} | HOST:{HOST}")
    threading.Event().wait()


if __name__ == "__main__":
    iniciar_backend()