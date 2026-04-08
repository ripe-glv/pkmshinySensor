# ✦ Shiny Detector — pkmshinySensor

Sistema distribuído de detecção de Pokémon shiny. Múltiplos **sensores** simulam encontros aleatórios com Pokémon (consultando a PokéAPI), reportam ao **servidor central**, que repassa eventos shiny ao **atuador**, responsável por persistir os dados e exibir uma interface gráfica com a coleção capturada.

---

## Arquitetura

```
[sensor_gen1] ─┐
[sensor_gen2] ─┤
[sensor_gen3] ─┤  UDP:5000  ┌────────────┐  TCP:6000  ┌──────────────┐
[sensor_gen4] ─┼──────────▶ │  servidor  │──────────▶ │   atuador    │
[sensor_gen5] ─┤            └────────────┘            └──────────────┘
[sensor_gen6] ─┤                  │                          │
[sensor_gen7] ─┤            TCP:7000                   shinies.json
[sensor_gen8] ─┤                  │
[sensor_gen9] ─┘            ┌────────────┐
                             │ gerenciador│  (controla start/stop dos sensores)
                             └────────────┘
                                                    GUI roda no host local
```

Cada componente roda em seu próprio container Docker:

| Serviço | Função |
|---|---|
| `servidor` | Hub central — recebe pacotes UDP dos sensores, distribui eventos SHINY via TCP aos atuadores e encaminha comandos ao gerenciador |
| `sensor_gen1`…`sensor_gen9` | Simulam encontros para cada geração Pokémon (Kanto a Paldea), enviam pacotes UDP ao servidor |
| `atuador` | Recebe eventos TCP, persiste shinies capturados em `shinies.json` (volume compartilhado com o host) |
| `gerenciador` | Controla o ciclo de vida dos containers de sensor via Docker Compose, respondendo a comandos da GUI |
| `main_gui.py` | Interface Tkinter rodando **no host** (não em Docker), lê o JSON do atuador e permite ativar/desativar sensores |

---

## Estrutura do projeto

```
pkmshinySensor/
├── servidor.py              # Backend central (UDP + TCP)
├── sensores.py              # Fonte única de dados das gerações (também é o sensor Docker)
├── atuador_headless.py      # Atuador sem GUI para rodar em container
├── gerenciador.py           # Gerenciador de sensores via Docker
├── main_gui.py              # Interface gráfica (roda no host)
├── mvc/
│   ├── model.py             # Lê shinies.json do volume
│   ├── view.py              # Janela Tkinter com cards dos shinies
│   └── controller.py        # Liga view ao model e ao servidor TCP
├── data/
│   └── shinies.json         # Persistência dos shinies (bind mount)
├── docker-compose.yml       # Compose principal (modo single/dual-PC)
├── docker-compose.lab.yml   # Compose para laboratório com 2 PCs físicos
├── Dockerfile.servidor
├── Dockerfile.atuador
├── Dockerfile.sensor
├── dockerfile.gerenciador
├── requirements.txt
├── .env.example
└── README_DOCKER.md
```

---

## Pré-requisitos

- **Docker** e **Docker Compose** (v2+)
- **Python 3.11+** (apenas para rodar a GUI localmente)
- Dependências da GUI: `pip install -r requirements.txt`

---

## Configuração

Copie o arquivo de exemplo e ajuste conforme o seu cenário:

```bash
cp .env.example .env
```

Variáveis disponíveis:

| Variável | Padrão | Descrição |
|---|---|---|
| `SERVER_HOST` | `localhost` | IP/hostname do servidor (alterar apenas em modo multi-PC) |
| `UDP_PORT` | `5000` | Porta UDP dos sensores → servidor |
| `TCP_PORT` | `6000` | Porta TCP do servidor → atuador/GUI |
| `CTRL_PORT` | `7000` | Porta TCP do gerenciador de sensores |
| `COMPOSE_PROJECT_NAME` | `pkmshinysensor` | Nome do projeto Compose |

