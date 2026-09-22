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
    from backend.nomus_client import NomusAuthError, NomusClient, NomusError, chaves_de_pedido
    from backend.transformer import DATA_REFERENCIA, VENDEDOR_NATALIA, montar_carteira
else:
    from .nomus_client import NomusAuthError, NomusClient, NomusError, chaves_de_pedido
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
    destino = Path(argumentos.saida)
    historico = _ler_json(destino)
    conhecidos = _chaves_do_historico(historico)
    cliente = NomusClient(max_paginas=argumentos.max_paginas)
    try:
        cliente.semear_produtos(_produtos_do_historico(historico))
        clientes, modo_clientes, novos_clientes = reunir_clientes(cliente, historico, argumentos.full)
        print("\n--- Iniciando coleta de pedidos recentes ---", flush=True)
        pedidos_novos = cliente.listar_pedidos_recentes(conhecidos)
        anteriores = historico.get("nomusPedidos")
        if not isinstance(anteriores, list):
            anteriores = []
        pedidos = _mesclar_pedidos(pedidos_novos, anteriores)
        print("\n--- Iniciando coleta de produtos ---", flush=True)
        produtos = cliente.garantir_produtos(_ids_produto(pedidos))
    finally:
        cliente.fechar()

    carteira = montar_carteira(
        clientes,
        produtos,
        pedidos,
        vendedor_id=argumentos.vendedor_id,
        referencia=DATA_REFERENCIA,
    )
    payload = carteira.model_dump(mode="json")
    payload["clientes"] = payload["clients"]
    payload["nomusPedidos"] = pedidos
    payload["nomusProdutos"] = produtos
    payload["nomusClientes"] = clientes
    _gravar_json(destino, payload)
    print(
        f"\n[Sucesso] Arquivo gerado em backend/output/dados_ehe.json com {len(clientes)} clientes.",
        flush=True,
    )
    if destino.resolve() != CARTEIRA_COMPAT.resolve():
        _gravar_json(CARTEIRA_COMPAT, payload)
    contagem: dict[str, int] = {}
    for ficha in carteira.clients:
        contagem[ficha.ranking] = contagem.get(ficha.ranking, 0) + 1
    print(f"Carteira de {len(carteira.clients)} cliente(s) em {destino}")
    print(f"Clientes ({modo_clientes}): {len(clientes)} no total · novos nesta consulta: {len(novos_clientes)}")
    print(
        f"Pedidos novos: {len(pedidos_novos)} · reunidos com o histórico: {len(pedidos)} · "
        f"produtos em cache: {len(produtos)}"
    )
    print(f"Produtos vendáveis: {len(carteira.produtos)} · preços: {len(carteira.historico_precos)}")
    print(
        "Filas: "
        + ", ".join(f"{fila}={contagem.get(fila, 0)}" for fila in ("contato", "resposta", "sazonal", "inativos"))
    )
    for aviso in carteira.avisos:
        print(f"- {aviso}")
    return 0


def _ler_json(caminho: Path) -> dict:
    if not caminho.is_file():
        return {}
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dados if isinstance(dados, dict) else {}


def clientes_em_cache(payload: dict) -> list[dict]:
    """Cadastro bruto já gravado. Ficha do CRMER não substitui o payload do Nomus."""
    for chave in ("nomusClientes", "clientes", "clients"):
        lista = payload.get(chave)
        if not isinstance(lista, list):
            continue
        brutos = [item for item in lista if isinstance(item, dict) and _parece_cliente_nomus(item)]
        if brutos:
            return brutos
    return []


def reunir_clientes(cliente, historico: dict, completo: bool) -> tuple[list[dict], str, list[dict]]:
    """Reusa o arquivo local. Sem --full, só as páginas recentes de cliente novo."""
    print("\n--- Iniciando coleta de clientes Nomus ---", flush=True)
    gravados = [] if completo else clientes_em_cache(historico)
    if completo or not gravados:
        lidos = cliente.listar_clientes()
        return lidos, "completa", lidos
    conhecidos = {f"id:{item['id']}" for item in gravados if item.get("id") is not None}
    novos = cliente.listar_clientes_recentes(conhecidos)
    return _mesclar_clientes(novos, gravados), "incremental", novos


