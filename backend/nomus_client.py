"""Cliente HTTP da Fase 1: lê o Nomus e recua quando a cota do gateway aperta.

Entre páginas bem-sucedidas há 1,5 s. A sessão repete 429 e falha de
gateway com urllib3: 5 tentativas, backoff de 2, 4, 8, 16 e 32 s, e obedece
Retry-After. Se a resposta ainda for 429, o método `_get` espera o inteiro
do cabeçalho ou um backoff com jitter.
"""

from __future__ import annotations

import os
import random
import time
from collections.abc import Callable, Iterable, Iterator
from itertools import takewhile
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

RECURSO_PEDIDOS = "pedidos"
QUERY_PEDIDO_VENDA = "idTipoPedido=2"
RECURSOS = ("clientes", "produtos", RECURSO_PEDIDOS)
STATUS_PARA_REPETIR = frozenset({406, 429, 500, 502, 503, 504})
STATUS_ADAPTADOR = [429, 500, 502, 503, 504]
PAGINAS_MAXIMAS = 500
INTERVALO_PAGINA = 1.5
TIMEOUT_PROCESSO = 60
INTERVALO_PRODUTO = 1.0
TENTATIVAS_RESPOSTA = 5
BASE_DELAY = 2
PAGINAS_PEDIDOS_RECENTES = 10
PAGINAS_CLIENTES_RECENTES = 3


class NomusError(Exception):
    """Falha de consulta que o operador consegue corrigir ou repetir."""


class NomusAuthError(NomusError):
    """Token ausente ou recusado. A mensagem nunca inclui o segredo."""


