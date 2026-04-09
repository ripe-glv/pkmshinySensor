"""
gerenciador_sensores.py
───────────────────────
Atuador gerenciador de sensores — roda em Docker.

Conecta-se ao servidor via TCP (igual ao atuador_headless.py),
mas em vez de capturar shinies, escuta comandos de controle de sensores.

Protocolo de comandos recebidos do servidor (enviados pela GUI):
  CMD|ATIVAR|<gen>         → inicia o container sensor_gen<gen>
  CMD|DESATIVAR|<gen>      → para o container sensor_gen<gen>
  CMD|STATUS               → responde com a lista de sensores ativos

Protocolo de resposta enviado de volta ao servidor (e repassado à GUI):
  STATUS_SENSORES|<gen1>,<gen2>,...   → gens atualmente running

Variáveis de ambiente:
  SERVER_HOST     — hostname do servidor  (padrão: servidor)
  TCP_PORT        — porta TCP             (padrão: 6000)
  CTRL_PORT       — porta TCP própria de controle (padrão: 7000)
  COMPOSE_PROJECT — nome do projeto compose (padrão: pkmshinysensor)
"""

import os
import re
import socket
import subprocess
import threading
import time

SERVER_HOST     = os.environ.get("SERVER_HOST",     "servidor")
TCP_PORT        = int(os.environ.get("TCP_PORT",    6000))
CTRL_PORT       = int(os.environ.get("CTRL_PORT",   7000))
COMPOSE_PROJECT = os.environ.get("COMPOSE_PROJECT", "pkmshinysensor")

_lock_sensores = threading.Lock()


# ── docker helpers ─────────────────────────────────────────────────────────────

def _docker(*args) -> tuple[bool, str]:
    """Executa docker compose <args>. Retorna (ok, saída)."""
    try:
        result = subprocess.run(
            ["docker", "compose"] + list(args),
            capture_output=True, text=True, timeout=20,
            env={**os.environ, "COMPOSE_PROJECT_NAME": COMPOSE_PROJECT},
        )
        return result.returncode == 0, (result.stdout + result.stderr).strip()
    except Exception as e:
        return False, str(e)


def _sensores_ativos() -> list[int]:
    """Retorna lista de gerações com container running.
    
    No Linux, o Docker Compose nomeia containers como:
      <projeto>-sensor_gen<N>-1   (ex: pkmshinysensor-sensor_gen3-1)
    No Windows/Mac pode ser apenas:
      sensor_gen<N>
    O regex abaixo cobre os dois casos.
    """
    ok, out = _docker("ps", "--format", "{{.Name}} {{.State}}")
    if not ok:
        return []
    gens = []
    for line in out.splitlines():
        # Cobre: "sensor_gen3 running" e "pkmshinysensor-sensor_gen3-1 running"
        m = re.search(r"sensor_gen(\d+)(?:-\d+)?\s+running", line)
        if m:
            gens.append(int(m.group(1)))
    return sorted(gens)


def _ativar(gen: int) -> str:
    # "docker compose start <serviço>" usa o nome do serviço, não do container
    ok, out = _docker("start", f"sensor_gen{gen}")
    if ok:
        return f"OK|ATIVADO|{gen}"
    # Fallback: tenta via docker diretamente pelo nome do container Linux
    ok2, out2 = _docker_container_cmd("start", gen)
    if ok2:
        return f"OK|ATIVADO|{gen}"
    return f"ERRO|ATIVAR|{gen}|{out[:200]}"


def _desativar(gen: int) -> str:
    ok, out = _docker("stop", f"sensor_gen{gen}")
    if ok:
        return f"OK|DESATIVADO|{gen}"
    # Fallback: tenta via docker diretamente pelo nome do container Linux
    ok2, out2 = _docker_container_cmd("stop", gen)
    if ok2:
        return f"OK|DESATIVADO|{gen}"
    return f"ERRO|DESATIVAR|{gen}|{out[:200]}"


def _docker_container_cmd(cmd: str, gen: int) -> tuple[bool, str]:
    """Fallback: chama 'docker <cmd> <container>' para cobrir nomes Linux."""
    # Tenta os dois padrões de nome possíveis
    nomes = [
        f"sensor_gen{gen}",
        f"{COMPOSE_PROJECT}-sensor_gen{gen}-1",
        f"{COMPOSE_PROJECT.lower()}-sensor_gen{gen}-1",
    ]
    for nome in nomes:
        try:
            result = subprocess.run(
                ["docker", cmd, nome],
                capture_output=True, text=True, timeout=20,
            )
            if result.returncode == 0:
                return True, result.stdout.strip()
        except Exception:
            pass
    return False, f"container sensor_gen{gen} não encontrado"


