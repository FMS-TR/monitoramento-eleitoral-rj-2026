import os
import csv
import io
import json
import hashlib
import zipfile
import requests
from pathlib import Path

UF = "RJ"

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

TSE_ZIP_URL = (
    "https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/"
    "consulta_cand_2026.zip"
)

CARGOS = {
    "GOVERNADOR": "Governador",
    "SENADOR": "Senador",
    "DEPUTADO FEDERAL": "Deputado Federal",
    "DEPUTADO ESTADUAL": "Deputado Estadual",
}

ESTADO = Path("estado.json")


def telegram(mensagem):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    resposta = requests.post(
        url,
        json={
            "chat_id": CHAT_ID,
            "text": mensagem,
        },
        timeout=30,
    )

    resposta.raise_for_status()


def baixar_rj():
    print("Baixando dados oficiais do TSE...")

    resposta = requests.get(TSE_ZIP_URL, timeout=120)
    resposta.raise_for_status()

    print(f"Download concluído: {len(resposta.content)} bytes")

    with zipfile.ZipFile(io.BytesIO(resposta.content)) as z:
        nome_rj = None

        for arquivo in z.namelist():
            nome = arquivo.replace("\\", "/").split("/")[-1]

            if nome.lower() == "consulta_cand_2026_rj.csv":
                nome_rj = arquivo
                break

        if not nome_rj:
            raise RuntimeError(
                "consulta_cand_2026_RJ.csv não foi encontrado."
            )

        print(f"Arquivo RJ encontrado: {nome_rj}")

        return z.read(nome_rj)


def ler_candidatos():
    conteudo = baixar_rj()

    texto = None

    for encoding in ("latin1", "cp1252", "utf-8"):
        try:
            texto = conteudo.decode(encoding)
            print(f"Arquivo decodificado como: {encoding}")
            break
        except UnicodeDecodeError:
            pass

    if texto is None:
        raise RuntimeError("Não foi possível decodificar o CSV.")

    primeira_linha = texto.splitlines()[0]

    if ";" in primeira_linha:
        delimitador = ";"
    elif "," in primeira_linha:
        delimitador = ","
    else:
        raise RuntimeError("Delimitador não identificado.")

    leitor = csv.DictReader(
        io.StringIO(texto),
        delimiter=delimitador,
    )

    if not leitor.fieldnames:
        raise RuntimeError("CSV sem cabeçalho.")

    candidatos = []

    for linha in leitor:

        uf = (linha.get("SG_UF") or "").strip().upper()

        if uf != UF:
            continue

        cargo = (
            linha.get("DS_CARGO")
            or linha.get("NM_CARGO")
            or ""
        ).strip().upper()

        if cargo not in CARGOS:
            continue

        candidatos.append(linha)

    return candidatos


def identidade(candidato):
    return (
        candidato.get("SQ_CANDIDATO")
        or candidato.get("NR_CANDIDATO")
        or candidato.get("NM_CANDIDATO")
        or ""
    ).strip()


def nome(candidato):
    return (
        candidato.get("NM_CANDIDATO")
        or candidato.get("NM_URNA_CANDIDATO")
        or "Nome não informado"
    ).strip()


def cargo(candidato):
    valor = (
        candidato.get("DS_CARGO")
        or candidato.get("NM_CARGO")
        or ""
    ).strip().upper()

    return CARGOS.get(valor, valor)


def resumo(candidato):
    return {
        "nome": nome(candidato),
        "cargo": cargo(candidato),
        "numero": (
            candidato.get("NR_CANDIDATO") or ""
        ).strip(),
        "partido": (
            candidato.get("SG_PARTIDO") or ""
        ).strip(),
        "situacao": (
            candidato.get("DS_SITUACAO_CANDIDATURA") or ""
        ).strip(),
        "coligacao": (
            candidato.get("NM_COLIGACAO") or ""
        ).strip(),
        "municipio": (
            candidato.get("NM_UE") or ""
        ).strip(),
    }


def carregar_estado():
    if not ESTADO.exists():
        return {}

    try:
        with ESTADO.open("r", encoding="utf-8") as arquivo:
            return json.load(arquivo)
    except Exception:
        return {}


def salvar_estado(estado):
    temporario = Path("estado.tmp")

    with temporario.open("w", encoding="utf-8") as arquivo:
        json.dump(
            estado,
            arquivo,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )

    temporario.replace(ESTADO)


