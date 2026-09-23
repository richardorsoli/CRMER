"""Recebe a sugestão da Natália e acrescenta em backend/output/sugestoes.json.

O protótipo em servidor estático não tem esta rota. Nesse caso a tela
guarda a sugestão no navegador e baixa o JSON. Para gravar no arquivo:

    python -m backend.feedback_handler

O mesmo processo serve a pasta do CRMER e responde POST /api/feedback.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

RAIZ = Path(__file__).resolve().parent.parent
SAIDA_PADRAO = Path(__file__).resolve().parent / "output" / "sugestoes.json"
LIMITE_CORPO = 32_768
MODULOS = {
    "Ficha do Cliente",
    "Histórico de Pedidos/NF",
    "Produtos",
    "Dashboard",
    "Outro",
}
TIPOS = {
    "Sugestão de funcionalidade",
    "Ajuste visual/usabilidade",
    "Inconsistência de dado",
}
PRIORIDADES = {"Baixa", "Média", "Alta"}


class FeedbackError(ValueError):
    """Payload que a tela consegue corrigir."""


def registrar_sugestao(payload: dict[str, Any], caminho: Path | None = None) -> dict[str, Any]:
    """Valida o POST e devolve o item já gravado, com id e status."""
    destino = caminho or SAIDA_PADRAO
    item = _montar_item(payload, _proximo_id(destino))
    registros = _ler(destino)
    registros.append(item)
    _gravar(destino, registros)
    return item


def _montar_item(payload: dict[str, Any], identificador: int) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise FeedbackError("O corpo precisa ser um objeto JSON.")
    modulo = _escolha(payload.get("modulo"), MODULOS, "módulo")
    tipo = _escolha(payload.get("tipo"), TIPOS, "tipo")
    descricao = _texto(payload.get("descricao"))
    if not descricao:
        raise FeedbackError("Descreva a sugestão.")
    if len(descricao) > 4000:
        raise FeedbackError("A descrição passou de 4000 caracteres.")
    prioridade = _prioridade(payload.get("prioridade"))
    autor = _texto(payload.get("autor")) or "Natália"
    return {
        "id": identificador,
        "data": _formatar_data(payload.get("data")),
        "autor": autor,
        "modulo": modulo,
        "tipo": tipo,
        "descricao": descricao,
        "prioridade": prioridade,
        "status": "Pendente",
        "resposta_tecnica": "",
    }


def _escolha(valor: Any, permitidos: set[str], nome: str) -> str:
    texto = _texto(valor)
    if texto not in permitidos:
        raise FeedbackError(f"Escolha um {nome} da lista.")
    return texto


def _prioridade(valor: Any) -> str:
    texto = _texto(valor)
    if texto in PRIORIDADES:
        return texto
    if texto.casefold().startswith("alta"):
        return "Alta"
    raise FeedbackError("Escolha a prioridade percebida.")


def _texto(valor: Any) -> str:
    if valor is None:
        return ""
    return " ".join(str(valor).split())


def _formatar_data(valor: Any) -> str:
    texto = _texto(valor)
    if not texto:
        momento = datetime.now()
    else:
        try:
            momento = datetime.fromisoformat(texto.replace("Z", "+00:00"))
        except ValueError as exc:
            raise FeedbackError("A data da sugestão não é válida.") from exc
        if momento.tzinfo is not None:
            momento = momento.astimezone().replace(tzinfo=None)
    return momento.strftime("%Y-%m-%d %H:%M")


def _proximo_id(caminho: Path) -> int:
    maior = 0
    for item in _ler(caminho):
        ident = item.get("id")
        if isinstance(ident, bool) or not isinstance(ident, int):
            continue
        maior = max(maior, ident)
    return maior + 1


def _ler(caminho: Path) -> list[dict[str, Any]]:
    if not caminho.is_file():
        return []
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(dados, list):
        return []
    return [item for item in dados if isinstance(item, dict)]


def _gravar(caminho: Path, registros: list[dict[str, Any]]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(registros, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class FeedbackHandler(SimpleHTTPRequestHandler):
    """Serve o protótipo e aceita POST /api/feedback."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(RAIZ), **kwargs)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/feedback":
            self.send_error(404)
            return
        tamanho = int(self.headers.get("Content-Length") or 0)
        if tamanho <= 0 or tamanho > LIMITE_CORPO:
            self._json(400, {"erro": "Corpo da sugestão ausente ou grande demais."})
            return
        bruto = self.rfile.read(tamanho)
        try:
            payload = json.loads(bruto.decode("utf-8"))
            item = registrar_sugestao(payload)
        except FeedbackError as exc:
            self._json(400, {"erro": str(exc)})
            return
        except json.JSONDecodeError:
            self._json(400, {"erro": "O corpo não é JSON."})
            return
        self._json(201, {"ok": True, "item": item})

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        corpo = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve o CRMER e grava sugestões em backend/output/sugestoes.json.")
    parser.add_argument("--porta", type=int, default=8080, help="Porta local. O padrão é 8080.")
    parser.add_argument("--host", default="127.0.0.1", help="Endereço de escuta.")
    return parser


def main(argv: list[str] | None = None) -> int:
    argumentos = construir_parser().parse_args(argv)
    servidor = ThreadingHTTPServer((argumentos.host, argumentos.porta), FeedbackHandler)
    print(f"CRMER em http://{argumentos.host}:{argumentos.porta}/  ·  POST /api/feedback", flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor encerrado.", flush=True)
    finally:
        servidor.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
