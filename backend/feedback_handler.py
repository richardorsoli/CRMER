"""Servidor HTTP local do CRMER com suporte a feedback, sincronização e atividades."""

from __future__ import annotations

import argparse
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

RAIZ = Path(__file__).resolve().parent.parent
PASTA_OUTPUT = RAIZ / "backend" / "output"
ARQUIVO_SUGESTOES = PASTA_OUTPUT / "sugestoes.json"
ARQUIVO_ATIVIDADES = PASTA_OUTPUT / "atividades.json"
CAMINHO_DADOS = PASTA_OUTPUT / "dados_ehe.json"
ARQUIVO_ENV = RAIZ / ".env"

LIMITE_CORPO = 64 * 1024
FUSO_BRASILIA = timezone(timedelta(hours=-3))


def agora_brasilia() -> str:
    """Horário de Brasília (UTC-3), sem horário de verão."""
    return datetime.now(FUSO_BRASILIA).isoformat(timespec="seconds")


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
    """Erro de validação."""


def validar_sugestao(payload: Any) -> dict[str, Any]:
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
        "id": f"sug-{uuid.uuid4().hex[:8]}",
        "data": agora_brasilia(),
        "modulo": modulo,
        "tipo": tipo,
        "descricao": descricao,
        "prioridade": prioridade if prioridade in {"baixa", "media", "alta"} else "media",
        "usuario": str(payload.get("usuario", "Natália")).strip() or "Natália",
    }


def registrar_sugestao(payload: Any) -> dict[str, Any]:
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