def _parece_cliente_nomus(cliente: dict) -> bool:
    ident = cliente.get("id")
    if isinstance(ident, bool) or not isinstance(ident, int):
        return False
    return "razaoSocial" in cliente or "vendedores" in cliente or "cnpj" in cliente


def _mesclar_clientes(novos: list, antigos: list) -> list[dict]:
    saida: list[dict] = []
    vistos: set[str] = set()
    for cliente in [*novos, *antigos]:
        if not isinstance(cliente, dict):
            continue
        ident = cliente.get("id")
        marca = f"id:{ident}" if ident is not None else repr(id(cliente))
        if marca in vistos:
            continue
        vistos.add(marca)
        saida.append(cliente)
    return saida


def _chaves_do_historico(payload: dict) -> set[str]:
    """Códigos e ids já gravados em dados_ehe.json. A varredura para neles."""
    chaves: set[str] = set()
    for pedido in payload.get("nomusPedidos") or []:
        if isinstance(pedido, dict):
            chaves.update(chaves_de_pedido(pedido))
    for grupo in ("clientes", "clients"):
        for cliente in payload.get(grupo) or []:
            if not isinstance(cliente, dict):
                continue
            for pedido in cliente.get("pedidos") or []:
                if isinstance(pedido, dict):
                    chaves.update(chaves_de_pedido(pedido))
    return chaves


def _mesclar_pedidos(novos: list, antigos: list) -> list[dict]:
    """Pedidos desta consulta na frente; o que já estava no arquivo permanece."""
    saida: list[dict] = []
    vistos: set[str] = set()
    for pedido in [*novos, *antigos]:
        if not isinstance(pedido, dict):
            continue
        marcas = chaves_de_pedido(pedido)
        if marcas and marcas & vistos:
            continue
        vistos.update(marcas)
        saida.append(pedido)
    return saida


def _ids_produto(pedidos: list[dict]) -> list[int]:
    ids: list[int] = []
    vistos: set[int] = set()
    for pedido in pedidos:
        for item in pedido.get("itensPedido") or []:
            if not isinstance(item, dict):
                continue
            ident = item.get("idProduto")
            if isinstance(ident, bool) or ident is None or ident == "":
                continue
            try:
                numero = int(ident)
            except (TypeError, ValueError):
                continue
            if numero not in vistos:
                vistos.add(numero)
                ids.append(numero)
    return ids


def _produtos_do_historico(payload: dict) -> list[dict]:
    brutos = payload.get("nomusProdutos")
    if isinstance(brutos, list) and brutos:
        return [item for item in brutos if isinstance(item, dict)]
    convertidos: list[dict] = []
    for produto in payload.get("produtos") or []:
        if isinstance(produto, dict) and produto.get("id") is not None:
            convertidos.append(_produto_local_como_nomus(produto))
    return convertidos


def _produto_local_como_nomus(produto: dict) -> dict:
    """Reaproveita o catálogo já exportado sem pedir o mesmo produto ao Nomus."""
    grupo = produto.get("grupo") or produto.get("familia") or ""
    return {
        "id": produto.get("id"),
        "codigo": produto.get("codigo") or "",
        "descricao": produto.get("descricao") or "",
        "nomeGrupoProduto": grupo,
        "nomeTipoProduto": "",
        "custoPadraoCompra": produto.get("custo", 0),
        "siglaUnidadeMedida": produto.get("unidade") or "UN",
        "empresasSetoresEstoque": [{"saldoEstoqueAtualEmpresa": produto.get("saldoEstoque", 0)}],
    }


def _gravar_json(destino: Path, payload: dict) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Consulta a carteira da Natália no Nomus e gera o JSON do CRMER.")
    parser.add_argument("--saida", default=str(SAIDA_PADRAO), help="Caminho do JSON de saída.")
    parser.add_argument("--vendedor-id", type=int, default=VENDEDOR_NATALIA, help="idPessoaVendedor no Nomus.")
    parser.add_argument("--max-paginas", type=int, default=500, help="Trava de segurança da paginação.")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Varre /clientes desde a página 1, sem reaproveitar o arquivo local.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    argumentos = construir_parser().parse_args(argv)
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
