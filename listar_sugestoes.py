from pathlib import Path
import json
import sys
from datetime import datetime

# Se existir a pasta CRMER-PROD ao lado, prioriza ela pois é onde a Natália grava
caminho_prod = Path("../CRMER-PROD/backend/output/sugestoes.json")
caminho_local = Path("backend/output/sugestoes.json")

caminho = caminho_prod if caminho_prod.exists() else caminho_local

def carregar_dados():
    if not caminho.exists():
        print(f"\n[Aviso] Nenhuma sugestão registrada ainda ({caminho} não existe).\n")
        return None
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Erro ao ler {caminho}: {exc}")
        return None

def salvar_dados(dados):
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")

def resolver_sugestao(indices, nota="Resolvido"):
    dados = carregar_dados()
    if not dados:
        return
    indices_int = [int(i) for i in indices if i.isdigit()]
    alterados = 0
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for idx, item in enumerate(dados, start=1):
        if idx in indices_int:
            item["status"] = "resolvida"
            item["resolvida_em"] = agora
            item["resolucao_nota"] = nota
            alterados += 1
            print(f"[OK] Sugestão #{idx} marcada como resolvida!")

    if alterados:
        salvar_dados(dados)
    else:
        print("[Aviso] Nenhum ID correspondente encontrado.")

def listar(filtro="pendentes"):
    dados = carregar_dados()
    if not dados:
        return

    itens_filtrados = []
    for idx, item in enumerate(dados, start=1):
        status = item.get("status", "pendente")
        if filtro == "pendentes" and status != "resolvida":
            itens_filtrados.append((idx, item))
        elif filtro == "resolvidas" and status == "resolvida":
            itens_filtrados.append((idx, item))
        elif filtro == "todas":
            itens_filtrados.append((idx, item))

    titulo_filtro = {
        "pendentes": "PENDENTES (FILA DE TRABALHO)",
        "resolvidas": "HISTÓRICO DE RESOLVIDAS",
        "todas": "TODAS AS SUGESTÕES"
    }.get(filtro, filtro.upper())

    print(f"\nFonte de dados: {caminho.resolve()}")
    print(f"{'='*70}")
    print(f" TOTAL DE SUGESTÕES [{titulo_filtro}]: {len(itens_filtrados)} / {len(dados)}")
    print(f"{'='*70}\n")

    if not itens_filtrados:
        print(f"Nenhuma sugestão encontrada para o filtro: {filtro}.\n")
        return

    for idx, item in itens_filtrados:
        status = item.get("status", "pendente").upper()
        prio = item.get("prioridade", "media").upper()
        autor = item.get("usuario", "Natália")
        modulo = item.get("modulo", "Geral")
        tipo = item.get("tipo", "Melhoria")
        data = item.get("data", "")[:19].replace("T", " ")
        desc = item.get("descricao", "")

        print(f"#{idx} [{status}] [{prio}] - {modulo} ({tipo})")
        print(f"   Autor: {autor} | Data: {data}")
        if status == "RESOLVIDA":
            res_em = item.get("resolvida_em", "-")
            res_nota = item.get("resolucao_nota", "")
            print(f"   Resolvida em: {res_em} | Nota: {res_nota}")
        print(f"   Sugestão: {desc}")
        print(f"{'-'*70}")
    print()

if __name__ == "__main__":
    args = sys.argv[1:]
    if "--todas" in args:
        listar("todas")
    elif "--resolvidas" in args:
        listar("resolvidas")
    elif "--resolver" in args:
        pos = args.index("--resolver")
        ids = args[pos+1:]
        resolver_sugestao(ids)
    else:
        listar("pendentes")
