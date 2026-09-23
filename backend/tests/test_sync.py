"""Testes da consulta sem chamar o Nomus."""

from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

import requests
from urllib3.util.retry import RequestHistory

from backend.nomus_client import (
    BASE_DELAY,
    INTERVALO_PAGINA,
    STATUS_ADAPTADOR,
    TENTATIVAS_RESPOSTA,
    NomusAuthError,
    NomusClient,
    NomusError,
)
from backend.sync_runner import clientes_em_cache, construir_parser, reunir_clientes
from backend.transformer import (
    extrair_dados_xml_nfe,
    montar_carteira,
    parse_nomus_date,
    parse_ptbr_float,
)


class _Resposta:
    def __init__(self, status: int, payload, headers=None, text: str = ""):
        self.status_code = status
        self._payload = payload
        self.headers = headers or {}
        self.content = b"{}" if payload is not None else b""
        self.text = text

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            erro = requests.HTTPError(f"status {self.status_code}")
            erro.response = self
            raise erro


class _Sessao:
    def __init__(self, respostas):
        self._respostas = list(respostas)
        self.headers: dict[str, str] = {}
        self.chamadas: list[dict] = []

    def get(self, url, params=None, timeout=None):
        self.chamadas.append({"url": url, "params": params, "timeout": timeout})
        if not self._respostas:
            raise AssertionError("consulta além das respostas preparadas")
        return self._respostas.pop(0)

    def close(self):
        return None


def _cliente(identificador, nome, vendedores=None, **extra):
    base = {
        "id": identificador,
        "codigo": f"C{identificador}",
        "cnpj": "11222333000181",
        "ativo": True,
        "razaoSocial": nome,
        "nome": extra.pop("fantasia", nome),
        "email": "compras@example.com",
        "telefone": "(11) 98810-2201",
        "municipio": "São Paulo",
        "uf": "sp",
        "vendedores": vendedores if vendedores is not None else [{"id": 3237, "nome": "NATALIA"}],
    }
    base.update(extra)
    return base


def _produto(identificador, grupo, descricao):
    return {
        "id": identificador,
        "codigo": f"AI {identificador:05d}",
        "descricao": descricao,
        "nomeGrupoProduto": grupo,
        "custoPadraoCompra": "10,50",
        "siglaUnidadeMedida": "UN",
        "empresasSetoresEstoque": [{"saldoEstoqueAtualEmpresa": "2,00"}],
    }


def _pedido(identificador, cliente, emissao, valor, produto, vendedor=3237, entrega=""):
    return {
        "id": identificador,
        "codigoPedido": f"PD {identificador:05d}",
        "idPessoaCliente": cliente,
        "idPessoaVendedor": vendedor,
        "valorTotal": valor,
        "dataEmissao": emissao,
        "dataEntregaPadrao": entrega,
        "itensPedido": [
            {"idProduto": produto, "quantidade": "2,00", "valorUnitario": "100,00", "status": 1}
        ],
    }


class ParseTests(unittest.TestCase):
    def test_dinheiro_ptbr(self):
        self.assertEqual(parse_ptbr_float("785,70"), 785.70)
        self.assertEqual(parse_ptbr_float("4150,00"), 4150.0)
        self.assertEqual(parse_ptbr_float("4.150,00"), 4150.0)
        self.assertEqual(parse_ptbr_float("4.150"), 4150.0)
        self.assertEqual(parse_ptbr_float("R$ 1.234,5"), 1234.5)

    def test_dinheiro_recusa_vazio(self):
        with self.assertRaises(ValueError):
            parse_ptbr_float("   ")

    def test_data_nomus(self):
        self.assertEqual(parse_nomus_date("22/09/2026").date(), date(2026, 9, 22))
        self.assertEqual(parse_nomus_date("22/09/2026 14:30:00").hour, 14)
        with self.assertRaises(ValueError):
            parse_nomus_date("2026-09-22")


