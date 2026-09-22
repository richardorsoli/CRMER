"""Agenda a consulta Nomus na janela de almoço da Natália.

A tarefa começa às 12:00, de segunda a sexta, para a sincronização correr
entre 12h e 13h. Este script não registra a tarefa sozinho.

No Windows, a partir da raiz do repositório:

    python -m backend.scheduler
    python -m backend.scheduler --registrar

No Linux, a linha equivalente é a do cron impressa abaixo.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TAREFA = "CRMER Sincronizar Nomus"


def comando_windows() -> list[str]:
    python = sys.executable
    return [
        "schtasks",
        "/Create",
        "/F",
        "/TN",
        TAREFA,
        "/SC",
        "WEEKLY",
        "/D",
        "MON,TUE,WED,THU,FRI",
        "/ST",
        "12:00",
        "/TR",
        f'"{python}" -m backend.sync_runner',
        "/RL",
        "LIMITED",
    ]


def linha_cron() -> str:
    return f"0 12 * * 1-5 cd {RAIZ} && {sys.executable} -m backend.sync_runner"


def _exibir(comando: list[str]) -> str:
    partes = []
    for parte in comando:
        if " " in parte and not (parte.startswith('"') and parte.endswith('"')):
            partes.append(f'"{parte}"')
        else:
            partes.append(parte)
    return " ".join(partes)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mostra ou registra a sincronização das 12h, de segunda a sexta.")
    parser.add_argument("--registrar", action="store_true", help="Cria a tarefa no Agendador do Windows.")
    argumentos = parser.parse_args(argv)
    comando = comando_windows()
    print("Janela: segunda a sexta, início às 12:00, para concluir até 13:00.")
    print("Windows:")
    print(_exibir(comando))
    print("Cron:")
    print(linha_cron())
    if not argumentos.registrar:
        return 0
    resultado = subprocess.run(comando, cwd=RAIZ, check=False)
    return resultado.returncode


if __name__ == "__main__":
    raise SystemExit(main())
