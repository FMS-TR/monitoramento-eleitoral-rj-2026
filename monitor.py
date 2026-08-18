import os
import csv
import io
import json
import hashlib
import requests
import zipfile

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
        raise RuntimeError(
            "O catálogo do TSE não retornou sucesso."
        )

    recursos = dados["result"]["resources"]

    for recurso in recursos:
        nome = str(recurso.get("name", "")).lower()

        if "candidato" in nome:
            url = recurso.get("url")

            if url:
                print("Arquivo oficial encontrado:")
                print(url)
                return url

    raise RuntimeError(
        "Não foi encontrado o arquivo de candidatos 2026."
    )


def baixar_candidatos():
    url = obter_url_candidatos()

    print("Baixando dados oficiais do TSE...")

    resposta = requests.get(
        url,
        timeout=180,
    )

    resposta.raise_for_status()

    conteudo = resposta.content

    print(
        f"Download concluído: {len(conteudo)} bytes"
    )

    return conteudo


def extrair_csv_do_zip(conteudo):
    if not zipfile.is_zipfile(io.BytesIO(conteudo)):
        return conteudo

    print("Arquivo ZIP detectado.")

    with zipfile.ZipFile(
        io.BytesIO(conteudo)
    ) as arquivo_zip:

        nomes = arquivo_zip.namelist()

        print("Arquivos encontrados no ZIP:")

        for nome in nomes:
            print("-", nome)

        csvs = [
            nome
            for nome in nomes
            if nome.lower().endswith(".csv")
        ]

        if not csvs:
            raise RuntimeError(
                "O ZIP do TSE não contém arquivo CSV."
            )

        # Preferir o arquivo principal de candidatos
        principal = None

        for nome in csvs:
            nome_lower = nome.lower()

            if "consulta_cand" in nome_lower:
                principal = nome
                break

            if "candidato" in nome_lower:
                principal = nome
                break

        if principal is None:
            principal = csvs[0]

        print(
            f"Usando arquivo: {principal}"
        )

        return arquivo_zip.read(principal)


def encontrar_coluna(cabecalho, nomes):
    mapa = {}

    for coluna in cabecalho:
        limpa = (
            str(coluna)
            .replace("\ufeff", "")
            .strip()
            .upper()
        )

        mapa[limpa] = coluna

    for nome in nomes:
        nome_upper = nome.upper()

        if nome_upper in mapa:
            return mapa[nome_upper]

    return None


def ler_candidatos(conteudo):
    conteudo = extrair_csv_do_zip(conteudo)

    tentativas = [
        ("latin1", ";"),
        ("utf-8-sig", ";"),
        ("latin1", ","),
        ("utf-8-sig", ","),
    ]

    for encoding, delimitador in tentativas:

        try:
            texto = conteudo.decode(
                encoding
            )

            leitor = csv.DictReader(
                io.StringIO(texto),
                delimiter=delimitador,
            )

            cabecalho = leitor.fieldnames or []

            uf_col = encontrar_coluna(
                cabecalho,
                [
                    "SG_UF",
                    "SG_UF_CANDIDATO",
                    "UF",
                ],
            )

            cargo_col = encontrar_coluna(
                cabecalho,
                [
                    "DS_CARGO",
                    "CARGO",
                ],
            )

            if uf_col and cargo_col:

                print(
                    f"Colunas encontradas: "
                    f"{uf_col} / {cargo_col}"
                )

                candidatos = []

                for linha in leitor:

                    uf = str(
                        linha.get(
                            uf_col,
                            "",
                        )
                    ).strip().upper()

                    cargo = str(
                        linha.get(
                            cargo_col,
                            "",
                        )
                    ).strip()

                    if uf != UF:
                        continue

                    if cargo not in CARGOS:
                        continue

                    candidatos.append(linha)

                return candidatos

        except UnicodeDecodeError:
            continue

    raise RuntimeError(
        "Não foi possível identificar as colunas "
        "SG_UF e DS_CARGO no arquivo do TSE."
    )