class CarteiraTests(unittest.TestCase):
    def test_filtra_natalia_e_classifica_uma_fila(self):
        produtos = [
            _produto(1, "Saneamento", "Caixa de hidrômetro"),
            _produto(2, "Gás", "Abrigo de gás GLP"),
            _produto(3, "Solda", "Eletrodo"),
        ]
        clientes = [
            _cliente(1, "Construtora Pacaembu", fantasia="Pacaembu"),
            _cliente(2, "Construtora Horizonte", fantasia="Horizonte"),
            _cliente(3, "Construtora Alfa", fantasia="Alfa"),
            _cliente(4, "Núcleo Socioambiental Nova Europa", fantasia="Nova Europa"),
            _cliente(5, "Outra Carteira", vendedores=[{"id": 9, "nome": "OUTRO"}]),
            _cliente(6, "Cliente Sem Pedido"),
        ]
        pedidos = [
            _pedido(10, 1, "01/09/2026", "1000,00", 1),
            _pedido(11, 2, "25/09/2025", "800,00", 2),
            _pedido(12, 3, "01/01/2026", "5000,00", 2),
            _pedido(13, 1, "02/09/2026", "50,00", 1, vendedor=9),
            _pedido(14, 5, "02/09/2026", "999,00", 1),
            _pedido(15, 4, "02/09/2026", "10,00", 1),
        ]
        carteira = montar_carteira(clientes, produtos, pedidos)
        ids = {ficha.nomusId for ficha in carteira.clients}
        self.assertEqual(ids, {1, 2, 3, 5, 6})
        por_id = {ficha.nomusId: ficha for ficha in carteira.clients}

        self.assertEqual(por_id[1].ranking, "contato")
        self.assertEqual(por_id[1].proximoContato, "2026-09-22")
        self.assertEqual(por_id[1].linhas, ["Saneamento"])
        self.assertEqual(por_id[1].cnpj, "11.222.333/0001-81")
        self.assertEqual(por_id[1].uf, "SP")
        self.assertEqual(por_id[1].tipo, "Construtora")
        self.assertEqual(por_id[1].pedidos[0].valor, 1000.0)
        self.assertEqual(por_id[1].orcamentos, [])

        self.assertEqual(por_id[2].ranking, "sazonal")
        self.assertIn("Setembro e outubro", por_id[2].janelaSazonal)

        self.assertEqual(por_id[3].ranking, "inativos")
        self.assertEqual(por_id[3].curva, "A")
        self.assertEqual(por_id[6].ranking, "contato")
        self.assertEqual(por_id[6].proximoContato, "2026-09-22")
        self.assertNotIn("resposta", {ficha.ranking for ficha in carteira.clients})
        self.assertTrue(any("orçamento" in aviso for aviso in carteira.avisos))
        self.assertTrue(any("comunitária" in aviso for aviso in carteira.avisos))
        self.assertEqual({produto.id for produto in carteira.produtos}, {1, 2})
        self.assertEqual(set(carteira.produtosPorFamilia), {"Gás", "Saneamento", "Elétrica", "Fechamento"})
        preco = next(row for row in carteira.historico_precos if row.idCliente == 1)
        self.assertEqual(preco.valorUnitario, 100.0)
        self.assertEqual(preco.quantidade, 2.0)
        self.assertEqual(preco.nomeProduto, "Caixa de hidrômetro")

    def test_pedido_no_meio_do_ciclo_sai_da_agenda_de_hoje(self):
        carteira = montar_carteira(
            [_cliente(1, "Instaladora Beta")],
            [_produto(1, "Gás", "Abrigo para medidor de gás")],
            [_pedido(10, 1, "01/08/2026", "200,00", 1)],
        )
        ficha = carteira.clients[0]
        self.assertEqual(ficha.ranking, "contato")
        self.assertEqual(ficha.tipo, "Instaladora")
        self.assertEqual(ficha.proximoContato, "2026-10-06")

    def test_entrega_com_menos_de_sete_dias_entra_na_agenda(self):
        cliente = [_cliente(1, "Instaladora Beta")]
        produto = [_produto(1, "Gás", "Abrigo de gás GLP")]
        perto = montar_carteira(
            cliente,
            produto,
            [_pedido(10, 1, "01/08/2026", "200,00", 1, entrega="28/09/2026")],
        )
        no_limite = montar_carteira(
            cliente,
            produto,
            [_pedido(10, 1, "01/08/2026", "200,00", 1, entrega="29/09/2026")],
        )
        self.assertEqual(perto.clients[0].proximoContato, "2026-09-22")
        self.assertEqual(no_limite.clients[0].proximoContato, "2026-10-06")

    def test_ignora_registro_invalido_sem_derrubar_o_lote(self):
        carteira = montar_carteira(
            [{"id": "x"}, _cliente(1, "Construtora Alfa")],
            [_produto(1, "Elétrica", "Abrigo de medição elétrica")],
            [_pedido(10, 1, "10/05/2026", "300,00", 1)],
        )
        self.assertEqual(len(carteira.clients), 1)
        self.assertTrue(any("Cliente ignorado" in aviso for aviso in carteira.avisos))


