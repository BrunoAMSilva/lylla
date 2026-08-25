"""OS GESTOS DOS BRAÇOS.

╔══════════════════════════════════════════════════════════════════════════╗
║  LARA: este ficheiro é teu, tal como o expressions.py.                   ║
║                                                                          ║
║  Uma POSE é uma posição parada: que ângulo tem cada junta.               ║
║  Um GESTO é uma sequência de poses com pausas entre elas.                ║
║                                                                          ║
║  Os ângulos vão de 0 a 180 graus. Se puseres um número fora dos          ║
║  limites do config/robot.yaml, o robô corrige-o sozinho e avisa-te —     ║
║  não parte nada.                                                         ║
║                                                                          ║
║  Para experimentar:   python scripts/test_arms.py festejar               ║
╚══════════════════════════════════════════════════════════════════════════╝

Como descobrir os ângulos certos (fase 8): move o servo devagar com o
`test_arms.py`, vê onde o braço bate no corpo, e anota. Não há fórmula —
mede-se.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# POSES — uma posição parada
# ---------------------------------------------------------------------------

POSES: dict[str, dict[str, float]] = {
    # Braços caídos ao lado do corpo. É aqui que ele fica quando não faz nada.
    "descanso": {
        "ombro_esq": 20, "cotovelo_esq": 20,
        "ombro_dir": 20, "cotovelo_dir": 20,
    },
    # Braços levantados, prontos a acenar
    "acenar_cima": {
        "ombro_esq": 20,  "cotovelo_esq": 20,
        "ombro_dir": 140, "cotovelo_dir": 110,
    },
    "acenar_fora": {"cotovelo_dir": 140},
    "acenar_dentro": {"cotovelo_dir": 80},

    # Apontar
    "apontar_dir": {"ombro_dir": 100, "cotovelo_dir": 160},
    "apontar_esq": {"ombro_esq": 100, "cotovelo_esq": 160},
    "apontar_cima": {"ombro_dir": 165, "cotovelo_dir": 160},

    # Emoções
    "festa": {
        "ombro_esq": 160, "cotovelo_esq": 150,
        "ombro_dir": 160, "cotovelo_dir": 150,
    },
    "encolher_ombros": {
        "ombro_esq": 60, "cotovelo_esq": 120,
        "ombro_dir": 60, "cotovelo_dir": 120,
    },
    "abraco": {
        "ombro_esq": 90, "cotovelo_esq": 160,
        "ombro_dir": 90, "cotovelo_dir": 160,
    },
    "envergonhado": {
        "ombro_esq": 20,  "cotovelo_esq": 20,
        "ombro_dir": 130, "cotovelo_dir": 170,
    },
    "dar_cinco": {"ombro_dir": 130, "cotovelo_dir": 150},
}


# ---------------------------------------------------------------------------
# GESTOS — sequências de (pose ou ângulos, segundos de pausa)
# ---------------------------------------------------------------------------

GESTOS: dict[str, list[tuple]] = {
    "acenar": [
        ("acenar_cima", 0.3),
        ("acenar_fora", 0.25), ("acenar_dentro", 0.25),
        ("acenar_fora", 0.25), ("acenar_dentro", 0.25),
        ("acenar_fora", 0.25),
        ("descanso", 0.0),
    ],
    "festejar": [
        ("festa", 0.3),
        ({"cotovelo_esq": 120, "cotovelo_dir": 120}, 0.2),
        ("festa", 0.2),
        ({"cotovelo_esq": 120, "cotovelo_dir": 120}, 0.2),
        ("festa", 0.3),
        ("descanso", 0.0),
    ],
    "nao_sei": [
        ("encolher_ombros", 0.9),
        ("descanso", 0.0),
    ],
    "espreguicar": [
        ("festa", 1.2),
        ("encolher_ombros", 0.5),
        ("descanso", 0.0),
    ],
    "dar_cinco": [
        ("dar_cinco", 1.5),
        ("descanso", 0.0),
    ],
    "abracar": [
        ("abraco", 1.5),
        ("descanso", 0.0),
    ],
}


def validar_todos() -> None:
    """Confirma que todos os gestos usam poses e juntas que existem.

    Chamado pelos testes e pelo check_health, para a Lara descobrir um erro
    de escrita antes de o robô fazer alguma coisa estranha.
    """
    from robot import config

    juntas_validas = set(config.obter("bracos.juntas", {}) or {})

    for nome, pos in POSES.items():
        for junta in pos:
            if juntas_validas and junta not in juntas_validas:
                raise ValueError(
                    f"A pose '{nome}' usa a junta '{junta}', que não existe.\n"
                    f"As juntas definidas em config/robot.yaml são: "
                    f"{', '.join(sorted(juntas_validas))}"
                )

    for nome, passos in GESTOS.items():
        for passo, _pausa in passos:
            if isinstance(passo, str):
                if passo not in POSES:
                    raise ValueError(
                        f"O gesto '{nome}' usa a pose '{passo}', que não existe.\n"
                        f"As poses são: {', '.join(sorted(POSES))}"
                    )
            else:
                for junta in passo:
                    if juntas_validas and junta not in juntas_validas:
                        raise ValueError(
                            f"O gesto '{nome}' usa a junta '{junta}', que não existe."
                        )


if __name__ == "__main__":
    validar_todos()
    print(f"{len(POSES)} poses e {len(GESTOS)} gestos, todos válidos.")
    for nome in sorted(GESTOS):
        print(f"  · {nome}")
