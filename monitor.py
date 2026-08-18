import os
import json
import hashlib
import requests
from pathlib import Path

TSE_BASE = "https://divulgacandcontas.tse.jus.br/divulga/rest/v1"

ELEICAO = "20322002026"
UF = "RJ"

CARGOS = {
    3: "Governador",
    5: "Senador",
    6: "Deputado Federal",
    7: "Deputado Estadual",
}

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

ESTADO = Path("estado.json")


def telegram(mensagem):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    r = requests.post(
        url,
        json={
            "chat_id": CHAT_ID,
            "text": mensagem,
        },
        timeout=30,
    )

    r.raise_for_status()


def buscar_candidatos(cargo):
    url = f"{TSE_BASE}/candidatura/buscar/{ELEICAO}/{UF}/{cargo}"

    r = requests.get(url, timeout=60)

    if r.status_code != 200:
        print("Erro TSE:", r.status_code, url)
        return []

    try:
        dados = r.json()
    except Exception:
        return []

    if isinstance(dados, list):
        return dados

    if isinstance(dados, dict):
        for chave in ("candidatos", "content", "lista", "dados"):
            if isinstance(dados.get(chave), list):
                return dados[chave]

    return []


def resumo(candidato):
    texto = json.dumps(
        candidato,
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(texto.encode()).hexdigest()


def carregar_estado():
    if not ESTADO.exists():
        return {}

    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except Exception:
        return {}


def salvar_estado(estado):
    ESTADO.write_text(
        json.dumps(
            estado,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def nome_candidato(c):
    return (
        c.get("nomeUrna")
        or c.get("nomeCompleto")
        or c.get("nome")
        or "Candidato"
    )


def main():

    print("INICIANDO MONITORAMENTO TSE...")
    print("Eleição:", ELEICAO)
    print("UF:", UF)

    estado_anterior = carregar_estado()
    estado_novo = {}

    total = 0
    alteracoes = []

    for cargo, nome_cargo in CARGOS.items():

        print(f"Consultando {nome_cargo}...")

        candidatos = buscar_candidatos(cargo)

        print("Encontrados:", len(candidatos))

        for candidato in candidatos:

            chave = (
                str(
                    candidato.get("id")
                    or candidato.get("sequencial")
                    or candidato.get("numero")
                    or resumo(candidato)
                )
            )

            assinatura = resumo(candidato)

            estado_novo[chave] = assinatura
            total += 1

            anterior = estado_anterior.get(chave)

            if anterior is not None and anterior != assinatura:

                alteracoes.append(
                    f"⚠️ ALTERAÇÃO DETECTADA\n"
                    f"Cargo: {nome_cargo}\n"
                    f"Candidato: {nome_candidato(candidato)}"
                )

    salvar_estado(estado_novo)

    print("Total de candidatos:", total)
    print("Alterações:", len(alteracoes))

    if alteracoes:

        mensagem = (
            "🗳️ MONITORAMENTO ELEITORAL RJ 2026\n\n"
            + "\n\n".join(alteracoes)
        )

        telegram(mensagem)

    else:

        print("Nenhuma alteração detectada.")


if __name__ == "__main__":
    main()
