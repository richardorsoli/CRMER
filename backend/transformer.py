"""Converte o payload do Nomus na ficha que a carteira do CRMER já entende.

Cada cliente sai em uma única fila. Processo de vendas na etapa
Proposta / Orçamentos alimenta a fila `resposta`. Sem esses processos,
a fila de orçamento continua vazia: /pedidos não traz proposta.
"""

from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DATA_REFERENCIA = date(2026, 9, 22)
VENDEDOR_NATALIA = 3237
INATIVIDADE_DIAS = 120
AGENDA_RECENTE_DIAS = 30
REAGENDAR_DIAS = 14
ENTREGA_PROXIMA_DIAS = 7
PEDIDOS_NA_FICHA = 12
LINHAS = ("Gás", "Saneamento", "Elétrica", "Fechamento")
Ranking = Literal["contato", "resposta", "sazonal", "inativos"]
ETAPA_PROPOSTA = "Proposta / Orçamentos"
_NS_NFE = {"nfe": "http://www.portalfiscal.inf.br/nfe"}
_STATUS_PROCESSO_FECHADO = frozenset(
    {"concluido", "concluida", "cancelado", "cancelada", "encerrado", "encerrada", "finalizado", "finalizada"}
)

_GRUPOS = {
    "gas": "Gás",
    "glp": "Gás",
    "saneamento": "Saneamento",
    "hidrometro": "Saneamento",
    "eletrica": "Elétrica",
    "fechamento": "Fechamento",
    "shaft": "Fechamento",
}

_MESES = (
    "",
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
)


def parse_ptbr_float(val: str) -> float:
    """Converte número pt-BR (`785,70`, `4.150,00`, `4150,00`) em float."""
    if not isinstance(val, str):
        raise TypeError("parse_ptbr_float espera str")
    text = val.strip().replace("R$", "").replace(" ", "")
    if not text:
        raise ValueError("valor vazio")
    negativo = text.startswith("-")
    text = text.lstrip("+-")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    elif text.count(".") > 1:
        text = text.replace(".", "")
    elif text.count(".") == 1:
        esquerda, direita = text.split(".")
        if esquerda.isdigit() and direita.isdigit() and len(direita) == 3:
            text = esquerda + direita
    try:
        numero = float(text)
    except ValueError as exc:
        raise ValueError(f"valor numérico inválido: {val!r}") from exc
    if numero != numero or numero in {float("inf"), float("-inf")}:
        raise ValueError(f"valor numérico inválido: {val!r}")
    return -numero if negativo else numero


def parse_nomus_date(val: str) -> datetime:
    """Lê `DD/MM/YYYY` ou `DD/MM/YYYY HH:mm:ss` como datetime ingênuo."""
    if not isinstance(val, str):
        raise TypeError("parse_nomus_date espera str")
    text = val.strip()
    for formato in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, formato)
        except ValueError:
            continue
    raise ValueError(f"data Nomus inválida: {val!r}")


def _dinheiro(valor: Any) -> float:
    if valor is None or valor == "":
        return 0.0
    if isinstance(valor, bool):
        raise ValueError("valor monetário inválido")
    if isinstance(valor, (int, float)):
        return float(valor)
    return parse_ptbr_float(str(valor))


def _data_opcional(valor: Any) -> datetime | None:
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    if isinstance(valor, datetime):
        return valor
    if isinstance(valor, date):
        return datetime(valor.year, valor.month, valor.day)
    return parse_nomus_date(str(valor))


def _texto(valor: Any) -> str:
    if valor is None:
        return ""
    return str(valor).strip()


def _dobrar(texto: str) -> str:
    base = unicodedata.normalize("NFD", texto or "")
    sem_acento = "".join(caractere for caractere in base if not unicodedata.combining(caractere))
    return sem_acento.casefold()


def _inteiro(valor: Any, campo: str) -> int:
    if isinstance(valor, bool) or valor is None or valor == "":
        raise ValueError(f"{campo} ausente")
    try:
        return int(valor)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{campo} inválido") from exc


class ModeloNomus(BaseModel):
    model_config = ConfigDict(extra="ignore")


class VendedorNomus(ModeloNomus):
    id: int
    nome: str = ""

    @field_validator("id", mode="before")
    @classmethod
    def _id(cls, valor: Any) -> int:
        return _inteiro(valor, "vendedor.id")


class ClienteNomus(ModeloNomus):
    id: int
    codigo: str = ""
    cnpj: str = ""
    ativo: bool = True
    razaoSocial: str = ""
    nome: str = ""
    email: str = ""
    telefone: str = ""
    endereco: str = ""
    numero: str = ""
    bairro: str = ""
    municipio: str = ""
    uf: str = ""
    cep: str = ""
    vendedores: list[VendedorNomus] = Field(default_factory=list)

    @field_validator("id", mode="before")
    @classmethod
    def _id(cls, valor: Any) -> int:
        return _inteiro(valor, "cliente.id")

    @field_validator("ativo", mode="before")
    @classmethod
    def _ativo(cls, valor: Any) -> bool:
        if isinstance(valor, str):
            return valor.strip().casefold() not in {"", "0", "false", "nao", "não"}
        return bool(valor) if valor is not None else True

    @field_validator(
        "codigo",
        "cnpj",
        "razaoSocial",
        "nome",
        "email",
        "telefone",
        "endereco",
        "numero",
        "bairro",
        "municipio",
        "uf",
        "cep",
        mode="before",
    )
    @classmethod
    def _campos_texto(cls, valor: Any) -> str:
        return _texto(valor)


class SetorEstoqueNomus(ModeloNomus):
    saldoEstoqueAtualEmpresa: float = 0

    @field_validator("saldoEstoqueAtualEmpresa", mode="before")
    @classmethod
    def _saldo(cls, valor: Any) -> float:
        return _dinheiro(valor)


