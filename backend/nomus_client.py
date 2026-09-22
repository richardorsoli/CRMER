"""Cliente HTTP da Fase 1: lê o Nomus, pagina e espera quando a API pede recuo."""

from __future__ import annotations

import os
import random
import time
from collections.abc import Callable, Iterator
from typing import Any

import requests

RECURSOS = ("clientes", "produtos", "pedidos-venda")
STATUS_PARA_REPETIR = frozenset({406, 429, 500, 502, 503, 504})
PAGINAS_MAXIMAS = 500


class NomusError(Exception):
    """Falha de consulta que o operador consegue corrigir ou repetir."""


class NomusAuthError(NomusError):
    """Token ausente ou recusado. A mensagem nunca inclui o segredo."""


class NomusClient:
    """Sessão única para /clientes, /produtos e /pedidos-venda.

    A paginação para quando a página volta vazia. 406 e 429 (e falhas
    transitórias de servidor) repetem com espera exponencial.
    """

    def __init__(
        self,
        base_url: str | None = None,
        auth_token: str | None = None,
        session: requests.Session | None = None,
        timeout: float = 30,
        max_tentativas: int = 5,
        espera_pagina: float = 0.4,
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
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Basic {self._token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

    def fechar(self) -> None:
        self.session.close()

    def listar_clientes(self) -> list[dict[str, Any]]:
        return self.listar("clientes")

    def listar_produtos(self) -> list[dict[str, Any]]:
        return self.listar("produtos")

    def listar_pedidos_venda(self) -> list[dict[str, Any]]:
        return self.listar("pedidos-venda")

    def listar(self, recurso: str) -> list[dict[str, Any]]:
        if recurso not in RECURSOS:
            raise NomusError(f"Recurso Nomus desconhecido: {recurso}")
        return list(self._paginas(recurso))

    def _paginas(self, recurso: str) -> Iterator[dict[str, Any]]:
        vistos: set[str] = set()
        for pagina in range(1, self.max_paginas + 1):
            payload = self._get(recurso, {"pagina": pagina})
            linhas = _como_lista(payload, recurso, pagina)
            if not linhas:
                return
            assinatura = _assinatura(linhas[0])
            if assinatura in vistos:
                return
            vistos.add(assinatura)
            yield from linhas
            if self.espera_pagina:
                self._dormir(self.espera_pagina)
        raise NomusError(
            f"A paginação de /{recurso} passou de {self.max_paginas} páginas. A consulta foi interrompida."
        )

    def _get(self, recurso: str, params: dict[str, Any]) -> Any:
        url = f"{self.base_url}/{recurso}"
        ultimo_status = 0
        for tentativa in range(self.max_tentativas + 1):
            try:
                resposta = self.session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                if tentativa >= self.max_tentativas:
                    raise NomusError(f"Sem resposta de /{recurso} depois de {tentativa + 1} tentativas.") from exc
                self._dormir(self._espera(tentativa, None))
                continue

            ultimo_status = resposta.status_code
            if resposta.status_code in {401, 403}:
                raise NomusAuthError("O Nomus recusou a autenticação. Confira NOMUS_AUTH_TOKEN.")
            if resposta.status_code in STATUS_PARA_REPETIR:
                if tentativa >= self.max_tentativas:
                    break
                self._dormir(self._espera(tentativa, resposta.headers.get("Retry-After")))
                continue
            if resposta.status_code == 204 or not resposta.content:
                return []
            try:
                resposta.raise_for_status()
            except requests.HTTPError as exc:
                raise NomusError(
                    f"O Nomus respondeu {resposta.status_code} em /{recurso}. {_detalhe(resposta, self._token)}"
                ) from exc
            try:
                return resposta.json()
            except ValueError as exc:
                raise NomusError(f"A resposta de /{recurso} não é JSON.") from exc

        raise NomusError(
            f"O Nomus manteve o status {ultimo_status} em /{recurso} depois de {self.max_tentativas + 1} tentativas."
        )

    @staticmethod
    def _espera(tentativa: int, retry_after: str | None) -> float:
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                pass
        base = min(32.0, 0.5 * (2**tentativa))
        return base + random.uniform(0, 0.25)


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


def _assinatura(registro: dict[str, Any]) -> str:
    identificador = registro.get("id")
    if identificador is not None:
        return str(identificador)
    return repr(sorted(registro.keys()))


def _detalhe(resposta: requests.Response, token: str) -> str:
    texto = (resposta.text or "").replace(token, "[redigido]").strip().replace("\n", " ")
    if not texto:
        return ""
    return texto[:180]
