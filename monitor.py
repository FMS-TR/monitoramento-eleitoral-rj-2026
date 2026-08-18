import os
import json
import hashlib
import requests
import time
from pathlib import Path

TSE_BASE = "https://divulgacandcontas.tse.jus.br/divulga/rest/v1"

ANO = 2026
ELEICAO = 20322002026
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


def obter_candidatos(cargo):
    """
    Consulta diretamente a candidatura do RJ.
    Para eleições gerais, não usamos a antiga
    consulta de municípios.
    """

    # Código da unidade eleitoral do RJ usado pelo TSE
    municipios = [3304557]

    todos = []

    for municipio in municipios:

        url = (
            f"{TSE_BASE}/candidatura/listar/"
            f"{ANO}/{municipio}/{ELEICAO}/{cargo}/candidatos"
        )

        try:
            r = requests.get(url, timeout=30)

            print(f"Consulta cargo {cargo}: HTTP {r.status_code}")

            if r.status_code == 200:
                dados = r.json()

                if isinstance(dados, dict):
                    candidatos = dados.get("candidatos", [])

                elif isinstance(dados, list):
                    candidatos = dados

                else:
                    candidatos = []

                todos.extend(candidatos)

            else:
                print(f"Resposta TSE: {r.text[:300]}")

        except Exception as e:
            print(f"Erro na consulta: {e}")

        time.sleep(1)

    return todos


def carregar_estado():
    if ESTADO.exists():
        try:
            return json.loads(
                ESTADO.read_text(encoding="utf-8")
            )
        except Exception:
            pass

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


def identificador(candidato):
    texto = json.dumps(
        candidato,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )

    return hashlib.sha256(
        texto.encode("utf-8")
    ).hexdigest()


def nome_candidato(candidato):
    return (
        candidato.get("nm_CANDIDATO")
        or candidato.get("nomeCompleto")
        or candidato.get("nomeCandidato")
        or candidato.get("nm_candidato")
        or candidato.get("nome")
        or "Nome não informado"
    )


def numero_candidato(candidato):
    return (
        candidato.get("nr_CANDIDATO")
        or candidato.get("numero")
        or ""
    )


def partido_candidato(candidato):
    partido = candidato.get("partido")

    if isinstance(partido, dict):
        return (
            partido.get("sigla")
            or partido.get("nome")
            or ""
        )

    return (
        candidato.get("sg_PARTIDO")
        or candidato.get("siglaPartido")
        or ""
    )


def situacao_candidato(candidato):
    return (
        candidato.get("ds_SITUACAO_CANDIDATURA")
        or candidato.get("descricaoSituacao")
        or candidato.get("descricaoSituacaoCandidato")
        or candidato.get("situacaoCandidato")
        or candidato.get("stRegistro")
        or "Não informada"
    )


def analisar_mudancas(
    candidatos,
    estado_anterior,
    cargo_nome
):
    novas = []
    alteradas = []

    for candidato in candidatos:

        chave_original = (
            candidato.get("sq_CANDIDATO")
            or candidato.get("idCandidato")
            or candidato.get("id")
            or candidato.get("nr_CANDIDATO")
            or candidato.get("numero")
        )

        if chave_original is None:
            chave_original = nome_candidato(candidato)

        chave = f"{cargo_nome}:{chave_original}"

        atual = identificador(candidato)

        if chave not in estado_anterior:
            novas.append(
                (chave, candidato, atual)
            )

        elif estado_anterior[chave] != atual:
            alteradas.append(
                (chave, candidato, atual)
            )

    return novas, alteradas


def main():

    print("===================================")
    print("MONITORAMENTO ELEITORAL RJ 2026")
    print("===================================")
    print(f"Eleição: {ELEICAO}")
    print(f"UF: {UF}")

    estado_anterior = carregar_estado()

    estado_novo = dict(estado_anterior)

    total_novos = 0
    total_alterados = 0
    total_candidatos = 0

    for cargo, cargo_nome in CARGOS.items():

        print("")
        print(f"Consultando {cargo_nome}...")

        candidatos = obter_candidatos(cargo)

        print(
            f"Candidatos encontrados: "
            f"{len(candidatos)}"
        )

        total_candidatos += len(candidatos)

        novas, alteradas = analisar_mudancas(
            candidatos,
            estado_anterior,
            cargo_nome,
        )

        for chave, candidato, assinatura in novas:

            mensagem = (
                "🗳️ NOVA CANDIDATURA — RJ 2026\n\n"
                f"Cargo: {cargo_nome}\n"
                f"Candidato: {nome_candidato(candidato)}\n"
                f"Número: {numero_candidato(candidato)}\n"
                f"Partido: {partido_candidato(candidato)}\n"
                f"Situação: {situacao_candidato(candidato)}"
            )

            try:
                telegram(mensagem)
                print("Telegram enviado.")
            except Exception as e:
                print(
                    f"Erro ao enviar Telegram: {e}"
                )

            estado_novo[chave] = assinatura
            total_novos += 1

        for chave, candidato, assinatura in alteradas:

            mensagem = (
                "⚠️ ALTERAÇÃO EM CANDIDATURA — RJ 2026\n\n"
                f"Cargo: {cargo_nome}\n"
                f"Candidato: {nome_candidato(candidato)}\n"
                f"Número: {numero_candidato(candidato)}\n"
                f"Partido: {partido_candidato(candidato)}\n"
                f"Situação: {situacao_candidato(candidato)}"
            )

            try:
                telegram(mensagem)
                print("Telegram enviado.")
            except Exception as e:
                print(
                    f"Erro ao enviar Telegram: {e}"
                )

            estado_novo[chave] = assinatura
            total_alterados += 1

    salvar_estado(estado_novo)

    print("")
    print("===================================")
    print("MONITORAMENTO CONCLUÍDO")
    print(f"Total de candidatos: {total_candidatos}")
    print(f"Novas candidaturas: {total_novos}")
    print(f"Alterações: {total_alterados}")
    print("===================================")


if __name__ == "__main__":
    main()
