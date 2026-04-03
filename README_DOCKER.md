# Shiny Detector — Configuração Docker

## Arquitetura

Cada instância roda em seu próprio container (computador virtual independente):

```
[sensor_gen1] ─┐
[sensor_gen2] ─┤
[sensor_gen3] ─┤  UDP:5000  ┌──────────┐  TCP:6000  ┌──────────┐
[sensor_gen4] ─┼──────────▶ │ servidor │──────────▶ │ atuador  │
[sensor_gen5] ─┤            └──────────┘            └──────────┘
[sensor_gen6] ─┤                                          │
[sensor_gen7] ─┤                                    (GUI roda no
[sensor_gen8] ─┤                                     host local)
[sensor_gen9] ─┘
```

## Arquivos alterados

| Arquivo | O que mudou |
|---|---|
| `servidor.py` | Usa `BIND_HOST=0.0.0.0` para aceitar conexões de outros containers |
| `atuador/sensores.py` | Usa `SERVER_HOST` para saber o endereço do servidor |
| `atuador/atuador.py` | Usa `SERVER_HOST` e repassa env vars para subprocessos |
| `atuador_headless.py` | **Novo** — atuador sem GUI para rodar em Docker |
| `Dockerfile.servidor` | **Novo** — imagem do servidor |
| `Dockerfile.sensor` | **Novo** — imagem de sensor (recebe GEN por env var) |
| `Dockerfile.atuador` | **Atualizado** — usa atuador_headless.py |
| `docker-compose.yml` | **Reescrito** — define todos os serviços com rede interna |

## Como usar

### Subir tudo (servidor + atuador + todos os 9 sensores)
```bash
docker compose up --build
```

### Subir só alguns sensores
```bash
docker compose up --build servidor atuador sensor_gen1 sensor_gen3
```

### Ver logs de um serviço específico
```bash
docker compose logs -f sensor_gen1
docker compose logs -f servidor
```

### Parar tudo
```bash
docker compose down
```

## Interface gráfica (GUI)

A interface Tkinter **não roda em Docker** pois precisa de tela.
Rode ela localmente no seu computador, apontando para o servidor:

```bash
# No seu terminal local:
SERVER_HOST=localhost TCP_PORT=6000 python main_gui.py
```

Ou se o servidor Docker estiver exposto na porta 6000, a GUI local se conecta normalmente.

## Variáveis de ambiente

| Variável | Serviço | Padrão | Descrição |
|---|---|---|---|
| `BIND_HOST` | servidor | `0.0.0.0` | Interface de escuta |
| `UDP_PORT` | servidor | `5000` | Porta UDP dos sensores |
| `TCP_PORT` | servidor/atuador | `6000` | Porta TCP do atuador |
| `SERVER_HOST` | sensor/atuador | `servidor` | Hostname do servidor na rede Docker |
| `UDP_SERVER_PORT` | sensor | `5000` | Porta UDP do servidor |
| `GEN` | sensor | `1` | Geração Pokémon (1-9) |