def validar_atividade(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise FeedbackError("O corpo da requisição precisa ser um objeto JSON.")

    nomus_id = payload.get("nomusId")
    if nomus_id is None:
        raise FeedbackError("O campo 'nomusId' é obrigatório.")
    try:
        nomus_id = int(nomus_id)
    except (ValueError, TypeError):
        raise FeedbackError("O campo 'nomusId' deve ser numérico.")

    tipo = str(payload.get("tipo", "")).strip()
    tipos_validos = {"WhatsApp", "E-mail", "Ligação"}
    if tipo not in tipos_validos:
        raise FeedbackError(f"Tipo inválido. Opções permitidas: {', '.join(tipos_validos)}.")

    status = str(payload.get("status", "")).strip()
    status_validos = {"Sucesso", "Sem sucesso"}
    if status not in status_validos:
        raise FeedbackError(f"Status inválido. Opções permitidas: {', '.join(status_validos)}.")

    data_informada = payload.get("data")
    if data_informada and isinstance(data_informada, str):
        data_registro = data_informada.strip()
    else:
        data_registro = agora_brasilia()

    return {
        "id": f"act-{uuid.uuid4().hex[:8]}",
        "nomusId": nomus_id,
        "usuario": str(payload.get("usuario") or payload.get("vendedor") or "Natália").strip() or "Natália",
        "tipo": tipo,
        "status": status,
        "data": data_registro,
        "observacao": str(payload.get("observacao", "")).strip(),
    }


def carregar_atividades() -> list[dict[str, Any]]:
    if not ARQUIVO_ATIVIDADES.exists():
        return []
    try:
        with open(ARQUIVO_ATIVIDADES, "r", encoding="utf-8") as f:
            conteudo = json.load(f)
            return conteudo if isinstance(conteudo, list) else []
    except Exception:
        return []


ETAPAS_FUNIL = {"orcamentos", "negociacoes", "producao", "perdido"}


def _bate_proposta(item: dict[str, Any], alvo: str) -> bool:
    for campo in ("id_proposta", "numero_proposta"):
        valor = item.get(campo)
        if valor not in (None, "") and str(valor).strip() == alvo:
            return True
    return False


def atualizar_status_proposta(payload: Any) -> dict[str, Any]:
    """Grava etapa_kanban ou a perda indexada ao proposta_id, sem mexer em etapa_vendas."""
    if not isinstance(payload, dict):
        raise FeedbackError("O corpo da requisição precisa ser um objeto JSON.")
    proposta_id = payload.get("proposta_id")
    if proposta_id in (None, ""):
        raise FeedbackError("O campo 'proposta_id' é obrigatório.")
    alvo = str(proposta_id).strip()
    if not alvo:
        raise FeedbackError("O campo 'proposta_id' é obrigatório.")

    etapa = str(payload.get("etapa_kanban") or "").strip()
    if etapa and etapa not in ETAPAS_FUNIL:
        raise FeedbackError("Etapa de funil inválida.")
    motivo = str(payload.get("motivo") or "").strip()
    if etapa == "perdido" and not motivo:
        raise FeedbackError("O motivo da perda é obrigatório.")

    if not CAMINHO_DADOS.exists():
        raise FeedbackError("Arquivo dados_ehe.json não encontrado.")

    with open(CAMINHO_DADOS, "r", encoding="utf-8") as arquivo:
        dados = json.load(arquivo)
    if not isinstance(dados, dict) or not isinstance(dados.get("clientes"), list):
        raise FeedbackError("A base local não tem a lista de clientes.")

    orcamento = None
    for cliente in dados["clientes"]:
        if not isinstance(cliente, dict):
            continue
        for item in cliente.get("orcamentos") or []:
            if isinstance(item, dict) and _bate_proposta(item, alvo):
                orcamento = item
                break
        if orcamento:
            break
    if not orcamento:
        raise FeedbackError("Proposta não encontrada na base local.")

    if etapa and etapa != "perdido":
        orcamento["etapa_kanban"] = etapa
    if etapa == "perdido" or motivo:
        orcamento["status_orcamento"] = "Perdido"
        registro = {
            "proposta_id": alvo,
            "categoria": str(payload.get("categoria") or "").strip(),
            "motivo": motivo,
            "observacao": str(payload.get("observacao") or "").strip(),
            "data": agora_brasilia(),
        }
        perdas = dados.get("perdas_por_proposta")
        if not isinstance(perdas, dict):
            perdas = {}
            dados["perdas_por_proposta"] = perdas
        perdas[alvo] = registro

    with open(CAMINHO_DADOS, "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)
    return {
        "proposta_id": alvo,
        "etapa_kanban": orcamento.get("etapa_kanban") or "",
        "status_orcamento": orcamento.get("status_orcamento") or "",
    }


def registrar_atividade(payload: Any) -> dict[str, Any]:
    item = validar_atividade(payload)
    PASTA_OUTPUT.mkdir(parents=True, exist_ok=True)
    itens = carregar_atividades()
    itens.insert(0, item)  # mais recente primeiro

    with open(ARQUIVO_ATIVIDADES, "w", encoding="utf-8") as f:
        json.dump(itens, f, ensure_ascii=False, indent=2)
    return item


class FeedbackHandler(SimpleHTTPRequestHandler):
    """Serve a interface web e responde aos endpoints da API interna."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(RAIZ), **kwargs)

    def _json(self, status: int, payload: dict[str, Any] | list[Any]) -> None:
        corpo = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/atividades":
            params = parse_qs(parsed.query)
            todas = carregar_atividades()

            if "nomusId" in params:
                try:
                    filtro_id = int(params["nomusId"][0])
                    todas = [a for a in todas if a.get("nomusId") == filtro_id]
                except ValueError:
                    pass

            if "vendedor" in params:
                filtro_v = params["vendedor"][0].strip().lower()
                todas = [a for a in todas if str(a.get("usuario", "")).lower() == filtro_v]

            self._json(200, todas)
            return

        super().do_GET()

    def do_POST(self) -> None:
        caminho = urlparse(self.path).path
        tamanho = int(self.headers.get("Content-Length") or 0)
        if tamanho <= 0 or tamanho > LIMITE_CORPO:
            self._json(400, {"erro": "Corpo da requisição ausente ou grande demais."})
            return

        try:
            payload = json.loads(self.rfile.read(tamanho).decode("utf-8"))
        except json.JSONDecodeError:
            self._json(400, {"erro": "O corpo não é um JSON válido."})
            return

        if caminho == "/api/feedback":
            try:
                item = registrar_sugestao(payload)
                self._json(201, {"ok": True, "item": item})
            except FeedbackError as exc:
                self._json(400, {"erro": str(exc)})
            return

        if caminho == "/api/clientes/contatos":
            try:
                if not isinstance(payload, dict):
                    raise FeedbackError("O corpo da requisição precisa ser um objeto JSON.")
                contatos = payload.get("contatos")
                if not isinstance(contatos, list):
                    raise FeedbackError("O campo 'contatos' precisa ser uma lista.")
                if not CAMINHO_DADOS.exists():
                    self._json(404, {"erro": "Arquivo dados_ehe.json não encontrado."})
                    return
                with open(CAMINHO_DADOS, "r", encoding="utf-8") as f:
                    dados = json.load(f)
                clientes = dados.get("clientes") if isinstance(dados, dict) else None
                if not isinstance(clientes, list):
                    raise FeedbackError("A base local não tem a lista de clientes.")
                alvo_id = str(payload.get("id") or "")
                alvo_nomus = payload.get("nomusId")
                cliente = None
                for item in clientes:
                    if alvo_id and str(item.get("id")) == alvo_id:
                        cliente = item
                        break
                    if alvo_nomus is not None and item.get("nomusId") == alvo_nomus:
                        cliente = item
                        break
                if not cliente:
                    self._json(404, {"erro": "Cliente não encontrado na base local."})
                    return
                cliente["contatos"] = [
                    {
                        "nome": str(c.get("nome") or "").strip(),
                        "cargo": str(c.get("cargo") or "").strip(),
                        "departamento": str(c.get("departamento") or "").strip(),
                        "telefone": str(c.get("telefone") or "").strip(),
                        "email": str(c.get("email") or "").strip(),
                    }
                    for c in contatos
                    if isinstance(c, dict) and str(c.get("nome") or "").strip()
                ]
                with open(CAMINHO_DADOS, "w", encoding="utf-8") as f:
                    json.dump(dados, f, ensure_ascii=False, indent=2)
                self._json(200, {"sucesso": True, "contatos": cliente["contatos"]})
            except FeedbackError as exc:
                self._json(400, {"erro": str(exc)})
            return

        if caminho == "/api/propostas/status":
            try:
                item = atualizar_status_proposta(payload)
                self._json(200, {"sucesso": True, "proposta": item})
            except FeedbackError as exc:
                self._json(400, {"erro": str(exc)})
            return

        if caminho == "/api/atividades":
            try:
                item = registrar_atividade(payload)
                self._json(201, {"sucesso": True, "atividade": item})
            except FeedbackError as exc:
                self._json(400, {"erro": str(exc)})
            return

        if caminho == "/api/clientes":
            try:
                if not isinstance(payload, dict):
                    raise FeedbackError("O corpo da requisição precisa ser um objeto JSON.")
                payload_nomus = {
                    "razaoSocial": str(payload.get("razaoSocial") or "").strip(),
                    "nomeFantasia": str(payload.get("nomeFantasia") or "").strip(),
                    "cnpj": str(payload.get("cnpj") or "").strip(),
                    "tipoPessoa": payload.get("tipoPessoa", 1),
                    "telefone": str(payload.get("telefone") or "").strip(),
                    "email": str(payload.get("email") or "").strip(),
                    "observacoes": str(payload.get("observacoes") or payload.get("anotacoes") or "").strip(),
                    "logradouro": str(payload.get("logradouro") or "").strip(),
                    "bairro": str(payload.get("bairro") or "").strip(),
                    "cidade": str(payload.get("cidade") or "").strip(),
                    "uf": str(payload.get("uf") or "").strip(),
                    "cep": str(payload.get("cep") or "").strip(),
                }
                if not payload_nomus["razaoSocial"]:
                    raise FeedbackError("O campo 'razaoSocial' é obrigatório.")

                from backend.nomus_client import NomusClient

                client = NomusClient()
                resp = client.criar_cliente(payload_nomus)
                id_nomus = resp.get("id") or resp.get("nomusId")
                if id_nomus is None:
                    self._json(502, {"sucesso": False, "erro": "O Nomus não devolveu o id do cliente criado."})
                    return

                novo_cliente = {
                    "id": f"nomus-{id_nomus}",
                    "nomusId": id_nomus,
                    "razaoSocial": payload_nomus["razaoSocial"],
                    "nomeFantasia": payload_nomus["nomeFantasia"],
                    "cnpj": payload_nomus["cnpj"],
                    "tipoPessoa": payload_nomus["tipoPessoa"],
                    "telefone": payload_nomus["telefone"],
                    "email": payload_nomus["email"],
                    "anotacoes": payload_nomus["observacoes"],
                    "cidade": payload_nomus["cidade"],
                    "uf": payload_nomus["uf"],
                    "logradouro": payload_nomus["logradouro"],
                    "bairro": payload_nomus["bairro"],
                    "cep": payload_nomus["cep"],
                    "pedidos": [],
                    "orcamentos": [],
                }

                PASTA_OUTPUT.mkdir(parents=True, exist_ok=True)
                dados: dict[str, Any] = {"clientes": []}
                if CAMINHO_DADOS.exists():
                    with open(CAMINHO_DADOS, "r", encoding="utf-8") as f:
                        carregado = json.load(f)
                    if isinstance(carregado, dict):
                        dados = carregado
                if not isinstance(dados.get("clientes"), list):
                    dados["clientes"] = []
                dados["clientes"].insert(0, novo_cliente)
                with open(CAMINHO_DADOS, "w", encoding="utf-8") as f:
                    json.dump(dados, f, ensure_ascii=False, indent=2)

                self._json(201, {"sucesso": True, "cliente": novo_cliente})
            except FeedbackError as exc:
                self._json(400, {"sucesso": False, "erro": str(exc)})
            except Exception as exc:
                self._json(500, {"sucesso": False, "erro": str(exc)})
            return

        self.send_error(404)

    def do_PUT(self) -> None:
        caminho = urlparse(self.path).path
        match = re.match(r"^/api/clientes/(\d+)$", caminho)
        if not match:
            self.send_error(404, "Rota não encontrada")
            return

        id_cliente = int(match.group(1))
        tamanho = int(self.headers.get("Content-Length") or 0)
        if tamanho <= 0 or tamanho > LIMITE_CORPO:
            self._json(400, {"erro": "Corpo da requisição ausente ou inválido."})
            return

        try:
            dados_novos = json.loads(self.rfile.read(tamanho).decode("utf-8"))
        except Exception:
            self._json(400, {"erro": "JSON inválido."})
            return

        if not CAMINHO_DADOS.exists():
            self._json(404, {"erro": "Arquivo dados_ehe.json não encontrado."})
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
                self._json(404, {"erro": f"Cliente {id_cliente} não encontrado na base local."})
                return

            nome_display = cliente.get("nomeFantasia") or cliente.get("razaoSocial") or ""
            payload_nomus = {
                "id": id_cliente,
                "nome": dados_novos.get("nomeFantasia") or dados_novos.get("razaoSocial") or nome_display,
                "razaoSocial": dados_novos.get("razaoSocial", cliente.get("razaoSocial") or nome_display),
                "nomeFantasia": dados_novos.get("nomeFantasia", cliente.get("nomeFantasia", "")),
                "cnpj": dados_novos.get("cnpj", cliente.get("cnpj") or ""),
                "tipoPessoa": dados_novos.get("tipoPessoa", cliente.get("tipoPessoa", 1)),
                "ativo": cliente.get("ativoNomus", True),
                "telefone": dados_novos.get("telefone", cliente.get("telefone", "")),
                "email": dados_novos.get("email", cliente.get("email", "")),
                "observacoes": dados_novos.get("observacoes", cliente.get("anotacoes", "")),
                "logradouro": dados_novos.get("logradouro", cliente.get("logradouro", "")),
                "bairro": dados_novos.get("bairro", cliente.get("bairro", "")),
                "cidade": dados_novos.get("cidade", cliente.get("cidade", "")),
                "uf": dados_novos.get("uf", cliente.get("uf", "")),
                "cep": dados_novos.get("cep", cliente.get("cep", "")),
            }

            from backend.nomus_client import NomusClient
            client = NomusClient()
            client.atualizar_cliente(id_cliente, payload_nomus)

            cliente["razaoSocial"] = payload_nomus["razaoSocial"]
            cliente["nomeFantasia"] = payload_nomus["nomeFantasia"]
            cliente["cnpj"] = payload_nomus["cnpj"]
            cliente["tipoPessoa"] = payload_nomus["tipoPessoa"]
            cliente["telefone"] = payload_nomus["telefone"]
            cliente["email"] = payload_nomus["email"]
            cliente["anotacoes"] = payload_nomus["observacoes"]
            cliente["logradouro"] = payload_nomus["logradouro"]
            cliente["bairro"] = payload_nomus["bairro"]
            cliente["cidade"] = payload_nomus["cidade"]
            cliente["uf"] = payload_nomus["uf"]
            cliente["cep"] = payload_nomus["cep"]

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
    print("Endpoints ativos: POST /api/feedback | POST /api/clientes | POST /api/clientes/contatos | POST /api/propostas/status | PUT /api/clientes/<id> | GET/POST /api/atividades", flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor encerrado.", flush=True)
    finally:
        servidor.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
