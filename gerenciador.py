"""
gerenciador_sensores.py
───────────────────────
Atuador gerenciador de sensores — roda em Docker.
"""

import os
import re
import socket
import threading
import time

# IMPORTANTE: Requer 'docker' no requirements.txt
try:
    import docker
except ImportError:
    print("[Gerenciador] ❌ Biblioteca 'docker' não instalada! Adicione ao requirements.txt e faça o build novamente.")
    docker = None

SERVER_HOST     = os.environ.get("SERVER_HOST",     "servidor")
TCP_PORT        = int(os.environ.get("TCP_PORT",    6000))
CTRL_PORT       = int(os.environ.get("CTRL_PORT",   7000))

_lock_sensores = threading.Lock()

# ── Conexão Direta com a API do Docker do Linux (via Socket) ───────────────────

def obter_cliente_docker():
    if not docker: return None
    try:
        # Força o uso do socket do Linux mapeado no docker-compose
        return docker.DockerClient(base_url='unix://var/run/docker.sock')
    except Exception as e:
        print(f"[Gerenciador] ❌ ERRO de Socket: Verifique permissões ou mapeamento de volume: {e}")
        return None

docker_client = obter_cliente_docker()

# ── docker helpers (Via API Nativa) ────────────────────────────────────────────

def _encontrar_container_gen(gen: int):
    """Busca o container de uma geração específica independentemente do prefixo."""
    if not docker_client: return None
    try:
        containers = docker_client.containers.list(all=True)
        for c in containers:
            # Procura por "sensor_gen1", "shiny_sensor_gen1", "pkmshinysensor-sensor_gen1-1", etc.
            if f"sensor_gen{gen}" in c.name:
                return c
    except Exception as e:
        print(f"Erro ao buscar container: {e}")
    return None

def _sensores_ativos() -> list[int]:
    """Retorna lista de gerações com container rodando."""
    if not docker_client: return []
    gens = set()
    try:
        containers = docker_client.containers.list(all=True)
        for c in containers:
            if "sensor_gen" in c.name and c.status in ["running", "up"]:
                m = re.search(r"sensor_gen(\d+)", c.name)
                if m:
                    gens.add(int(m.group(1)))
    except Exception as e:
        print(f"Erro ao listar status: {e}")
    return sorted(list(gens))

def _ativar(gen: int) -> str:
    if not docker_client: return "ERRO|SEM_DOCKER_API"
    container = _encontrar_container_gen(gen)
    
    if not container:
        return f"ERRO|NAO_ENCONTRADO|O container da gen {gen} não existe no PC."
        
    try:
        container.start()
        return f"OK|ATIVADO|{gen}"
    except Exception as e:
        return f"ERRO|ATIVAR|{gen}|{str(e)[:100]}"

def _desativar(gen: int) -> str:
    if not docker_client: return "ERRO|SEM_DOCKER_API"
    container = _encontrar_container_gen(gen)
    
    if not container:
        return f"ERRO|NAO_ENCONTRADO|O container da gen {gen} não existe no PC."
        
    try:
        container.stop()
        return f"OK|DESATIVADO|{gen}"
    except Exception as e:
        return f"ERRO|DESATIVAR|{gen}|{str(e)[:100]}"

def _status_msg() -> str:
    gens = _sensores_ativos()
    return "STATUS_SENSORES|" + ",".join(str(g) for g in gens)

# ── servidor de controle TCP (escuta conexões da GUI / servidor) ───────────────
# ... (O RESTANTE DO CÓDIGO CONTINUA EXATAMENTE IGUAL) ...

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
    if not partes: return None
    tipo = partes[0].upper()

    if tipo == "CMD":
        if len(partes) < 2: return "ERRO|CMD_INVALIDO"
        acao = partes[1].upper()

        if acao == "STATUS":
            return _status_msg()

        if acao in ("ATIVAR", "DESATIVAR") and len(partes) >= 3:
            try:
                gen = int(partes[2])
            except ValueError:
                return f"ERRO|GEN_INVALIDO|{partes[2]}"
            with _lock_sensores:
                if acao == "ATIVAR": resp = _ativar(gen)
                else: resp = _desativar(gen)
            return resp + "\n" + _status_msg()

    return f"ERRO|DESCONHECIDO|{linha[:100]}"

def loop_controle():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", CTRL_PORT))
    srv.listen(10)
    print(f"[Gerenciador] Escutando comandos em TCP:{CTRL_PORT}")
    while True:
        conn, addr = srv.accept()
        threading.Thread(target=_tratar_conexao, args=(conn, addr), daemon=True).start()

def loop_servidor():
    print(f"[Gerenciador] Conectando ao servidor {SERVER_HOST}:{TCP_PORT}...")
    while True:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((SERVER_HOST, TCP_PORT))
            print("[Gerenciador] ✅ Conectado ao servidor principal")
            sock.sendall(b"GERENCIADOR_SENSORES\n")
            buf = ""
            while True:
                chunk = sock.recv(4096).decode(errors="replace")
                if not chunk: break
                buf += chunk
                while "\n" in buf:
                    linha, buf = buf.split("\n", 1)
                    linha = linha.strip()
                    if not linha: continue
                    resposta = _processar_cmd(linha)
                    if resposta:
                        try: sock.sendall((resposta + "\n").encode())
                        except Exception: break
        except Exception as e:
            print(f"[Gerenciador] Desconectado: {e}. Reconectando em 5s...")
        finally:
            try: sock.close()
            except Exception: pass
        time.sleep(5)

def loop_heartbeat(intervalo: int = 30):
    while True:
        time.sleep(intervalo)
        gens = _sensores_ativos()
        print(f"[Gerenciador] Sensores ativos: {gens if gens else 'nenhum'}")

if __name__ == "__main__":
    if docker_client: print("[Gerenciador] ✅ API do Docker carregada com sucesso!")
    print(f"[Gerenciador] Iniciando | CTRL_PORT:{CTRL_PORT} | SERVER:{SERVER_HOST}:{TCP_PORT}")
    threading.Thread(target=loop_controle, daemon=True).start()
    threading.Thread(target=loop_heartbeat, daemon=True).start()
    loop_servidor()