class ProdutoNomus(ModeloNomus):
    id: int
    codigo: str = ""
    descricao: str = ""
    idGrupoProduto: int | None = None
    nomeGrupoProduto: str = ""
    nomeTipoProduto: str = ""
    custoPadraoCompra: float = 0
    siglaUnidadeMedida: str = ""
    empresasSetoresEstoque: list[SetorEstoqueNomus] = Field(default_factory=list)

    @field_validator("id", mode="before")
    @classmethod
    def _id(cls, valor: Any) -> int:
        return _inteiro(valor, "produto.id")

    @field_validator("custoPadraoCompra", mode="before")
    @classmethod
    def _custo(cls, valor: Any) -> float:
        return _dinheiro(valor)

    @field_validator("codigo", "descricao", "nomeGrupoProduto", "nomeTipoProduto", "siglaUnidadeMedida", mode="before")
    @classmethod
    def _campos_texto(cls, valor: Any) -> str:
        return _texto(valor)


class ItemPedidoNomus(ModeloNomus):
    idProduto: int | None = None
    quantidade: float = 0
    valorUnitario: float = 0
    status: int | None = None

    @field_validator("quantidade", "valorUnitario", mode="before")
    @classmethod
    def _numeros(cls, valor: Any) -> float:
        return _dinheiro(valor)

    @field_validator("idProduto", "status", mode="before")
    @classmethod
    def _ids(cls, valor: Any) -> int | None:
        if valor is None or valor == "":
            return None
        return _inteiro(valor, "item")


class PedidoNomus(ModeloNomus):
    id: int
    codigoPedido: str = ""
    idPessoaCliente: int | None = None
    idPessoaVendedor: int | None = None
    valorTotal: float = 0
    condicaoPagamentoTexto: str = ""
    observacoes: str = ""

    @model_validator(mode="before")
    @classmethod
    def _junta_observacao(cls, valor: Any) -> Any:
        if not isinstance(valor, dict) or valor.get("observacoes"):
            return valor
        texto = valor.get("observacao") or valor.get("observacaoPedido") or ""
        if not texto:
            return valor
        copia = dict(valor)
        copia["observacoes"] = texto
        return copia
    dataEmissao: datetime | None = None
    dataEntregaPadrao: datetime | None = None
    dataCriacao: datetime | None = None
    itensPedido: list[ItemPedidoNomus] = Field(default_factory=list)
    nfes: list[NfeVinculoNomus] = Field(default_factory=list)

    @field_validator("nfes", mode="before")
    @classmethod
    def _nfes(cls, valor: Any) -> list:
        if not isinstance(valor, list):
            return []
        return [item for item in valor if isinstance(item, dict)]

    @field_validator("id", mode="before")
    @classmethod
    def _id(cls, valor: Any) -> int:
        return _inteiro(valor, "pedido.id")

    @field_validator("idPessoaCliente", "idPessoaVendedor", mode="before")
    @classmethod
    def _pessoas(cls, valor: Any) -> int | None:
        if valor is None or valor == "":
            return None
        return _inteiro(valor, "pedido.pessoa")

    @field_validator("valorTotal", mode="before")
    @classmethod
    def _valor(cls, valor: Any) -> float:
        return _dinheiro(valor)

    @field_validator("dataEmissao", "dataEntregaPadrao", "dataCriacao", mode="before")
    @classmethod
    def _datas(cls, valor: Any) -> datetime | None:
        return _data_opcional(valor)

    @field_validator("codigoPedido", "condicaoPagamentoTexto", "observacoes", mode="before")
    @classmethod
    def _campos_texto(cls, valor: Any) -> str:
        return _texto(valor)


class NfeVinculoNomus(ModeloNomus):
    """Nota já citada no pedido. O XML continua em /nfes."""

    chave: str = ""
    numero: str = ""

    @field_validator("chave", "numero", mode="before")
    @classmethod
    def _campos_texto(cls, valor: Any) -> str:
        return _texto(valor)


PedidoNomus.model_rebuild()


class NfeInfoCrmer(BaseModel):
    pedido_numero: str = ""
    numero_nf: str = ""
    transportadora: str = ""
    destino_obra: str = ""
    chave_nfe: str = ""


class PedidoCrmer(BaseModel):
    codigo: str
    data: str
    item: str
    quantidade: float
    valor: float
    condicaoPagamento: str = ""
    nfe_info: NfeInfoCrmer | None = None


class ClienteCrmer(BaseModel):
    """Mesmos campos da ficha em js/mock-data.js, mais a chave do Nomus."""

    id: str
    nomeFantasia: str
    razaoSocial: str
    cnpj: str
    tipo: str
    contato: str = ""
    cargo: str = ""
    email: str = ""
    telefone: str = ""
    whatsapp: str = ""
    cidade: str = ""
    uf: str = ""
    endereco: str = ""
    numero: str = ""
    bairro: str = ""
    cep: str = ""
    linhas: list[str]
    ranking: Ranking
    prioridade: Literal["alta", "media"]
    curva: Literal["", "A", "B", "C"]
    faturamento12m: float
    ultimaCompra: str = ""
    proximoContato: str = ""
    janelaSazonal: str = ""
    resumo: str
    anotacoes: str = ""
    pedidos: list[PedidoCrmer]
    orcamentos: list[dict[str, Any]] = Field(default_factory=list)
    processos: list[ProcessoCrmer] = Field(default_factory=list)
    nomusId: int
    codigoNomus: str = ""
    ativoNomus: bool = True


class ProcessoCrmer(BaseModel):
    """Tarefa de vendas ligada à pessoa do cliente."""

    id: str = ""
    equipe: str = ""
    etapa: str = ""
    prioridade: str = ""
    dataHoraProgramada: str = ""
    dataEnvio: str = ""
    descricao: str = ""
    pessoa: str = ""
    documento: str = ""
    valor: float = 0


ClienteCrmer.model_rebuild()


class ProdutoCrmer(BaseModel):
    id: int
    codigo: str
    descricao: str
    grupo: str
    linha: str = ""
    familia: str = ""
    custo: float
    unidade: str
    saldoEstoque: float
    vendavel: bool = True


class PrecoHistorico(BaseModel):
    idCliente: int
    idProduto: int | None = None
    nomeProduto: str
    dataEmissao: str
    quantidade: float
    valorUnitario: float
    condicaoPagamento: str = ""
    observacoes: str = ""


class Apuracao(BaseModel):
    faturamento12m: float
    faturamentoMesReferencia: float
    porLinha: list[dict[str, Any]]