---

## Como usar

### Modo local — tudo em um único PC

```bash
# Subir servidor + atuador + todos os 9 sensores
docker compose --profile pc_1 up --build

# Em outro terminal, rodar a GUI
python main_gui.py
```

### Modo multi-PC — dois computadores na mesma rede

**PC 1 (servidor/atuador):**
```bash
# Descobrir o IP do PC 1
ip addr show   # Linux/Mac
ipconfig       # Windows

# Editar .env: SERVER_HOST=<IP do PC 1>
docker compose --profile pc_1 up --build
python main_gui.py
```

**PC 2 (sensores/gerenciador):**
```bash
# Copiar o mesmo .env do PC 1 para este PC
docker compose --profile pc_2 up --build
```

### Modo laboratório (arquivo separado)

```bash
# PC servidor (roda servidor + atuador + sensores gen2-gen9)
docker compose -f docker-compose.lab.yml --profile servidor up --build

# PC remoto (roda sensor gen1 apontando para o PC servidor)
docker compose -f docker-compose.lab.yml --profile sensor up --build
python main_gui.py
```

### Comandos úteis

```bash
# Ver logs de um serviço específico
docker compose logs -f servidor
docker compose logs -f sensor_gen1

# Subir apenas alguns sensores
docker compose up --build servidor atuador sensor_gen1 sensor_gen3

# Parar tudo
docker compose down
```

---

## Interface gráfica (GUI)

A GUI Tkinter **não roda em Docker** pois requer acesso à tela. Ela se conecta ao servidor via TCP e lê o `shinies.json` pelo bind mount do volume.

Funcionalidades:
- Exibe cards com imagem, nome, geração e tipo de cada shiny capturado
- Aba **Sensores**: ativa/desativa sensores por geração em tempo real
- Botão **Libertar**: remove um shiny da coleção local
- Detalhes do Pokémon: tipos, altura, peso, stats e movimentos (via PokéAPI)
- Log em tempo real de eventos recebidos

---

## Protocolo de comunicação

**Sensores → Servidor (UDP):**
```json
{
  "id": 25,
  "nome": "pikachu",
  "shiny": true,
  "link_img": "https://raw.githubusercontent.com/PokeAPI/sprites/.../shiny/25.png",
  "sensor_id": "gen1"
}
```

**Servidor → Atuador/GUI (TCP, separado por `\n`):**
```
SHINY|pikachu|25|<url_imagem>|gen1|1
APARECER|charmander|4|<url_imagem>|gen1|1
CMD|ATIVAR|3          ← enviado pela GUI ao servidor
CMD|DESATIVAR|3
STATUS_SENSORES|1,3,5 ← resposta do gerenciador
```

---

## Gerações suportadas

| Gen | Região | IDs |
|---|---|---|
| I | Kanto | 1–151 |
| II | Johto | 152–251 |
| III | Hoenn | 252–386 |
| IV | Sinnoh | 387–493 |
| V | Unova | 494–649 |
| VI | Kalos | 650–721 |
| VII | Alola | 722–809 |
| VIII | Galar | 810–905 |
| IX | Paldea | 906–1025 |

---

## Tecnologias

- **Python 3.11** — toda a lógica de negócio
- **Tkinter** — interface gráfica (GUI no host)
- **Docker / Docker Compose** — orquestração dos serviços
- **Sockets UDP/TCP** — comunicação entre componentes
- **PokéAPI** (`pokeapi.co`) — dados e sprites dos Pokémon
- **JSON** — persistência simples dos shinies capturados

---

## Notas

- A taxa de shiny é de **1%** por encontro (simulada no sensor).
- O atuador ignora duplicatas: se um shiny com o mesmo ID já estiver no JSON, ele não é registrado novamente.
- A GUI lê o JSON diretamente do bind mount — não precisa de conexão com o atuador para exibir o histórico.
- O gerenciador precisa de acesso ao socket do Docker (`/var/run/docker.sock`) para controlar os containers de sensor.
