import os
import csv
import io
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
    print("Baixando arquivo oficial do TSE...")
    print(TSE_ZIP_URL)

    resposta = requests.get(TSE_ZIP_URL, timeout=120)
    resposta.raise_for_status()

    print(f"Download concluído: {len(resposta.content)} bytes")

    with zipfile.ZipFile(io.BytesIO(resposta.content)) as z:
        arquivos = z.namelist()

        print("Arquivos encontrados no ZIP:")
        for arquivo in arquivos:
            print("-", arquivo)

        nome_rj = None

        for arquivo in arquivos:
            nome = arquivo.replace("\\", "/").split("/")[-1]

            if nome.lower() == "consulta_cand_2026_rj.csv":
                nome_rj = arquivo
                break

        if not nome_rj:
            raise RuntimeError(
                "ERRO: consulta_cand_2026_RJ.csv não foi encontrado no ZIP."
            )

        print(f"Arquivo RJ encontrado: {nome_rj}")

        conteudo = z.read(nome_rj)

        return conteudo


def ler_candidatos():
    conteudo = baixar_rj()

    # O TSE normalmente fornece arquivos em Latin-1/Windows-1252.
    texto = None

    for encoding in ("latin1", "cp1252", "utf-8"):
        try:
            texto = conteudo.decode(encoding)
            print(f"Arquivo decodificado como: {encoding}")
            break
        except UnicodeDecodeError:
            continue

    if texto is None:
        raise RuntimeError("Não foi possível decodificar o CSV do TSE.")

    primeira_linha = texto.splitlines()[0]

    if ";" in primeira_linha:
        delimitador = ";"
    elif "," in primeira_linha:
        delimitador = ","
    else:
        raise RuntimeError("Não foi possível identificar o delimitador do CSV.")

    print(f"Delimitador identificado: {repr(delimitador)}")

    leitor = csv.DictReader(
        io.StringIO(texto),
        delimiter=delimitador,
    )

    if not leitor.fieldnames:
        raise RuntimeError("O CSV não possui cabeçalho.")

    print("Colunas encontradas:")
    print(" / ".join(leitor.fieldnames))

    candidatos = []

    for linha in leitor:
        uf = (linha.get("SG_UF") or "").strip().upper()

        if uf and uf != UF:
            continue

        cargo = (
            linha.get("DS_CARGO")
            or linha.get("NM_CARGO")
            or ""
        ).strip().upper()

        if cargo in CARGOS:
            candidatos.append(linha)

    return candidatos


def nome_candidato(candidato):
    return (
        candidato.get("NM_CANDIDATO")
        or candidato.get("nm_CANDIDATO")
        or candidato.get("NM_URNA_CANDIDATO")
        or "Nome não informado"
    ).strip()


def situacao(candidato):
    return (
        candidato.get("DS_SITUACAO_CANDIDATURA")
        or candidato.get("DS_SITUACAO")
        or "Não informada"
    ).strip()


def main():
    print("=" * 60)
    print("MONITORAMENTO ELEITORAL RJ 2026")
    print("=" * 60)

    candidatos = ler_candidatos()

    contagem = {
        "Governador": 0,
        "Senador": 0,
        "Deputado Federal": 0,
        "Deputado Estadual": 0,
    }

    exemplos = {
        "Governador": [],
        "Senador": [],
        "Deputado Federal": [],
        "Deputado Estadual": [],
    }

    for candidato in candidatos:
        cargo_original = (
            candidato.get("DS_CARGO")
            or candidato.get("NM_CARGO")
            or ""
        ).strip().upper()

        cargo_nome = CARGOS.get(cargo_original)

        if not cargo_nome:
            continue

        contagem[cargo_nome] += 1

        if len(exemplos[cargo_nome]) < 3:
            exemplos[cargo_nome].append(
                nome_candidato(candidato)
            )

    total = sum(contagem.values())

    print()
    print("RESULTADO DO TESTE:")
    print("Governador:", contagem["Governador"])
    print("Senador:", contagem["Senador"])
    print("Deputado Federal:", contagem["Deputado Federal"])
    print("Deputado Estadual:", contagem["Deputado Estadual"])
    print("TOTAL:", total)

    mensagem = (
        "🧪 TESTE TSE — RJ 2026\n\n"
        f"Governador: {contagem['Governador']}\n"
        f"Senador: {contagem['Senador']}\n"
        f"Deputado Federal: {contagem['Deputado Federal']}\n"
        f"Deputado Estadual: {contagem['Deputado Estadual']}\n\n"
        f"TOTAL: {total}\n\n"
        "Fonte: TSE — Candidatos 2026."
    )

    if total > 0:
        mensagem += "\n\nExemplos encontrados:\n"

        for cargo in exemplos:
            if exemplos[cargo]:
                mensagem += (
                    f"\n{cargo}:\n"
                    + "\n".join(
                        f"• {nome}" for nome in exemplos[cargo]
                    )
                    + "\n"
                )

    telegram(mensagem)

    print()
    print("Mensagem enviada para o Telegram.")
    print("TESTE CONCLUÍDO.")


if __name__ == "__main__":
    main()
