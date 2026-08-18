import os
import csv
import io
import json
import hashlib
import requests

UF = "RJ"

CARGOS = {
    "Governador",
    "Senador",
    "Deputado Federal",
    "Deputado Estadual",
    "Deputado Distrital",
}

CKAN_API = "https://dadosabertos.tse.jus.br/api/3/action/package_show"
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

STATE_FILE = "estado_monitoramento.json"


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


def obter_url_candidatos():
    print("Consultando catálogo oficial do TSE...")

    resposta = requests.get(
        CKAN_API,
        params={"id": "candidatos-2026"},
        timeout=30,
    )

    resposta.raise_for_status()

    dados = resposta.json()

    if not dados.get("success"):
        raise RuntimeError("O catálogo do TSE não retornou sucesso.")

    recursos = dados["result"]["resources"]

    for recurso in recursos:
        nome = str(recurso.get("name", "")).lower()
        formato = str(recurso.get("format", "")).lower()

        if "candidato" in nome and formato == "csv":
            print("Arquivo oficial encontrado:")
            print(recurso["url"])
            return recurso["url"]

    raise RuntimeError("Não foi encontrado o CSV oficial de candidatos 2026.")


def baixar_candidatos():
    url = obter_url_candidatos()

    print("Baixando dados oficiais do TSE...")

    resposta = requests.get(
        url,
        timeout=120,
    )

    resposta.raise_for_status()

    print("Download concluído.")

    return resposta.content


def encontrar_coluna(cabecalho, nomes):
    mapa = {c.strip().upper(): c for c in cabecalho}

    for nome in nomes:
        if nome.upper() in mapa:
            return mapa[nome.upper()]

    return None


def ler_candidatos(conteudo):
    texto = conteudo.decode("latin1")

    amostra = texto[:10000]

    try:
        dialect = csv.Sniffer().sniff(
            amostra,
            delimiters=";,|\t",
        )
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = ";"

    leitor = csv.DictReader(
        io.StringIO(texto),
        dialect=dialect,
    )

    cabecalho = leitor.fieldnames or []

    uf_col = encontrar_coluna(
        cabecalho,
        ["SG_UF"],
    )

    cargo_col = encontrar_coluna(
        cabecalho,
        ["DS_CARGO"],
    )

    if not uf_col:
        raise RuntimeError(
            "A coluna SG_UF não foi encontrada no arquivo do TSE."
        )

    if not cargo_col:
        raise RuntimeError(
            "A coluna DS_CARGO não foi encontrada no arquivo do TSE."
        )

    candidatos = []

    for linha in leitor:
        uf = str(linha.get(uf_col, "")).strip().upper()
        cargo = str(linha.get(cargo_col, "")).strip()

        if uf != UF:
            continue

        if cargo not in CARGOS:
            continue

        candidatos.append(linha)

    return candidatos


def preparar_registro(candidato):
    campos_importantes = [
        "SQ_CANDIDATO",
        "NR_CANDIDATO",
        "NM_CANDIDATO",
        "NM_URNA_CANDIDATO",
        "DS_CARGO",
        "SG_PARTIDO",
        "NM_PARTIDO",
        "DS_SITUACAO_CANDIDATURA",
        "DS_DETALHE_SITUACAO_CAND",
    ]

    registro = {}

    for campo in campos_importantes:
        valor = candidato.get(campo)

        if valor is not None:
            registro[campo] = str(valor).strip()

    if not registro:
        registro = {
            str(k): str(v)
            for k, v in candidato.items()
        }

    return registro


def gerar_hash(candidatos):
    registros = [
        preparar_registro(c)
        for c in candidatos
    ]

    registros.sort(
        key=lambda x: (
            x.get("SQ_CANDIDATO", ""),
            x.get("NM_CANDIDATO", ""),
        )
    )

    texto = json.dumps(
        registros,
        ensure_ascii=False,
        sort_keys=True,
    )

    return hashlib.sha256(
        texto.encode("utf-8")
    ).hexdigest(), registros


def carregar_estado():
    if not os.path.exists(STATE_FILE):
        return None

    with open(
        STATE_FILE,
        "r",
        encoding="utf-8",
    ) as arquivo:
        return json.load(arquivo)


def salvar_estado(hash_atual, registros):
    estado = {
        "hash": hash_atual,
        "total": len(registros),
        "candidatos": registros,
    }

    with open(
        STATE_FILE,
        "w",
        encoding="utf-8",
    ) as arquivo:
        json.dump(
            estado,
            arquivo,
            ensure_ascii=False,
            indent=2,
        )


def resumo(registros):
    contagem = {}

    for candidato in registros:
        cargo = candidato.get(
            "DS_CARGO",
            "Cargo não informado",
        )

        contagem[cargo] = contagem.get(cargo, 0) + 1

    linhas = []

    for cargo in sorted(contagem):
        linhas.append(
            f"{cargo}: {contagem[cargo]}"
        )

    return "\n".join(linhas)


def monitorar():
    print("=" * 50)
    print("MONITORAMENTO ELEITORAL RJ 2026")
    print("=" * 50)

    print(f"UF: {UF}")
    print("Fonte: TSE - Candidatos 2026")

    conteudo = baixar_candidatos()

    candidatos = ler_candidatos(conteudo)

    print(
        f"Candidatos RJ nos cargos monitorados: {len(candidatos)}"
    )

    hash_atual, registros = gerar_hash(candidatos)

    estado_anterior = carregar_estado()

    if estado_anterior is None:
        salvar_estado(hash_atual, registros)

        mensagem = (
            "🟢 MONITORAMENTO ELEITORAL RJ 2026\n\n"
            "Monitoramento iniciado com sucesso.\n\n"
            f"Candidatos monitorados: {len(registros)}\n\n"
            f"{resumo(registros)}\n\n"
            "Fonte: TSE - Candidatos 2026."
        )

        telegram(mensagem)

        print("Primeira execução concluída.")
        return

    if estado_anterior.get("hash") == hash_atual:
        print("Nenhuma alteração detectada.")
        return

    anterior = estado_anterior.get(
        "candidatos",
        [],
    )

    antigos = {
        x.get("SQ_CANDIDATO", ""): x
        for x in anterior
    }

    atuais = {
        x.get("SQ_CANDIDATO", ""): x
        for x in registros
    }

    adicionados = [
        atuais[k]
        for k in atuais
        if k not in antigos
    ]

    removidos = [
        antigos[k]
        for k in antigos
        if k not in atuais
    ]

    mensagem = (
        "🚨 ALTERAÇÃO NO MONITORAMENTO ELEITORAL RJ 2026\n\n"
        f"Candidatos atuais: {len(registros)}\n\n"
    )

    if adicionados:
        mensagem += "🟢 NOVOS CANDIDATOS:\n"

        for candidato in adicionados[:30]:
            mensagem += (
                f"- {candidato.get('NM_CANDIDATO', 'Nome não informado')} "
                f"({candidato.get('DS_CARGO', '')})\n"
            )

        mensagem += "\n"

    if removidos:
        mensagem += "🔴 CANDIDATOS REMOVIDOS:\n"

        for candidato in removidos[:30]:
            mensagem += (
                f"- {candidato.get('NM_CANDIDATO', 'Nome não informado')} "
                f"({candidato.get('DS_CARGO', '')})\n"
            )

        mensagem += "\n"

    mensagem += "Fonte: TSE - Candidatos 2026."

    telegram(mensagem)

    salvar_estado(hash_atual, registros)

    print("Alteração detectada e enviada pelo Telegram.")


if __name__ == "__main__":
    monitorar()