_XML_NFE = """<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
  <NFe>
    <infNFe Id="NFe35260911222333000181550010000012341000012345">
      <ide><nNF>1234</nNF></ide>
      <dest><enderDest><xMun>Campinas</xMun><UF>SP</UF></enderDest></dest>
      <det nItem="1"><prod><xPed>PD 00010</xPed></prod></det>
      <transp><transporta><xNome>Transportadora Obra Ltda</xNome></transporta></transp>
      <infAdic><infCpl>Entrega na obra: Rua das Flores, 100 - Campinas/SP</infCpl></infAdic>
    </infNFe>
  </NFe>
  <protNFe><infProt><chNFe>35260911222333000181550010000012341000012345</chNFe></infProt></protNFe>
</nfeProc>
"""


class NfeProcessoTests(unittest.TestCase):
    def test_parser_de_xml_no_modelo_da_nfe(self):
        dados = extrair_dados_xml_nfe(_XML_NFE)
        self.assertEqual(dados["pedido_numero"], "PD 00010")
        self.assertEqual(dados["numero_nf"], "1234")
        self.assertEqual(dados["transportadora"], "Transportadora Obra Ltda")
        self.assertEqual(dados["destino_obra"], "Entrega na obra: Rua das Flores, 100 - Campinas/SP")
        self.assertEqual(dados["chave_nfe"], "35260911222333000181550010000012341000012345")
        fiscal = _XML_NFE.replace(
            "<infCpl>Entrega na obra: Rua das Flores, 100 - Campinas/SP</infCpl>",
            "<infCpl>PIS AL 1.65% VALOR R$45,56|++++++++++++++++++++++++++++++++|OBRA: RESIDENCIAL ARES - ENDERECO: AV MARIO ZAMPIERI, 1592 - ARARAQUARA - SP</infCpl>",
        ).replace("<xNome>Transportadora Obra Ltda</xNome>", "<xNome>MOVVI LOGISTICA LTDA</xNome>")
        obra = extrair_dados_xml_nfe(fiscal)
        self.assertEqual(obra["transportadora"], "MOVVI LOGISTICA LTDA")
        self.assertTrue(obra["destino_obra"].startswith("OBRA: RESIDENCIAL ARES"))
        self.assertNotIn("PIS", obra["destino_obra"])

        sem_complemento = _XML_NFE.replace(
            "<infAdic><infCpl>Entrega na obra: Rua das Flores, 100 - Campinas/SP</infCpl></infAdic>",
            "",
        )
        self.assertEqual(extrair_dados_xml_nfe(sem_complemento)["destino_obra"], "Campinas/SP")
        self.assertEqual(extrair_dados_xml_nfe(None)["numero_nf"], "")
        self.assertEqual(extrair_dados_xml_nfe("<nfe")["pedido_numero"], "")

    def test_pedido_recebe_nfe_pelo_xped(self):
        carteira = montar_carteira(
            [_cliente(1, "Construtora Pacaembu")],
            [_produto(1, "Saneamento", "Caixa de hidrômetro")],
            [
                _pedido(10, 1, "01/09/2026", "1000,00", 1),
                _pedido(11, 1, "02/09/2026", "50,00", 1),
            ],
            nfes_raw=[{"id": 9, "xml": _XML_NFE}],
        )
        por_codigo = {pedido.codigo: pedido for pedido in carteira.clients[0].pedidos}
        vinculado = por_codigo["PD 00010"].nfe_info
        self.assertIsNotNone(vinculado)
        self.assertEqual(vinculado.numero_nf, "1234")
        self.assertEqual(vinculado.transportadora, "Transportadora Obra Ltda")
        self.assertIn("Rua das Flores", vinculado.destino_obra)
        self.assertIsNone(por_codigo["PD 00011"].nfe_info)

    def test_nfe_entra_no_pedido_pela_chave_quando_xped_e_do_cliente(self):
        xml = _XML_NFE.replace("<xPed>PD 00010</xPed>", "<xPed>4509572623</xPed>")
        pedido = _pedido(10, 1, "01/09/2026", "1000,00", 1)
        pedido["codigoPedido"] = "PD 06456"
        pedido["nfes"] = [{"chave": "35260911222333000181550010000012341000012345", "numero": "1234"}]
        pedido["observacoes"] = "OBRA RESIDENCIAL ARES\nPedido de Compras MRV: 4509572623"
        carteira = montar_carteira(
            [_cliente(1, "Construtora Pacaembu")],
            [_produto(1, "Saneamento", "Caixa de hidrômetro")],
            [pedido],
            nfes_raw=[{"id": 9, "xml": xml, "chave": "35260911222333000181550010000012341000012345"}],
        )
        info = carteira.clients[0].pedidos[0].nfe_info
        self.assertIsNotNone(info)
        self.assertEqual(info.numero_nf, "1234")
        self.assertEqual(info.transportadora, "Transportadora Obra Ltda")
        self.assertIn("Rua das Flores", info.destino_obra)

    def test_processo_de_venda_vai_para_o_cliente_pela_pessoa(self):
        carteira = montar_carteira(
            [
                _cliente(1, "Construtora Pacaembu", fantasia="Pacaembu"),
                _cliente(2, "Instaladora Beta", fantasia="Beta"),
            ],
            [_produto(1, "Gás", "Abrigo de gás GLP")],
            [_pedido(10, 1, "01/01/2026", "5000,00", 1)],
            processos_raw=[
                {
                    "id": 77,
                    "equipe": "Vendas",
                    "etapa": "Proposta / Orçamentos",
                    "prioridade": "Alta",
                    "dataHoraProgramada": "25/09/2026 09:00:00",
                    "descricao": "Abrigo de gás GLP da obra escola",
                    "valor": "86400,00",
                    "pessoa": {"id": 1, "nome": "Construtora Pacaembu", "documento": "11222333000181"},
                },
                {
                    "id": 78,
                    "equipe": "Produção",
                    "etapa": "Proposta / Orçamentos",
                    "pessoa": {"id": 1, "nome": "Construtora Pacaembu"},
                },
                {
                    "id": 79,
                    "equipe": "Vendas",
                    "etapa": "Proposta / Orçamentos",
                    "concluido": True,
                    "pessoa": {"nome": "Construtora Pacaembu"},
                },
                {
                    "id": 80,
                    "equipe": "Vendas",
                    "etapa": "Visita à obra",
                    "prioridade": "Média",
                    "dataHoraProgramada": "23/09/2026 14:00:00",
                    "descricao": "Confirmar shaft na obra",
                    "pessoa": "Instaladora Beta",
                },
            ],
        )
        por_id = {ficha.nomusId: ficha for ficha in carteira.clients}
        pacaembu = por_id[1]
        self.assertEqual(pacaembu.ranking, "resposta")
        self.assertEqual([proc.id for proc in pacaembu.processos], ["77"])
        self.assertEqual(pacaembu.processos[0].pessoa, "Construtora Pacaembu")
        self.assertEqual(pacaembu.processos[0].prioridade, "Alta")
        self.assertEqual(pacaembu.processos[0].dataHoraProgramada, "25/09/2026 09:00:00")
        self.assertEqual(pacaembu.orcamentos[0]["item"], "Abrigo de gás GLP da obra escola")
        self.assertEqual(pacaembu.orcamentos[0]["valor"], 86400.0)
        self.assertEqual(pacaembu.orcamentos[0]["data"], "2026-09-25")
        beta = por_id[2]
        self.assertEqual([proc.id for proc in beta.processos], ["80"])
        self.assertEqual(beta.processos[0].pessoa, "Instaladora Beta")
        self.assertNotEqual(beta.ranking, "resposta")


