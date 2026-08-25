"""A BATERIA — quanta energia resta.

O Raspberry Pi **não tem conversor analógico-digital nenhum**. Para ler uma
tensão é preciso um chip à parte: o ADS1115 (I2C, endereço 0x48).

E como a bateria dá 12,8 V mas o ADS1115 só aguenta 3,3 V na entrada, há um
divisor resistivo pelo meio:

        bateria ──[ R1 ]──┬──[ R2 ]── GND
                          │
                       ADS1115 A0

    Com R1 = 100 kΩ e R2 = 22 kΩ:  fator = (100+22)/22 = 5,545
    14,6 V (LiFePO4 4S em carga máxima) ÷ 5,545 = 2,63 V  ✓ dentro do limite

⚠️ CALIBRAR NA FASE 7: medir a tensão real com o multímetro e ajustar o
   `energia.divisor` no robot.yaml até a leitura bater certo.

A curva de descarga de uma LiFePO4 é muito plana — fica quase toda a vida
perto dos 13 V e cai a pique no fim. Por isso a percentagem calculada a
partir da tensão é grosseira. Serve para "tenho fome", não para uma barra
de precisão.
"""

from __future__ import annotations

from robot import config

_ads = None
_iniciado = False

# Pontos da curva de descarga de uma LiFePO4 4S (tensão em repouso → % restante)
#
# A curva é MUITO plana: fica quase toda a vida entre 13,4 e 13,1 V e cai a
# pique no fim. Um pack cheio em repouso fica perto dos 13,4 V — por isso o
# topo da curva é 13,4 e não 14,6, senão o robô nunca diria 100%.
_CURVA = [
    (13.6, 100), (13.4, 97), (13.3, 80), (13.2, 55),
    (13.1, 30), (13.0, 20), (12.8, 10), (12.0, 5), (10.0, 0),
]

# Quantas leituras críticas seguidas antes de o robô se desligar.
# ⚠️ Uma amostra única NÃO chega: a curva é de tensão em REPOUSO, mas nós
#    lemos sob carga. O arranque de dois servos faz cair 0,3-0,5 V, e isso
#    bastaria para o robô se desligar a meio da brincadeira.
_criticas_seguidas = 0


def _iniciar():
    global _ads, _iniciado
    if _iniciado or config.a_simular():
        _iniciado = True
        return _ads
    _iniciado = True
    try:
        import smbus2

        _ads = smbus2.SMBus(1)
    except Exception as erro:  # noqa: BLE001
        print(f"⚠️  ADS1115 indisponível ({erro}). Sem leitura de bateria.")
        _ads = None
    return _ads


def _ler_adc_bruto(canal: int = 0) -> int | None:
    """Lê um canal do ADS1115 em modo single-shot, ganho ±4,096 V."""
    bus = _iniciar()
    if bus is None:
        return None
    endereco = int(config.obter("i2c.ads1115", 0x48))
    # OS=1 (começar), MUX=canal single-ended, PGA=±4,096V, MODE=single-shot,
    # 128 SPS, comparador desligado
    config_reg = 0x8000 | ((0x04 + canal) << 12) | (0x01 << 9) | 0x0100 | 0x0083
    try:
        import time

        bus.write_i2c_block_data(
            endereco, 0x01, [(config_reg >> 8) & 0xFF, config_reg & 0xFF]
        )
        time.sleep(0.01)
        dados = bus.read_i2c_block_data(endereco, 0x00, 2)
        valor = (dados[0] << 8) | dados[1]
        if valor > 0x7FFF:
            valor -= 0x10000
        return valor
    except Exception as erro:  # noqa: BLE001
        print(f"⚠️  Falha a ler o ADS1115: {erro}")
        return None


def tensao(amostras: int = 5) -> float | None:
    """Tensão da bateria em volts, filtrada. None se não houver ADC.

    Devolve a MEDIANA de várias leituras, não uma só. Um pico de corrente
    de um servo dá uma leitura baixa espúria, e a mediana ignora-a — uma
    média não ignoraria.
    """
    if config.a_simular():
        return 13.2
    canal = int(config.obter("energia.canal_adc", 0))
    divisor = float(config.obter("energia.divisor", 5.545))
    leituras = []
    for _ in range(max(1, amostras)):
        bruto = _ler_adc_bruto(canal)
        if bruto is not None:
            # ±4,096 V em 15 bits → 0,125 mV por passo
            leituras.append(bruto * 4.096 / 32767.0 * divisor)
    if not leituras:
        return None
    leituras.sort()
    return round(leituras[len(leituras) // 2], 2)


def percentagem() -> int | None:
    """Percentagem aproximada de carga restante.

    Grosseira de propósito — a curva da LiFePO4 é quase plana. Serve para o
    robô dizer "tenho fome", não para uma barra de precisão.
    """
    v = tensao()
    if v is None:
        return None
    if v >= _CURVA[0][0]:
        return 100
    if v <= _CURVA[-1][0]:
        return 0
    for (v_alto, p_alto), (v_baixo, p_baixo) in zip(_CURVA, _CURVA[1:]):
        if v_baixo <= v <= v_alto:
            fatia = (v - v_baixo) / (v_alto - v_baixo)
            return int(round(p_baixo + fatia * (p_alto - p_baixo)))
    return None


def tem_fome() -> bool:
    """True quando é altura de avisar que a bateria está a acabar."""
    p = percentagem()
    return p is not None and p <= int(config.obter("energia.aviso_pct", 20))


def critico() -> bool:
    """True quando o robô se devia desligar sozinho, para não danificar o pack.

    Exige várias leituras críticas SEGUIDAS. Uma leitura isolada durante um
    pico de corrente não chega — senão o robô desligava-se a meio de um gesto.
    """
    global _criticas_seguidas
    p = percentagem()
    if p is None:
        _criticas_seguidas = 0
        return False
    if p <= int(config.obter("energia.critico_pct", 5)):
        _criticas_seguidas += 1
    else:
        _criticas_seguidas = 0
    return _criticas_seguidas >= int(config.obter("energia.leituras_criticas", 3))


def estado() -> dict:
    return {
        "tensao_v": tensao(),
        "percentagem": percentagem(),
        "tem_fome": tem_fome(),
        "critico": critico(),
    }


def disponivel() -> bool:
    return config.a_simular() or _iniciar() is not None
