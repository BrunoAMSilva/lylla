"""Rende a respiracao do capacete num WAV, para ouvir antes de gravar no Teensy.

A respiracao e toda sintetica, por isso o que sai daqui e praticamente o que sai
do Teensy: mesmos filtros, mesmos envelopes, mesmos ganhos, e os ganhos mudam de
bloco em bloco como no loop(). A voz nao da para prever assim porque depende do
microfone e de quem fala.

    python previsao_respiracao.py

Escreve respiracao-nova.wav e imprime os picos de cada no. Se algum passar de
1,0 e porque corta no Teensy. Os valores aqui em cima tem de acompanhar o .ino.
"""
import numpy as np
from scipy import signal
from scipy.io import wavfile

FS = 44100.0
BLOCO = 128

# ---- os mesmos valores do .ino ----
CICLO_MS, EXPIRA_EM_MS = 4000, 2050
VOL_INSPIRA, VOL_EXPIRA = 1.50, 1.00
AMP_INSP, AMP_EXP = 0.45, 0.9

INSP_DUR_MS, INSP_SUBIDA, INSP_DESCIDA = 1250, 0.18, 0.45
INSP = [(300.0, 4.0, 2.6), (750.0, 3.0, 1.8), (1700.0, 2.0, 1.2)]
INSP_TAMPA_HZ, INSP_CORTE_HZ = 2600.0, 130.0

EXP_DUR_MS, EXP_SUBIDA, EXP_DESCIDA = 1150, 0.16, 0.50
EXP = [(220.0, 3.0, 1.1), (520.0, 2.4, 0.8)]
EXP_TAMPA_HZ = 1500.0

TURB_HZ, TURB_INSP, TURB_EXP = 12.0, 0.22, 0.18


def _biquad(b, a, x):
    return signal.lfilter(b / a[0], a / a[0], x)


def passa_banda(x, fc, q):
    w = 2 * np.pi * fc / FS
    al = np.sin(w) / (2 * q)
    c = np.cos(w)
    return _biquad(np.array([al, 0, -al]), np.array([1 + al, -2 * c, 1 - al]), x)


def passa_baixo(x, fc, q=0.707):
    w = 2 * np.pi * fc / FS
    al = np.sin(w) / (2 * q)
    c = np.cos(w)
    return _biquad(np.array([(1 - c) / 2, 1 - c, (1 - c) / 2]),
                   np.array([1 + al, -2 * c, 1 - al]), x)


def passa_alto(x, fc, q=0.707):
    w = 2 * np.pi * fc / FS
    al = np.sin(w) / (2 * q)
    c = np.cos(w)
    return _biquad(np.array([(1 + c) / 2, -(1 + c), (1 + c) / 2]),
                   np.array([1 + al, -2 * c, 1 - al]), x)


def suave(fase, subida, descida):
    """A mesma do .ino: smoothstep, sem cantos nas juncoes."""
    if fase <= 0.0 or fase >= 1.0:
        return 0.0
    if fase < subida:
        x = fase / subida
        return x * x * (3 - 2 * x)
    if fase > 1 - descida:
        x = (1 - fase) / descida
        return x * x * (3 - 2 * x)
    return 1.0


def ganhos_por_bloco(n, dur_ms, subida, descida, turb_prof, rng, atraso_ms=0):
    """Um valor por bloco de 128 amostras, como as chamadas a gain() no loop()."""
    nb = n // BLOCO + 1
    coef = 1 - np.exp(-(BLOCO / FS) * 2 * np.pi * TURB_HZ)
    turb = 0.0
    g = np.zeros(nb)
    brilho = np.zeros(nb)
    for k in range(nb):
        t = k * BLOCO * 1000.0 / FS
        fase = (t - atraso_ms) / dur_ms if t >= atraso_ms else 0.0
        e = suave(fase, subida, descida)
        turb += (rng.uniform(-1, 1) - turb) * coef
        g[k] = max(0.0, e * (1.0 + turb_prof * turb * 3.0))
        brilho[k] = e
    return np.repeat(g, BLOCO)[:n], np.repeat(brilho, BLOCO)[:n]


