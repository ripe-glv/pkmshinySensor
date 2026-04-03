"""
atuador_headless.py
────────────────────
Versão headless do atuador para rodar em Docker (sem GUI Tkinter).
Conecta ao servidor TCP e imprime eventos no stdout.

Variáveis de ambiente:
  SERVER_HOST  — hostname/IP do servidor       (padrão: servidor)
  TCP_PORT     — porta TCP do servidor         (padrão: 6000)
"""

import socket
import time
import os

SERVER_HOST = os.environ.get("SERVER_HOST", "servidor")
TCP_PORT    = int(os.environ.get("TCP_PORT", 6000))


def loop():
    print(f"[Atuador] Conectando ao servidor {SERVER_HOST}:{TCP_PORT}...")
    while True:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((SERVER_HOST, TCP_PORT))
            print(f"[Atuador] ✅ Conectado!")

            buffer = ""
            while True:
                chunk = sock.recv(4096).decode(errors="replace")
                if not chunk:
                    break
                buffer += chunk
                while "\n" in buffer:
                    linha, buffer = buffer.split("\n", 1)
                    linha = linha.strip()
                    if not linha:
                        continue
                    partes = linha.split("|")
                    if len(partes) < 5:
                        continue
                    tipo, nome, p_id, url, sensor_id = partes[:5]
                    gen = partes[5] if len(partes) > 5 else "?"
                    if tipo == "SHINY":
                        print(f"[Atuador] ✨ SHINY capturado! {nome} (#{p_id}) — Gen {gen} — sensor: {sensor_id}")
                    elif tipo == "APARECER":
                        print(f"[Atuador] 👀 {nome} (#{p_id}) — Gen {gen} — sensor: {sensor_id}")

        except Exception as e:
            print(f"[Atuador] ❌ {e} — reconectando em 3s...")
            time.sleep(3)
        finally:
            try:
                sock.close()
            except Exception:
                pass


if __name__ == "__main__":
    loop()
