"""
main_gui.py
───────────
Interface gráfica que conecta ao servidor Docker via TCP.
Os containers (servidor, sensores, atuador) rodam independentemente.

Lê configuração do .env na mesma pasta:
  SERVER_HOST   — IP do servidor         (padrão: localhost)
  TCP_PORT      — porta TCP              (padrão: 6000)
  COMPOSE_FILE  — arquivo compose a usar (padrão: Docker-compose.yml)
  COMPOSE_DIR   — pasta do projeto       (padrão: pasta deste script)
"""

import os
import re
import socket
import subprocess
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

SERVER_HOST  = os.environ.get("SERVER_HOST",  "localhost")
TCP_PORT     = int(os.environ.get("TCP_PORT", 6000))
COMPOSE_DIR  = os.environ.get("COMPOSE_DIR",  str(Path(__file__).parent))
COMPOSE_FILE = os.environ.get("COMPOSE_FILE", "Docker-compose.yml")

from mvc.model      import ShinyModel
from mvc.view       import AtuadorView
from mvc.controller import AtuadorController


# ── docker helpers ────────────────────────────────────────────────────────────

def _docker_compose(*args) -> tuple[bool, str]:
    """Roda docker compose -f <COMPOSE_FILE> <args>. Retorna (sucesso, saída)."""
    try:
        result = subprocess.run(
            ["docker", "compose", "-f", COMPOSE_FILE] + list(args),
            cwd=COMPOSE_DIR,
            capture_output=True, text=True, timeout=15,
        )
        return result.returncode == 0, (result.stdout + result.stderr).strip()
    except Exception as e:
        return False, str(e)


def _sensores_ativos() -> set[int]:
    """Consulta o Docker e retorna as gerações com container rodando (running)."""
    ok, out = _docker_compose("ps", "--format", "{{.Name}} {{.State}}")
    if not ok:
        return set()
    gens = set()
    for line in out.splitlines():
        # linha esperada: "shiny_sensor_gen3 running"
        m = re.search(r"sensor_gen(\d+)\s+running", line)
        if m:
            gens.add(int(m.group(1)))
    return gens


def _ativar_sensor(gen: int, view: AtuadorView):
    def _run():
        view.after(0, lambda: view.log(f"[docker] iniciando sensor_gen{gen}..."))
        ok, out = _docker_compose("start", f"sensor_gen{gen}")
        if ok:
            view.after(0, lambda: view.log(f"✅ sensor_gen{gen} iniciado"))
            _sincronizar_sensores(view)
        else:
            view.after(0, lambda: view.log(f"❌ sensor_gen{gen}: {out}"))
    threading.Thread(target=_run, daemon=True).start()


def _desativar_sensor(gen: int, view: AtuadorView):
    def _run():
        view.after(0, lambda: view.log(f"[docker] parando sensor_gen{gen}..."))
        ok, out = _docker_compose("stop", f"sensor_gen{gen}")
        if ok:
            view.after(0, lambda: view.log(f"⏹ sensor_gen{gen} parado"))
            _sincronizar_sensores(view)
        else:
            view.after(0, lambda: view.log(f"❌ sensor_gen{gen}: {out}"))
    threading.Thread(target=_run, daemon=True).start()


def _sincronizar_sensores(view: AtuadorView):
    """Consulta o Docker e atualiza a view com os sensores atualmente ativos."""
    gens = _sensores_ativos()
    # atualizar_lista_sensores espera dict {gen: qualquer}, usa só as chaves
    view.after(0, lambda g=gens: view.atualizar_lista_sensores({gen: True for gen in g}))


# ── TCP ───────────────────────────────────────────────────────────────────────

def _loop_tcp(controller: AtuadorController):
    """Conecta ao servidor TCP e repassa eventos ao controller."""
    while controller.ativo:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect((SERVER_HOST, TCP_PORT))
            controller.view.after(0, lambda: controller.view.set_status_online("Docker"))
            controller.view.after(0, lambda: controller.view.log(f"✅ Conectado a {SERVER_HOST}:{TCP_PORT}"))

            buffer = ""
            while controller.ativo:
                chunk = sock.recv(4096).decode(errors="replace")
                if not chunk:
                    break
                buffer += chunk
                while "\n" in buffer:
                    linha, buffer = buffer.split("\n", 1)
                    linha = linha.strip()
                    if linha:
                        controller.processar(linha)

        except Exception as e:
            controller.view.after(0, lambda err=e: controller.view.log(f"❌ TCP: {err}"))
        finally:
            try:
                sock.close()
            except Exception:
                pass

        if controller.ativo:
            controller.view.after(0, controller.view.set_status_offline)
            time.sleep(2)

    controller.view.after(0, controller.view.set_status_offline)


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    model      = ShinyModel()
    view       = AtuadorView()
    controller = AtuadorController(model, view)

    # liga botões de sensor ao docker
    view.cb_ativar_sensor    = lambda gen: _ativar_sensor(gen, view)
    view.cb_desativar_sensor = lambda gen: _desativar_sensor(gen, view)

    controller.iniciar()

    # carrega estado inicial dos sensores em background
    threading.Thread(target=lambda: _sincronizar_sensores(view), daemon=True).start()

    # inicia loop TCP
    threading.Thread(target=_loop_tcp, args=(controller,), daemon=True).start()

    view.mainloop()
