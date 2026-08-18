import os
import json
import hashlib
import requests
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


def obter_municipios():
    """
    Para Eleições Gerais 2026, a API não está aceitando
    a antiga consulta de municípios usada anteriormente.

    Como os cargos monitorados são estaduais/federais,
    usamos diretamente os códigos de municípios do RJ
    conhecidos pelo TSE.
    """

    url = f"{TSE_BASE}/eleicao/buscar/{UF}/{ELEICAO}/municipios"

    try:
        r = requests.get(url, timeout=30)

        if r.status_code == 200:
            dados = r.json()

            if isinstance(dados, list):
                return dados

            if isinstance(dados, dict):
                for chave in ("municipios", "eleicoes", "unidadesEleitorais"):
                    if chave in dados and isinstance(dados[chave], list):
                        return dados[chave]

        print(f"Consulta de municípios retornou HTTP {r.status_code}")

    except Exception as e:
        print(f"Erro ao consultar municípios: {e}")

    return []


def obter_candidatos(municipio, cargo):
    url = (
        f"{TSE_BASE}/candidatura/listar/"
        f"{ANO}/{municipio}/{ELEICAO}/{cargo}/candidatos"
    )

    try:
        r = requests.get(url, timeout=30)

        if r.status_code == 200:
            dados = r.json()

            if isinstance(dados, dict):
                return dados.get("candidatos", [])

            if isinstance(dados, list):
                return dados

    except Exception as e:
        print(f"Erro no município {municipio}: {e}")

    return []


def carregar_estado():
    if ESTADO.exists():
        try:
            return json.loads(ESTADO.read_text(encoding="utf-8"))
        except Exception:
            pass

    return {}


def salvar_estado(estado):
    ESTADO.write_text(
        json.dumps(estado, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def identificador(candidato):
    texto = json.dumps(
        candidato,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )

    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def nome_candidato(candidato):
    return (
        candidato.get("nm_CANDIDATO")
        or candidato.get("nomeCandidato")
        or candidato.get("nm_candidato")
        or candidato.get("nome")
        or "Nome não informado"
    )


def situacao_candidato(candidato):
    return (
        candidato.get("ds_SITUACAO_CANDIDATURA")
        or candidato.get("descricaoSituacaoCandidato")
        or candidato.get("situacaoCandidato")
        or candidato.get("stRegistro")
        or "Não informada"
    )


def analisar_mudancas(candidatos, estado_anterior, cargo_nome):
    novas = []
    alteradas = []

    for candidato in candidatos:
        chave_original = (
            candidato.get("sq_CANDIDATO")
            or candidato.get("idCandidato")
            or candidato.get("id")
            or candidato.get("nr_CANDIDATO")
        )

        if chave_original is None:
            chave_original = nome_candidato(candidato)

        chave = f"{cargo_nome}:{chave_original}"

        atual = identificador(candidato)

        if chave not in estado_anterior:
            novas.append((chave, candidato, atual))

        elif estado_anterior[chave] != atual:
            alteradas.append((chave, candidato, atual))

    return novas, alteradas


def main():
    print("Iniciando monitoramento eleitoral RJ 2026...")

    estado_anterior = carregar_estado()

    print("Obtendo municípios do RJ...")

    municipios = obter_municipios()

    if not municipios:
        raise RuntimeError(
            "Não foi possível obter os municípios do RJ pela API do TSE."
        )

    print(f"Municípios encontrados: {len(municipios)}")

    estado_novo = dict(estado_anterior)

    total_novos = 0
    total_alterados = 0

    for municipio_data in municipios:

        if isinstance(municipio_data, dict):
            municipio = (
                municipio_data.get("codigo")
                or municipio_data.get("id")
                or municipio_data.get("codMunicipio")
            )

            nome_municipio = (
                municipio_data.get("nome")
                or municipio_data.get("nmUe")
                or municipio_data.get("nomeMunicipio")
                or str(municipio)
            )

        else:
            municipio = municipio_data
            nome_municipio = str(municipio)

        if municipio is None:
            continue

        for cargo, cargo_nome in CARGOS.items():

            candidatos = obter_candidatos(municipio, cargo)

            if not candidatos:
                continue

            novas, alteradas = analisar_mudancas(
                candidatos,
                estado_anterior,
                cargo_nome,
            )

            for chave, candidato, assinatura in novas:

                mensagem = (
                    "🗳️ NOVA CANDIDATURA — RJ 2026\n\n"
                    f"Cargo: {cargo_nome}\n"
                    f"Município: {nome_municipio}\n"
                    f"Candidato: {nome_candidato(candidato)}\n"
                    f"Situação: {situacao_candidato(candidato)}"
                )

                try:
                    telegram(mensagem)
                    print(mensagem)
                except Exception as e:
                    print(f"Erro ao enviar Telegram: {e}")

                estado_novo[chave] = assinatura
                total_novos += 1

            for chave, candidato, assinatura in alteradas:

                mensagem = (
                    "⚠️ ALTERAÇÃO EM CANDIDATURA — RJ 2026\n\n"
                    f"Cargo: {cargo_nome}\n"
                    f"Município: {nome_municipio}\n"
                    f"Candidato: {nome_candidato(candidato)}\n"
                    f"Situação: {situacao_candidato(candidato)}"
                )

                try:
                    telegram(mensagem)
                    print(mensagem)
                except Exception as e:
                    print(f"Erro ao enviar Telegram: {e}")

                estado_novo[chave] = assinatura
                total_alterados += 1

    salvar_estado(estado_novo)

    print(
        f"Monitoramento concluído. "
        f"Novas: {total_novos}. "
        f"Alteradas: {total_alterados}."
    )


if __name__ == "__main__":
    main()