class ClienteHttpTests(unittest.TestCase):
    def test_pagina_ate_lista_vazia_e_respeita_retry_after(self):
        sessao = _Sessao(
            [
                _Resposta(429, [], headers={"Retry-After": "11"}),
                _Resposta(200, [{"id": 1}, {"id": 2}]),
                _Resposta(200, []),
            ]
        )
        esperas: list[float] = []
        cliente = NomusClient(
            base_url="https://ehe.example/rest",
            auth_token="tokensecreto",
            session=sessao,
            espera_pagina=0,
            dormir=esperas.append,
        )
        linhas = cliente.listar_clientes()
        self.assertEqual([item["id"] for item in linhas], [1, 2])
        self.assertEqual(sessao.chamadas[0]["params"], {"pagina": 1})
        self.assertEqual(sessao.chamadas[-1]["params"], {"pagina": 2})
        self.assertEqual(sessao.headers["Authorization"], "Basic tokensecreto")
        self.assertEqual(esperas, [11.0])

    def test_429_sem_cabecalho_usa_backoff_com_jitter(self):
        sessao = _Sessao([_Resposta(429, []), _Resposta(200, [{"id": 3}]), _Resposta(200, [])])
        esperas: list[float] = []
        cliente = NomusClient(
            base_url="https://ehe.example/rest",
            auth_token="abc",
            session=sessao,
            espera_pagina=0,
            dormir=esperas.append,
        )
        with patch("backend.nomus_client.random.uniform", return_value=0.7) as jitter:
            linhas = cliente.listar_clientes()
        self.assertEqual([item["id"] for item in linhas], [3])
        self.assertEqual(esperas, [BASE_DELAY * (2**0) + 0.7])
        self.assertEqual(jitter.call_args.args, (0.5, 1.5))

    def test_429_encerra_na_quinta_tentativa(self):
        sessao = _Sessao([_Resposta(429, []) for _ in range(TENTATIVAS_RESPOSTA)])
        esperas: list[float] = []
        cliente = NomusClient(
            base_url="https://ehe.example/rest",
            auth_token="abc",
            session=sessao,
            espera_pagina=0,
            dormir=esperas.append,
        )
        with patch("backend.nomus_client.random.uniform", return_value=1.0):
            with self.assertRaises(NomusError) as captura:
                cliente.listar_clientes()
        self.assertIn("5 tentativas", str(captura.exception))
        self.assertEqual(esperas, [BASE_DELAY * (2**tentativa) + 1.0 for tentativa in range(TENTATIVAS_RESPOSTA - 1)])
        self.assertEqual(len(sessao.chamadas), TENTATIVAS_RESPOSTA)

    def test_adaptador_urllib3_repete_429_com_backoff(self):
        sessao = requests.Session()
        cliente = NomusClient(
            base_url="https://ehe.example/rest",
            auth_token="abc",
            session=sessao,
            dormir=lambda _: None,
        )
        try:
            politica = sessao.get_adapter("https://ehe.example/rest/clientes").max_retries
        finally:
            cliente.fechar()
        self.assertEqual(politica.total, TENTATIVAS_RESPOSTA)
        self.assertEqual(politica.backoff_factor, BASE_DELAY)
        self.assertEqual(politica.raise_on_status, False)
        self.assertEqual(politica.respect_retry_after_header, True)
        self.assertTrue(all(codigo in politica.status_forcelist for codigo in STATUS_ADAPTADOR))
        self.assertEqual(cliente.retentativa.total, 5)
        self.assertEqual(cliente.retentativa.backoff_factor, 2)
        historico: tuple = ()
        pausas: list[float] = []
        politica = cliente.retentativa
        for _ in range(5):
            historico = historico + (RequestHistory("GET", "https://ehe.example/rest/clientes", None, 429, None),)
            politica = politica.new(history=historico)
            pausas.append(politica.get_backoff_time())
        self.assertEqual(pausas, [2.0, 4.0, 8.0, 16.0, 32.0])

    def test_intervalo_padrao_entre_paginas(self):
        cliente = NomusClient(
            base_url="https://ehe.example/rest",
            auth_token="abc",
            session=_Sessao([]),
            dormir=lambda _: None,
        )
        self.assertEqual(cliente.espera_pagina, INTERVALO_PAGINA)
        self.assertEqual(INTERVALO_PAGINA, 1.5)

    def test_pausa_de_1_5s_entre_paginas_bem_sucedidas(self):
        sessao = _Sessao(
            [
                _Resposta(200, [{"id": 1}]),
                _Resposta(200, [{"id": 2}]),
                _Resposta(200, []),
            ]
        )
        esperas: list[float] = []
        cliente = NomusClient(
            base_url="https://ehe.example/rest",
            auth_token="abc",
            session=sessao,
            dormir=esperas.append,
        )
        self.assertEqual([item["id"] for item in cliente.listar_produtos()], [1, 2])
        self.assertEqual(esperas, [1.5, 1.5])

    def test_pagina_repetida_nao_entra_em_loop(self):
        sessao = _Sessao([_Resposta(200, [{"id": 7}]), _Resposta(200, [{"id": 7}])])
        cliente = NomusClient(
            base_url="https://ehe.example/rest",
            auth_token="abc",
            session=sessao,
            espera_pagina=0,
            dormir=lambda _: None,
        )
        self.assertEqual(len(cliente.listar_produtos()), 1)

    def test_401_nao_revela_o_token(self):
        sessao = _Sessao([_Resposta(401, {"erro": "tokensecreto"}, text="tokensecreto")])
        cliente = NomusClient(
            base_url="https://ehe.example/rest",
            auth_token="tokensecreto",
            session=sessao,
            dormir=lambda _: None,
        )
        with self.assertRaises(NomusAuthError) as captura:
            cliente.listar_pedidos_venda()
        self.assertNotIn("tokensecreto", str(captura.exception))
        self.assertTrue(sessao.chamadas[0]["url"].endswith("/pedidos"))
        self.assertNotIn("pedidos-venda", sessao.chamadas[0]["url"])

    def test_pedidos_recentes_filtram_pedido_de_venda(self):
        sessao = _Sessao(
            [
                _Resposta(200, [{"id": 30, "codigoPedido": "PD 00030", "dataEmissao": "22/09/2026"}]),
                _Resposta(200, []),
            ]
        )
        cliente = NomusClient(
            base_url="https://ehe.example/rest",
            auth_token="abc",
            session=sessao,
            espera_pagina=0,
            dormir=lambda _: None,
        )
        linhas = cliente.listar_pedidos_recentes(set())
        self.assertEqual([item["id"] for item in linhas], [30])
        self.assertTrue(all(chamada["url"].endswith("/pedidos") for chamada in sessao.chamadas))
        self.assertEqual(sessao.chamadas[0]["params"], {"query": "idTipoPedido=2", "pagina": 1})
        self.assertEqual(sessao.chamadas[1]["params"], {"query": "idTipoPedido=2", "pagina": 2})

    def test_formato_inesperado_explica_a_pagina(self):
        sessao = _Sessao([_Resposta(200, {"content": [{"id": 1}]})])
        cliente = NomusClient(
            base_url="https://ehe.example/rest",
            auth_token="abc",
            session=sessao,
            dormir=lambda _: None,
        )
        with self.assertRaises(NomusError):
            cliente.listar_clientes()

    def test_token_ausente(self):
        with self.assertRaises(NomusAuthError):
            NomusClient(base_url="https://ehe.example/rest", auth_token="")

    def test_clientes_recentes_param_no_id_conhecido(self):
        sessao = _Sessao(
            [
                _Resposta(200, [{"id": 4, "razaoSocial": "Antiga"}, {"id": 9, "razaoSocial": "Nova"}, {"id": 8}]),
                _Resposta(200, [{"id": 1}]),
            ]
        )
        cliente = NomusClient(
            base_url="https://ehe.example/rest",
            auth_token="abc",
            session=sessao,
            espera_pagina=0,
            dormir=lambda _: None,
        )
        novos = cliente.listar_clientes_recentes({"id:4"})
        self.assertEqual([item["id"] for item in novos], [9, 8])
        self.assertEqual(len(sessao.chamadas), 1)

    def test_processos_paginam_com_pausa_e_filtram_vendas(self):
        sessao = _Sessao(
            [
                _Resposta(200, [{"id": 1, "equipe": "Vendas"}, {"id": 2, "equipe": "Produção"}]),
                _Resposta(200, [{"id": 3, "equipe": "vendas"}]),
                _Resposta(200, []),
            ]
        )
        esperas: list[float] = []
        cliente = NomusClient(
            base_url="https://ehe.example/rest",
            auth_token="abc",
            session=sessao,
            dormir=esperas.append,
        )
        linhas = cliente.listar_processos(paginas=3)
        self.assertEqual([item["id"] for item in linhas], [1, 3])
        self.assertTrue(sessao.chamadas[0]["url"].endswith("/processos"))
        self.assertEqual(sessao.chamadas[0]["timeout"], 60)
        self.assertEqual(sessao.chamadas[0]["params"], {"pagina": 1})
        self.assertEqual(sessao.chamadas[1]["params"], {"pagina": 2})
        self.assertEqual(esperas, [1.5, 1.5])

    def test_nfes_devolve_o_xml_das_paginas_recentes(self):
        sessao = _Sessao(
            [
                _Resposta(200, [{"id": 9, "xml": "<NFe/>"}]),
                _Resposta(200, []),
            ]
        )
        cliente = NomusClient(
            base_url="https://ehe.example/rest",
            auth_token="abc",
            session=sessao,
            espera_pagina=0,
            dormir=lambda _: None,
        )
        notas = cliente.listar_nfes(paginas=2)
        self.assertEqual(notas[0]["xml"], "<NFe/>")
        self.assertTrue(sessao.chamadas[0]["url"].endswith("/nfes"))
        self.assertEqual(sessao.chamadas[0]["params"], {"pagina": 1})