class CarteiraExport(BaseModel):
    TODAY: str
    fonte: str
    aviso: str
    vendedorId: int
    clients: list[ClienteCrmer]
    produtos: list[ProdutoCrmer]
    produtosPorFamilia: dict[str, list[ProdutoCrmer]]
    historico_precos: list[PrecoHistorico]
    apuracao: Apuracao
    avisos: list[str]


def formatar_cnpj(valor: str) -> str:
    digitos = re.sub(r"\D", "", valor or "")
    if len(digitos) != 14:
        return (valor or "").strip()
    return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"


def pertence_a_vendedora(cliente: ClienteNomus, vendedor_id: int) -> bool:
    return any(vendedor.id == vendedor_id for vendedor in cliente.vendedores)


def eh_entidade_comunitaria(cliente: ClienteNomus) -> bool:
    """Nova Europa, Guardinha e Fórum não entram na carteira da EHE."""
    texto = _dobrar(f"{cliente.razaoSocial} {cliente.nome}")
    if "nova europa" in texto or "guardinha" in texto or "nucleo socioambiental" in texto:
        return True
    partes = re.split(r"[^a-z0-9]+", texto)
    return "forum" in partes


def linha_comercial(*partes: str) -> str:
    for parte in partes:
        chave = _dobrar(parte).strip()
        if chave in _GRUPOS:
            return _GRUPOS[chave]
    texto = _dobrar(" ".join(parte for parte in partes if parte))
    regras = (
        ("glp", "Gás"),
        ("abrigo de gas", "Gás"),
        ("medidor de gas", "Gás"),
        ("regulador", "Gás"),
        ("hidrometro", "Saneamento"),
        ("caixa de inspecao", "Saneamento"),
        ("saneamento", "Saneamento"),
        ("medicao eletrica", "Elétrica"),
        ("abrigo de medicao", "Elétrica"),
        ("caixa de passagem", "Elétrica"),
        ("eletrica", "Elétrica"),
        ("fechamento", "Fechamento"),
        ("shaft", "Fechamento"),
    )
    for termo, linha in regras:
        if termo in texto:
            return linha
    return ""


def inferir_tipo(razao: str, fantasia: str) -> str:
    texto = _dobrar(f"{razao} {fantasia}")
    if "instal" in texto or "eletric" in texto:
        return "Instaladora"
    if "construt" in texto:
        return "Construtora"
    return "Cliente"


def _janela(referencia: date) -> tuple[int, int, str]:
    primeiro = referencia.month
    segundo = 1 if primeiro == 12 else primeiro + 1
    rotulo = f"{_MESES[primeiro]} e {_MESES[segundo].lower()}"
    return primeiro, segundo, rotulo


def _iso(dia: date | None) -> str:
    return dia.isoformat() if dia else ""


def _curva_abc(faturamentos: dict[int, float]) -> dict[int, str]:
    """A enquanto o acumulado anterior está abaixo de 80%, B até 95%, o restante C.

    Quem não faturou nos últimos 12 meses fica sem curva e não entra em inativos.
    """
    positivos = sorted(
        ((cliente_id, valor) for cliente_id, valor in faturamentos.items() if valor > 0),
        key=lambda item: item[1],
        reverse=True,
    )
    total = sum(valor for _, valor in positivos)
    curvas: dict[int, str] = {cliente_id: "" for cliente_id in faturamentos}
    if total <= 0:
        return curvas
    acumulado = 0.0
    for cliente_id, valor in positivos:
        antes = acumulado / total
        acumulado += valor
        if antes < 0.80:
            curvas[cliente_id] = "A"
        elif antes < 0.95:
            curvas[cliente_id] = "B"
        else:
            curvas[cliente_id] = "C"
    return curvas


class _ItemPreco(BaseModel):
    model_config = ConfigDict(extra="ignore")
    idProduto: int | None = None
    nomeProduto: str
    quantidade: float
    valorUnitario: float


class _PedidoPronto(BaseModel):
    model_config = ConfigDict(extra="ignore")
    codigo: str
    emissao: date | None
    entrega: date | None
    valor: float
    quantidade: float
    item: str
    linhas: list[str]
    por_linha: dict[str, float]
    produto_ids: list[int]
    condicao: str = ""
    observacoes: str = ""
    chaves_nfe: list[str] = Field(default_factory=list)
    numeros_nfe: list[str] = Field(default_factory=list)
    itens: list[_ItemPreco] = Field(default_factory=list)


def _vazio_nfe() -> dict[str, str]:
    return {
        "pedido_numero": "",
        "numero_nf": "",
        "transportadora": "",
        "destino_obra": "",
        "chave_nfe": "",
    }


def _texto_nodo(nodo: ET.Element | None) -> str:
    if nodo is None or nodo.text is None:
        return ""
    return " ".join(nodo.text.split())


def _encontrar(raiz: ET.Element, caminho: str) -> ET.Element | None:
    nodo = raiz.find(caminho, _NS_NFE)
    if nodo is not None:
        return nodo
    return raiz.find(caminho.replace("nfe:", ""))


def _encontrar_todos(raiz: ET.Element, caminho: str) -> list[ET.Element]:
    achados = raiz.findall(caminho, _NS_NFE)
    if achados:
        return achados
    return raiz.findall(caminho.replace("nfe:", ""))


def extrair_dados_xml_nfe(xml_string: str | None) -> dict[str, str]:
    """Lê o XML da NF-e. XML vazio, None ou malformado devolve campos vazios."""
    dados, _numeros = _ler_xml_nfe(xml_string)
    return dados