def ruido_branco(n, rng, amp):
    """amplitude(A) no Teensy e ruido cheio escalado por A, ou seja uniforme em +-A."""
    return rng.uniform(-amp, amp, n)


def ruido_rosa(n, rng, amp):
    y = signal.lfilter([0.049922035, -0.095993537, 0.050612699, -0.004408786],
                       [1, -2.494956002, 2.017265875, -0.5221894],
                       rng.standard_normal(n + 2000))[2000:]
    return y / np.max(np.abs(y)) * amp


def um_ciclo(rng, relatar=False):
    passo = int(CICLO_MS * FS / 1000)
    branco = ruido_branco(passo, rng, AMP_INSP)
    rosa = ruido_rosa(passo, rng, AMP_EXP)

    gI, briI = ganhos_por_bloco(passo, INSP_DUR_MS, INSP_SUBIDA, INSP_DESCIDA, TURB_INSP, rng)
    mixI = np.zeros(passo)
    for i, (fc, q, ganho) in enumerate(INSP):
        mixI += ganho * gI * (briI ** i) * passa_banda(branco, fc, q)
    inspira = passa_alto(passa_baixo(passa_baixo(mixI, INSP_TAMPA_HZ), INSP_TAMPA_HZ),
                         INSP_CORTE_HZ)

    gE, briE = ganhos_por_bloco(passo, EXP_DUR_MS, EXP_SUBIDA, EXP_DESCIDA, TURB_EXP,
                                rng, atraso_ms=EXPIRA_EM_MS)
    mixE = np.zeros(passo)
    for i, (fc, q, ganho) in enumerate(EXP):
        mixE += ganho * gE * (briE ** i) * passa_banda(rosa, fc, q)
    expira = passa_baixo(mixE, EXP_TAMPA_HZ)

    if relatar:
        pico = lambda v: np.max(np.abs(v))
        for nome, v in [("misturaInsp", mixI), ("inspiracao final", VOL_INSPIRA * inspira),
                        ("misturaExp", mixE), ("expiracao final", VOL_EXPIRA * expira)]:
            print(f"  {nome:20s} pico {pico(v):5.3f}  {'CORTA' if pico(v) >= 1.0 else 'ok'}")
    return VOL_INSPIRA * inspira + VOL_EXPIRA * expira


def centroide(y, fmax=12000):
    j = int(0.06 * FS)
    c = []
    for i in range(0, len(y) - j, j):
        s = y[i:i + j]
        if np.sqrt(np.mean(s ** 2)) < 1e-4:
            continue
        S = np.abs(np.fft.rfft(s * np.hanning(j)))
        fr = np.fft.rfftfreq(j, 1 / FS)
        m = fr < fmax
        c.append(np.sum(fr[m] * S[m]) / np.sum(S[m]))
    return np.array(c)


if __name__ == "__main__":
    rng = np.random.default_rng(7)
    print("picos em cada no:")
    ciclos = [um_ciclo(rng, relatar=(k == 0)) for k in range(4)]
    y = np.concatenate(ciclos)
    wavfile.write("respiracao-nova.wav", int(FS), (np.clip(y, -1, 1) * 32767).astype(np.int16))
    print(f"\npico total {np.max(np.abs(y)):.3f}   ciclo {CICLO_MS} ms")
    c = centroide(y[:int(1.4 * FS)])
    print(f"centroide da inspiracao: {' '.join(f'{v:.0f}' for v in c)} Hz")
    ce = centroide(y[int(2.1 * FS):int(3.2 * FS)])
    print(f"centroide da expiracao:  {' '.join(f'{v:.0f}' for v in ce)} Hz")