class _FonteClientes:
    def __init__(self, recentes=None, completos=None):
        self.recentes = recentes if recentes is not None else [{"id": 9, "razaoSocial": "Nova", "cnpj": "1"}]
        self.completos = completos if completos is not None else [{"id": 1, "razaoSocial": "Todas", "cnpj": "2"}]
        self.chamou_completa = 0
        self.chamou_recente = 0
        self.conhecidos = None

    def listar_clientes(self):
        self.chamou_completa += 1
        return list(self.completos)

    def listar_clientes_recentes(self, conhecidos):
        self.chamou_recente += 1
        self.conhecidos = set(conhecidos)
        return list(self.recentes)


class CacheClientesTests(unittest.TestCase):
    def test_ficha_do_crmer_nao_conta_como_cache_nomus(self):
        payload = {"clientes": [{"id": "nomus-1", "razaoSocial": "Pacaembu", "ranking": "contato"}]}
        self.assertEqual(clientes_em_cache(payload), [])

    def test_arquivo_local_evita_varredura_completa(self):
        historico = {
            "nomusClientes": [
                {"id": 4, "razaoSocial": "Horizonte", "cnpj": "11222333000181"},
            ]
        }
        fonte = _FonteClientes()
        clientes, modo, novos = reunir_clientes(fonte, historico, completo=False)
        self.assertEqual(modo, "incremental")
        self.assertEqual(fonte.chamou_completa, 0)
        self.assertEqual(fonte.chamou_recente, 1)
        self.assertEqual(fonte.conhecidos, {"id:4"})
        self.assertEqual([item["id"] for item in novos], [9])
        self.assertEqual([item["id"] for item in clientes], [9, 4])

    def test_full_forca_varredura_desde_o_inicio(self):
        historico = {"nomusClientes": [{"id": 4, "razaoSocial": "Horizonte", "cnpj": "1"}]}
        fonte = _FonteClientes()
        clientes, modo, novos = reunir_clientes(fonte, historico, completo=True)
        self.assertEqual(modo, "completa")
        self.assertEqual(fonte.chamou_completa, 1)
        self.assertEqual(fonte.chamou_recente, 0)
        self.assertEqual(clientes, novos)
        self.assertTrue(construir_parser().parse_args(["--full"]).full)


if __name__ == "__main__":
    unittest.main()
