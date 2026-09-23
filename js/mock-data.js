/*
 * Dados simulados da carteira EHE e usuários de teste.
 * Senhas não aparecem aqui: cada conta guarda só sal e hash SHA-256.
 */
(function (root) {
  "use strict";
  root.CRMER_MOCK = {
  "TODAY": "2026-09-22",
  "LINHAS": [
    "Gás",
    "Saneamento",
    "Elétrica",
    "Fechamento"
  ],
  "UFS": [
    "SP",
    "RJ",
    "MG",
    "PR",
    "SC",
    "RS"
  ],
  "RANKINGS": {
    "contato": {
      "label": "Devem receber contato",
      "help": "Follow-up de hoje ou atrasado. Se o contato é reagendado para outra data, a ficha continua aqui, no grupo Reagendados, e sai da agenda de hoje."
    },
    "resposta": {
      "label": "Aguardando resposta",
      "help": "Orçamento já enviado, ainda sem retorno do comprador. A negociação continua viva."
    },
    "sazonal": {
      "label": "Compram nesta época",
      "help": "Histórico de compra neste período do ano, mesmo sem pedido aberto. O contato é pela janela da obra."
    },
    "inativos": {
      "label": "Importantes inativos",
      "help": "Curva A ou B, com faturamento relevante e sem compra recente. O contato é de reativação."
    }
  },
  "EHE": {
    "faturamentoNatalia": 186400,
    "metaMes": 250000,
    "faturamentoEquipe": 642800,
    "linhas": [
      {
        "nome": "Gás",
        "faturamento": 244264,
        "pecas": 860
      },
      {
        "nome": "Saneamento",
        "faturamento": 199268,
        "pecas": 1240
      },
      {
        "nome": "Elétrica",
        "faturamento": 141416,
        "pecas": 540
      },
      {
        "nome": "Fechamento",
        "faturamento": 57852,
        "pecas": 210
      }
    ]
  },
  "usuarios": [
    {
      "nome": "Natália",
      "email": "natalia@ehe.example",
      "usuario": "natalia",
      "perfil": "vendedora",
      "salt": "e2baf0939f90439f648b42120c422472",
      "passwordHash": "b58a1f307131c142a28e4021491efb1824a35878fd9bdbdb4ca1f99e04124b7a"
    },
    {
      "nome": "Helena Duarte",
      "email": "admin@ehe.example",
      "usuario": "admin",
      "perfil": "administrador",
      "salt": "24aec8a7214f0031d2e35bfc2089bc6c",
      "passwordHash": "6ec83f3cae1def7c273e7b7e2d9c3db2d1fd2055e48bc0f311e816d73cb2ebc5"
    }
  ],
  "clients": [
    {
      "nomeFantasia": "Pacaembu",
      "cnpj": "11.111.110/0001-01",
      "whatsapp": "(11) 98810-2290",
      "id": "cli-pacaembu",
      "razaoSocial": "Construtora Pacaembu",
      "tipo": "Construtora",
      "contato": "Ricardo Mendes",
      "cargo": "Comprador",
      "email": "compras@pacaembu.example",
      "telefone": "(11) 98810-2201",
      "cidade": "São Paulo",
      "uf": "SP",
      "linhas": [
        "Saneamento"
      ],
      "ranking": "contato",
      "prioridade": "alta",
      "curva": "",
      "faturamento12m": 428600,
      "ultimaCompra": "2026-08-12",
      "proximoContato": "2026-09-22",
      "janelaSazonal": "",
      "resumo": "Confirmar o lote de caixas de hidrômetro da obra na Vila Mariana.",
      "anotacoes": "Obra de duas torres na Vila Mariana. O padrão é caixa de hidrômetro para 1 medidor, tampa basculante e pintura eletrostática cinza. Ricardo atende melhor no fim da manhã e pediu para não misturar abrigo de gás neste contrato.",
      "pedidos": [
        {
          "codigo": "NM-10482",
          "data": "2026-08-12",
          "item": "Caixa de hidrômetro metálica, 1 medidor",
          "quantidade": 40,
          "valor": 18400,
          "nfe_info": {
            "pedido_numero": "NM-10482",
            "numero_nf": "45821",
            "transportadora": "TransOeste Cargas",
            "destino_obra": "Obra Vila Mariana — Rua Domingos de Morais, 1200, São Paulo/SP",
            "chave_nfe": "35260811111110000101550010000458211000045821"
          }
        },
        {
          "codigo": "NM-9860",
          "data": "2026-05-03",
          "item": "Caixa de inspeção para cavalete",
          "quantidade": 20,
          "valor": 7600
        },
        {
          "codigo": "NM-9422",
          "data": "2026-02-17",
          "item": "Caixa de hidrômetro metálica, 1 medidor",
          "quantidade": 60,
          "valor": 31200
        }
      ],
      "orcamentos": []
    },
    {
      "nomeFantasia": "Hidrosul",
      "cnpj": "11.111.111/0001-02",
      "whatsapp": "(11) 99720-4418",
      "id": "cli-hidrosul",
      "razaoSocial": "Hidrosul Instalações",
      "tipo": "Instaladora",
      "contato": "Carla Nogueira",
      "cargo": "Sócia",
      "email": "carla@hidrosul.example",
      "telefone": "(11) 99720-4418",
      "cidade": "Guarulhos",
      "uf": "SP",
      "linhas": [
        "Saneamento"
      ],
      "ranking": "contato",
      "prioridade": "alta",
      "curva": "",
      "faturamento12m": 196400,
      "ultimaCompra": "2026-07-28",
      "proximoContato": "2026-09-18",
      "janelaSazonal": "",
      "resumo": "Follow-up atrasado sobre o lote reserva de 30 caixas de hidrômetro.",
      "anotacoes": "Parceira em obras de saneamento na zona leste. Ficou de confirmar se o condomínio de Guarulhos mantém o lote reserva. Ligar antes das 10h.",
      "pedidos": [
        {
          "codigo": "NM-10311",
          "data": "2026-07-28",
          "item": "Caixa de hidrômetro metálica, 1 medidor",
          "quantidade": 30,
          "valor": 13800
        },
        {
          "codigo": "NM-9904",
          "data": "2026-04-09",
          "item": "Caixa de hidrômetro para 2 medidores",
          "quantidade": 15,
          "valor": 11250
        }
      ],
      "orcamentos": []
    },
    {
      "nomeFantasia": "Vale Verde",
      "cnpj": "11.111.112/0001-03",
      "whatsapp": "(11) 98116-9033",
      "id": "cli-valeverde",
      "razaoSocial": "Construtora Vale Verde",
      "tipo": "Construtora",
      "contato": "André Luz",
      "cargo": "Engenheiro de obras",
      "email": "andre.luz@valeverde.example",
      "telefone": "(11) 98116-9033",
      "cidade": "Osasco",
      "uf": "SP",
      "linhas": [
        "Saneamento",
        "Gás"
      ],
      "ranking": "contato",
      "prioridade": "media",
      "curva": "",
      "faturamento12m": 154200,
      "ultimaCompra": "2026-08-30",
      "proximoContato": "2026-09-22",
      "janelaSazonal": "",
      "resumo": "Fechar a medição da torre B: caixas de hidrômetro e um lote pequeno de abrigo de gás.",
      "anotacoes": "Condomínio em Osasco, fase de instalações. A torre A já foi faturada. A torre B precisa de caixas de hidrômetro e poucos abrigos de gás no mesmo pedido.",
      "pedidos": [
        {
          "codigo": "NM-10540",
          "data": "2026-08-30",
          "item": "Caixa de hidrômetro metálica, 1 medidor",
          "quantidade": 24,
          "valor": 11040
        },
        {
          "codigo": "NM-10541",
          "data": "2026-08-30",
          "item": "Abrigo de gás GLP de sobrepor",
          "quantidade": 6,
          "valor": 18600
        }
      ],
      "orcamentos": []
    },
    {
      "nomeFantasia": "Paulista",
      "cnpj": "11.111.113/0001-04",
      "whatsapp": "(11) 97654-1199",
      "id": "cli-paulista",
      "razaoSocial": "Instaladora Paulista",
      "tipo": "Instaladora",
      "contato": "Fernanda Alves",
      "cargo": "Compradora",
      "email": "fernanda@paulista.example",
      "telefone": "(11) 97654-1180",
      "cidade": "São Paulo",
      "uf": "SP",
      "linhas": [
        "Gás"
      ],
      "ranking": "resposta",
      "prioridade": "alta",
      "curva": "",
      "faturamento12m": 312900,
      "ultimaCompra": "2026-06-18",
      "proximoContato": "",
      "janelaSazonal": "",
      "resumo": "Orçamento de abrigos de gás da obra em Perdizes parado com o engenheiro.",
      "anotacoes": "ORC-3391 enviado em 10/09. Fernanda disse que a obra de Perdizes depende da aprovação do engenheiro. Não oferecer desconto antes do retorno técnico. O kit de ventilação foi orçado à parte.",
      "pedidos": [
        {
          "codigo": "NM-10102",
          "data": "2026-06-18",
          "item": "Abrigo para medidor de gás",
          "quantidade": 18,
          "valor": 43200
        },
        {
          "codigo": "NM-9720",
          "data": "2026-03-11",
          "item": "Abrigo de gás GLP de sobrepor",
          "quantidade": 10,
          "valor": 31000
        }
      ],
      "orcamentos": [
        {
          "codigo": "ORC-3391",
          "data": "2026-09-10",
          "item": "Abrigo de gás GLP de sobrepor",
          "valor": 86400
        },
        {
          "codigo": "ORC-3404",
          "data": "2026-09-16",
          "item": "Kit de ventilação para abrigo de gás",
          "valor": 6200
        }
      ],
      "processos": [
        {
          "id": "77",
          "equipe": "Vendas",
          "etapa": "Proposta / Orçamentos",
          "prioridade": "Alta",
          "dataHoraProgramada": "24/09/2026 09:30:00",
          "descricao": "Abrigo de gás GLP da obra em Perdizes",
          "pessoa": "Instaladora Paulista"
        }
      ]
    },
    {
      "nomeFantasia": "Beta",
      "cnpj": "11.111.114/0001-05",
      "whatsapp": "(11) 99440-2275",
      "id": "cli-beta",
      "razaoSocial": "Instaladora Beta",
      "tipo": "Instaladora",
      "contato": "Marcos Teixeira",
      "cargo": "Supervisor de compras",
      "email": "marcos@instaladorabeta.example",
      "telefone": "(11) 99440-2275",
      "cidade": "Santo André",
      "uf": "SP",
      "linhas": [
        "Gás"
      ],
      "ranking": "resposta",
      "prioridade": "media",
      "curva": "",
      "faturamento12m": 188300,
      "ultimaCompra": "2026-07-02",
      "proximoContato": "",
      "janelaSazonal": "",
      "resumo": "Proposta de abrigo para medidor de gás sem retorno desde 5 de setembro.",
      "anotacoes": "Cliente recorrente de abrigo para medidor de gás. A proposta de Santo André está parada. Marcos costuma responder melhor por telefone do que por e-mail.",
      "pedidos": [
        {
          "codigo": "NM-10244",
          "data": "2026-07-02",
          "item": "Abrigo para medidor de gás",
          "quantidade": 12,
          "valor": 28800
        }
      ],
      "orcamentos": [
        {
          "codigo": "ORC-3360",
          "data": "2026-09-05",
          "item": "Abrigo para medidor de gás",
          "valor": 42750
        }
      ]
    },
    {
      "nomeFantasia": "Elétrica Norte",
      "cnpj": "11.111.115/0001-06",
      "whatsapp": "(19) 98821-6409",
      "id": "cli-norte",
      "razaoSocial": "Elétrica Norte Instalações",
      "tipo": "Instaladora",
      "contato": "Paulo Henrique Dias",
      "cargo": "Comprador",
      "email": "paulo@eletricanorte.example",
      "telefone": "(19) 98821-6409",
      "cidade": "Campinas",
      "uf": "SP",
      "linhas": [
        "Elétrica"
      ],
      "ranking": "resposta",
      "prioridade": "media",
      "curva": "",
      "faturamento12m": 143800,
      "ultimaCompra": "2026-05-26",
      "proximoContato": "",
      "janelaSazonal": "",
      "resumo": "Abrigos de medição para subestação compacta, com instalação prevista em outubro.",
      "anotacoes": "Obra em Campinas. O prazo de instalação é outubro, então o silêncio de uma semana ainda cabe numa cobrança leve. Paulo compara com o padrão de chapa que usaram no ano passado.",
      "pedidos": [
        {
          "codigo": "NM-9988",
          "data": "2026-05-26",
          "item": "Abrigo de medição elétrica",
          "quantidade": 8,
          "valor": 24800
        }
      ],
      "orcamentos": [
        {
          "codigo": "ORC-3412",
          "data": "2026-09-15",
          "item": "Abrigo de medição elétrica",
          "valor": 63200
        }
      ]
    },
    {
      "nomeFantasia": "Horizonte",
      "cnpj": "11.111.116/0001-07",
      "whatsapp": "(11) 98330-5512",
      "id": "cli-horizonte",
      "razaoSocial": "Construtora Horizonte",
      "tipo": "Construtora",
      "contato": "Helena Prado",
      "cargo": "Engenharia",
      "email": "helena.prado@horizonte.example",
      "telefone": "(11) 98330-5512",
      "cidade": "São Paulo",
      "uf": "SP",
      "linhas": [
        "Elétrica"
      ],
      "ranking": "sazonal",
      "prioridade": "media",
      "curva": "",
      "faturamento12m": 221500,
      "ultimaCompra": "2026-05-20",
      "proximoContato": "",
      "janelaSazonal": "Setembro e outubro",
      "resumo": "Todo setembro e outubro compra abrigos elétricos para obras de escolas.",
      "anotacoes": "Em 2025 foram cerca de 80 abrigos elétricos entre setembro e outubro. Neste ano o pedido ainda não abriu. Vale falar com a Helena sobre o calendário das escolas.",
      "pedidos": [
        {
          "codigo": "NM-10011",
          "data": "2026-05-20",
          "item": "Caixa de passagem elétrica",
          "quantidade": 50,
          "valor": 9500
        },
        {
          "codigo": "NM-8810",
          "data": "2025-09-25",
          "item": "Abrigo de medição elétrica",
          "quantidade": 80,
          "valor": 196000
        }
      ],
      "orcamentos": []
    },
    {
      "nomeFantasia": "Alfa",
      "cnpj": "11.111.117/0001-08",
      "whatsapp": "(11) 99102-7741",
      "id": "cli-alfa",
      "razaoSocial": "Construtora Alfa",
      "tipo": "Construtora",
      "contato": "Renata Martins",
      "cargo": "Coordenadora de suprimentos",
      "email": "renata.martins@alfa.example",
      "telefone": "(11) 99102-7741",
      "cidade": "São Bernardo do Campo",
      "uf": "SP",
      "linhas": [
        "Fechamento",
        "Elétrica"
      ],
      "ranking": "sazonal",
      "prioridade": "media",
      "curva": "",
      "faturamento12m": 267400,
      "ultimaCompra": "2026-04-02",
      "proximoContato": "",
      "janelaSazonal": "Setembro e outubro",
      "resumo": "Pico de fechamento de shaft no início da primavera, junto com abrigo elétrico.",
      "anotacoes": "No ano passado levaram portas de shaft e abrigo elétrico no mesmo mês. A engenharia puxa a especificação; o pedido nasce no suprimentos com a Renata.",
      "pedidos": [
        {
          "codigo": "NM-9644",
          "data": "2026-04-02",
          "item": "Porta de fechamento de shaft",
          "quantidade": 30,
          "valor": 27600
        },
        {
          "codigo": "NM-8702",
          "data": "2025-09-18",
          "item": "Porta de fechamento de shaft",
          "quantidade": 46,
          "valor": 42320
        }
      ],
      "orcamentos": []
    },
    {
      "nomeFantasia": "Serra Azul",
      "cnpj": "11.111.118/0001-09",
      "whatsapp": "(15) 99771-2208",
      "id": "cli-serra",
      "razaoSocial": "Construtora Serra Azul",
      "tipo": "Construtora",
      "contato": "Tiago Beraldo",
      "cargo": "Suprimentos",
      "email": "tiago@serraazul.example",
      "telefone": "(15) 99771-2208",
      "cidade": "Sorocaba",
      "uf": "SP",
      "linhas": [
        "Elétrica"
      ],
      "ranking": "sazonal",
      "prioridade": "media",
      "curva": "",
      "faturamento12m": 98000,
      "ultimaCompra": "2026-06-11",
      "proximoContato": "",
      "janelaSazonal": "Setembro",
      "resumo": "Em setembro costuma repor caixas de passagem para obras horizontais.",
      "anotacoes": "Padrão sazonal de caixas de passagem elétrica. O estoque da obra horizontal em Sorocaba é reposto quando a terraplenagem libera as ruas internas.",
      "pedidos": [
        {
          "codigo": "NM-10190",
          "data": "2026-06-11",
          "item": "Caixa de passagem elétrica",
          "quantidade": 80,
          "valor": 15200
        },
        {
          "codigo": "NM-8601",
          "data": "2025-09-09",
          "item": "Caixa de passagem elétrica",
          "quantidade": 140,
          "valor": 26600
        }
      ],
      "orcamentos": []
    },
    {
      "nomeFantasia": "Engeobra",
      "cnpj": "11.111.119/0001-10",
      "whatsapp": "(11) 98220-1194",
      "id": "cli-engeobra",
      "razaoSocial": "Engeobra Leste",
      "tipo": "Construtora",
      "contato": "Sérgio Albuquerque",
      "cargo": "Diretor de suprimentos",
      "email": "sergio@engeobra.example",
      "telefone": "(11) 98220-1194",
      "cidade": "São Paulo",
      "uf": "SP",
      "linhas": [
        "Gás",
        "Saneamento"
      ],
      "ranking": "inativos",
      "prioridade": "alta",
      "curva": "A",
      "faturamento12m": 512000,
      "ultimaCompra": "2026-01-18",
      "proximoContato": "",
      "janelaSazonal": "",
      "resumo": "Curva A sem pedido desde janeiro. Reativar o relacionamento, sem reabrir orçamento antigo.",
      "anotacoes": "Última compra grande misturou abrigos de gás e caixas de hidrômetro. Desde então não houve obra nova informada. O contato certo é o Sérgio, não o comprador operacional que saiu em fevereiro.",
      "pedidos": [
        {
          "codigo": "NM-9102",
          "data": "2026-01-18",
          "item": "Abrigo de gás GLP de sobrepor",
          "quantidade": 22,
          "valor": 68200
        },
        {
          "codigo": "NM-9103",
          "data": "2026-01-18",
          "item": "Caixa de hidrômetro metálica, 1 medidor",
          "quantidade": 90,
          "valor": 41400
        }
      ],
      "orcamentos": []
    },
    {
      "nomeFantasia": "Gás Service",
      "cnpj": "11.111.120/0001-11",
      "whatsapp": "(11) 99660-8080",
      "id": "cli-gasservice",
      "razaoSocial": "Gás Service Instalações",
      "tipo": "Instaladora",
      "contato": "Patrícia Roman",
      "cargo": "Diretora técnica",
      "email": "patricia@gasservice.example",
      "telefone": "(11) 99660-8080",
      "cidade": "São José dos Campos",
      "uf": "SP",
      "linhas": [
        "Gás"
      ],
      "ranking": "inativos",
      "prioridade": "alta",
      "curva": "A",
      "faturamento12m": 389000,
      "ultimaCompra": "2026-03-02",
      "proximoContato": "",
      "janelaSazonal": "",
      "resumo": "Especialista em gás, sem compra desde março. Investigar se o padrão de abrigo mudou.",
      "anotacoes": "Faturamento alto até março e silêncio depois. Pode ter trocado o modelo de abrigo ou concentrado a compra em outro fornecedor. A conversa precisa ser técnica, de preferência com visita, não só uma ligação de cobrança.",
      "pedidos": [
        {
          "codigo": "NM-9488",
          "data": "2026-03-02",
          "item": "Abrigo para regulador de gás",
          "quantidade": 16,
          "valor": 51200
        },
        {
          "codigo": "NM-9301",
          "data": "2026-01-07",
          "item": "Abrigo de gás GLP de sobrepor",
          "quantidade": 14,
          "valor": 43400
        }
      ],
      "orcamentos": []
    },
    {
      "nomeFantasia": "Centro",
      "cnpj": "11.111.121/0001-12",
      "whatsapp": "(11) 97331-4456",
      "id": "cli-centro",
      "razaoSocial": "Instaladora Centro",
      "tipo": "Instaladora",
      "contato": "Juliana Rocha",
      "cargo": "Compradora",
      "email": "juliana@centro.example",
      "telefone": "(11) 97331-4456",
      "cidade": "São Paulo",
      "uf": "SP",
      "linhas": [
        "Saneamento"
      ],
      "ranking": "inativos",
      "prioridade": "media",
      "curva": "B",
      "faturamento12m": 276000,
      "ultimaCompra": "2025-12-09",
      "proximoContato": "",
      "janelaSazonal": "",
      "resumo": "Curva B de caixas de hidrômetro, parada desde dezembro de 2025.",
      "anotacoes": "Comprava com frequência até o fim de 2025. A obra que puxava o volume pode ter sido concluída. Confirmar se a Juliana ainda responde pelo compras antes de montar uma proposta nova.",
      "pedidos": [
        {
          "codigo": "NM-8022",
          "data": "2025-12-09",
          "item": "Caixa de hidrômetro metálica, 1 medidor",
          "quantidade": 70,
          "valor": 32200
        },
        {
          "codigo": "NM-7740",
          "data": "2025-09-02",
          "item": "Caixa de hidrômetro para 2 medidores",
          "quantidade": 20,
          "valor": 15000
        }
      ],
      "orcamentos": []
    }
  ],
  "produtos": [
    { "id": "prd-hidrometro-1", "codigo": "AI 00118", "descricao": "Caixa de hidrômetro metálica, 1 medidor", "familia": "Saneamento", "grupo": "Saneamento", "unidade": "UN", "vendavel": true },
    { "id": "prd-hidrometro-2", "codigo": "AI 00119", "descricao": "Caixa de hidrômetro para 2 medidores", "familia": "Saneamento", "grupo": "Saneamento", "unidade": "UN", "vendavel": true },
    { "id": "prd-inspecao", "codigo": "AI 00120", "descricao": "Caixa de inspeção para cavalete", "familia": "Saneamento", "grupo": "Saneamento", "unidade": "UN", "vendavel": true },
    { "id": "prd-glp", "codigo": "AI 00210", "descricao": "Abrigo de gás GLP de sobrepor", "familia": "Gás", "grupo": "Gás", "unidade": "UN", "vendavel": true },
    { "id": "prd-medidor-gas", "codigo": "AI 00211", "descricao": "Abrigo para medidor de gás", "familia": "Gás", "grupo": "Gás", "unidade": "UN", "vendavel": true },
    { "id": "prd-ventilacao", "codigo": "AI 00212", "descricao": "Kit de ventilação para abrigo de gás", "familia": "Gás", "grupo": "Gás", "unidade": "UN", "vendavel": true },
    { "id": "prd-medicao", "codigo": "AI 00330", "descricao": "Abrigo de medição elétrica", "familia": "Elétrica", "grupo": "Elétrica", "unidade": "UN", "vendavel": true },
    { "id": "prd-passagem", "codigo": "AI 00331", "descricao": "Caixa de passagem elétrica", "familia": "Elétrica", "grupo": "Elétrica", "unidade": "UN", "vendavel": true },
    { "id": "prd-shaft", "codigo": "AI 00440", "descricao": "Porta de fechamento de shaft", "familia": "Fechamento", "grupo": "Fechamento", "unidade": "UN", "vendavel": true }
  ]
};

  const condicoesDemo = ["28 dias", "21/28/35 dias", "30/60 dias", "À vista"];
  root.CRMER_MOCK.clients.forEach((client, index) => {
    (client.pedidos || []).forEach((order, orderIndex) => {
      if (!order.condicaoPagamento) order.condicaoPagamento = condicoesDemo[(index + orderIndex) % condicoesDemo.length];
      if (order.valorUnitario == null && order.quantidade) {
        order.valorUnitario = Math.round((order.valor / order.quantidade) * 100) / 100;
      }
    });
  });
})(window);