class NomusClient:
    """Sessão única para /clientes, /produtos, /pedidos, /processos e /nfes.

    A paginação para quando a página volta vazia. Depois de cada página
    bem-sucedida, a próxima espera 1,5 s. O 429 que sobrevive ao adaptador
    espera Retry-After ou o backoff com jitter, no máximo cinco vezes.
    """

    def __init__(
        self,
        base_url: str | None = None,
        auth_token: str | None = None,
        session: requests.Session | None = None,
        timeout: float = 30,
        max_tentativas: int = TENTATIVAS_RESPOSTA,
        espera_pagina: float = INTERVALO_PAGINA,
        max_paginas: int = PAGINAS_MAXIMAS,
        dormir: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = (base_url or os.environ.get("NOMUS_BASE_URL", "")).strip().rstrip("/")
        self._token = (auth_token if auth_token is not None else os.environ.get("NOMUS_AUTH_TOKEN", "")).strip()
        if not self.base_url:
            raise NomusAuthError("Defina NOMUS_BASE_URL no ambiente. Veja .env.example.")
        if not self._token:
            raise NomusAuthError("Defina NOMUS_AUTH_TOKEN no ambiente. O token não fica no código.")
        self.timeout = timeout
        self.max_tentativas = max_tentativas
        self.espera_pagina = espera_pagina
        self.max_paginas = max_paginas
        self._dormir = dormir
        self._ultima_pagina_ok = False
        self._houve_consulta_produto = False
        self.cache_produtos: dict[int, dict[str, Any]] = {}
        self._produtos_ausentes: set[int] = set()
        self.session = session or requests.Session()
        self.retentativa = self._montar_retentativas()
        self.session.headers.update(
            {
                "Authorization": f"Basic {self._token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

    def fechar(self) -> None:
        self.session.close()

    def _montar_retentativas(self) -> Retry:
        """Adaptador nativo: 5 tentativas, backoff 2 s e Retry-After do Nomus."""
        politica = _politica_retry()
        if hasattr(self.session, "mount"):
            self.session.mount("https://", HTTPAdapter(max_retries=_politica_retry()))
            self.session.mount("http://", HTTPAdapter(max_retries=_politica_retry()))
        return politica

    def atualizar_cliente(self, id_cliente: int, payload: dict[str, Any]) -> dict[str, Any]:
        """Atualiza dados cadastrais de um cliente no Nomus via PUT /clientes/:id."""
        url = f"{self.base_url}/clientes/{int(id_cliente)}"
        try:
            resposta = self.session.put(url, json=payload, timeout=self.timeout)
        except requests.RequestException as exc:
            raise NomusError(f"Falha de conexão ao atualizar cliente {id_cliente}: {exc}") from exc

        if resposta.status_code in {401, 403}:
            raise NomusAuthError("O Nomus recusou a autenticação ou permissão de escrita. Confira NOMUS_AUTH_TOKEN.")

        if resposta.status_code not in {200, 201, 204}:
            raise NomusError(
                f"O Nomus respondeu status {resposta.status_code} ao atualizar cliente {id_cliente}. {_detalhe(resposta, self._token)}"
            )

        if resposta.status_code == 204 or not resposta.content:
            return {"id": id_cliente, "sucesso": True}

        try:
            return resposta.json()
        except ValueError as exc:
            raise NomusError(f"A resposta da atualização do cliente {id_cliente} não é um JSON válido.") from exc

    def criar_cliente(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Cria um cliente no Nomus via POST /clientes e devolve o JSON com o id gerado."""
        url = f"{self.base_url}/clientes"
        try:
            resposta = self.session.post(url, json=payload, timeout=self.timeout)
        except requests.RequestException as exc:
            raise NomusError(f"Falha de conexão ao criar cliente: {exc}") from exc

        if resposta.status_code in {401, 403}:
            raise NomusAuthError("O Nomus recusou a autenticação ou permissão de escrita. Confira NOMUS_AUTH_TOKEN.")

        if resposta.status_code not in {200, 201}:
            raise NomusError(
                f"O Nomus respondeu status {resposta.status_code} ao criar cliente. {_detalhe(resposta, self._token)}"
            )

        try:
            corpo = resposta.json()
        except ValueError as exc:
            raise NomusError("A resposta da criação do cliente não é um JSON válido.") from exc
        if not isinstance(corpo, dict):
            raise NomusError("A resposta da criação do cliente não veio como objeto.")
        return corpo

    def listar_clientes(self) -> list[dict[str, Any]]:
        return self.listar("clientes")

    def listar_clientes_recentes(self, ids_conhecidos: set[str] | None = None) -> list[dict[str, Any]]:
        """Até 3 páginas de /clientes, do id maior para o menor.

        A página 1 do Nomus vem primeiro. A busca para no primeiro id que já
        está no arquivo local, para não reler a base inteira.
        """
        conhecidos = set(ids_conhecidos or ())
        coletados: list[dict[str, Any]] = []
        assinaturas: set[str] = set()
        for pagina in range(1, PAGINAS_CLIENTES_RECENTES + 1):
            _anunciar_pagina("clientes", pagina)
            payload = self._get("clientes", {"pagina": pagina})
            linhas = _como_lista(payload, "clientes", pagina)
            if not linhas:
                break
            assinatura = _assinatura(linhas[0])
            if assinatura in assinaturas:
                break
            assinaturas.add(assinatura)
            encerrar = False
            ordenados = sorted(linhas, key=lambda item: _inteiro_opcional(item.get("id")) or 0, reverse=True)
            for cliente in ordenados:
                ident = cliente.get("id")
                if ident is not None and f"id:{ident}" in conhecidos:
                    encerrar = True
                    break
                coletados.append(cliente)
            if encerrar:
                break
        return coletados

    def listar_produtos(self) -> list[dict[str, Any]]:
        return self.listar("produtos")

    def listar_pedidos_venda(self) -> list[dict[str, Any]]:
        return self.listar(RECURSO_PEDIDOS)

    def semear_produtos(self, produtos: Iterable[dict[str, Any]]) -> None:
        """Guarda produtos já conhecidos para não pedir o mesmo id de novo."""
        for produto in produtos:
            if not isinstance(produto, dict):
                continue
            ident = _inteiro_opcional(produto.get("id"))
            if ident is None:
                continue
            self.cache_produtos[ident] = produto
            self._produtos_ausentes.discard(ident)

    def obter_produto(self, produto_id: int) -> dict[str, Any] | None:
        """Devolve o produto do cache. Só consulta o Nomus na primeira vez."""
        ident = int(produto_id)
        if ident in self.cache_produtos or ident in self._produtos_ausentes:
            print(f"[Cache] Produto {ident} já conhecido, ignorando requisição.", flush=True)
            return self.cache_produtos.get(ident)
        if self._houve_consulta_produto:
            self._dormir(INTERVALO_PRODUTO)
        print(f"[Nomus] Consultando detalhes do produto {ident}...", flush=True)
        self._houve_consulta_produto = True
        payload = self._get(f"produtos/{ident}", {}, vazio_se=frozenset({404}), pausar=False)
        if not isinstance(payload, dict):
            self._produtos_ausentes.add(ident)
            return None
        if payload.get("id") is None:
            payload = {**payload, "id": ident}
        self.cache_produtos[ident] = payload
        return payload

    def garantir_produtos(self, ids: Iterable[int]) -> list[dict[str, Any]]:
        """Completa o cache com os ids citados e devolve os produtos conhecidos."""
        for produto_id in ids:
            self.obter_produto(int(produto_id))
        return list(self.cache_produtos.values())

    def listar_pedidos_recentes(self, conhecidos: set[str] | None = None) -> list[dict[str, Any]]:
        """Lê no máximo 10 páginas de /pedidos?query=idTipoPedido=2, da mais nova para a mais antiga.

        idTipoPedido=2 é o pedido de venda. A primeira página do Nomus já traz
        os mais recentes. A busca para no primeiro pedido que já está no
        histórico local. A pausa de 1,5 s fica no `_get`.
        """
        ja_vistos = set(conhecidos or ())
        coletados: list[dict[str, Any]] = []
        assinaturas: set[str] = set()
        for pagina in range(1, PAGINAS_PEDIDOS_RECENTES + 1):
            _anunciar_pagina(RECURSO_PEDIDOS, pagina)
            payload = self._get(RECURSO_PEDIDOS, {"query": QUERY_PEDIDO_VENDA, "pagina": pagina})
            linhas = _como_lista(payload, RECURSO_PEDIDOS, pagina)
            if not linhas:
                break
            assinatura = _assinatura(linhas[0])
            if assinatura in assinaturas:
                break
            assinaturas.add(assinatura)
            encerrar = False
            for pedido in sorted(linhas, key=_chave_recente, reverse=True):
                if ja_vistos and chaves_de_pedido(pedido) & ja_vistos:
                    encerrar = True
                    break
                coletados.append(pedido)
            if encerrar:
                break
        return coletados

    def listar_processos(self, paginas: int = 3) -> list[dict[str, Any]]:
        """Lê /processos com timeout de 60 s e a pausa de 1,5 s entre páginas."""
        return [
            item
            for item in self._listar_paginas("processos", paginas, timeout=TIMEOUT_PROCESSO)
            if _equipe_e_vendas(item)
        ]

    def listar_nfes(self, paginas: int = 3) -> list[dict[str, Any]]:
        """Lê /nfes nas páginas pedidas, com o XML de cada nota."""
        return self._listar_paginas("nfes", paginas)

    def _listar_paginas(self, recurso: str, paginas: int, timeout: float | None = None) -> list[dict[str, Any]]:
        """Paginação curta. A pausa de 1,5 s entre páginas bem-sucedidas fica no `_get`."""
        coletados: list[dict[str, Any]] = []
        assinaturas: set[str] = set()
        limite = max(0, int(paginas))
        for pagina in range(1, limite + 1):
            _anunciar_pagina(recurso, pagina)
            payload = self._get(recurso, {"pagina": pagina}, timeout=timeout)
            linhas = _como_lista(payload, recurso, pagina)
            if not linhas:
                break
            assinatura = _assinatura(linhas[0])
            if assinatura in assinaturas:
                break
            assinaturas.add(assinatura)
            coletados.extend(linhas)
        return coletados

    def listar(self, recurso: str) -> list[dict[str, Any]]:
        if recurso not in RECURSOS:
            raise NomusError(f"Recurso Nomus desconhecido: {recurso}")
        return list(self._paginas(recurso))

    def _paginas(self, recurso: str) -> Iterator[dict[str, Any]]:
        vistos: set[str] = set()
        for pagina in range(1, self.max_paginas + 1):
            _anunciar_pagina(recurso, pagina)
            payload = self._get(recurso, {"pagina": pagina})
            linhas = _como_lista(payload, recurso, pagina)
            if not linhas:
                return
            assinatura = _assinatura(linhas[0])
            if assinatura in vistos:
                return
            vistos.add(assinatura)
            yield from linhas
        raise NomusError(
            f"A paginação de /{recurso} passou de {self.max_paginas} páginas. A consulta foi interrompida."
        )

    def _pausa_entre_paginas(self) -> None:
        """1,5 s depois de uma página que já voltou, antes da próxima."""
        if self._ultima_pagina_ok and self.espera_pagina:
            self._dormir(self.espera_pagina)
        self._ultima_pagina_ok = False

    def _get(
        self,
        recurso: str,
        params: dict[str, Any],
        *,
        vazio_se: frozenset[int] | None = None,
        pausar: bool = True,
        timeout: float | None = None,
    ) -> Any:
        url = f"{self.base_url}/{recurso}"
        prazo = self.timeout if timeout is None else timeout
        if pausar:
            self._pausa_entre_paginas()
        ultimo_status = 0
        for tentativa in range(self.max_tentativas):
            try:
                resposta = self.session.get(url, params=params, timeout=prazo)
            except requests.RequestException as exc:
                ultimo_status = 0
                if tentativa >= self.max_tentativas - 1:
                    raise NomusError(f"Sem resposta de /{recurso} depois de {tentativa + 1} tentativas.") from exc
                self._dormir(espera_recuo(tentativa, None))
                continue

            ultimo_status = resposta.status_code
            if resposta.status_code in {401, 403}:
                raise NomusAuthError("O Nomus recusou a autenticação. Confira NOMUS_AUTH_TOKEN.")
            if resposta.status_code in STATUS_PARA_REPETIR:
                if tentativa >= self.max_tentativas - 1:
                    break
                cabecalho = resposta.headers.get("Retry-After") if resposta.status_code == 429 else None
                espera = espera_recuo(tentativa, cabecalho)
                if resposta.status_code == 429:
                    print(
                        f"[Nomus] Limite 429 detectado em {recurso}. Aguardando {espera}s...",
                        flush=True,
                    )
                self._dormir(espera)
                continue
            if vazio_se and resposta.status_code in vazio_se:
                self._ultima_pagina_ok = True
                return None
            if resposta.status_code == 204 or not resposta.content:
                self._ultima_pagina_ok = True
                return []
            try:
                resposta.raise_for_status()
            except requests.HTTPError as exc:
                raise NomusError(
                    f"O Nomus respondeu {resposta.status_code} em /{recurso}. {_detalhe(resposta, self._token)}"
                ) from exc
            try:
                payload = resposta.json()
            except ValueError as exc:
                raise NomusError(f"A resposta de /{recurso} não é JSON.") from exc
            self._ultima_pagina_ok = True
            return payload

        if ultimo_status == 429:
            raise NomusError(f"O Nomus respondeu 429 em /{recurso} depois de {self.max_tentativas} tentativas.")
        raise NomusError(
            f"O Nomus manteve o status {ultimo_status} em /{recurso} depois de {self.max_tentativas} tentativas."
        )


class RecuoNomus(Retry):
    """O Retry do urllib3 zera a primeira espera. Aqui a série começa em 2 s."""

    def get_backoff_time(self) -> float:
        consecutivos = len(
            list(takewhile(lambda item: item.redirect_location is None, reversed(self.history)))
        )
        if consecutivos <= 0:
            return 0.0
        valor = self.backoff_factor * (2 ** (consecutivos - 1))
        return float(max(0, min(self.backoff_max, valor)))


def _equipe_e_vendas(registro: dict[str, Any]) -> bool:
    equipe = registro.get("equipe")
    if isinstance(equipe, dict):
        equipe = equipe.get("nome") or equipe.get("descricao") or ""
    return str(equipe or "").strip().casefold() == "vendas"


def _anunciar_pagina(recurso: str, pagina: int) -> None:
    print(f"[Nomus] Lendo {recurso} - Página {pagina}...", flush=True)


def _politica_retry() -> RecuoNomus:
    return RecuoNomus(
        total=TENTATIVAS_RESPOSTA,
        backoff_factor=BASE_DELAY,
        status_forcelist=list(STATUS_ADAPTADOR),
        respect_retry_after_header=True,
        raise_on_status=False,
    )


def espera_recuo(tentativa: int, retry_after: str | None) -> float:
    """429: o inteiro de Retry-After, ou base * 2^tentativa mais jitter."""
    if retry_after is not None and str(retry_after).strip():
        texto = str(retry_after).strip()
        try:
            return float(int(texto))
        except ValueError:
            try:
                return float(int(float(texto)))
            except ValueError:
                pass
    return (BASE_DELAY * (2**tentativa)) + random.uniform(0.5, 1.5)


def _como_lista(payload: Any, recurso: str, pagina: int) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise NomusError(
            f"/{recurso} página {pagina} não veio como lista. A paginação espera [] quando acaba."
        )
    for item in payload:
        if not isinstance(item, dict):
            raise NomusError(f"/{recurso} página {pagina} trouxe um item que não é objeto.")
    return payload


def chaves_de_pedido(pedido: dict[str, Any]) -> set[str]:
    """Identidade usada para reconhecer um pedido que já está no JSON local."""
    chaves: set[str] = set()
    identificador = pedido.get("id")
    if identificador is not None and identificador != "":
        chaves.add(f"id:{identificador}")
    for campo in ("codigoPedido", "codigo"):
        codigo = pedido.get(campo)
        if codigo is not None and str(codigo).strip():
            chaves.add(f"codigo:{str(codigo).strip()}")
    return chaves


def _assinatura(registro: dict[str, Any]) -> str:
    identificador = registro.get("id")
    if identificador is not None:
        return str(identificador)
    return repr(sorted(registro.keys()))


def _inteiro_opcional(valor: Any) -> int | None:
    if isinstance(valor, bool) or valor is None or valor == "":
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _chave_recente(pedido: dict[str, Any]) -> tuple[tuple[int, int, int, int, int, int], int]:
    texto = str(pedido.get("dataEmissao") or pedido.get("dataCriacao") or "").strip()
    ident = _inteiro_opcional(pedido.get("id")) or 0
    return (_data_para_ordem(texto), ident)


def _data_para_ordem(texto: str) -> tuple[int, int, int, int, int, int]:
    if not texto:
        return (0, 0, 0, 0, 0, 0)
    partes = texto.split()
    dia_mes_ano = partes[0].split("/")
    if len(dia_mes_ano) != 3:
        return (0, 0, 0, 0, 0, 0)
    try:
        dia, mes, ano = (int(parte) for parte in dia_mes_ano)
    except ValueError:
        return (0, 0, 0, 0, 0, 0)
    hora = minuto = segundo = 0
    if len(partes) > 1:
        try:
            numeros = [int(parte) for parte in partes[1].split(":")]
        except ValueError:
            numeros = []
        if numeros:
            hora = numeros[0]
        if len(numeros) > 1:
            minuto = numeros[1]
        if len(numeros) > 2:
            segundo = numeros[2]
    return (ano, mes, dia, hora, minuto, segundo)


def _detalhe(resposta: requests.Response, token: str) -> str:
    texto = (resposta.text or "").replace(token, "[redigido]").strip().replace("\n", " ")
    if not texto:
        return ""
    return texto[:180]
