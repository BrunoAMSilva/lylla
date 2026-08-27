#!/usr/bin/env python3
"""ESTÁ TUDO BEM? — verifica cada peça do robô, uma a uma.

    python scripts/check_health.py

Corre isto SEMPRE que alguma coisa parecer estranha, antes de mexer em código.
Responde à pergunta que interessa: é o hardware ou é o programa?
"""

from __future__ import annotations

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


def _voz_local_pronta(nome: str) -> str | bool:
    """O .onnx e o .onnx.json estão os dois lá? O Piper precisa dos dois."""
    modelo = config.MODELS_DIR / f"{nome}.onnx"
    configuracao = config.MODELS_DIR / f"{nome}.onnx.json"
    if not modelo.is_file():
        return False
    if not configuracao.is_file():
        return f"falta o {configuracao.name}"
    return f"{modelo.stat().st_size / 1e6:.0f} MB"


def _voz_do_mac_responde(url: str) -> str | bool:
    """Pergunta ao serviço de voz (do cérebro, ou ao antigo servidor_voz.py)."""
    import json
    from urllib.request import urlopen

    base = url.rsplit("/", 1)[0]
    for caminho in ("/saude", "/v1/saude"):     # o novo e o antigo
        try:
            with urlopen(base.replace("/v1", "") + caminho, timeout=3) as resposta:  # noqa: S310
                dados = json.load(resposta)
        except Exception:  # noqa: BLE001
            continue
        voz = dados.get("falar", {}).get("voz") or dados.get("voz")
        cache = dados.get("falar", {}).get("em_cache", dados.get("em_cache"))
        return f"{voz} · {cache} frases em cache no Mac"
    return False


def _comando(*args) -> bool:
    try:
        r = subprocess.run(args, capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:  # noqa: BLE001
        return False


def main() -> int:
    nome = config.nome_do_robo()
    print(f"\n{'=' * 62}")
    print(f"  DIAGNÓSTICO DO {nome.upper()}")
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
            r = subprocess.run(["i2cdetect", "-y", "1"], capture_output=True, text=True)
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
            r = subprocess.run(["i2cdetect", "-y", "1"], capture_output=True, text=True)
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
        verificar("libcamera vê a câmara",
                  lambda: _comando("libcamera-hello", "--list-cameras", "-t", "1"),
                  "⚠️  FALTA O CABO ADAPTADOR CSI 22→15 PINOS?")

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

    motor = config.obter("voz.motor", "mac")
    modelo_voz = config.obter("voz.modelo_tts")
    lingua = config.obter("lingua", "pt")
    print(f"  ·  motor: {motor} · língua: {lingua}")

    # A voz local (GLaDOS ou tugão) verifica-se sempre que estiver configurada,
    # seja ela o motor principal ou o recurso.
    if modelo_voz:
        verificar(f"voz local '{modelo_voz}'",
                  lambda: _voz_local_pronta(modelo_voz),
                  "python scripts/download_models.py")

    from robot.voice import speak as _speak_url

    servidor = _speak_url._url_do_servidor()
    if servidor and motor == "mac":
        verificar(f"serviço de voz no Mac ({config.obter('voz.voz_mac', 'Joana')})",
                  lambda: _voz_do_mac_responde(servidor),
                  "No mini:  python -m cerebro.servidor")
        # Isto é o que permite ao robô falar com o Mac desligado. Zero não é
        # avaria — é só um robô que ainda não abriu a boca.
        verificar("frases guardadas no Pi",
                  lambda: _speak.frases_em_cache() or "nenhuma ainda")
    elif not modelo_voz:
        verificar("alguma voz configurada", lambda: False,
                  "põe voz.modelo_tts (local) ou cerebro.url (no mini) no robot.yaml")
    if not config.a_simular():
        verificar("microfone", lambda: _comando("arecord", "-l"),
                  "arecord -l não encontra nada. O microfone USB está ligado?")
        verificar("coluna", lambda: _comando("aplay", "-l"),
                  "Falta dtoverlay=hifiberry-dac no /boot/firmware/config.txt?")

    # ---------------------------------------------------- cérebro grande
    print("\n🌐 CÉREBRO (o mac mini)")
    from robot.brain import cerebro as _cerebro

    saude = _cerebro.saude()
    if saude:
        print(f"  {OK} {saude['nome']} em {_cerebro.base_url()} ({saude['maquina']})")
        print(f"  {OK} ouvir: {saude['ouvir']['motor']} · {saude['ouvir']['modelo']}")
        if saude["pensar"]["ligado"]:
            print(f"  {OK} pensar: {saude['pensar']['motor']} · {saude['pensar']['modelo']}")
        else:
            print(f"  {MAU} pensar: o {saude['pensar']['motor']} não responde no mini")
            _problemas.append("modelo do cérebro")
        print(f"  {OK} falar: {saude['falar']['motor']} · {saude['falar']['voz']}")
    else:
        print(f"  {AVISO}o cérebro não responde em {_cerebro.base_url()}")
        print("       → no mini: python -m cerebro.servidor")
        print("       → vou ver se pelo menos o Ollama está de pé")

    if not saude:
        _problemas.append("cérebro offline")

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
