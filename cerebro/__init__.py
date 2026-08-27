"""O CÉREBRO — o serviço de IA que corre no mac mini.

    python -m cerebro.servidor            # arranca o serviço (porta 8420)
    python -m cerebro.medir               # mede latências e ajuda a escolher modelos

Três coisas, uma API:

    ouvir   → áudio para texto      (Whisper, em MLX)
    pensar  → texto para resposta   (LLM no Ollama, saída estruturada)
    falar   → texto para áudio      (Piper, ou as vozes do macOS)

E um `turno` que faz as três seguidas e vai mandando as frases ao Pi à
medida que saem. Ver docs/AI-config.md.
"""
