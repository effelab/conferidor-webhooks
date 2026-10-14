"""Resumo do relatorio em portugues simples, escrito por um modelo de linguagem.

O modelo so redige. O veredito de cada cenario ja foi decidido pelo juiz,
antes. Se a chave nao estiver no .env, ou o provedor falhar, o resumo sai de
um texto fixo e o relatorio continua igual.

Configuracao no .env (opcional):
    OPENROUTER_API_KEY=...
    MODELO_RESUMO=google/gemini-2.5-flash-lite     (padrao)

So vai para o provedor a tabela de vereditos: nome do cenario, resultado,
motivos e tempos. Nenhuma credencial, nenhum documento, nenhum dado de cliente.
"""
import json
import urllib.error
import urllib.request

from conferidor import config

URL = "https://openrouter.ai/api/v1/chat/completions"
MODELO_PADRAO = "google/gemini-2.5-flash-lite"

INSTRUCAO = (
    "Você escreve o resumo de um relatório técnico de testes, em português do Brasil, para uma pessoa leiga. "
    "Use só os dados recebidos. Não invente números, causas nem recomendações que os dados não sustentem. "
    "A contagem de resultados já foi escrita por outra parte do sistema: NÃO escreva nenhum número nem quantidade. "
    "Você recebe grupos já separados por operação e meio de pagamento. Escreva exatamente uma frase curta por grupo, "
    "começando pelo nome do grupo como ele está, explicando o motivo em linguagem simples. "
    "Nunca atribua o motivo de um grupo a outro grupo. "
    "Inconclusivo quer dizer que a plataforma ainda não processou o fato; não é falha do app. "
    "Se nenhum cenário tiver motivo, diga apenas que todos os avisos esperados chegaram. "
    "Não use travessão. Não use markdown."
)


def contagem(linhas):
    """A frase com os numeros. Sempre escrita por codigo, nunca pelo modelo."""
    total = len(linhas)
    c = {r: sum(1 for x in linhas if x["resultado"] == r) for r in ("passou", "falhou", "inconclusivo", "não executado")}
    return (f"{c['passou']} de {total} cenários passaram, {c['falhou']} falharam,"
            f" {c['inconclusivo']} ficaram inconclusivos e {c['não executado']} não foram executados.")


def agrupar(linhas):
    """Junta cenarios de mesma operacao, meio e motivo (CPF e CNPJ viram um grupo so). Feito por codigo."""
    grupos = {}
    for x in linhas:
        operacao_e_meio = " · ".join(x["nome"].split(" · ")[:2])
        chave = (operacao_e_meio, x["resultado"], tuple(m.replace(x["nome"], "") for m in x["motivos"]))
        grupos.setdefault(chave, 0)
        grupos[chave] += 1
    return [{"grupo": g, "resultado": r, "motivos": list(m)} for (g, r, m) in grupos if m]         or [{"grupo": "todos os cenários", "resultado": "passou", "motivos": []}]


def texto_fixo(linhas):
    frase = contagem(linhas)
    motivos = [m for x in linhas for m in x["motivos"]]
    if motivos:
        frase += f" Primeiro motivo registrado: {motivos[0]}."
    return frase


def escrever(linhas, abrir=urllib.request.urlopen):
    """Devolve (texto, origem, custo_usd). origem: o nome do modelo, ou 'texto fixo'."""
    dados = config.ler()
    chave, modelo = dados.get("OPENROUTER_API_KEY"), dados.get("MODELO_RESUMO") or MODELO_PADRAO
    if not chave:
        return texto_fixo(linhas), "texto fixo (sem OPENROUTER_API_KEY no .env)", 0.0
    tabela = agrupar(linhas)
    corpo = {"model": modelo, "max_tokens": 400, "temperature": 0.2, "usage": {"include": True},
             "messages": [{"role": "system", "content": INSTRUCAO},
                          {"role": "user", "content": json.dumps(tabela, ensure_ascii=False)}]}
    requisicao = urllib.request.Request(URL, json.dumps(corpo).encode(), {
        "Authorization": f"Bearer {chave}", "Content-Type": "application/json",
        "X-Title": "conferidor-webhooks"})
    try:
        with abrir(requisicao, timeout=30) as r:
            resposta = json.load(r)
        texto = resposta["choices"][0]["message"]["content"].strip().replace("—", ",").replace("–", ",")
        texto = f"{contagem(linhas)} {texto}"
        custo = float((resposta.get("usage") or {}).get("cost") or 0.0)
        return texto, modelo, custo
    except (urllib.error.URLError, KeyError, IndexError, ValueError, TimeoutError) as erro:
        return texto_fixo(linhas), f"texto fixo (o provedor falhou: {type(erro).__name__})", 0.0
