import socket
import random
import time
import json
import urllib.request

# Configuração
API_BASE_URL = "https://pokeapi.co/api/v2/pokemon/"
SERVER_IP = "127.0.0.1"
PORT = 5000
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

def buscar_nome_pokemon(codigo, is_shiny):
    url = f"{API_BASE_URL}{codigo}"

    req = urllib.request.Request(
        url, 
        headers={'User-Agent': 'Filipe'}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=3) as response:
            res_data = json.loads(response.read().decode())
            if is_shiny:           
                return [res_data["name"], res_data["sprites"]["front_shiny"]]
            else:
                return [res_data["name"], res_data["sprites"]["front_default"]]
    except Exception as e:
        print(f"Erro na API: {e}")
        return "Desconhecido"

print("Gerador iniciado...")

while True:
    codigo = random.randint(1, 1010)
    is_shiny = random.random() < 0.01 
    pokemon = buscar_nome_pokemon(codigo, is_shiny)
    pacote = {
        "id": codigo,
        "nome": pokemon[0],
        "shiny": is_shiny,
        "link_img": pokemon[1]
    }
    
    s.sendto(json.dumps(pacote).encode(), (SERVER_IP, PORT))
    print(f"Enviado: {pokemon[0]} | Shiny: {is_shiny}")
    time.sleep(0.1)