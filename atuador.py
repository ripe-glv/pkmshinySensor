import socket
import json
import os

SERVER_IP = "127.0.0.1"
PORT = 6000
ARQUIVO = "shinies.json"

def salvar(dados):
    lista = []
    if os.path.exists(ARQUIVO):
        with open(ARQUIVO, "r") as f:
            try: lista = json.load(f)
            except: lista = []
    lista.append(dados)
    with open(ARQUIVO, "w") as f:
        json.dump(lista, f, indent=4)

def iniciar_atuador():
    cliente = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        cliente.connect((SERVER_IP, PORT))
        print("Atuador pronto e conectado ao Backend.")
        
        while True:
            try:
                msg = cliente.recv(1024).decode()
             
                partes = msg.strip().split("|")
                if len(partes) == 3:
                    nome, p_id, img = partes
                    print(f"Capturado: {nome}! Salvando link: {img}")
                    salvar({"nome": nome, "id": p_id, "imagem": img})
            except ConnectionResetError:
                print("Erro 10054: Conexão perdida com o Backend.")
                break
    except Exception as e:
        print(f"Erro ao conectar: {e}")
    finally:
        cliente.close()

if __name__ == "__main__":
    iniciar_atuador()