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

# ── docker helpers ─────────────────────────────────────────────────────────────

def _docker(*args) -> tuple[bool, str]:
    """Executa docker puro (sem compose). Retorna (ok, saída)."""
    try:
        # Removemos o "compose" da lista. Vamos direto no motor do Docker!
        result = subprocess.run(
            ["docker"] + list(args),
            capture_output=True, text=True, timeout=20
        )
        return result.returncode == 0, (result.stdout + result.stderr).strip()
    except Exception as e:
        return False, str(e)


def _sensores_ativos() -> list[int]:
    """Retorna lista de gerações com container running."""
    # Busca apenas os containers que têm "shiny_sensor_gen" no nome
    ok, out = _docker("ps", "-a", "--format", "{{.Names}}|{{.State}}", "--filter", "name=shiny_sensor_gen")
    if not ok:
        return []
    
    gens = []
    for line in out.splitlines():
        # A linha virá no formato: shiny_sensor_gen1|running
        linha_lower = line.lower()
        if "running" in linha_lower or "up" in linha_lower:
            m = re.search(r"shiny_sensor_gen(\d+)", linha_lower)
            if m:
                gens.append(int(m.group(1)))
    return sorted(gens)


def _ativar(gen: int) -> str:
    # Chama o container diretamente pelo nome que definimos no YAML
    ok, out = _docker("start", f"shiny_sensor_gen{gen}")
    if ok:
        return f"OK|ATIVADO|{gen}"
    return f"ERRO|ATIVAR|{gen}|{out[:200]}"


def _desativar(gen: int) -> str:
    # Para o container diretamente pelo nome
    ok, out = _docker("stop", f"shiny_sensor_gen{gen}")
    if ok:
        return f"OK|DESATIVADO|{gen}"
    return f"ERRO|DESATIVAR|{gen}|{out[:200]}"


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