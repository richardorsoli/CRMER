"""Gera a carteira da Natália a partir da consulta ao Nomus.

Uso, na raiz do repositório:

    python -m backend.sync_runner

O token vem de NOMUS_AUTH_TOKEN. O JSON sai em backend/output/ e não deve ir para o Git.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from backend.nomus_client import NomusAuthError, NomusClient, NomusError
    from backend.transformer import DATA_REFERENCIA, VENDEDOR_NATALIA, montar_carteira
else:
    from .nomus_client import NomusAuthError, NomusClient, NomusError
    from .transformer import DATA_REFERENCIA, VENDEDOR_NATALIA, montar_carteira

RAIZ = Path(__file__).resolve().parent.parent
SAIDA_PADRAO = Path(__file__).resolve().parent / "output" / "dados_ehe.json"
CARTEIRA_COMPAT = Path(__file__).resolve().parent / "output" / "carteira_natalia.json"


def carregar_env(caminho: Path) -> None:
    """Preenche o ambiente com o .env local sem substituir variável já definida."""
    if not caminho.is_file():
        return
    for bruta in caminho.read_text(encoding="utf-8").splitlines():
        linha = bruta.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        chave = chave.strip()
        valor = valor.strip().strip('"').strip("'")
        if chave and chave not in os.environ:
            os.environ[chave] = valor


def executar(argumentos: argparse.Namespace) -> int:
    carregar_env(RAIZ / ".env")
    cliente = NomusClient(max_paginas=argumentos.max_paginas)
    try:
        clientes = cliente.listar_clientes()
        produtos = cliente.listar_produtos()
        pedidos = cliente.listar_pedidos_venda()
    finally:
        cliente.fechar()

    carteira = montar_carteira(
        clientes,
        produtos,
        pedidos,
        vendedor_id=argumentos.vendedor_id,
        referencia=DATA_REFERENCIA,
    )
    destino = Path(argumentos.saida)
    payload = carteira.model_dump(mode="json")
    payload["clientes"] = payload["clients"]
    _gravar_json(destino, payload)
    if destino.resolve() != CARTEIRA_COMPAT.resolve():
        _gravar_json(CARTEIRA_COMPAT, payload)
    contagem: dict[str, int] = {}
    for ficha in carteira.clients:
        contagem[ficha.ranking] = contagem.get(ficha.ranking, 0) + 1
    print(f"Carteira de {len(carteira.clients)} cliente(s) em {destino}")
    print(f"Produtos vendáveis: {len(carteira.produtos)} · preços: {len(carteira.historico_precos)}")
    print(
        "Filas: "
        + ", ".join(f"{fila}={contagem.get(fila, 0)}" for fila in ("contato", "resposta", "sazonal", "inativos"))
    )
    for aviso in carteira.avisos:
        print(f"- {aviso}")
    return 0


def _gravar_json(destino: Path, payload: dict) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Consulta a carteira da Natália no Nomus e gera o JSON do CRMER.")
    parser.add_argument("--saida", default=str(SAIDA_PADRAO), help="Caminho do JSON de saída.")
    parser.add_argument("--vendedor-id", type=int, default=VENDEDOR_NATALIA, help="idPessoaVendedor no Nomus.")
    parser.add_argument("--max-paginas", type=int, default=500, help="Trava de segurança da paginação.")
    argumentos = parser.parse_args(argv)
    try:
        return executar(argumentos)
    except NomusAuthError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (NomusError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
