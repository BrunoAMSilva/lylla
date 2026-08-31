# Instruções

## Como ligar à Lylla

1. Abrir o terminal
2. `ssh lara@lylla.local`
3. Colocar a palavra-passe

## Testar a câmara

1. Listar câmaras: `rpicam-hello --list-cameras`
2. Tirar uma foto: `rpicam-jpeg -o teste.jpg`
3. Verificar a foto: `eog teste.jpg`

## Librarias externas

Para instalar as librarias externas, precisamos de criar um ambiente virtual para isolar as dependências.

### Criar ambiente virtual

1. `python3 -m venv --system-site-packages .venv`
2. `source .venv/bin/activate`

### Instalar OpenWakeWord

1. `pip install --no-deps "openwakeword>=0.6.0"`

### Instalar requisitos da câmara

1. `
