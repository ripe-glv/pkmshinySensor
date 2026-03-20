import socket
import json
import threading

UDP_PORT = 5000 
TCP_PORT = 6000
HOST = '127.0.0.1'

def tratar_atuador(conn, addr):
    print(f" Atuador conectado em: {addr}")
    conn.send(b"Aguardando Shinies...\n")

    return conn

def iniciar_backend():

    sock_gerador = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock_gerador.bind((HOST, UDP_PORT))

    sock_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock_tcp.bind((HOST, TCP_PORT))
    sock_tcp.listen(1)
    
    print(f"Backend ouvindo Gerador (UDP:{UDP_PORT}) e Atuador (TCP:{TCP_PORT})...")

    conn_atuador, addr_atuador = sock_tcp.accept()
    
    while True:
        # Recebe dados do Gerador
        data, addr = sock_gerador.recvfrom(1024)
        pokemon = json.loads(data.decode())

        if pokemon['shiny']:
            print("--- SHINY DETECTADO! ---")
            msg_captura = f"{pokemon['nome']}|{pokemon['id']}|{pokemon['link_img']}\n"
            try:
                conn_atuador.send(msg_captura.encode())
            except Exception as e:
                print(e)
                print("Erro ao falar com atuador. Reconectando...")
                conn_atuador, addr_atuador = sock_tcp.accept()

if __name__ == "__main__":
    iniciar_backend()