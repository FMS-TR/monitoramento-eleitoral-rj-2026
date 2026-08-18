import os
import csv
import io
import json
import zipfile
import hashlib
import requests
from pathlib import Path

ANO = 2026
UF = "RJ"

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

ESTADO = Path("estado.json")

URL_CANDIDATOS = (
    "https://cdn.tse.jus.br/estatistica/sead/odsele/"
    "consulta_cand/2026/consulta_cand_2026.zip"
)

CARGOS = {
    "GOVERNADOR": "Governador",
    "SENADOR": "Senador",
    "DEPUTADO FEDERAL": "Deputado Federal",
    "DEPUTADO ESTADUAL": "Deputado Estadual",
}


def telegram(texto):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    resposta = requests.post(
        url,
        json={
            "chat_id": CHAT_ID,
            "text": texto,
        },
        timeout=30,
    )

    resposta.raise_for_status()


def baixar_candidatos():
    print("Baixando dados oficiais do TSE...")

    resposta = requests.get(
        URL_CANDIDATOS,
        timeout=120,
    )

    resposta.raise_for_status()

    print(
        f"Arquivo recebido: "
        f"{len(resposta.content) / 1024 / 1024:.1f} MB"
    )

    arquivo_zip = zipfile.ZipFile(
        io.BytesIO(resposta.content)
    )

    arquivos = arquivo_zip.namelist()

    arquivo_rj = None

    for nome in arquivos:
        nome_maiusculo = nome.upper()

        if (
            "CONSULTA_CAND_2026_RJ" in nome_maiusculo
            and nome_maiusculo.endswith(".CSV")
        ):
            arquivo_rj = nome
            break

    if arquivo_rj is None:
        raise RuntimeError(
            "Arquivo de candidatos do RJ não encontrado no ZIP."
        )

    print(f"Lendo: {arquivo_rj}")

    dados = arquivo_zip.read(arquivo_rj)

    return dados


def ler_candidatos(dados):
    candidatos = []

    texto = dados.decode(
        "latin-1",
        errors="replace"
    )

    leitor = csv.DictReader(
        io.StringIO(texto),
        delimiter=";"
    )

    for linha in leitor:

        if linha.get("SG_UF", "").strip().upper() != UF:
            continue

        cargo = (
            linha.get("DS_CARGO", "")
            .strip()
            .upper()
        )

        if cargo not in CARGOS:
            continue

        candidatos.append(linha)

    return candidatos


def carregar_estado():
    if not ESTADO.exists():
        return {}

    try:
        return json.loads(
            ESTADO.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return {}


def salvar_estado(estado):
    ESTADO.write_text(
        json.dumps(
            estado,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8",
    )


def assinatura(candidato):
    texto = json.dumps(
        candidato,
        ensure_ascii=False,
        sort_keys=True,
    )

    return hashlib.sha256(
        texto.encode("utf-8")
    ).hexdigest()


def monitorar():

    print("")
    print("==============================")
    print("MONITORAMENTO ELEITORAL RJ 2026")
    print("==============================")
    print("Fonte: TSE - Candidatos 2026")
    print("UF: RJ")
    print("")

    dados = baixar_candidatos()

    candidatos = ler_candidatos(dados)

    print(
        f"Total de candidatos encontrados: "
        f"{len(candidatos)}"
    )

    estado_anterior = carregar_estado()
    estado_novo = {}

    novas = []
    alteracoes = []

    for candidato in candidatos:

        id_candidato = (
            candidato.get("SQ_CANDIDATO")
            or candidato.get("NR_CANDIDATO")
            or candidato.get("NM_CANDIDATO")
        )

        chave = (
            f"{candidato.get('DS_CARGO','')}|"
            f"{id_candidato}"
        )

        atual = assinatura(candidato)

        estado_novo[chave] = atual

        if chave not in estado_anterior:

            novas.append(candidato)

        elif estado_anterior[chave] != atual:

            alteracoes.append(candidato)

    print(
        f"Novas candidaturas: {len(novas)}"
    )

    print(
        f"Alterações: {len(alteracoes)}"
    )

    for candidato in novas:

        cargo = candidato.get(
            "DS_CARGO",
            ""
        )

        nome = candidato.get(
            "NM_CANDIDATO",
            ""
        )

        urna = candidato.get(
            "NM_URNA_CANDIDATO",
            ""
        )

        numero = candidato.get(
            "NR_CANDIDATO",
            ""
        )

        partido = candidato.get(
            "SG_PARTIDO",
            ""
        )

        situacao = candidato.get(
            "DS_SITUACAO_CANDIDATURA",
            ""
        )

        mensagem = (
            "🗳️ NOVA CANDIDATURA — RJ 2026\n\n"
            f"Cargo: {cargo}\n"
            f"Candidato: {nome}\n"
            f"Nome de urna: {urna}\n"
            f"Número: {numero}\n"
            f"Partido: {partido}\n"
            f"Situação: {situacao}"
        )

        print(
            f"Enviando nova candidatura: {nome}"
        )

        telegram(mensagem)

    for candidato in alteracoes:

        cargo = candidato.get(
            "DS_CARGO",
            ""
        )

        nome = candidato.get(
            "NM_CANDIDATO",
            ""
        )

        urna = candidato.get(
            "NM_URNA_CANDIDATO",
            ""
        )

        numero = candidato.get(
            "NR_CANDIDATO",
            ""
        )

        partido = candidato.get(
            "SG_PARTIDO",
            ""
        )

        situacao = candidato.get(
            "DS_SITUACAO_CANDIDATURA",
            ""
        )

        mensagem = (
            "⚠️ ALTERAÇÃO EM CANDIDATURA — RJ 2026\n\n"
            f"Cargo: {cargo}\n"
            f"Candidato: {nome}\n"
            f"Nome de urna: {urna}\n"
            f"Número: {numero}\n"
            f"Partido: {partido}\n"
            f"Situação: {situacao}"
        )

        print(
            f"Enviando alteração: {nome}"
        )

        telegram(mensagem)

    salvar_estado(estado_novo)

    print("")
    print("==============================")
    print("MONITORAMENTO CONCLUÍDO")
    print("==============================")


if __name__ == "__main__":
    monitorar()