def _ler_xml_nfe(xml_string: str | None) -> tuple[dict[str, str], list[str]]:
    vazio = _vazio_nfe()
    if xml_string is None:
        return vazio, []
    if isinstance(xml_string, bytes):
        xml_string = xml_string.decode("utf-8", errors="replace")
    if not isinstance(xml_string, str) or not xml_string.strip():
        return vazio, []
    try:
        raiz = ET.fromstring(xml_string.lstrip("\ufeff").strip())
    except ET.ParseError:
        return vazio, []

    numeros: list[str] = []
    for nodo in _encontrar_todos(raiz, ".//nfe:det/nfe:prod/nfe:xPed"):
        numero = _texto_nodo(nodo)
        if numero and numero not in numeros:
            numeros.append(numero)

    municipio = _texto_nodo(_encontrar(raiz, ".//nfe:dest/nfe:enderDest/nfe:xMun"))
    uf = _texto_nodo(_encontrar(raiz, ".//nfe:dest/nfe:enderDest/nfe:UF"))
    # infCpl mistura texto fiscal e o endereço real da obra. A cidade do destinatário cobre a nota sem entrega.
    complemento = _texto_nodo(_encontrar(raiz, ".//nfe:infAdic/nfe:infCpl"))
    destino = _destino_obra(complemento, municipio, uf)

    chave = ""
    inf = _encontrar(raiz, ".//nfe:infNFe")
    if inf is not None:
        ident = str(inf.attrib.get("Id") or "").strip()
        if ident.lower().startswith("nfe"):
            ident = ident[3:]
        chave = ident
    if not chave:
        chave = _texto_nodo(_encontrar(raiz, ".//nfe:chNFe"))

    return (
        {
            "pedido_numero": numeros[0] if numeros else "",
            "numero_nf": _texto_nodo(_encontrar(raiz, ".//nfe:ide/nfe:nNF")),
            "transportadora": _texto_nodo(_encontrar(raiz, ".//nfe:transp/nfe:transporta/nfe:xNome")),
            "destino_obra": destino,
            "chave_nfe": chave,
        },
        numeros,
    )


_RE_ENTREGA_OBRA = re.compile(r"obra\s*:", re.IGNORECASE)
_RE_ENTREGA_ENDERECO = re.compile(r"endere[cç]o de entrega\s*:", re.IGNORECASE)
_RE_ENTREGA_CURTO = re.compile(r"endere[cç]o\s*:", re.IGNORECASE)


def _destino_obra(complemento: str, municipio: str, uf: str) -> str:
    texto = re.sub(r"<br\s*/?>", " ", complemento or "", flags=re.IGNORECASE)
    texto = " ".join(texto.replace("\xa0", " ").split())
    trecho = _trecho_entrega(texto)
    if trecho:
        return trecho
    if municipio and uf:
        return f"{municipio}/{uf}"
    return municipio or uf


def _trecho_entrega(texto: str) -> str:
    """Tira PIS/COFINS e o separador de mais e fica com obra ou endereço de entrega."""
    if not texto:
        return ""
    if not _texto_fiscal(texto):
        return texto
    partes = [parte.strip(" +") for parte in re.split(r"\|+", texto)]
    partes = [parte for parte in partes if parte and not re.fullmatch(r"\++", parte)]
    candidato = ""
    for parte in partes:
        if _marcador_entrega(parte):
            candidato = parte
            break
    if not candidato and _marcador_entrega(texto):
        candidato = texto
    if not candidato:
        return ""
    marcador = _marcador_entrega(candidato)
    if marcador is None:
        return ""
    return candidato[marcador.start():].strip(" -")


def _texto_fiscal(texto: str) -> bool:
    baixo = _dobrar(texto)
    return "pis " in baixo or "cofins" in baixo or "ibpt" in baixo or "++++" in texto or "|" in texto


def _marcador_entrega(texto: str) -> re.Match[str] | None:
    return _RE_ENTREGA_OBRA.search(texto) or _RE_ENTREGA_ENDERECO.search(texto) or _RE_ENTREGA_CURTO.search(texto)


def _chaves_pedido_nfe(numero: str) -> list[str]:
    chaves: list[str] = []
    limpo = re.sub(r"\s+", "", numero or "").casefold()
    if limpo:
        chaves.append(f"txt:{limpo}")
    # Número com letra (TRAY: 4769) não vira chave numérica: cairia em outro PD.
    if numero and not re.search(r"[A-Za-z]", numero):
        digitos = re.sub(r"\D", "", numero).lstrip("0")
        if digitos:
            chaves.append(f"num:{digitos}")
    return chaves


def _indexar_nfes(brutos: list[dict[str, Any]] | None) -> dict[str, dict[str, str]]:
    """Primeira NF-e de cada pedido ganha. Páginas recentes chegam antes."""
    indice: dict[str, dict[str, str]] = {}
    if not brutos:
        return indice
    for bruto in brutos:
        if not isinstance(bruto, dict):
            continue
        xml = bruto.get("xml") if isinstance(bruto.get("xml"), str) else bruto.get("xmlNfe")
        if not isinstance(xml, str):
            xml = ""
        dados, numeros = _ler_xml_nfe(xml)
        if not dados["chave_nfe"]:
            dados["chave_nfe"] = _texto(bruto.get("chave") or bruto.get("chaveNfe") or bruto.get("chave_nfe"))
        if not dados["numero_nf"]:
            dados["numero_nf"] = _texto(bruto.get("numero") or bruto.get("nNF") or bruto.get("numeroNf"))
        if dados["pedido_numero"] and dados["pedido_numero"] not in numeros:
            numeros.insert(0, dados["pedido_numero"])
        if not any(dados[campo] for campo in ("numero_nf", "transportadora", "destino_obra", "chave_nfe")):
            continue
        if dados["chave_nfe"]:
            indice.setdefault(f"chave:{dados['chave_nfe']}", dados)
        if dados["numero_nf"]:
            token = dados["numero_nf"].lstrip("0")
            if token:
                indice.setdefault(f"nf:{token}", dados)
        for numero in numeros:
            for chave in _chaves_pedido_nfe(numero):
                indice.setdefault(chave, dados)
            if numero and not re.search(r"[A-Za-z]", numero):
                token = re.sub(r"\D", "", numero).lstrip("0")
                if len(token) >= 5:
                    indice.setdefault(f"xped:{token}", dados)
    return indice


