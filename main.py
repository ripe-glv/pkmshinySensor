"""
main.py
───────
Ponto de entrada do sistema completo.

Sobe em background:
  - servidor.py    (central)
  - atuador/atuador.py  (como modulo)

Abre a interface grafica (mvc/).
"""

import sys
import threading
import subprocess
import time


def _subir(nome: str, args: list):
    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        for linha in proc.stdout:
            print(f"[{nome}] {linha}", end="")
        proc.wait()
    except Exception as e:
        print(f"[main] Erro ao iniciar {nome}: {e}")


if __name__ == "__main__":
    # 1. servidor
    threading.Thread(
        target=_subir,
        args=("servidor", [sys.executable, "-X", "utf8", "servidor.py"]),
        daemon=True
    ).start()

    time.sleep(1.0)

    # 2. atuador (processo separado)
    threading.Thread(
        target=_subir,
        args=("atuador", [sys.executable, "-X", "utf8", "-m", "atuador.atuador"]),
        daemon=True
    ).start()

    time.sleep(0.5)

    # 3. interface
    from mvc.model      import ShinyModel
    from mvc.view       import AtuadorView
    from mvc.controller import AtuadorController

    model      = ShinyModel()
    view       = AtuadorView()
    controller = AtuadorController(model, view)
    controller.iniciar()
    view.mainloop()
