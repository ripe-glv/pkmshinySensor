import subprocess
import sys
import time
import os

def iniciar_projeto():
    print("Iniciando Sistema Pokémon...")
    
    python_exe = sys.executable

    backend = subprocess.Popen([python_exe, "backend.py"])
    time.sleep(2)

    atuador = subprocess.Popen([python_exe, "atuador.py"])

    gerador = subprocess.Popen([python_exe, "sensor.py"])

    print("Todos os módulos estão rodando.")

    atuador.wait()
    
    backend.terminate()
    gerador.terminate()

if __name__ == "__main__":
    iniciar_projeto()