def preparar_registro(candidato):

    campos = [
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

    for campo in campos:

        valor = candidato.get(campo)

        if valor is not None:

            registro[campo] = str(
                valor
            ).strip()

    if not registro:

        registro = {
            str(k): str(v)
            for k, v in candidato.items()
        }

    return registro


def gerar_hash(candidatos):

    registros = [
        preparar_registro(candidato)
        for candidato in candidatos
    ]

    registros.sort(
        key=lambda x: (
            x.get(
                "SQ_CANDIDATO",
                "",
            ),
            x.get(
                "NM_CANDIDATO",
                "",
            ),
        )
    )

    texto = json.dumps(
        registros,
        ensure_ascii=False,
        sort_keys=True,
    )

    hash_atual = hashlib.sha256(
        texto.encode("utf-8")
    ).hexdigest()

    return hash_atual, registros


def carregar_estado():

    if not os.path.exists(
        STATE_FILE
    ):
        return None

    with open(
        STATE_FILE,
        "r",
        encoding="utf-8",
    ) as arquivo:

        return json.load(arquivo)


def salvar_estado(
    hash_atual,
    registros,
):

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

        contagem[cargo] = (
            contagem.get(cargo, 0) + 1
        )

    linhas = []

    for cargo in sorted(contagem):

        linhas.append(
            f"{cargo}: "
            f"{contagem[cargo]}"
        )

    return "\n".join(linhas)


def monitorar():

    print("=" * 50)
    print("MONITORAMENTO ELEITORAL RJ 2026")
    print("=" * 50)

    print(f"UF: {UF}")
    print("Fonte: TSE - Candidatos 2026")

    conteudo = baixar_candidatos()

    candidatos = ler_candidatos(
        conteudo
    )

    print(
        "Candidatos RJ encontrados: "
        f"{len(candidatos)}"
    )

    hash_atual, registros = (
        gerar_hash(candidatos)
    )

    estado_anterior = carregar_estado()

    if estado_anterior is None:

        salvar_estado(
            hash_atual,
            registros,
        )

        mensagem = (
            "🟢 MONITORAMENTO ELEITORAL "
            "RJ 2026\n\n"
            "Monitoramento iniciado "
            "com sucesso.\n\n"
            f"Candidatos monitorados: "
            f"{len(registros)}\n\n"
            f"{resumo(registros)}\n\n"
            "Fonte: TSE - Candidatos 2026."
        )

        telegram(mensagem)

        print(
            "Primeira execução concluída."
        )

        return

    if (
        estado_anterior.get("hash")
        == hash_atual
    ):

        print(
            "Nenhuma alteração detectada."
        )

        return

    anterior = estado_anterior.get(
        "candidatos",
        [],
    )

    antigos = {
        x.get(
            "SQ_CANDIDATO",
            "",
        ): x
        for x in anterior
    }

    atuais = {
        x.get(
            "SQ_CANDIDATO",
            "",
        ): x
        for x in registros
    }

    adicionados = [
        atuais[chave]
        for chave in atuais
        if chave not in antigos
    ]

    removidos = [
        antigos[chave]
        for chave in antigos
        if chave not in atuais
    ]

    mensagem = (
        "🚨 ALTERAÇÃO NO MONITORAMENTO "
        "ELEITORAL RJ 2026\n\n"
        f"Candidatos atuais: "
        f"{len(registros)}\n\n"
    )

    if adicionados:

        mensagem += (
            "🟢 NOVOS CANDIDATOS:\n"
        )

        for candidato in adicionados[:30]:

            mensagem += (
                f"- "
                f"{candidato.get('NM_CANDIDATO', 'Nome não informado')} "
                f"("
                f"{candidato.get('DS_CARGO', '')}"
                f")\n"
            )

        mensagem += "\n"

    if removidos:

        mensagem += (
            "🔴 CANDIDATOS REMOVIDOS:\n"
        )

        for candidato in removidos[:30]:

            mensagem += (
                f"- "
                f"{candidato.get('NM_CANDIDATO', 'Nome não informado')} "
                f"("
                f"{candidato.get('DS_CARGO', '')}"
                f")\n"
            )

        mensagem += "\n"

    mensagem += (
        "Fonte: TSE - Candidatos 2026."
    )

    telegram(mensagem)

    salvar_estado(
        hash_atual,
        registros,
    )

    print(
        "Alteração detectada e enviada "
        "pelo Telegram."
    )


if __name__ == "__main__":
    monitorar()