def _status_msg() -> str:
    gens = _sensores_ativos()
    return "STATUS_SENSORES|" + ",".join(str(g) for g in gens)


# ── servidor de controle TCP (escuta conexões da GUI / servidor) ───────────────

def _tratar_conexao(conn: socket.socket, addr):
    print(f"[Gerenciador] Conexão de controle: {addr}")
    try:
        conn.sendall((_status_msg() + "\n").encode())
        buf = ""
        while True:
            chunk = conn.recv(1024).decode(errors="replace")
            if not chunk:
                break
            buf += chunk
            while "\n" in buf:
                linha, buf = buf.split("\n", 1)
                linha = linha.strip()
                if not linha:
                    continue
                resposta = _processar_cmd(linha)
                if resposta:
                    conn.sendall((resposta + "\n").encode())
    except Exception as e:
        print(f"[Gerenciador] Erro conexão {addr}: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass
    print(f"[Gerenciador] Conexão encerrada: {addr}")


def _processar_cmd(linha: str) -> str | None:
    partes = linha.split("|")
    if not partes:
        return None

    tipo = partes[0].upper()

    if tipo == "CMD":
        if len(partes) < 2:
            return "ERRO|CMD_INVALIDO"
        acao = partes[1].upper()

        if acao == "STATUS":
            return _status_msg()

        if acao in ("ATIVAR", "DESATIVAR") and len(partes) >= 3:
            try:
                gen = int(partes[2])
            except ValueError:
                return f"ERRO|GEN_INVALIDO|{partes[2]}"
            with _lock_sensores:
                if acao == "ATIVAR":
                    resp = _ativar(gen)
                else:
                    resp = _desativar(gen)
            # Após qualquer mudança, envia status atualizado
            return resp + "\n" + _status_msg()

    return f"ERRO|DESCONHECIDO|{linha[:100]}"


def loop_controle():
    """Aceita conexões TCP diretas (da GUI ou do servidor ponte)."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", CTRL_PORT))
    srv.listen(10)
    print(f"[Gerenciador] Escutando comandos em TCP:{CTRL_PORT}")
    while True:
        conn, addr = srv.accept()
        threading.Thread(target=_tratar_conexao, args=(conn, addr), daemon=True).start()


# ── conexão ao servidor principal (para receber CMD encaminhados) ──────────────

def loop_servidor():
    """
    Conecta ao servidor TCP como se fosse um atuador normal.
    O servidor pode repassar mensagens CMD|... vindas da GUI.
    """
    print(f"[Gerenciador] Conectando ao servidor {SERVER_HOST}:{TCP_PORT}...")
    while True:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((SERVER_HOST, TCP_PORT))
            print("[Gerenciador] ✅ Conectado ao servidor principal")

            # Identifica-se como gerenciador
            sock.sendall(b"GERENCIADOR_SENSORES\n")

            buf = ""
            while True:
                chunk = sock.recv(4096).decode(errors="replace")
                if not chunk:
                    break
                buf += chunk
                while "\n" in buf:
                    linha, buf = buf.split("\n", 1)
                    linha = linha.strip()
                    if not linha:
                        continue
                    resposta = _processar_cmd(linha)
                    if resposta:
                        try:
                            sock.sendall((resposta + "\n").encode())
                        except Exception:
                            break
        except Exception as e:
            print(f"[Gerenciador] Desconectado do servidor: {e}. Reconectando em 5s...")
        finally:
            try:
                sock.close()
            except Exception:
                pass
        time.sleep(5)


# ── heartbeat — loga status periodicamente ────────────────────────────────────

def loop_heartbeat(intervalo: int = 30):
    while True:
        time.sleep(intervalo)
        gens = _sensores_ativos()
        print(f"[Gerenciador] Sensores ativos: {gens if gens else 'nenhum'}")


# ── main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"[Gerenciador] Iniciando | CTRL_PORT:{CTRL_PORT} | SERVER:{SERVER_HOST}:{TCP_PORT}")

    # Servidor de controle local (porta própria)
    threading.Thread(target=loop_controle, daemon=True).start()

    # Heartbeat de status
    threading.Thread(target=loop_heartbeat, daemon=True).start()

    # Conexão ao servidor principal (para receber CMDs encaminhados pela GUI)
    loop_servidor()   # bloqueia aqui; reconecta automaticamente