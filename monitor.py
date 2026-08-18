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


def municipios():
    url = f"{TSE_BASE}/eleicao/buscar/{UF}/{ELEICAO}/municipios"

    r = requests.get(url, timeout=60)
    r.raise_for_status()

    return r.json()


def candidatos(municipio, cargo):
    url = (
        f"{TSE_BASE}/candidatura/listar/"
        f"{ANO}/{municipio}/{ELEICAO}/{cargo}/candidatos"
    )

    r = requests.get(url, timeout=60)

    if r.status_code == 404:
        return []

    r.raise_for_status()

    dados = r.json()

    return dados.get("candidatos", [])


def carregar_estado():
    if ESTADO.exists():
        return json.loads(ESTADO.read_text(encoding="utf-8"))

    return {}


def salvar_estado(dados):
    ESTADO.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2),
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


def nome_candidato(c):
    return (
        c.get("nomeCompleto")
        or c.get("nm_CANDIDATO")
        or c.get("nomeUrna")
        or c.get("nm_URNA")
        or "Nome não informado"
    )


def situacao(c):
    return (
        c.get("descricaoSituacao")
        or c.get("situacaoCandidato")
        or c.get("descricaoSituacaoCandidato")
        or "Não informado"
    )


def partido(c):
    return (
        c.get("siglaPartido")
        or c.get("sg_PARTIDO")
        or "Não informado"
    )


def numero(c):
    return (
        c.get("numero")
        or c.get("nr_CANDIDATO")
        or "Não informado"
    )


def identificador(c):
    return str(
        c.get("id")
        or c.get("sq_CANDIDATO")
        or c.get("idCandidato")
        or ""
    )


def main():

    anterior = carregar_estado()
    atual = {}

    print("Obtendo municípios do RJ...")

    dados_municipios = municipios()

    lista = (
        dados_municipios.get("municipios")
        if isinstance(dados_municipios, dict)
        else dados_municipios
    )

    if not lista:
        raise RuntimeError("Não foi possível obter os municípios do RJ.")

    print(f"Municípios encontrados: {len(lista)}")

    alteracoes = []

    for municipio in lista:

        codigo = (
            municipio.get("codigo")
            or municipio.get("cdMunicipio")
            or municipio.get("codMunicipio")
        )

        if not codigo:
            continue

        for cargo, nome_cargo in CARGOS.items():

            try:
                resposta = candidatos(codigo, cargo)
            except Exception as erro:
                print(
                    f"Erro no município {codigo}, "
                    f"cargo {nome_cargo}: {erro}"
                )
                continue

            for c in resposta:

                cid = identificador(c)

                if not cid:
                    continue

                chave = f"{cargo}-{cid}"

                registro = {
                    "cargo": nome_cargo,
                    "nome": nome_candidato(c),
                    "numero": numero(c),
                    "partido": partido(c),
                    "situacao": situacao(c),
                    "dados": c,
                }

                atual[chave] = registro

                nova_assinatura = assinatura(registro)

                antigo = anterior.get(chave)

                if antigo is None:
                    alteracoes.append(
                        ("nova", registro)
                    )

                elif antigo.get("assinatura") != nova_assinatura:
                    alteracoes.append(
                        ("alteracao", registro)
                    )

                atual[chave]["assinatura"] = nova_assinatura

    salvar_estado(atual)

    print(f"Alterações encontradas: {len(alteracoes)}")

    for tipo, c in alteracoes:

        if tipo == "nova":
            titulo = "🆕 NOVA CANDIDATURA"
        else:
            titulo = "🚨 ALTERAÇÃO DETECTADA"

        mensagem = (
            f"{titulo}\n\n"
            f"Cargo: {c['cargo']}\n"
            f"Candidato: {c['nome']}\n"
            f"Número: {c['numero']}\n"
            f"Partido: {c['partido']}\n"
            f"Situação: {c['situacao']}\n\n"
            f"Fonte: DivulgaCandContas/TSE"
        )

        telegram(mensagem)


if __name__ == "__main__":
    main()