def gerar_estado(candidatos):
    estado = {}

    for candidato in candidatos:
        chave = identidade(candidato)

        if not chave:
            continue

        dados = resumo(candidato)

        estado[chave] = dados

    return estado


def detectar_alteracoes(antigo, novo):

    adicionados = []
    removidos = []
    alterados = []

    for chave, dados in novo.items():

        if chave not in antigo:
            adicionados.append(dados)

        elif antigo[chave] != dados:

            alterados.append(
                {
                    "antes": antigo[chave],
                    "depois": dados,
                }
            )

    for chave, dados in antigo.items():

        if chave not in novo:
            removidos.append(dados)

    return adicionados, removidos, alterados


def mensagem_alteracoes(adicionados, removidos, alterados):

    partes = []

    if adicionados:

        texto = "🟢 NOVAS CANDIDATURAS\n\n"

        for candidato in adicionados[:30]:

            texto += (
                f"• {candidato['nome']}\n"
                f"Cargo: {candidato['cargo']}\n"
                f"Partido: {candidato['partido']}\n"
                f"Situação: {candidato['situacao']}\n\n"
            )

        partes.append(texto)

    if removidos:

        texto = "🔴 CANDIDATURAS REMOVIDAS\n\n"

        for candidato in removidos[:30]:

            texto += (
                f"• {candidato['nome']}\n"
                f"Cargo: {candidato['cargo']}\n"
                f"Partido: {candidato['partido']}\n\n"
            )

        partes.append(texto)

    if alterados:

        texto = "🟡 ALTERAÇÕES EM CANDIDATURAS\n\n"

        for item in alterados[:30]:

            antes = item["antes"]
            depois = item["depois"]

            texto += (
                f"• {depois['nome']}\n"
                f"Cargo: {depois['cargo']}\n"
            )

            if antes["situacao"] != depois["situacao"]:
                texto += (
                    f"Situação: {antes['situacao']} "
                    f"→ {depois['situacao']}\n"
                )

            if antes["partido"] != depois["partido"]:
                texto += (
                    f"Partido: {antes['partido']} "
                    f"→ {depois['partido']}\n"
                )

            if antes["numero"] != depois["numero"]:
                texto += (
                    f"Número: {antes['numero']} "
                    f"→ {depois['numero']}\n"
                )

            if antes["coligacao"] != depois["coligacao"]:
                texto += (
                    f"Coligação: {antes['coligacao']} "
                    f"→ {depois['coligacao']}\n"
                )

            texto += "\n"

        partes.append(texto)

    return "\n".join(partes)


def main():

    print("=" * 60)
    print("MONITORAMENTO ELEITORAL RJ 2026")
    print("=" * 60)

    candidatos = ler_candidatos()

    print(f"Candidatos monitorados: {len(candidatos)}")

    novo_estado = gerar_estado(candidatos)

    antigo_estado = carregar_estado()

    # Primeira execução:
    # cria a base sem disparar falso alerta.
    if not antigo_estado:

        salvar_estado(novo_estado)

        mensagem = (
            "🟢 MONITORAMENTO ELEITORAL RJ 2026\n\n"
            "Monitoramento iniciado com sucesso.\n\n"
            f"Candidatos monitorados: {len(novo_estado)}\n\n"
            "Esta primeira execução criou a base de comparação.\n"
            "A partir da próxima execução, alterações serão "
            "enviadas automaticamente.\n\n"
            "Fonte: TSE — Candidatos 2026."
        )

        telegram(mensagem)

        print("Primeira execução concluída.")
        print("Base inicial criada.")

        return

    adicionados, removidos, alterados = detectar_alteracoes(
        antigo_estado,
        novo_estado,
    )

    salvar_estado(novo_estado)

    total_alteracoes = (
        len(adicionados)
        + len(removidos)
        + len(alterados)
    )

    print(f"Novos: {len(adicionados)}")
    print(f"Removidos: {len(removidos)}")
    print(f"Alterados: {len(alterados)}")

    if total_alteracoes == 0:

        print("Nenhuma alteração encontrada.")

        return

    mensagem = mensagem_alteracoes(
        adicionados,
        removidos,
        alterados,
    )

    mensagem += (
        "\n\nFonte: TSE — Candidatos 2026."
    )

    telegram(mensagem)

    print("ALERTA ENVIADO PARA O TELEGRAM.")


if __name__ == "__main__":
    main()