def _nfe_do_pedido(pedido: _PedidoPronto, indice: dict[str, dict[str, str]]) -> dict[str, str] | None:
    """A chave da nota no pedido vem primeiro. xPed liga o pedido de compra do cliente."""
    if not indice:
        return None
    for chave in pedido.chaves_nfe:
        achado = indice.get(f"chave:{chave}")
        if achado:
            return achado
    for numero in pedido.numeros_nfe:
        token = str(numero).lstrip("0")
        achado = indice.get(f"nf:{token}") if token else None
        if achado:
            return achado
    for chave in _chaves_pedido_nfe(pedido.codigo):
        achado = indice.get(chave)
        if achado:
            return achado
    for token in re.findall(r"\d{5,}", pedido.observacoes or ""):
        achado = indice.get(f"xped:{token.lstrip('0')}")
        if achado:
            return achado
    return None


def _eh_equipe_vendas(bruto: dict[str, Any]) -> bool:
    equipe = bruto.get("equipe")
    if isinstance(equipe, dict):
        equipe = equipe.get("nome") or equipe.get("descricao") or ""
    return _dobrar(_texto(equipe)) == "vendas"


def _processo_aberto(bruto: dict[str, Any]) -> bool:
    for campo in ("concluido", "concluida", "encerrado", "cancelado", "finalizado"):
        valor = bruto.get(campo)
        if valor is True or (isinstance(valor, str) and valor.strip().casefold() in {"1", "true", "sim", "s"}):
            return False
    status = _dobrar(_texto(bruto.get("status") or bruto.get("situacao") or bruto.get("situacaoProcesso")))
    return status not in _STATUS_PROCESSO_FECHADO


def _eh_etapa_proposta(etapa: str) -> bool:
    texto = _dobrar(etapa)
    return "proposta" in texto and "orcamento" in texto


def _pessoa_campos(bruto: dict[str, Any]) -> tuple[str, str, str]:
    pessoa = bruto.get("pessoa")
    if pessoa is None:
        pessoa = bruto.get("cliente") or ""
    if isinstance(pessoa, str):
        return "", "", pessoa.strip()
    if not isinstance(pessoa, dict):
        return "", "", ""
    ident = pessoa.get("id")
    if ident is None:
        ident = pessoa.get("idPessoa") or pessoa.get("idCliente") or ""
    documento = pessoa.get("documento") or pessoa.get("cnpj") or pessoa.get("cpfCnpj") or pessoa.get("cpf_cnpj") or ""
    nome = pessoa.get("nome") or pessoa.get("razaoSocial") or pessoa.get("nomeFantasia") or ""
    return _texto(ident), _texto(documento), _texto(nome)


def _pontuar_pessoa(cliente: ClienteNomus, ident: str, documento: str, nome: str) -> int:
    if ident and ident == str(cliente.id):
        return 4
    doc = re.sub(r"\D", "", documento)
    cnpj = re.sub(r"\D", "", cliente.cnpj)
    if doc and cnpj and doc == cnpj:
        return 3
    alvo = _dobrar(nome)
    if not alvo:
        return 0
    nomes = {_dobrar(cliente.razaoSocial), _dobrar(cliente.nome)}
    nomes.discard("")
    if alvo in nomes:
        return 2
    if len(alvo) >= 8 and any(alvo in item or item in alvo for item in nomes):
        return 1
    return 0


def _iso_flex(valor: Any) -> str:
    if valor is None:
        return ""
    texto = str(valor).strip()
    if not texto:
        return ""
    if len(texto) >= 10 and texto[4] == "-" and texto[7] == "-":
        return texto[:10]
    try:
        return parse_nomus_date(texto).date().isoformat()
    except ValueError:
        return ""


def _processo_crmer(bruto: dict[str, Any], nome: str, documento: str) -> ProcessoCrmer:
    etapa = _texto(bruto.get("etapa") or bruto.get("nomeEtapa") or bruto.get("etapaProcesso"))
    programada = _texto(bruto.get("dataHoraProgramada") or bruto.get("dataProgramada"))
    descricao = _texto(bruto.get("descricao") or bruto.get("titulo") or bruto.get("assunto") or bruto.get("nome"))
    try:
        bruto_valor = bruto.get("valor")
        if bruto_valor in (None, ""):
            bruto_valor = bruto.get("valorTotal") or 0
        valor = _dinheiro(bruto_valor)
    except ValueError:
        valor = 0.0
    envio = _iso_flex(
        bruto.get("dataCriacao")
        or bruto.get("dataAbertura")
        or bruto.get("dataEnvio")
        or bruto.get("dataEmissao")
        or bruto.get("data")
    )
    return ProcessoCrmer(
        id=_texto(bruto.get("id")),
        equipe="Vendas",
        etapa=etapa,
        prioridade=_texto(bruto.get("prioridade") or bruto.get("nomePrioridade")),
        dataHoraProgramada=programada,
        dataEnvio=envio,
        descricao=descricao,
        pessoa=nome,
        documento=documento,
        valor=round(valor, 2),
    )


def _orcamento_de_processo(processo: ProcessoCrmer) -> dict[str, Any]:
    return {
        "codigo": processo.id or "Processo",
        "data": processo.dataEnvio or _iso_flex(processo.dataHoraProgramada),
        "item": processo.descricao or processo.etapa or ETAPA_PROPOSTA,
        "valor": processo.valor,
        "prioridade": processo.prioridade,
        "dataHoraProgramada": processo.dataHoraProgramada,
    }


def _agrupar_processos(
    brutos: list[dict[str, Any]] | None,
    clientes: list[ClienteNomus],
    avisos: list[str],
) -> dict[int, list[ProcessoCrmer]]:
    grupos: dict[int, list[ProcessoCrmer]] = {cliente.id: [] for cliente in clientes}
    if not brutos:
        return grupos
    sem_cliente = 0
    for bruto in brutos:
        if not isinstance(bruto, dict) or not _eh_equipe_vendas(bruto) or not _processo_aberto(bruto):
            continue
        ident, documento, nome = _pessoa_campos(bruto)
        melhor: ClienteNomus | None = None
        pontos = 0
        for cliente in clientes:
            nota = _pontuar_pessoa(cliente, ident, documento, nome)
            if nota > pontos:
                melhor = cliente
                pontos = nota
        if melhor is None:
            sem_cliente += 1
            continue
        grupos[melhor.id].append(_processo_crmer(bruto, nome, documento))
    if sem_cliente:
        avisos.append(f"{sem_cliente} processo(s) de vendas não entraram porque a pessoa não está na carteira.")
    return grupos


