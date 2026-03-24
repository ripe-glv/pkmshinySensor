"""
atuador/atuador.py
──────────────────
Camada de rede do atuador.
Conecta-se via TCP ao servidor e despacha eventos para o Controller.

Correções:
- _relay_sensor_log fecha TCP quando o último sensor termina
- _fechar_tcp não chama on_status diretamente (evita double-call)
- Sem race condition no encerramento do último sensor
"""

import socket
import threading
import subprocess
import sys
import time
from typing import Callable

SERVER_IP = "127.0.0.1"
TCP_PORT  = 6000


class Atuador:
    def __init__(
        self,
        on_aparecer:      Callable[[str, str, str, int, str], None] | None = None,
        on_captura:       Callable[[str, str, str, int], None]       | None = None,
        on_log:           Callable[[str], None]                      | None = None,
        on_status:        Callable[[bool, str], None]                | None = None,
        on_sensor_update: Callable[[dict], None]                     | None = None,
    ):
        self._on_aparecer      = on_aparecer      or (lambda *a: None)
        self._on_captura       = on_captura       or (lambda *a: None)
        self._on_log           = on_log           or (lambda m: None)
        self._on_status        = on_status        or (lambda o, t: None)
        self._on_sensor_update = on_sensor_update or (lambda d: None)

        self._socket: socket.socket | None = None
        self._conectado = False

        self._sensores: dict[int, subprocess.Popen] = {}   # gen → Popen
        self._lock_sensores = threading.Lock()

        self._thread_tcp: threading.Thread | None = None

    # ── gerenciamento de sensores ─────────────────────────────────────────────

    def ativar_sensor(self, gen: int):
        with self._lock_sensores:
            if gen in self._sensores:
                self._on_log(f"[sensor] Geração {gen} já está ativa.")
                return

            proc = subprocess.Popen(
                [sys.executable, "-m", "atuador.sensores", str(gen)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            self._sensores[gen] = proc
            self._on_log(f"[sensor] Gen {gen} ativada (PID {proc.pid})")
            self._on_sensor_update(dict(self._sensores))

        threading.Thread(
            target=self._relay_sensor_log, args=(gen, proc), daemon=True
        ).start()

        self._garantir_tcp()

    def desativar_sensor(self, gen: int):
        with self._lock_sensores:
            proc = self._sensores.pop(gen, None)
            if proc is None:
                return
            try:
                proc.terminate()
            except Exception:
                pass
            self._on_log(f"[sensor] Gen {gen} desativada.")
            restantes = dict(self._sensores)

        self._on_sensor_update(restantes)

        if not restantes:
            self._fechar_tcp()

    def desativar_todos(self):
        with self._lock_sensores:
            gens = list(self._sensores.keys())
        for g in gens:
            self.desativar_sensor(g)

    def sensores_ativos(self) -> list[int]:
        with self._lock_sensores:
            return list(self._sensores.keys())

    def _relay_sensor_log(self, gen: int, proc: subprocess.Popen):
        """Repassa stdout do subprocesso sensor para o log e limpa ao terminar."""
        try:
            for linha in proc.stdout:
                self._on_log(linha.rstrip())
        except Exception:
            pass

        # processo terminou naturalmente — remove da lista
        with self._lock_sensores:
            if self._sensores.get(gen) is proc:
                self._sensores.pop(gen)
                restantes = dict(self._sensores)
            else:
                restantes = None   # já foi removido por desativar_sensor

        if restantes is not None:
            self._on_sensor_update(restantes)
            if not restantes:
                self._fechar_tcp()

    # ── TCP ───────────────────────────────────────────────────────────────────

    def _garantir_tcp(self):
        if self._conectado:
            return
        if self._thread_tcp and self._thread_tcp.is_alive():
            return
        self._thread_tcp = threading.Thread(target=self._loop_tcp, daemon=True)
        self._thread_tcp.start()

    def _fechar_tcp(self):
        """Encerra o socket TCP. on_status será chamado pelo _loop_tcp ao detectar o fechamento."""
        self._conectado = False
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None

    def _loop_tcp(self):
        while True:
            with self._lock_sensores:
                if not self._sensores:
                    break

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.connect((SERVER_IP, TCP_PORT))
                self._socket    = sock
                self._conectado = True
                self._on_status(True, "ONLINE")
                self._on_log("✅ Conectado ao servidor.")

                buffer = ""
                while True:
                    chunk = sock.recv(4096).decode(errors="replace")
                    if not chunk:
                        break
                    buffer += chunk
                    while "\n" in buffer:
                        linha, buffer = buffer.split("\n", 1)
                        linha = linha.strip()
                        if linha:
                            self._processar(linha)

            except Exception as e:
                self._on_log(f"❌ TCP: {e}")
            finally:
                self._conectado = False
                try:
                    sock.close()
                except Exception:
                    pass
                self._socket = None

            with self._lock_sensores:
                if not self._sensores:
                    break

            time.sleep(2)

        # sai do loop — notifica offline uma única vez
        self._on_status(False, "OFFLINE")

    # ── protocolo ────────────────────────────────────────────────────────────

    def _processar(self, linha: str):
        partes = linha.split("|")
        if len(partes) < 5:
            return

        tipo, nome, p_id, url, sensor_id = partes[:5]
        gen = int(partes[5]) if len(partes) > 5 else 1

        if tipo == "APARECER":
            self._on_aparecer(nome, p_id, url, gen, sensor_id)
        elif tipo == "SHINY":
            self._on_aparecer(nome, p_id, url, gen, sensor_id)
            self._on_captura(nome, p_id, url, gen)

    # ── compatibilidade ───────────────────────────────────────────────────────

    def conectar(self, gen: int):
        self.ativar_sensor(gen)

    def desconectar(self):
        self.desativar_todos()