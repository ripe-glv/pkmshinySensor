"""
main_gui.py
───────────
Interface gráfica que conecta ao servidor Docker via TCP.
Os containers (servidor, sensores, atuador, gerenciador) rodam independentemente.

NOVO: Controle de sensores via TCP ao invés de docker compose local.
  - Botões ATIVAR/DESATIVAR na aba SENSORES enviam CMD|ATIVAR|<gen> e
    CMD|DESATIVAR|<gen> ao servidor, que encaminha ao gerenciador_sensores.
  - O servidor retorna STATUS_SENSORES|<gens> para atualizar a view.

Lê configuração do .env na mesma pasta:
  SERVER_HOST   — IP do servidor         (padrão: localhost)
  TCP_PORT      — porta TCP              (padrão: 6000)
"""

import os
import socket
import threading
import time
from pathlib import Path

# ── carrega .env ──────────────────────────────────────────────────────────────
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

SERVER_HOST = os.environ.get("SERVER_HOST", "localhost")
TCP_PORT    = int(os.environ.get("TCP_PORT", 6000))

from mvc.model      import ShinyModel
from mvc.view       import AtuadorView
from mvc.controller import AtuadorController


# ── estado global da conexão TCP ──────────────────────────────────────────────

_sock_tcp: socket.socket | None = None
_sock_lock = threading.Lock()


def _enviar_cmd(msg: str):
    """Envia uma mensagem ao servidor via TCP (thread-safe)."""
    with _sock_lock:
        if _sock_tcp is None:
            return
        try:
            _sock_tcp.sendall((msg if msg.endswith("\n") else msg + "\n").encode())
        except Exception as e:
            print(f"[GUI] Erro ao enviar CMD: {e}")


# ── callbacks de sensor (chamados pela view) ───────────────────────────────────

def _ativar_sensor(gen: int, view: AtuadorView):
    view.log(f"[ctrl] → CMD|ATIVAR|{gen}")
    _enviar_cmd(f"CMD|ATIVAR|{gen}")


def _desativar_sensor(gen: int, view: AtuadorView):
    view.log(f"[ctrl] → CMD|DESATIVAR|{gen}")
    _enviar_cmd(f"CMD|DESATIVAR|{gen}")


# ── loop TCP principal ────────────────────────────────────────────────────────

def _loop_tcp(controller: AtuadorController):
    """Conecta ao servidor TCP e repassa eventos ao controller."""
    global _sock_tcp

    while controller.ativo:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        try:
            sock.connect((SERVER_HOST, TCP_PORT))
            with _sock_lock:
                _sock_tcp = sock

            # Volta com a indicação visual de online
            controller.view.after(0, lambda: controller.view.set_status_online("Servidor"))
            controller.view.after(0, lambda: controller.view.log(f"✅ Conectado ao servidor {SERVER_HOST}:{TCP_PORT}"))

            sock.sendall(b"CMD|STATUS\n")

            buf = ""
            while controller.ativo:
                chunk = sock.recv(4096).decode(errors="replace")
                if not chunk:
                    break
                buf += chunk
                while "\n" in buf:
                    linha, buf = buf.split("\n", 1)
                    linha = linha.strip()
                    if linha:
                        # Chama DIRETO (em background), sem .after!
                        _processar_linha(linha, controller)

        except Exception as e:
            controller.view.after(0, lambda err=e: controller.view.log(f"⚠ Desconectado: {err}. Reconectando em 5s..."))
        finally:
            with _sock_lock:
                _sock_tcp = None
            try:
                sock.close()
            except Exception:
                pass

        if controller.ativo:
            # Volta com a indicação visual de offline
            controller.view.after(0, controller.view.set_status_offline)
            time.sleep(5)


def _processar_linha(linha: str, controller: AtuadorController):
    """Processa uma linha recebida do servidor."""
    partes = linha.split("|")
    tipo   = partes[0].upper() if partes else ""

    # ── eventos de Pokémon ──────────────────────────────────────────────────
    if tipo == "APARECER" and len(partes) >= 7:
        nome, p_id, img, sensor_id, gen, tipos_str = partes[1], partes[2], partes[3], partes[4], partes[5], partes[6]
        tipos = tipos_str.split(";") if tipos_str else []
        
        # 1. Update the live view directly (Immediate feedback)
        controller.view.after(0, controller.view.atualizar_monitor_sensor, 
                              sensor_id, int(gen), nome, p_id, img, False)
        
        # 2. Pass to controller for logic (if any)
        try:
            controller.processar("APARECER", nome, p_id, img, sensor_id, int(gen), tipos)
        except Exception as e:
             controller.view.after(0, controller.view.log, f"[err] APARECER falhou: {e}")

    elif tipo == "SHINY" and len(partes) >= 7:
        nome, p_id, img, sensor_id, gen, tipos_str = partes[1], partes[2], partes[3], partes[4], partes[5], partes[6]
        tipos = tipos_str.split(";") if tipos_str else []
        
        # 1. Update the live view directly (Immediate feedback with Shiny flag)
        controller.view.after(0, controller.view.atualizar_monitor_sensor, 
                              sensor_id, int(gen), nome, p_id, img, True)
        
        # 2. Pass to controller to save the Shiny (JSON) and update the grid
        try:
            controller.processar("SHINY", nome, p_id, img, sensor_id, int(gen), tipos)
        except Exception as e:
             controller.view.after(0, controller.view.log, f"[err] SHINY falhou: {e}")

    # ── respostas do gerenciador (Esses precisam de .after para a View) ──
    elif tipo == "STATUS_SENSORES":
        gens_str = partes[1] if len(partes) > 1 else ""
        gens = set()
        for g in gens_str.split(","):
            g = g.strip()
            if g.isdigit():
                gens.add(int(g))
                
        # Envia as atualizações para a thread principal com segurança
        controller.view.after(0, controller.view.atualizar_lista_sensores, {g: True for g in gens})
        controller.view.after(0, controller.view.log, f"[sensores] ativos: {sorted(gens) if gens else 'nenhum'}")

    elif tipo in ("OK",):
        controller.view.after(0, controller.view.log, f"[ctrl] ✅ {linha}")

    elif tipo == "ERRO":
        controller.view.after(0, controller.view.log, f"[ctrl] ❌ {linha}")

    # ── mensagem genérica de texto ────────────────────────────────────────────
    else:
        controller.view.after(0, controller.view.log, f"[srv] {linha}")


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    model      = ShinyModel()
    view       = AtuadorView()
    controller = AtuadorController(model, view)

    # Liga callbacks de sensor ao envio de CMD via TCP
    view.cb_ativar_sensor    = lambda gen: _ativar_sensor(gen, view)
    view.cb_desativar_sensor = lambda gen: _desativar_sensor(gen, view)

    controller.iniciar()

    threading.Thread(target=_loop_tcp, args=(controller,), daemon=True).start()

    view.mainloop()
    controller.ativo = False