def montar_carteira(
    clientes_raw: list[dict[str, Any]],
    produtos_raw: list[dict[str, Any]],
    pedidos_raw: list[dict[str, Any]],
    vendedor_id: int = VENDEDOR_NATALIA,
    referencia: date = DATA_REFERENCIA,
    processos_raw: list[dict[str, Any]] | None = None,
    nfes_raw: list[dict[str, Any]] | None = None,
) -> CarteiraExport:
    avisos: list[str] = []
    produtos = _validar_produtos(produtos_raw, avisos)
    catalogo = {produto.id: produto for produto in produtos}
    clientes = _validar_clientes(clientes_raw, avisos)
    pedidos = _validar_pedidos(pedidos_raw, avisos)

    ids_com_pedido = {
        pedido.idPessoaCliente
        for pedido in pedidos
        if pedido.idPessoaVendedor == vendedor_id and pedido.idPessoaCliente is not None
    }
    comunitarios = 0
    ids_comunitarios: set[int] = set()
    da_natalia: list[ClienteNomus] = []
    for cliente in clientes:
        if eh_entidade_comunitaria(cliente):
            comunitarios += 1
            ids_comunitarios.add(cliente.id)
            continue
        if pertence_a_vendedora(cliente, vendedor_id) or cliente.id in ids_com_pedido:
            da_natalia.append(cliente)
    if comunitarios:
        avisos.append(
            f"{comunitarios} cadastro(s) de entidade comunitária ficaram fora da carteira comercial."
        )

    ids = {cliente.id for cliente in da_natalia}
    por_cliente: dict[int, list[_PedidoPronto]] = {cliente.id: [] for cliente in da_natalia}
    produtos_citados: set[int] = set()
    orfaos = 0
    for pedido in pedidos:
        if pedido.idPessoaVendedor != vendedor_id:
            continue
        if pedido.idPessoaCliente in ids_comunitarios:
            continue
        if pedido.idPessoaCliente not in ids:
            orfaos += 1
            continue
        pronto = _normalizar_pedido(pedido, catalogo)
        por_cliente[pedido.idPessoaCliente].append(pronto)
        produtos_citados.update(pronto.produto_ids)
    if orfaos:
        avisos.append(f"{orfaos} pedido(s) da vendedora não entraram porque o cliente não está na carteira dela.")

    faturamento = {
        cliente.id: _faturamento_12m(por_cliente[cliente.id], referencia) for cliente in da_natalia
    }
    curvas = _curva_abc(faturamento)
    processos_por_cliente = _agrupar_processos(processos_raw, da_natalia, avisos)
    nfes_por_pedido = _indexar_nfes(nfes_raw)
    fichas = [
        _ficha(
            cliente,
            por_cliente[cliente.id],
            faturamento[cliente.id],
            curvas[cliente.id],
            referencia,
            processos_por_cliente.get(cliente.id, []),
            nfes_por_pedido,
        )
        for cliente in da_natalia
    ]
    fichas.sort(key=lambda ficha: _dobrar(ficha.razaoSocial))
    produtos_usados = _produtos_da_carteira(catalogo, produtos_citados)
    historico = _historico(por_cliente)
    if any(ficha.ranking == "resposta" for ficha in fichas):
        avisos.append("A fila de orçamento usa processos de vendas na etapa Proposta / Orçamentos.")
    else:
        avisos.append(
            "Nenhum cliente foi para a fila de orçamento: /pedidos não informa proposta em aberto."
        )
    return CarteiraExport(
        TODAY=referencia.isoformat(),
        fonte="nomus-fase-1-consulta",
        aviso=(
            "Consulta da Fase 1 gravada em arquivo local. O navegador não chama o Nomus. "
            "Sem este arquivo, o protótipo usa a carteira simulada."
        ),
        vendedorId=vendedor_id,
        clients=fichas,
        produtos=produtos_usados,
        produtosPorFamilia=_agrupar_familias(produtos_usados),
        historico_precos=historico,
        apuracao=_apurar(por_cliente, referencia),
        avisos=avisos,
    )


def _validar_clientes(brutos: list[dict[str, Any]], avisos: list[str]) -> list[ClienteNomus]:
    validos: list[ClienteNomus] = []
    for indice, bruto in enumerate(brutos, start=1):
        try:
            validos.append(ClienteNomus.model_validate(bruto))
        except Exception as exc:
            avisos.append(f"Cliente ignorado na posição {indice}: {_resumo_erro(exc)}")
    return validos


def _validar_produtos(brutos: list[dict[str, Any]], avisos: list[str]) -> list[ProdutoNomus]:
    validos: list[ProdutoNomus] = []
    for indice, bruto in enumerate(brutos, start=1):
        try:
            validos.append(ProdutoNomus.model_validate(bruto))
        except Exception as exc:
            avisos.append(f"Produto ignorado na posição {indice}: {_resumo_erro(exc)}")
    return validos


def _validar_pedidos(brutos: list[dict[str, Any]], avisos: list[str]) -> list[PedidoNomus]:
    validos: list[PedidoNomus] = []
    for indice, bruto in enumerate(brutos, start=1):
        try:
            validos.append(PedidoNomus.model_validate(bruto))
        except Exception as exc:
            avisos.append(f"Pedido ignorado na posição {indice}: {_resumo_erro(exc)}")
    return validos


def _resumo_erro(exc: Exception) -> str:
    texto = str(exc).replace("\n", " ")
    return texto[:180] or exc.__class__.__name__


