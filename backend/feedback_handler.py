"""Servidor HTTP local do CRMER com suporte a feedback e escrita bidirecional."""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

RAIZ = Path(__file__).resolve().parent.parent
PASTA_OUTPUT = RAIZ / "backend" / "output"
ARQUIVO_SUGESTOES = PASTA_OUTPUT / "sugestoes.json"
CAMINHO_DADOS = PASTA_OUTPUT / "dados_ehe.json"
ARQUIVO_ENV = RAIZ / ".env"

LIMITE_CORPO = 64 * 1024


def carregar_env() -> None:
    """Carrega as variáveis do arquivo .env para o ambiente se não estiverem definidas."""
    if not ARQUIVO_ENV.exists():
        return
    with open(ARQUIVO_ENV, "r", encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, _, valor = linha.partition("=")
            chave = chave.strip()
            valor = valor.strip().strip("'\"")
            if chave and chave not in os.environ:
                os.environ[chave] = valor


carregar_env()


class FeedbackError(Exception):
    """Erro de validação ao registrar feedback."""


def validar_sugestao(payload: Any) -> dict[str, Any]:
    """Valida o payload de sugestão de melhoria."""
    if not isinstance(payload, dict):
        raise FeedbackError("O corpo da requisição precisa ser um objeto JSON.")

    modulo = str(payload.get("modulo", "")).strip()
    tipo = str(payload.get("tipo", "")).strip()
    descricao = str(payload.get("descricao", "")).strip()
    prioridade = str(payload.get("prioridade", "media")).strip().lower()

    if not modulo:
        raise FeedbackError("O campo 'modulo' é obrigatório.")
    if not tipo:
        raise FeedbackError("O campo 'tipo' é obrigatório.")
    if not descricao:
        raise FeedbackError("O campo 'descricao' é obrigatório.")

    return {
        "data": datetime.now(timezone.utc).isoformat(),
        "modulo": modulo,
        "tipo": tipo,
        "descricao": descricao,
        "prioridade": prioridade if prioridade in {"baixa", "media", "alta"} else "media",
        "usuario": str(payload.get("usuario", "Natália")).strip() or "Natália",
    }


def registrar_sugestao(payload: Any) -> dict[str, Any]:
    """Grava a sugestão em backend/output/sugestoes.json."""
    item = validar_sugestao(payload)
    PASTA_OUTPUT.mkdir(parents=True, exist_ok=True)

    itens: list[dict[str, Any]] = []
    if ARQUIVO_SUGESTOES.exists():
        try:
            with open(ARQUIVO_SUGESTOES, "r", encoding="utf-8") as f:
                conteudo = json.load(f)
                if isinstance(conteudo, list):
                    itens = conteudo
        except Exception:
            itens = []

    itens.append(item)

    with open(ARQUIVO_SUGESTOES, "w", encoding="utf-8") as f:
        json.dump(itens, f, ensure_ascii=False, indent=2)

    return item


class FeedbackHandler(SimpleHTTPRequestHandler):
    """Serve a interface web e responde aos endpoints da API interna."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(RAIZ), **kwargs)

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        corpo = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

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

    def do_PUT(self) -> None:
        caminho = urlparse(self.path).path
        match = re.match(r"^/api/clientes/(\d+)$", caminho)
        if not match:
            self.send_error(404, "Rota nao encontrada")
            return

        id_cliente = int(match.group(1))
        tamanho = int(self.headers.get("Content-Length") or 0)
        if tamanho <= 0 or tamanho > LIMITE_CORPO:
            self._json(400, {"erro": "Corpo da requisicao ausente ou invalido."})
            return

        try:
            dados_novos = json.loads(self.rfile.read(tamanho).decode("utf-8"))
        except Exception:
            self._json(400, {"erro": "JSON invalido."})
            return

        if not CAMINHO_DADOS.exists():
            self._json(404, {"erro": "Arquivo dados_ehe.json nao encontrado."})
            return

        try:
            with open(CAMINHO_DADOS, "r", encoding="utf-8") as f:
                dados = json.load(f)

            cliente = None
            for c in dados.get("clientes", []):
                if c.get("nomusId") == id_cliente or str(c.get("id")) in {str(id_cliente), f"nomus-{id_cliente}"}:
                    cliente = c
                    break

            if not cliente:
                self._json(404, {"erro": f"Cliente {id_cliente} nao encontrado na base local."})
                return

            nome_display = cliente.get("nomeFantasia") or cliente.get("razaoSocial") or ""
            payload_nomus = {
                "id": id_cliente,
                "nome": nome_display,
                "razaoSocial": cliente.get("razaoSocial") or nome_display,
                "cnpj": cliente.get("cnpj") or "",
                "tipoPessoa": cliente.get("tipoPessoa", 1),
                "ativo": cliente.get("ativoNomus", True),
                "telefone": dados_novos.get("telefone", cliente.get("telefone", "")),
                "email": dados_novos.get("email", cliente.get("email", "")),
                "observacoes": dados_novos.get("observacoes", cliente.get("anotacoes", "")),
            }

            from backend.nomus_client import NomusClient
            client = NomusClient()
            client.atualizar_cliente(id_cliente, payload_nomus)

            # Atualiza o cache local
            cliente["telefone"] = payload_nomus["telefone"]
            cliente["email"] = payload_nomus["email"]
            cliente["anotacoes"] = payload_nomus["observacoes"]

            with open(CAMINHO_DADOS, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False, indent=2)

            self._json(200, {"sucesso": True, "cliente": cliente})

        except Exception as exc:
            self._json(500, {"sucesso": False, "erro": str(exc)})


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve o CRMER e processa a API local.")
    parser.add_argument("--porta", type=int, default=8080, help="Porta local. Padrão 8080.")
    parser.add_argument("--host", default="0.0.0.0", help="Endereço de escuta. Padrão 0.0.0.0.")
    return parser


def main(argv: list[str] | None = None) -> int:
    carregar_env()
    argumentos = construir_parser().parse_args(argv)
    servidor = ThreadingHTTPServer((argumentos.host, argumentos.porta), FeedbackHandler)
    print(f"CRMER no ar em http://localhost:{argumentos.porta}/ (rede: 0.0.0.0)", flush=True)
    print("Endpoints ativos: POST /api/feedback  |  PUT /api/clientes/<id>", flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor encerrado.", flush=True)
    finally:
        servidor.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
