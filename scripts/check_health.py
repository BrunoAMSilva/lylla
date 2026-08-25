#!/usr/bin/env python3
"""ESTÁ TUDO BEM? — verifica cada peça do robô, uma a uma.

    python scripts/check_health.py

Corre isto SEMPRE que alguma coisa parecer estranha, antes de mexer em código.
Responde à pergunta que interessa: é o hardware ou é o programa?
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from robot import config  # noqa: E402

OK, MAU, AVISO = "✅", "❌", "⚠️ "
_problemas: list[str] = []


def verificar(nome: str, funcao, dica: str = "") -> None:
    try:
        resultado = funcao()
    except Exception as erro:  # noqa: BLE001
        resultado = f"erro: {erro}"
    if resultado is True:
        print(f"  {OK} {nome}")
    elif resultado is False or resultado is None:
        print(f"  {MAU} {nome}")
        if dica:
            print(f"       → {dica}")
        _problemas.append(nome)
    else:
        print(f"  {OK} {nome}: {resultado}")


def _voz_do_mac_responde(url: str) -> str | bool:
    """Pergunta ao servidor_voz.py do Mac se está de pé."""
    import json
    from urllib.request import urlopen

    try:
        with urlopen(url.rsplit("/", 1)[0] + "/saude", timeout=3) as resposta:  # noqa: S310
            dados = json.load(resposta)
        return f"{dados.get('voz')} · {dados.get('em_cache')} frases em cache no Mac"
    except Exception:  # noqa: BLE001
        return False


def _comando(*args) -> bool:
    try:
        r = subprocess.run(args, capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:  # noqa: BLE001
        return False


def _placa_de_som(nome: str) -> str | bool:
    """A placa `nome` aparece no `aplay -l`?  O reSpeaker chama-se "Array":
        card 4: Array [reSpeaker XVF3800 4-Mic Array], device 0: USB Audio
    Devolve a linha dela, para se ver o número do card."""
    try:
        r = subprocess.run(["aplay", "-l"], capture_output=True, text=True, timeout=10)
    except Exception:  # noqa: BLE001
        return False
    for linha in r.stdout.splitlines():
        if f": {nome} [" in linha:
            return linha.strip()
    return False


def _resolve(host: str) -> str | bool:
    """O nome existe na rede? Devolve o IP, ou False.

    Tem um limite de tempo próprio porque o timeout do requests/urlopen NÃO
    cobre a resolução de nomes — um nome .local que não existe pode demorar
    vários segundos a falhar, e parece que o script encravou."""
    import socket
    import threading

    resultado: list[str] = []

    def _tentar() -> None:
        try:
            resultado.append(socket.gethostbyname(host))
        except OSError:
            pass

    t = threading.Thread(target=_tentar, daemon=True)
    t.start()
    t.join(5)
    return resultado[0] if resultado else False


def _placa_por_omissao(nome: str) -> bool:
    """O ALSA usa a placa `nome` por omissão? Sem isto o `aplay` do speak.py e o
    `sounddevice` do listen.py vão para a primeira placa — o HDMI — em silêncio."""
    for caminho in (Path("/etc/asound.conf"), Path.home() / ".asoundrc"):
        try:
            texto = caminho.read_text(encoding="utf-8")
        except OSError:
            continue
        if re.search(rf"^\s*defaults\.pcm\.card\s+{re.escape(nome)}\s*$", texto, re.M):
            return True
    return False


def main() -> int:
    nome = config.nome_do_robo()
    print(f"\n{'=' * 62}")
    print(f"  DIAGNÓSTICO · {nome.upper()}")
    print(f"{'=' * 62}")

    if config.a_simular():
        print(f"\n  {AVISO}MODO SIMULAÇÃO — não estamos num Raspberry Pi.")
        print("     Os testes de hardware vão ser saltados.\n")

    # ---------------------------------------------------- configuração
    print("\n📋 CONFIGURAÇÃO")
    verificar("config/robot.yaml", lambda: bool(config.carregar()),
              "Falta o ficheiro config/robot.yaml")
    verificar("config/personalidade.txt",
              lambda: (config.CONFIG_DIR / "personalidade.txt").exists(),
              "Falta o system prompt do robô")

    # ---------------------------------------------------- expressões
    print("\n👀 OLHOS")

    def _expressoes():
        from robot.expressions import EXPRESSOES, validar_todas
        validar_todas()
        return f"{len(EXPRESSOES)} expressões, todas válidas"

    verificar("expressões", _expressoes,
              "Alguma grelha não tem 8×8. A mensagem de erro diz qual.")

    if not config.a_simular():
        verificar("SPI ativo", lambda: Path("/dev/spidev0.0").exists(),
                  "sudo raspi-config → Interface Options → SPI")

    # ---------------------------------------------------- motores
    print("\n🛞 MOTORES")
    if config.a_simular():
        print(f"  {AVISO}saltado (simulação)")
    else:
        def _i2c():
            r = subprocess.run(["i2cdetect", "-y", "1"], capture_output=True, text=True, timeout=15)
            return "40" in r.stdout
        verificar("PCA9685 dos motores (0x40)", _i2c,
                  "i2cdetect -y 1 não mostra 0x40. Verifica os cabos e a alimentação.")

    # ---------------------------------------------------- braços
    print("\n🦾 BRAÇOS")

    def _gestos():
        from robot.gestures import GESTOS, POSES, validar_todos
        validar_todos()
        return f"{len(POSES)} poses e {len(GESTOS)} gestos, todos válidos"

    verificar("poses e gestos", _gestos,
              "Alguma pose usa uma junta que não existe. A mensagem diz qual.")
    if config.a_simular():
        print(f"  {AVISO}servos saltados (simulação)")
    else:
        def _servos():
            r = subprocess.run(["i2cdetect", "-y", "1"], capture_output=True, text=True, timeout=15)
            return "41" in r.stdout
        verificar("PCA9685 dos servos (0x41)", _servos,
                  "Soldaste o jumper A0 do segundo PCA9685?")

    # ---------------------------------------------------- bateria
    print("\n🔋 BATERIA")
    from robot.hardware import power
    if config.a_simular():
        print(f"  {AVISO}saltado (simulação)")
    else:
        def _bat():
            v, p = power.tensao(), power.percentagem()
            return f"{v:.2f} V ({p}%)" if v is not None else False
        verificar("ADS1115 (0x48)", _bat,
                  "Verifica o I2C e o divisor resistivo. python scripts/test_power.py --calibrar")

    # ---------------------------------------------------- sensores
    print("\n📏 SENSORES")
    if config.a_simular():
        print(f"  {AVISO}saltado (simulação)")
    else:
        from robot.hardware import sensors
        verificar("ultrassons", lambda: f"{sensors.distancia_cm():.0f} cm",
                  "Confirma que é o modelo HC-SR04P (3,3 V)")
        verificar("precipício", lambda: "sem queda" if not sensors.ha_precipicio() else "QUEDA DETETADA")

    # ---------------------------------------------------- câmara
    print("\n📷 CÂMARA")
    if config.a_simular():
        print(f"  {AVISO}saltado (simulação)")
    else:
        verificar("rpicam vê a câmara",
                  lambda: _comando("rpicam-hello", "--list-cameras", "-t", "1"),
                  "⚠️  FALTA O CABO ADAPTADOR CSI 22→15 PINOS? (ou está ao contrário)")
        verificar("picamera2 importa neste venv",
                  lambda: importlib.util.find_spec("picamera2") is not None,
                  "apt install python3-picamera2, e o venv tem de ser --system-site-packages (Apêndice B)")

    # ---------------------------------------------------- visão
    print("\n🧠 MODELOS DE VISÃO")
    from robot.perception import faces
    verificar("YuNet (detetar caras)", lambda: faces.MODELO_DETETOR.exists(),
              "python scripts/download_models.py")
    verificar("SFace (reconhecer)", lambda: faces.MODELO_RECONHECEDOR.exists(),
              "python scripts/download_models.py")

    def _conhecidos():
        pessoas = faces.pessoas_conhecidas()
        return ", ".join(pessoas) if pessoas else False

    verificar("pessoas registadas", _conhecidos,
              "Ainda ninguém. Corre: python scripts/enrol_face.py Lara")

    # ---------------------------------------------------- áudio
    print("\n🔊 SOM")
    from robot.voice import speak as _speak

    servidor = config.obter("voz.servidor")
    if servidor:
        verificar(f"serviço de voz no Mac ({config.obter('voz.voz_mac', 'Joana')})",
                  lambda: _voz_do_mac_responde(servidor),
                  "No Mac:  python scripts/servidor_voz.py")
        # Isto é o que permite ao robô falar com o Mac desligado. Zero não é
        # avaria — é só um robô que ainda não abriu a boca.
        verificar("frases guardadas no Pi",
                  lambda: _speak.frases_em_cache() or "nenhuma ainda")
    else:
        modelo_voz = config.obter("voz.modelo_tts")
        verificar(f"voz {modelo_voz or '(nenhuma configurada)'}",
                  lambda: bool(modelo_voz) and (config.MODELS_DIR / f"{modelo_voz}.onnx").exists(),
                  "define voz.servidor no config/robot.yaml (a Joana vem do Mac)")
    verificar("faster-whisper (transcrever)",
              lambda: importlib.util.find_spec("faster_whisper") is not None,
              "pip install -r requirements.txt")
    verificar("openwakeword (palavra-chave)",
              lambda: importlib.util.find_spec("openwakeword") is not None,
              "pip install --no-deps 'openwakeword>=0.6.0'  (porquê --no-deps: ver requirements.txt)")
    if not config.a_simular():
        # A coluna E os microfones são a mesma placa: o reSpeaker XVF3800, por
        # USB. Aparece no ALSA como "Array". Se não aparecer, não há som nenhum.
        verificar("reSpeaker no ALSA (coluna + microfones)",
                  lambda: _placa_de_som("Array"),
                  "aplay -l não mostra 'Array'. O reSpeaker está ligado por USB? lsusb → 2886:001a")
        verificar("reSpeaker é a placa por omissão",
                  lambda: _placa_por_omissao("Array"),
                  "Falta em /etc/asound.conf:  defaults.pcm.card Array  /  defaults.ctl.card Array")

    # ---------------------------------------------------- cérebro grande
    print("\n🌐 CÉREBRO GRANDE (no Mac)")
    from robot.brain import llm
    host = config.obter("llm.host", "mac.local")
    modelo = config.obter("llm.modelo", "gemma4:12b")

    # Primeiro o nome, depois o serviço. Um nome que não existe na rede é a
    # causa mais comum de "está encravado": cada tentativa espera pelo mDNS
    # e pelo DNS antes de desistir, e este script tentaria três vezes.
    ip = _resolve(host)
    verificar(f"o nome {host} existe na rede", lambda: ip,
              f"No Mac: scutil --get LocalHostName → põe '<esse-nome>.local' em "
              f"config/robot.local.yaml (llm.host e voz.servidor)")

    if not ip:
        print("       (salto a verificação do Ollama — sem nome não há ligação)")
        _problemas.append("LLM offline")
    elif config.a_simular():
        # Em simulação o esta_ligado() devolve sempre True, para o ciclo
        # principal correr. Aqui fazemos a verificação a sério.
        disponiveis = llm.modelos_disponiveis()
        if disponiveis:
            print(f"  {OK} Ollama em {host}: {', '.join(disponiveis[:5])}")
        else:
            print(f"  {AVISO}não consigo falar com o Ollama em {host}")
            print("       → normal se estiveres a programar fora de casa")
    elif llm.esta_ligado():
        print(f"  {OK} Ollama em {host}")
        disponiveis = llm.modelos_disponiveis()
        if any(m.startswith(modelo.split(":")[0]) for m in disponiveis):
            print(f"  {OK} modelo {modelo}")
        else:
            print(f"  {MAU} modelo {modelo} não encontrado")
            print(f"       → no Mac: ollama pull {modelo}")
            print(f"       → disponíveis: {', '.join(disponiveis) or '(nenhum)'}")
            _problemas.append("modelo LLM")
    else:
        print(f"  {MAU} não consigo falar com o Ollama em {host}")
        print("       → o Mac está ligado?")
        print('       → launchctl setenv OLLAMA_HOST "0.0.0.0:11434"')
        print("       → reiniciar a app Ollama a seguir")
        _problemas.append("LLM offline")

    # ---------------------------------------------------- temperatura
    if not config.a_simular():
        print("\n🌡️  SAÚDE DO PI")
        try:
            t = subprocess.run(["vcgencmd", "measure_temp"],
                               capture_output=True, text=True).stdout.strip()
            print(f"  {OK} {t}")
            th = subprocess.run(["vcgencmd", "get_throttled"],
                                capture_output=True, text=True).stdout.strip()
            if "0x0" in th:
                print(f"  {OK} alimentação estável")
            else:
                print(f"  {AVISO}{th} — problema de alimentação!")
                print("       → a fonte dá 5V/5A? A power bank chega?")
        except Exception:  # noqa: BLE001
            pass

    # ---------------------------------------------------- resumo
    print(f"\n{'=' * 62}")
    if _problemas:
        print(f"  {len(_problemas)} coisa(s) a resolver: {', '.join(_problemas)}")
        print("  (o robô pode funcionar à mesma — nem tudo é obrigatório)")
    else:
        print(f"  🎉 Está tudo bem! O {nome} está pronto.")
    print(f"{'=' * 62}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