def _normalizar_pedido(pedido: PedidoNomus, catalogo: dict[int, ProdutoNomus]) -> _PedidoPronto:
    descricoes: list[str] = []
    linhas: list[str] = []
    por_linha: dict[str, float] = {}
    produto_ids: list[int] = []
    itens: list[_ItemPreco] = []
    quantidade = 0.0
    soma_itens = 0.0
    for item in pedido.itensPedido:
        if item.idProduto is not None:
            produto_ids.append(item.idProduto)
        quantidade += item.quantidade
        valor_item = item.quantidade * item.valorUnitario
        soma_itens += valor_item
        produto = catalogo.get(item.idProduto) if item.idProduto is not None else None
        descricao = produto.descricao if produto and produto.descricao else ""
        if not descricao and item.idProduto is not None:
            descricao = f"Produto {item.idProduto}"
        if descricao and descricao not in descricoes:
            descricoes.append(descricao)
        itens.append(
            _ItemPreco(
                idProduto=item.idProduto,
                nomeProduto=descricao or "Pedido Nomus",
                quantidade=round(item.quantidade, 3),
                valorUnitario=round(item.valorUnitario, 2),
            )
        )
        linha = ""
        if produto:
            linha = linha_comercial(produto.nomeGrupoProduto, produto.nomeTipoProduto, produto.descricao)
        if linha:
            if linha not in linhas:
                linhas.append(linha)
            por_linha[linha] = por_linha.get(linha, 0.0) + valor_item
    valor = pedido.valorTotal if pedido.valorTotal else soma_itens
    if valor and por_linha:
        soma = sum(por_linha.values())
        if soma > 0 and abs(soma - valor) > 0.01:
            fator = valor / soma
            por_linha = {linha: quantia * fator for linha, quantia in por_linha.items()}
    elif valor and linhas and not por_linha:
        parte = valor / len(linhas)
        por_linha = {linha: parte for linha in linhas}
    emissao = _dia(pedido.dataEmissao) or _dia(pedido.dataCriacao)
    item = " · ".join(descricoes) if descricoes else "Pedido Nomus"
    if len(item) > 180:
        item = f"{item[:179]}…"
    return _PedidoPronto(
        codigo=pedido.codigoPedido or f"NM-{pedido.id}",
        emissao=emissao,
        entrega=_dia(pedido.dataEntregaPadrao),
        valor=round(valor, 2),
        quantidade=round(quantidade, 3),
        item=item,
        linhas=linhas,
        por_linha=por_linha,
        produto_ids=produto_ids,
        condicao=pedido.condicaoPagamentoTexto,
        observacoes=pedido.observacoes,
        chaves_nfe=[nota.chave for nota in pedido.nfes if nota.chave],
        numeros_nfe=[nota.numero for nota in pedido.nfes if nota.numero],
        itens=itens,
    )


def _dia(momento: datetime | None) -> date | None:
    return momento.date() if momento else None


def _faturamento_12m(pedidos: list[_PedidoPronto], referencia: date) -> float:
    inicio = referencia - timedelta(days=365)
    total = sum(pedido.valor for pedido in pedidos if pedido.emissao and inicio < pedido.emissao <= referencia)
    return round(total, 2)


def _ultima_compra(pedidos: list[_PedidoPronto]) -> date | None:
    datas = [pedido.emissao for pedido in pedidos if pedido.emissao]
    return max(datas) if datas else None


def _ficha(
    cliente: ClienteNomus,
    pedidos: list[_PedidoPronto],
    faturamento: float,
    curva: str,
    referencia: date,
    processos: list[ProcessoCrmer] | None = None,
    nfes_por_pedido: dict[str, dict[str, str]] | None = None,
) -> ClienteCrmer:
    ultima = _ultima_compra(pedidos)
    ranking, prioridade, proximo, janela, resumo = _classificar(pedidos, ultima, curva, referencia)
    linhas = _linhas_dos_pedidos(pedidos)
    recentes = sorted(pedidos, key=lambda pedido: pedido.emissao or date.min, reverse=True)[:PEDIDOS_NA_FICHA]
    tarefas = list(processos or [])
    propostas = [tarefa for tarefa in tarefas if _eh_etapa_proposta(tarefa.etapa)]
    orcamentos: list[dict[str, Any]] = []
    if propostas:
        # Orçamento aberto tira o cliente das outras filas: a negociação continua viva.
        ranking = "resposta"
        janela = ""
        if any("alta" in _dobrar(proposta.prioridade) for proposta in propostas):
            prioridade = "alta"
        propostas_ordenadas = sorted(propostas, key=lambda proposta: proposta.dataHoraProgramada or "9999")
        quando = propostas_ordenadas[0].dataHoraProgramada or "sem data programada"
        resumo = f"Proposta em aberto ({len(propostas)}). Retorno programado: {quando}."
        orcamentos = [_orcamento_de_processo(proposta) for proposta in propostas]
        orcamentos.sort(key=lambda item: item.get("data") or "9999-99-99")
    indice = nfes_por_pedido or {}
    pedidos_ficha: list[PedidoCrmer] = []
    for pedido in recentes:
        info = _nfe_do_pedido(pedido, indice)
        pedidos_ficha.append(
            PedidoCrmer(
                codigo=pedido.codigo,
                data=_iso(pedido.emissao),
                item=pedido.item,
                quantidade=pedido.quantidade,
                valor=pedido.valor,
                condicaoPagamento=pedido.condicao,
                nfe_info=NfeInfoCrmer.model_validate(info) if info else None,
            )
        )
    return ClienteCrmer(
        id=f"nomus-{cliente.id}",
        nomeFantasia=cliente.nome or cliente.razaoSocial,
        razaoSocial=cliente.razaoSocial or cliente.nome or f"Cliente {cliente.id}",
        cnpj=formatar_cnpj(cliente.cnpj),
        tipo=inferir_tipo(cliente.razaoSocial, cliente.nome),
        contato="",
        cargo="",
        email=cliente.email.casefold(),
        telefone=cliente.telefone,
        whatsapp="",
        cidade=cliente.municipio,
        uf=cliente.uf.strip().upper()[:2],
        endereco=cliente.endereco,
        numero=cliente.numero,
        bairro=cliente.bairro,
        cep=cliente.cep,
        linhas=linhas,
        ranking=ranking,
        prioridade=prioridade,
        curva=curva if curva in {"A", "B", "C"} else "",
        faturamento12m=faturamento,
        ultimaCompra=_iso(ultima),
        proximoContato=proximo,
        janelaSazonal=janela,
        resumo=resumo,
        anotacoes="",
        pedidos=pedidos_ficha,
        orcamentos=orcamentos,
        processos=tarefas,
        nomusId=cliente.id,
        codigoNomus=cliente.codigo,
        ativoNomus=cliente.ativo,
    )


def _linhas_dos_pedidos(pedidos: list[_PedidoPronto]) -> list[str]:
    presentes = {linha for pedido in pedidos for linha in pedido.linhas}
    return [linha for linha in LINHAS if linha in presentes]


def _classificar(
    pedidos: list[_PedidoPronto],
    ultima: date | None,
    curva: str,
    referencia: date,
) -> tuple[Ranking, Literal["alta", "media"], str, str, str]:
    """Uma fila por cliente. Sazonal e inativo vêm antes para não lotar a agenda de hoje."""
    mes_a, mes_b, janela = _janela(referencia)
    anos_anteriores = {
        pedido.emissao.year
        for pedido in pedidos
        if pedido.emissao and pedido.emissao.year < referencia.year and pedido.emissao.month in {mes_a, mes_b}
    }
    comprou_nesta_janela = any(
        pedido.emissao and pedido.emissao.year == referencia.year and pedido.emissao.month in {mes_a, mes_b}
        for pedido in pedidos
    )
    if anos_anteriores and not comprou_nesta_janela:
        anos = ", ".join(str(ano) for ano in sorted(anos_anteriores))
        return (
            "sazonal",
            "media",
            "",
            janela,
            f"Histórico de compra em {janela.lower()} ({anos}), sem pedido desta janela em {referencia.year}.",
        )

    dias = (referencia - ultima).days if ultima else None
    if curva in {"A", "B"} and (dias is None or dias > INATIVIDADE_DIAS):
        quando = ultima.strftime("%d/%m/%Y") if ultima else "sem compra registrada"
        ha = f" há {dias} dias" if dias is not None else ""
        return (
            "inativos",
            "alta" if curva == "A" else "media",
            "",
            "",
            f"Curva {curva}. Última compra em {quando}{ha}. Contato de reativação, sem reabrir orçamento antigo.",
        )

    entrega_proxima = any(
        pedido.entrega and abs((pedido.entrega - referencia).days) < ENTREGA_PROXIMA_DIAS for pedido in pedidos
    )
    recente = dias is not None and dias <= AGENDA_RECENTE_DIAS
    if not pedidos or recente or entrega_proxima:
        if not pedidos:
            texto = "Cliente na carteira da Natália, ainda sem pedido nesta consulta."
        elif entrega_proxima:
            texto = "Entrega prevista perto da data de referência. Follow-up preliminar: o Nomus não devolve a agenda."
        else:
            texto = f"Pedido em {ultima.strftime('%d/%m/%Y')}. Follow-up preliminar: o Nomus não devolve a agenda."
        return ("contato", "alta" if curva == "A" or entrega_proxima else "media", referencia.isoformat(), "", texto)

    sugerido = referencia + timedelta(days=REAGENDAR_DIAS)
    return (
        "contato",
        "media",
        sugerido.isoformat(),
        "",
        "Sem follow-up no Nomus. Contato sugerido fora da agenda de hoje para não misturar com o que está vencido.",
    )


def _produtos_da_carteira(catalogo: dict[int, ProdutoNomus], citados: set[int]) -> list[ProdutoCrmer]:
    """Catálogo vendável das quatro linhas. Item de outro grupo só entra se a Natália pediu."""
    saida: list[ProdutoCrmer] = []
    for produto in catalogo.values():
        linha = linha_comercial(produto.nomeGrupoProduto, produto.nomeTipoProduto, produto.descricao)
        if not linha and produto.id not in citados:
            continue
        saldo = round(sum(setor.saldoEstoqueAtualEmpresa for setor in produto.empresasSetoresEstoque), 3)
        saida.append(
            ProdutoCrmer(
                id=produto.id,
                codigo=produto.codigo,
                descricao=produto.descricao,
                grupo=produto.nomeGrupoProduto,
                linha=linha,
                familia=linha,
                custo=round(produto.custoPadraoCompra, 2),
                vendavel=bool(linha),
                unidade=produto.siglaUnidadeMedida,
                saldoEstoque=saldo,
            )
        )
    saida.sort(key=lambda item: (item.linha, item.codigo))
    return saida


def _agrupar_familias(produtos: list[ProdutoCrmer]) -> dict[str, list[ProdutoCrmer]]:
    grupos: dict[str, list[ProdutoCrmer]] = {linha: [] for linha in LINHAS}
    for produto in produtos:
        if produto.linha in grupos:
            grupos[produto.linha].append(produto)
    return grupos


def _historico(por_cliente: dict[int, list[_PedidoPronto]]) -> list[PrecoHistorico]:
    linhas: list[PrecoHistorico] = []
    for cliente_id, pedidos in por_cliente.items():
        for pedido in pedidos:
            for item in pedido.itens:
                linhas.append(
                    PrecoHistorico(
                        idCliente=cliente_id,
                        idProduto=item.idProduto,
                        nomeProduto=item.nomeProduto,
                        dataEmissao=_iso(pedido.emissao),
                        quantidade=item.quantidade,
                        valorUnitario=item.valorUnitario,
                        condicaoPagamento=pedido.condicao,
                        observacoes=pedido.observacoes,
                    )
                )
    linhas.sort(key=lambda row: (row.dataEmissao, row.idCliente, row.nomeProduto))
    return linhas


def _apurar(por_cliente: dict[int, list[_PedidoPronto]], referencia: date) -> Apuracao:
    inicio = referencia - timedelta(days=365)
    doze = 0.0
    mes = 0.0
    linhas = {linha: 0.0 for linha in LINHAS}
    for pedidos in por_cliente.values():
        for pedido in pedidos:
            if not pedido.emissao or not (inicio < pedido.emissao <= referencia):
                continue
            doze += pedido.valor
            if pedido.emissao.year == referencia.year and pedido.emissao.month == referencia.month:
                mes += pedido.valor
            for linha, valor in pedido.por_linha.items():
                if linha in linhas:
                    linhas[linha] += valor
    return Apuracao(
        faturamento12m=round(doze, 2),
        faturamentoMesReferencia=round(mes, 2),
        porLinha=[{"nome": linha, "faturamento": round(valor, 2)} for linha, valor in linhas.items()],
    )
