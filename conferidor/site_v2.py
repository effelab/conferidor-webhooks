"""Gera a nova versao do site, numa pagina so: site-v2/index.html.

    python -m conferidor.site_v2

Segue o documento de UX de 14/10/2026. Todo numero exibido sai dos arquivos de
resultado (JSON, e o CSV de tentativas dos experimentos) por codigo. O que nao
esta em arquivo (medicao de 13/10 e trechos da documentacao publica) fica em
constantes nomeadas logo abaixo, com a fonte comentada.

Python puro, sem dependencia nova. Nao mexe em site/ nem em nenhum resultado.
"""
import csv
import json
import re
import shutil
import sys
from collections import Counter
from datetime import datetime
from html import escape
from pathlib import Path

from conferidor.relatorio import NOMES_DE_EVENTO, reais
from testador.cenarios import NAO_CONFERIVEIS

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "site-v2"

# Medicao de 13/10/2026. Fonte: texto de painel.html (secao "Resumo" e "Pedido a pedido")
# e HANDOFF-appmax-2026-10-13.md. Nao ha JSON gravado dessa medicao.
M1310_PEDIDOS = (27515, 27516, 27517, 27518)
M1310_DESLIGADOS = (27517, 27518)          # receptor desligado de proposito
M1310_VALOR_CENTAVOS = 12300               # R$ 123,00 por pedido
M1310_CONSULTAS = 4                        # consultas a API na conferencia
M1310_FALHA = datetime(2026, 10, 13, 17, 55)       # avisos falharam (erro 502)
M1310_VOLTA = datetime(2026, 10, 13, 17, 56)       # receptor de volta, em modo de registro
M1310_FIM_ESPERA = datetime(2026, 10, 14, 6, 41)   # ultimo momento observado
M1310_REENTREGAS = 0
M1310_FALTANTES = ("order_pix_created", "order_paid_by_pix", "order_approved")

# Documentacao publica da plataforma (guia "Webhooks"), citada em README e painel.html.
DOC_TENTATIVAS = 4
DOC_ESPERA_S = 5
DOC_JANELA_H = 6.5          # ultima tentativa em ate 6h30
PAINEL_APP_ESPERA_S = 10    # o que o painel do app informa (painel.html, experimentos)

# HANDOFF de 13/10, experimentos: "reavaliar depois das 18h". Estimado, nao medido.
PROXIMA_CONFERENCIA = "depois das 18h de 14/10/2026"

GRUPOS = ["derrubar", "falhar", "demorar:7", "demorar:12", "normal", "pendente"]
ROTULO_GRUPO = {
    "derrubar": "Servidor desligado",
    "falhar": "Servidor ligado, mas respondendo erro",
    "demorar:7": "Servidor responde, mas demora 7 s",
    "demorar:12": "Servidor responde, mas demora 12 s",
    "normal": "Servidor normal",
    "pendente": "Servidor normal, Pix deixado sem pagar",
}
TECNICO_GRUPO = {
    "derrubar": "o receptor fica desligado e o túnel devolve erro 502 (servidor fora do ar).",
    "falhar": "o receptor está ligado e responde erro 500 (erro interno do servidor).",
    "demorar:7": "o receptor responde certo, mas só depois de 7 segundos.",
    "demorar:12": "o receptor responde certo, mas só depois de 12 segundos.",
    "normal": "o receptor responde na hora.",
    "pendente": "Pix criado e nunca pago, para ver se o conferidor confunde não pago com aviso perdido.",
}
COM_FALHA = ("derrubar", "falhar")
STATUS_PAGO = {"aprovado", "integrado"}

MEIOS = [("pix", "Pix"), ("cartao_avista", "Cartão 1x"), ("cartao_parcelado", "Cartão 3x"), ("boleto", "Boleto")]
OPERACOES = [("compra", "Compra"), ("estorno_total", "Estorno total"), ("estorno_parcial", "Estorno parcial")]
DOCS = [("cpf", "CPF"), ("cnpj", "CNPJ")]
EVENTOS_DE_ESTORNO = {"order_refund", "order_partial_refund"}
NOMES = {**NOMES_DE_EVENTO, "order_partial_refund": "estorno parcial"}

GLOSSARIO = [
    ("webhook", "Aviso (webhook)", "Mensagem automática que a plataforma manda para o sistema da loja quando algo muda num pedido, como \"pedido pago\"."),
    ("receptor", "Receptor", "O programa da loja que recebe os avisos num endereço da internet. Se ele estiver desligado, o aviso não entra."),
    ("sandbox", "Sandbox", "Ambiente de teste da plataforma. Dinheiro de mentira, pedidos de mentira. Pode se comportar diferente do ambiente real."),
    ("status", "Status na API", "O que a plataforma responde quando você pergunta sobre um pedido. É a fonte da verdade."),
    ("reentrega", "Reentrega", "Quando o aviso falha, a plataforma deveria tentar de novo. A documentação pública fala em até 4 tentativas, a última em até 6h30."),
    ("janela", "Janela de espera", "Quanto tempo o testador espera os avisos antes de julgar: 10 minutos. Um aviso pode chegar depois disso."),
    ("estorno", "Estorno (total ou parcial)", "Devolver ao comprador o valor inteiro (total) ou só uma parte (parcial)."),
    ("homologacao", "Homologação", "Revisão que a plataforma faz antes de aceitar um app na loja de aplicativos. Este site não faz nem substitui essa revisão."),
]
_DEF = {chave: definicao for chave, _, definicao in GLOSSARIO}

# Selos de resultado: classe, palavra, icone. Nunca so cor.
ICONES = {
    "ok": '<path d="M3.5 8.5l3 3 6-7" />',
    "erro": '<path d="M4 4l8 8M12 4l-8 8" />',
    "atencao": '<path d="M8 3.5v5.5" /><circle cx="8" cy="12" r=".6" />',
    "neutro": '<path d="M3.5 8h9" />',
    "espera": '<circle cx="8" cy="8" r="5.5" /><path d="M8 5v3.2l2 1.3" />',
    "info": '<circle cx="8" cy="8" r="5.5" /><path d="M8 7.5v3.5" /><circle cx="8" cy="5.2" r=".5" />',
}
SELOS = {
    "passou": ("ok", "Passou"),
    "falhou": ("erro", "Falhou"),
    "inconclusivo": ("atencao", "Inconclusivo"),
    "não executado": ("neutro", "Não executado"),
    "esperando": ("espera", "Esperando avisos"),
}
O_QUE_FAZER = {
    "passou": ("Todos os avisos esperados chegaram ao seu app, e a API confirma o mesmo status.",
               "Nada. Siga para o próximo cenário."),
    "falhou": ("A API mostra que o fato aconteceu (por exemplo, o pedido foi pago), mas o aviso não chegou ao seu app em 10 minutos.",
               "Veja se o seu app estava no ar e respondeu rápido. Confira o endereço de avisos cadastrado no painel. "
               "Depois rode <code>python -m testador rejulgar</code>: se o aviso chegou atrasado, o resultado muda."),
    "inconclusivo": ("A plataforma ainda não terminou de processar este pedido (por exemplo, o estorno está em análise). "
                     "Então é normal o aviso ainda não ter chegado. Não é erro do seu app.",
                     "Espere e confira de novo com <code>python -m testador rejulgar</code>. Se continuar assim, "
                     "pergunte à plataforma quanto tempo leva esse processamento."),
    "não executado": ("A plataforma recusou uma etapa do teste (por exemplo, não aceita estorno de boleto pela API). "
                      "O seu app nem chegou a ser testado neste cenário.",
                      "Não é falha do seu app. Leia o motivo. Se o cenário for exigido, descubra com a plataforma como ele é feito "
                      "(no caso do boleto, a própria API pede que o estorno seja feito à mão)."),
}


# ---------------------------------------------------------------- formato

def virgula(x, casas=1):
    return f"{x:.{casas}f}".replace(".", ",")


def segundos(s):
    return f"{s:.0f} s"


def hora(iso):
    """'2026-10-14T11:42:23' vira '11h42 de 14/10/2026'."""
    data, h = iso.split("T")
    a, m, d = data.split("-")
    return f"{h[:2]}h{h[3:5]} de {d}/{m}/{a}"


def decimais_com_virgula(texto):
    return re.sub(r"(\d)\.(\d)", r"\1,\2", texto)


def horas_e_minutos(horas):
    """6.5 vira '6h30'."""
    total = round(horas * 60)
    return f"{total // 60}h{total % 60:02d}"


def termo(chave, texto):
    return f'<a class="termo" href="#g-{chave}" title="{escape(_DEF[chave])}">{texto}</a>'


def icone(tipo):
    return (f'<svg class="ic" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{ICONES[tipo]}</svg>')


def selo(resultado, pequeno=False):
    classe, palavra = SELOS[resultado]
    return f'<span class="selo {classe}{" p" if pequeno else ""}">{icone(classe)}{palavra}</span>'


def selo_livre(classe, palavra):
    return f'<span class="selo {classe}">{icone(classe)}{escape(palavra)}</span>'


def condicao(texto):
    return f'<p class="cond">{icone("info")}<span>{texto}</span></p>'


def numero(valor, frase, cond, n1=False, extra=""):
    return (f'<div class="num{" n1" if n1 else ""}"><div class="v">{valor}</div>'
            f'<div class="f">{frase}</div>{extra}{condicao(cond)}</div>')


def detalhe(rotulo, corpo, classe=""):
    return f'<details class="det {classe}"><summary>{rotulo}</summary><div class="det-c">{corpo}</div></details>'


def comando(texto):
    return f'<div class="cmd"><pre><code>{escape(texto)}</code></pre></div>'


# ---------------------------------------------------------------- dados

def _ler_json(raiz, nome):
    caminho = raiz / nome
    return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else None


def carregar(raiz=RAIZ):
    tentativas = raiz / "experimentos_tentativas.csv"
    return {
        "exp": _ler_json(raiz, "experimentos_resultado.json"),
        "exp_pedidos": _ler_json(raiz, "experimentos.json"),
        "tentativas": list(csv.DictReader(tentativas.read_text(encoding="utf-8").splitlines())) if tentativas.exists() else [],
        "rodadas": [r for r in (_ler_json(raiz, "testador_resultado.json"),
                                _ler_json(raiz, "testador_resultado_boleto_3x.json")) if r],
        "rodada1": _ler_json(raiz, "testador_resultado_rodada1.json"),
        "resistencia": _ler_json(raiz, "testador_resistencia.json"),
    }


def grupos_do_conferidor(exp):
    """Soma por grupo a partir da lista de pedidos do JSON."""
    grupos = {}
    for p in exp["pedidos"]:
        g = grupos.setdefault(p["grupo"], {"pedidos": 0, "pagos": 0, "tentativas": 0, "novas": 0,
                                           "apontados": 0, "recebidos": 0, "ids": []})
        envios = sum(p["envios_por_evento"].values())
        g["pedidos"] += 1
        g["pagos"] += p["status_api"] in STATUS_PAGO
        g["tentativas"] += envios or len(p["recebidos"])
        g["novas"] += p["reenvios"]
        g["apontados"] += bool(p["apontados"])
        g["recebidos"] += len(p["recebidos"])
        g["ids"].append(p["order_id"])
    return {k: grupos[k] for k in GRUPOS if k in grupos} | {k: v for k, v in grupos.items() if k not in GRUPOS}


def avisos_por_pedido_pix(exp):
    """Quantos avisos um pedido Pix normal recebe: o valor mais comum no grupo normal."""
    contagem = Counter(len(p["recebidos"]) for p in exp["pedidos"] if p["grupo"] == "normal")
    return contagem.most_common(1)[0][0] if contagem else 0


def fila(tentativas, exp_pedidos):
    """Intervalos entre avisos e atraso maximo nos grupos com demora, a partir do CSV de tentativas."""
    saida = {}
    for grupo in ("demorar:7", "demorar:12"):
        linhas = [r for r in tentativas if r["comportamento"] == grupo]
        if not linhas:
            continue
        instantes = sorted(datetime.fromisoformat(r["recebido_em"]).timestamp() for r in linhas)
        intervalos = [round(b - a) for a, b in zip(instantes, instantes[1:])]
        comuns = sorted(v for v, _ in Counter(intervalos).most_common(2))
        atraso = 0.0
        if exp_pedidos:
            atraso = max(datetime.fromisoformat(r["recebido_em"]).timestamp()
                         - exp_pedidos["pedidos"][r["order_id"]]["criado_em"] for r in linhas)
        saida[grupo] = {"instantes": [t - instantes[0] for t in instantes], "comuns": comuns,
                        "atraso_max_min": atraso / 60, "avisos": len(linhas)}
    return saida


def linhas_do_testador(rodadas):
    linhas = {}
    for rodada in rodadas:
        for x in rodada["linhas"]:
            linhas[x["id"]] = {**x, "_rodada": rodada}
    return linhas


def conta_testador(rodadas):
    todas = [x for r in rodadas for x in r["linhas"]]
    conta = Counter(x["resultado"] for x in todas)
    return {"total": len(todas), **{r: conta.get(r, 0) for r in ("passou", "falhou", "inconclusivo", "não executado")}}


# ---------------------------------------------------------------- secoes

def barra_superior():
    itens = [("problema", "O problema"), ("conferidor", "Conferidor"), ("testador", "Testador"),
             ("como-usar", "Como usar"), ("limites", "Limites")]
    links = "".join(f'<li><a href="#{a}">{t}</a></li>' for a, t in itens)
    return f"""<p class="aviso-topo">Projeto independente, sem vínculo com a plataforma. Medido no {termo("sandbox", "sandbox")} do próprio app do autor, sem dado de cliente.</p>
<header class="barra">
<div class="w barra-in">
<a class="nome" href="#topo">Conferidor de avisos</a>
<nav aria-label="Seções"><ul>{links}</ul></nav>
<a class="btn" href="#como-usar">Como usar</a>
</div>
</header>"""


def topo(d):
    exp, rodadas = d["exp"], d["rodadas"]
    numeros = []
    if exp:
        det = exp["resumo"]["deteccao"]
        numeros.append(numero(f"{det['derrubados_apontados']} de {det['derrubados']}",
                              "pedidos pagos sem aviso foram achados pelo conferidor", "Experimentos de 14/10"))
        numeros.append(numero(f"{det['normais_apontados_por_engano']} de {det['normais_e_pendentes']}",
                              "pedidos normais ou pendentes apontados por engano", "Experimentos de 14/10"))
    if rodadas:
        c = conta_testador(rodadas)
        numeros.append(numero(f"{c['falhou']} de {c['total']}", "cenários do testador falharam",
                              "Rodadas de 14/10, ver os inconclusivos"))
    cartao = (f'<div class="hero-card"><p class="rot">O que foi medido</p><div class="nums3">{"".join(numeros)}</div>'
              f'<p class="cond-faixa">{icone("info")}<span>Sandbox · um app · uma rodada · 13 e 14/10/2026</span></p></div>'
              if numeros else "")
    return f"""<section class="hero" id="topo">
<div class="w hero-in">
<div class="hero-txt">
<h1>Quando o aviso de pagamento se perde, a loja não sabe que vendeu</h1>
<p class="lead">Duas ferramentas para descobrir isso no seu ambiente de teste. Projeto independente, medido no sandbox do próprio app do autor.</p>
<div class="acoes"><a class="btn btn-branco" href="#como-usar">Como usar</a><a class="btn btn-lilas" href="#problema">Entender o problema</a></div>
</div>
{cartao}
</div>
</section>
<div class="w ferramentas">
<a class="card ferr" href="#conferidor"><span class="tag">Ferramenta 1</span><h2>Conferidor de avisos</h2>
<p>Acha os pedidos pagos de que a loja não ficou sabendo.</p><span class="ir">Ver o resultado</span></a>
<a class="card ferr" href="#testador"><span class="tag">Ferramenta 2</span><h2>Testador de cenários</h2>
<p>Roda a lista pública de cenários de homologação no seu sandbox e diz o que passou.</p><span class="ir">Ver o resultado</span></a>
</div>"""


def problema():
    passos = [("1", "Cliente paga", "O comprador paga o pedido com Pix, cartão ou boleto."),
              ("2", "Plataforma manda o aviso", f"Ela envia um {termo('webhook', 'aviso')} automático: \"pedido pago\"."),
              ("3", "Sistema da loja recebe", f"O {termo('receptor', 'receptor')} da loja registra a venda e libera o pedido.")]
    caixas = '<span class="seta" aria-hidden="true"></span>'.join(
        f'<div class="passo-d"><span class="bola">{n}</span><strong>{t}</strong><span>{x}</span></div>' for n, t, x in passos)
    return f"""<section class="sec" id="problema">
<div class="w">
<p class="olho">O problema</p>
<h2>Como um aviso se perde</h2>
<p class="sub">A plataforma avisa a loja. Se a loja não atende, o aviso pode ser descartado sem ninguém saber.</p>
<div class="card">
<p class="diag-rot">Quando dá certo</p>
<div class="diag">{caixas}</div>
<p class="diag-rot">Quando o servidor da loja está fora do ar</p>
<div class="diag perda">
<div class="passo-d"><span class="bola">1</span><strong>Cliente paga</strong><span>O dinheiro entra.</span></div>
<span class="seta" aria-hidden="true"></span>
<div class="passo-d"><span class="bola">2</span><strong>Plataforma manda o aviso</strong><span>Ninguém responde do outro lado.</span></div>
<span class="seta corte" aria-hidden="true">{icone("erro")}</span>
<div class="passo-d x"><span class="bola">{icone("erro")}</span><strong>Loja não fica sabendo</strong><span>O pedido fica parado, como se não tivesse sido pago.</span></div>
</div>
</div>
<div class="duas">
<div class="card">
<p class="selo-doc">Segundo a documentação pública</p>
<p>Se o servidor da loja não responde, a plataforma tenta de novo até <strong>{DOC_TENTATIVAS} vezes</strong>, esperando até
<strong>{DOC_ESPERA_S} s</strong> por resposta em cada uma, com a última em até {horas_e_minutos(DOC_JANELA_H)}. Depois disso o aviso é
descartado permanentemente, sem notificar ninguém.</p>
<p class="nota">Isto é o que a documentação descreve, não uma medição deste projeto.</p>
{detalhe("Documentação e painel do app dizem tempos diferentes",
         f"<p>A documentação fala em {DOC_ESPERA_S} s de espera por tentativa. O painel do app, na plataforma, fala em {PAINEL_APP_ESPERA_S} s. "
         "Nos experimentos abaixo a plataforma esperou mais do que isso sem cortar (ver \"Um app lento atrasa os avisos seguintes\"); daqui não dá para saber qual é o limite real.</p>")}
</div>
<div class="card">
<p class="selo-doc">A saída</p>
<p>Dá para descobrir o que se perdeu perguntando à API, que é a fonte da verdade. O conferidor compara os avisos que chegaram
com o que a API diz. Se a API diz pago e o aviso não chegou, ele aponta.</p>
<p>Antes de publicar um app, a plataforma testa uma lista pública de cenários. O testador roda essa lista no seu sandbox e diz,
cenário por cenário, o que aconteceu.</p>
</div>
</div>
</div>
</section>"""


def _linha_do_tempo(dados_fila):
    """Um ponto por aviso recebido, na mesma escala de tempo para os dois grupos."""
    if not dados_fila:
        return ""
    span = max(max(v["instantes"]) for v in dados_fila.values()) or 1
    linhas = []
    for grupo, v in dados_fila.items():
        pontos = "".join(f'<i style="left:{t / span * 100:.2f}%"></i>' for t in v["instantes"])
        linhas.append(f'<p class="tl-r">Demora de {grupo.split(":")[1]} s: {v["avisos"]} avisos</p>'
                      f'<div class="tl" aria-hidden="true">{pontos}</div>')
    return (f'<figure class="tl-f" role="img" aria-label="Linha do tempo: cada ponto é um aviso recebido, em fila, um por vez">'
            f'{"".join(linhas)}<figcaption class="tl-e"><span>0 s, primeiro aviso do grupo</span><span>{span:.0f} s</span></figcaption></figure>')


def conferidor(d):
    exp = d["exp"]
    if not exp:
        return estado_vazio("conferidor", "O conferidor achou os pedidos perdidos?",
                            "Ainda não há resultado. Rode <code>python -m conferidor.sandbox conferir</code> para criar a primeira conferência.")
    r = exp["resumo"]
    det = r["deteccao"]
    grupos = grupos_do_conferidor(exp)
    total = sum(g["pedidos"] for g in grupos.values())
    ids = [p["order_id"] for p in exp["pedidos"]]
    cond = f"Sandbox · um app · uma rodada · 14/10/2026 · {total} pedidos com Pix de teste"

    def apontou(chave, g):
        if chave in COM_FALHA:
            classe = "ok" if g["apontados"] == g["pedidos"] else "erro"
            return selo_livre(classe, f"Sim, {g['apontados']} de {g['pedidos']}")
        if chave in ("normal", "pendente"):
            classe = "ok" if g["apontados"] == 0 else "erro"
            return selo_livre(classe, f"Nenhum, {g['apontados']} de {g['pedidos']}") + '<span class="mini">correto: não havia aviso perdido</span>'
        return selo_livre("neutro", f"{g['apontados']} de {g['pedidos']}") + '<span class="mini">os que perderam algum aviso</span>'

    linhas = "".join(
        f"<tr><td data-r=\"Grupo\">{escape(ROTULO_GRUPO.get(k, k))}</td><td class=n data-r=\"Pedidos\">{g['pedidos']}</td>"
        f"<td class=n data-r=\"Pagos na API\">{g['pagos']}</td><td class=n data-r=\"Tentativas de entrega registradas\">{g['tentativas']}</td>"
        f"<td class=n data-r=\"Novas tentativas\">{g['novas']}</td><td data-r=\"O conferidor apontou?\">{apontou(k, g)}</td></tr>"
        for k, g in grupos.items())
    pagos_1310 = len(M1310_DESLIGADOS)
    linha_1310 = (f'<tr class="hist"><td data-r="Grupo">Medição de 13/10: servidor desligado em {pagos_1310} de {len(M1310_PEDIDOS)} pedidos</td>'
                  f'<td class=n data-r="Pedidos">{len(M1310_PEDIDOS)}</td><td class=n data-r="Pagos na API">{len(M1310_PEDIDOS)}</td>'
                  f'<td class=n data-r="Tentativas de entrega registradas">não registrado</td><td class=n data-r="Novas tentativas">{M1310_REENTREGAS}</td>'
                  f'<td data-r="O conferidor apontou?">{selo_livre("ok", f"Sim, {pagos_1310} de {pagos_1310}")}</td></tr>')

    # avisos que nunca chegaram com o receptor ligado (grupos com demora)
    por_pedido = avisos_por_pedido_pix(exp)
    lentos = [g for k, g in grupos.items() if k.startswith("demorar")]
    esperados = por_pedido * sum(g["pedidos"] for g in lentos)
    faltaram = esperados - sum(g["recebidos"] for g in lentos)
    pedidos_afetados = sum(g["apontados"] for g in lentos)

    novas = sum(grupos[k]["novas"] for k in COM_FALHA if k in grupos)
    com_falha = sum(grupos[k]["pedidos"] for k in COM_FALHA if k in grupos)
    minutos = round(r["horas_desde_a_criacao"] * 60)
    aberta = r["horas_desde_a_criacao"] < DOC_JANELA_H
    estado = (f'{selo_livre("atencao", "Em observação")}<p>Conferido {minutos} minutos depois dos pedidos, às {hora(r["avaliado_em"])}. '
              f'A documentação fala em tentativas até 6h30. Antes disso, zero nova tentativa ainda não é conclusão.</p>'
              f'<p class="mini">Próxima conferência: {PROXIMA_CONFERENCIA} (horário estimado, não medido).</p>'
              if aberta else
              f'{selo_livre("neutro", "Janela fechada")}<p>Conferido {minutos} minutos depois dos pedidos, às {hora(r["avaliado_em"])}, '
              f'depois do fim da janela de 6h30 descrita na documentação.</p>')
    espera_1310 = M1310_FIM_ESPERA - M1310_VOLTA
    h, resto = divmod(int(espera_1310.total_seconds()) // 60, 60)

    fl = fila(d["tentativas"], d["exp_pedidos"])
    textos_fila = "; ".join(
        f"com demora de {g.split(':')[1]} s, os avisos chegaram com {v['comuns'][0]} a {v['comuns'][-1]} s de intervalo"
        for g, v in fl.items())
    maior_demora = max((int(k.split(":")[1]) for k in grupos if k.startswith("demorar:")), default=0)
    atraso_max = max((v["atraso_max_min"] for v in fl.values()), default=0)

    nao_chegaram = ", ".join(NOMES[e] for e in M1310_FALTANTES)
    pedidos_1310 = "".join(
        f"<tr><td class=n data-r=\"Pedido\">{p}</td><td class=n data-r=\"Valor\">{reais(M1310_VALOR_CENTAVOS)}</td>"
        f"<td data-r=\"Como a loja soube\">{'Só pelo conferidor' if p in M1310_DESLIGADOS else 'Pelo aviso da plataforma'}</td>"
        f"<td data-r=\"Avisos que não chegaram\">{('Não chegaram: ' + nao_chegaram) if p in M1310_DESLIGADOS else 'nenhum'}</td></tr>"
        for p in M1310_PEDIDOS)
    detalhes_1310 = (
        f"<p>{len(M1310_PEDIDOS)} pedidos com Pix de teste, {reais(M1310_VALOR_CENTAVOS)} cada. Em {len(M1310_DESLIGADOS)} deles o receptor foi "
        f"desligado de propósito. {reais(M1310_VALOR_CENTAVOS * len(M1310_DESLIGADOS))} em pedidos que a loja só conhece pelo conferidor. "
        f"{M1310_CONSULTAS} consultas à API nesta conferência.</p>"
        f'<div class="tw"><table class="resp"><thead><tr><th class=n>Pedido</th><th class=n>Valor</th><th>Como a loja soube</th>'
        f"<th>Avisos que não chegaram</th></tr></thead><tbody>{pedidos_1310}</tbody></table></div>"
        f"<p>Os avisos falharam em {M1310_FALHA:%d/%m/%Y} às {M1310_FALHA.hour}h{M1310_FALHA.minute:02d}, com o erro 502 (o túnel responde assim quando o servidor está desligado). "
        f"Às {M1310_VOLTA.hour}h{M1310_VOLTA.minute:02d} o receptor voltou ao ar e ficou esperando até {M1310_FIM_ESPERA:%d/%m} às {M1310_FIM_ESPERA.hour}h{M1310_FIM_ESPERA.minute:02d}. "
        "A documentação não diz se o erro 502 gera nova tentativa.</p>")
    tecnicos = "".join(f"<li><code>{escape(k)}</code>: {escape(TECNICO_GRUPO[k])}</li>" for k in grupos if k in TECNICO_GRUPO)

    return f"""<section class="sec cinza" id="conferidor">
<div class="w">
<p class="olho">Ferramenta 1 · Conferidor</p>
<h2>O conferidor achou os pedidos perdidos?</h2>
<p class="sub">Desligamos de propósito o recebimento de avisos de alguns pedidos e vimos se ele percebia.</p>
<div class="nums">
{numero(f"{det['derrubados_apontados']} de {det['derrubados']}", "pedidos pagos sem aviso foram achados", cond, n1=True)}
{numero(f"{det['normais_apontados_por_engano']} de {det['normais_e_pendentes']}", "pedidos normais ou pendentes apontados por engano", cond)}
{numero(str(r['consultas_a_api']), "consultas à API", cond, extra='<div class="mini">perguntas feitas à plataforma nesta conferência</div>')}
</div>
<div class="card">
<h3>Como foi o teste</h3>
<p>{total} pedidos de teste ({ids[0]} a {ids[-1]}), divididos em grupos. Em cada grupo o {termo("receptor", "receptor")} se comportou de um jeito:
ligado, desligado, respondendo erro ou demorando para responder. Depois o conferidor perguntou à API o {termo("status", "status")} de cada pedido
e comparou com os avisos que chegaram.</p>
<div class="tw"><table class="resp">
<thead><tr><th>Como o receptor se comportou</th><th class=n>Pedidos</th><th class=n>Pagos na API</th>
<th class=n>Tentativas de entrega registradas</th><th class=n>Novas tentativas</th><th>O conferidor apontou?</th></tr></thead>
<tbody>{linhas}{linha_1310}</tbody></table></div>
<p class="nota">Tentativas de entrega registradas: quantas vezes a plataforma tentou entregar um aviso e isso ficou registrado, mesmo quando o servidor recusou.
Por isso o grupo "servidor desligado" tem tentativas, mas nenhum aviso entrou.</p>
<p class="nota">Os {grupos.get('falhar', {}).get('pedidos', 0)} pedidos do grupo "respondendo erro" também foram apontados e a API mostra todos como pagos.
O número principal fica nos {det['derrubados']} do grupo desligado até o autor confirmar a contagem.</p>
{detalhe("Nomes técnicos dos grupos e códigos de erro", f"<ul>{tecnicos}</ul><p>502: resposta do túnel quando o servidor está desligado. 500: erro interno do servidor da loja.</p>")}
</div>
<div class="card destaque">
<p><strong>{faltaram} de {esperados} avisos nunca chegaram com o receptor ligado o tempo todo.</strong> Causa desconhecida.
O conferidor apontou os {pedidos_afetados} pedidos.</p>
<p class="nota">Nos grupos com demora: {sum(g['pedidos'] for g in lentos)} pedidos, {por_pedido} avisos esperados por pedido Pix (o que cada pedido normal recebeu).</p>
</div>
<div class="duas">
<div class="card" id="reentrega">
<h3>A plataforma tentou entregar de novo?</h3>
<p class="sub2">Ainda em observação. Veja o estado abaixo.</p>
<div class="estado">{estado}</div>
<p><strong>{novas} novas tentativas</strong> em {com_falha} pedidos com falha (servidor desligado ou respondendo erro).</p>
<p class="hist-l">Histórico, 13/10: {len(M1310_DESLIGADOS)} pedidos, erro 502, <strong>nenhuma nova tentativa em {h}h{resto:02d}</strong> com o receptor de volta no ar.
A documentação não diz se o erro 502 gera nova tentativa.</p>
{condicao(f"Sandbox · um app · {len(M1310_DESLIGADOS)} pedidos em 13/10 e " + str(com_falha) + " em 14/10")}
</div>
<div class="card" id="fila">
<h3>Um app lento atrasa os avisos seguintes</h3>
<p class="sub2">Os avisos saíram em fila, um por vez.</p>
<p>{textos_fila.capitalize()}. Os últimos chegaram cerca de {virgula(atraso_max, 1)} min depois de o pedido ser criado.</p>
{_linha_do_tempo(fl)}
<p>A plataforma esperou {maior_demora} s sem cortar. <span class="hip">Não dá para saber daqui</span> se o limite real é maior ou se ela corta e não reenvia.</p>
{condicao("Sandbox · um app · uma rodada · 14/10/2026")}
</div>
</div>
{detalhe("Medição de 13/10, pedido a pedido", detalhes_1310)}
</div>
</section>"""


def _motivo_simples(x):
    meio, _, acao = x["id"].split("-")
    if x["resultado"] == "inconclusivo" and acao == "estorno_total":
        return "O estorno foi aceito e entrou em análise manual. O aviso só vem depois da análise."
    if x["resultado"] == "inconclusivo" and acao == "estorno_parcial":
        return "O estorno foi aceito, mas o status do pedido não muda e nenhum aviso chegou em 10 minutos. Não dá para saber se a plataforma já processou."
    if x["resultado"] == "não executado" and meio == "boleto":
        return "A plataforma não aceita estorno de boleto pela API e pede que seja feito à mão."
    if x["resultado"] == "passou":
        return "Todos os avisos esperados chegaram."
    return "; ".join(x["motivos"]) or "Sem motivo registrado."


def _celula(meio, acao, rotulo_meio, rotulo_acao, linhas):
    casos = [(rot, linhas.get(f"{meio}-{doc}-{acao}")) for doc, rot in DOCS]
    if not any(x for _, x in casos):
        return f'<td data-r="{rotulo_acao}"><span class="mini">sem rodada</span></td>'
    resumo = "".join(f'<span class="doc"><span class="doc-n">{rot}</span>{selo(x["resultado"], True) if x else "n/d"}</span>'
                     for rot, x in casos)
    partes = []
    for rot, x in casos:
        if not x:
            continue
        atrasos = sorted(x["atrasos"].items(), key=lambda kv: kv[1])
        tempos = "".join(
            f"<li>{escape(NOMES.get(e, e))}: {segundos(s)} {'depois do pedido de estorno' if e in EVENTOS_DE_ESTORNO else 'depois do pagamento'}</li>"
            for e, s in atrasos) or "<li>nenhum aviso medido</li>"
        tecnico = ""
        if x["resultado"] == "inconclusivo":
            tecnico = f'<p class="tec">Texto técnico original: {escape("; ".join(x["motivos"]))}</p>'
            if x["_rodada"].get("rejulgado_em"):
                tecnico += f'<p class="mini">Conferido de novo em {escape(x["_rodada"]["rejulgado_em"])}: seguia assim.</p>'
        elif x["resultado"] == "não executado":
            tecnico = '<p class="mini">Resposta literal da plataforma: ver "Resposta da plataforma ao estorno de boleto", abaixo da matriz.</p>'
        partes.append(f'<div class="caso"><p><strong>{rot}</strong> · pedido {x["order_id"] or "n/d"} · {selo(x["resultado"], True)}</p>'
                      f"<p>{escape(_motivo_simples(x))}</p><p class=\"mini\">Segundos até cada aviso:</p><ul>{tempos}</ul>{tecnico}</div>")
    return (f'<td data-r="{rotulo_acao}"><details class="cel"><summary><span class="docs">{resumo}</span>'
            f'<span class="abrir">detalhes</span></summary><div class="cel-c">'
            f'<p class="cel-t">{rotulo_meio} · {rotulo_acao}</p>{"".join(partes)}</div></details></td>')


def _resistencia(dados):
    if not dados:
        return ""
    primeira = dados["provas"][0]["detalhe"]
    m = re.search(r"(\d+) de (\d+) com 2xx; mediana ([\d.]+) s, pior ([\d.]+) s", primeira)
    linha = (f"{m.group(1)} de {m.group(2)} avisos respondidos em até {virgula(float(m.group(4)), 2)} s"
             if m else "ver as provas")
    provas = "".join(
        f"<tr><td data-r=\"Prova\">{escape(p['nome'])}</td>"
        f"<td data-r=\"Resultado\">{selo('passou' if p['passou'] else 'falhou', True)}"
        f"{'<span class=mini>informativo, não é exigência</span>' if p.get('informativo') else ''}</td>"
        f"<td data-r=\"Detalhe\">{escape(decimais_com_virgula(p['detalhe']))}</td></tr>" for p in dados["provas"])
    passaram = sum(1 for p in dados["provas"] if p["passou"])
    corpo = (f"<p>Avisos falsos enviados direto para o app, medindo só a resposta. {passaram} de {len(dados['provas'])} provas passaram.</p>"
             f'<div class="tw"><table class="resp"><thead><tr><th>Prova</th><th>Resultado</th><th>Detalhe</th></tr></thead>'
             f"<tbody>{provas}</tbody></table></div>"
             f"<p class=\"nota\">Executado em {escape(dados['executado_em'])}. Endereço testado: <code>{escape(dados['alvo'])}</code> "
             f"(endereço local, sem a internet no meio; pelo túnel o tempo inclui a rede). Pedidos fictícios {escape(dados['pedidos_sinteticos'])}. "
             "Mede só a resposta e o tempo; o que o app faz por dentro não é visível daqui.</p>")
    return detalhe(f"O seu endereço de avisos aguenta repetição e desordem? <span class=\"res\">{escape(linha)}</span>", corpo)


def _como_e_feito(rodadas, rodada1):
    partes = []
    for r in rodadas:
        origem = r.get("origem_resumo", "")
        if origem.startswith("texto fixo"):
            resumo = "Resumo em texto fixo (sem chave de modelo ou provedor fora do ar). O resultado não muda."
        else:
            resumo = (f"Resumo em texto escrito por modelo de linguagem ({escape(origem)}), custo US$ "
                      f"{virgula(r.get('custo_resumo_usd') or 0.0, 6)}. O modelo não conta nem decide.")
        partes.append(f"<li>Rodada de {escape(r['executado_em'])}: {len(r['linhas'])} cenários, {r['chamadas']} chamadas à API. {resumo}</li>")
    anterior = (f"<p>Uma rodada anterior ({len(rodada1['linhas'])} cenários, com regra antiga) não está nesta tabela.</p>"
                if rodada1 else "")
    corpo = ("<p>Uma regra fixa decide o resultado de cada cenário, antes de qualquer resumo: só é falha quando a API mostra que o fato "
             "aconteceu e o aviso não chegou.</p>"
             f"<ul>{''.join(partes)}</ul>{anterior}"
             "<p>Os segundos de cada aviso são contados a partir do pagamento feito pelo testador; para os avisos de estorno, a partir do pedido de estorno.</p>")
    return detalhe("Como este relatório é feito", corpo)


def testador(d):
    rodadas = d["rodadas"]
    if not rodadas:
        return estado_vazio("testador", "O que aconteceu em cada cenário",
                            "Ainda não há resultado. Rode <code>python -m testador rodar</code> para criar a primeira rodada.")
    erro = [r for r in rodadas if r.get("erro")]
    faixa_erro = "".join(
        f'<div class="faixa-erro" role="alert">{icone("erro")}<div><strong>A rodada não terminou. Isto não é resultado do seu app.</strong>'
        f'<p>{escape(str(r["erro"]))}</p></div></div>' for r in erro)
    c = conta_testador(rodadas)
    linhas = linhas_do_testador(rodadas)
    janela = max(r["espera_s"] for r in rodadas) // 60
    datas = " e ".join(r["executado_em"].split(" ")[1] for r in rodadas)
    cond = f"Sandbox · um app · {len(rodadas)} rodadas em {rodadas[0]['executado_em'].split(' ')[0]} ({datas}) · janela de {janela} min"
    cabeca = "".join(f"<th>{rot}</th>" for _, rot in OPERACOES)
    corpo = "".join(
        f'<tr><th scope="row" data-r="Meio">{rot_m}</th>'
        + "".join(_celula(m, a, rot_m, rot_a, linhas) for a, rot_a in OPERACOES) + "</tr>"
        for m, rot_m in MEIOS if any(k.startswith(m + "-") for k in linhas))
    legenda = "".join(
        f'<div class="leg">{selo(r)}<p>{O_QUE_FAZER[r][0]}</p><p><strong>O que você faz:</strong> {O_QUE_FAZER[r][1]}</p></div>'
        for r in O_QUE_FAZER)
    erros_boleto = sorted({x["execucao"]["erro"] for x in linhas.values() if x["resultado"] == "não executado" and x["execucao"].get("erro")})
    literal = (detalhe("Resposta da plataforma ao estorno de boleto",
                       "".join(f"<pre class=\"lit\"><code>{escape(e)}</code></pre>" for e in erros_boleto)
                       + "<p class=\"nota\">HTTP 400 quer dizer que a plataforma recusou o pedido. A mensagem, em inglês, pede que o estorno de boleto seja feito à mão.</p>")
               if erros_boleto else "")
    cartoes = "".join(
        f'<div class="num"><div class="v">{c[r]}</div><div class="f">{selo(r)}</div></div>'
        for r in ("passou", "falhou", "inconclusivo", "não executado"))
    return f"""<section class="sec" id="testador">
<div class="w">
<p class="olho">Ferramenta 2 · Testador</p>
<h2>O que aconteceu em cada cenário</h2>
<p class="sub">{c['total']} cenários: compra, {termo("estorno", "estorno")} total e estorno parcial, por meio de pagamento, com CPF e CNPJ.</p>
{faixa_erro}
<div class="nums t">
{numero(f"{c['falhou']} de {c['total']}", "cenários falharam", cond, n1=True)}
<div class="num4">{cartoes}</div>
</div>
<p class="fixo">{icone("info")}<span>Isto não é a {termo("homologacao", "homologação")} da plataforma e não dá aprovação.</span></p>
<div class="tw matriz-w"><table class="matriz">
<thead><tr><th>Meio</th>{cabeca}</tr></thead>
<tbody>{corpo}</tbody></table></div>
<p class="nota">Só conta como falha quando a API confirma que o fato aconteceu e o aviso não chegou. Cada célula mostra CPF e CNPJ; toque para ver os detalhes.
A {termo("janela", "janela de espera")} foi de {janela} minutos. Cartão 1x e 3x representam "sem juros" e "com juros": <span class="hip">suposição</span>, os juros dependem da configuração da loja.</p>
{literal}
<h3 class="leg-t">Os quatro resultados e o que fazer</h3>
<div class="legenda">{legenda}</div>
{_resistencia(d["resistencia"])}
{_como_e_feito(rodadas, d["rodada1"])}
</div>
</section>"""


def estado_vazio(ancora, titulo, texto):
    return f"""<section class="sec" id="{ancora}"><div class="w"><h2>{titulo}</h2>
<div class="card vazio">{icone("neutro")}<p>{texto}</p><a class="btn" href="#como-usar">Ver como usar</a></div></div></section>"""


def _passos(lista):
    return "".join(
        f'<li class="card passo"><span class="bola g">{n}</span><div class="passo-c"><h3>{verbo}</h3>{cmd}'
        f'<p class="esperar"><strong>O que esperar:</strong> {esperar}</p></div></li>'
        for n, verbo, cmd, esperar in lista)


def como_usar(d):
    preparo = [
        ("1", "Prepare o ambiente (uma vez só)",
         "<p>Crie um app no sandbox da plataforma, copie <code>.env.exemplo</code> para <code>.env</code> e preencha os dados do app e o endereço do túnel. Depois instale o app numa loja de teste:</p>"
         + comando("python -m conferidor.sandbox instalar"),
         "a loja de teste passa a mandar avisos para o seu computador."),
        ("2", "Ligue o receptor (sempre, antes de usar qualquer ferramenta)",
         "<p>Num terminal que fica aberto:</p>" + comando("python -m conferidor.receptor"),
         "cada aviso que chega aparece numa linha. Os dois usos abaixo dependem dele."),
    ]
    n_rodada = len(d['rodadas'][0]['linhas']) if d['rodadas'] else 12
    conferidor_passos = [
        ("A", "Crie pedidos de teste", comando("python -m conferidor.sandbox pix --quantos 3"),
         "três Pix de teste, aprovados sozinhos em cerca de 5 segundos. Para simular aviso perdido, pare o receptor e crie mais alguns."),
        ("B", "Confira", comando("python -m conferidor.sandbox conferir"),
         "para cada pedido: o que a loja sabia, o que a API informa e quais avisos não chegaram."),
        ("C", "Leia o painel", "<p>Abra <code>painel.html</code> no navegador.</p>",
         "os pedidos pagos sem aviso aparecem em vermelho."),
    ]
    testador_passos = [
        ("A", "Teste rápido (1 minuto)", comando("python -m testador rodar --meios pix --documentos cpf --acoes compra --espera 3"),
         "uma compra com Pix e o selo do resultado. Bom para conferir se está tudo ligado."),
        ("B", "Rodada completa", comando("python -m testador rodar"),
         f"{n_rodada} cenários (Pix e cartão 1x, CPF e CNPJ, compra e estornos), até 10 minutos de espera pelos avisos. Boleto e cartão 3x: "
         "<code>--meios boleto,cartao_parcelado --nome boleto_3x</code>."),
        ("C", "Leia e reconfira", "<p>Abra <code>testador.html</code> no navegador. Mais tarde, sem criar pedidos:</p>" + comando("python -m testador rejulgar"),
         "um selo por cenário. Inconclusivo vira resultado final quando a plataforma termina de processar."),
    ]
    extra = detalhe("Teste extra do testador: o seu endereço aguenta aviso repetido e fora de ordem?",
                    comando("python -m testador resistencia --alvo URL")
                    + "<p>Rode contra um segundo receptor (<code>--porta 8081 --banco outro.db</code>) para não misturar pedidos fictícios.</p>")
    return f"""<section class="sec cinza" id="como-usar">
<div class="w">
<p class="olho">Como usar</p>
<h2>Prepare uma vez, depois use cada ferramenta</h2>
<p class="sub">Os dois primeiros passos valem para as duas ferramentas. Depois, cada uma tem o seu caminho.</p>
<p class="pre"><strong>Você precisa de:</strong> Python 3.10 ou mais novo (nenhuma dependência), um app próprio no {termo("sandbox", "sandbox")} da plataforma
e um túnel que deixe o seu computador receber avisos da internet.</p>
<p class="fixo alerta">{icone("atencao")}<span>Use só com o seu próprio app, no sandbox. Nunca aponte para a produção de terceiros.</span></p>
<h3 class="titulo-bloco">Preparar (vale para as duas)</h3>
<ol class="passos">{_passos(preparo)}</ol>
<div class="duas-col">
<div><h3 class="titulo-bloco">Usar o conferidor</h3><p class="sub">Descobre os pedidos pagos de que a loja não soube.</p><ol class="passos">{_passos(conferidor_passos)}</ol></div>
<div><h3 class="titulo-bloco">Usar o testador</h3><p class="sub">Roda a lista de cenários de homologação e dá um selo para cada um.</p><ol class="passos">{_passos(testador_passos)}</ol>{extra}</div>
</div>
<p class="nota">O repositório do código é privado. Código disponível sob pedido ao autor.</p>
</div>
</section>"""


def limites(d):
    exp = d["exp"]
    minutos = round(exp["resumo"]["horas_desde_a_criacao"] * 60) if exp else None
    janela = max((r["espera_s"] for r in d["rodadas"]), default=600) // 60
    ressalvas = [
        "Tudo foi medido no <strong>sandbox</strong>, que pode se comportar diferente da produção.",
        "<strong>Um app só</strong>, o do próprio autor.",
        "<strong>Uma rodada</strong> de cada experimento (o testador teve uma rodada anterior com regra antiga, não exibida).",
        (f"<strong>Janela de reentrega ainda aberta</strong> na conferência de 14/10 (feita cerca de {minutos} min após os pedidos). Zero nova tentativa ainda não é conclusão."
         if exp and exp["resumo"]["horas_desde_a_criacao"] < DOC_JANELA_H else
         "A conferência de reentrega de 14/10 foi feita depois do fim da janela descrita na documentação."),
        f"A observação de reentrega de 13/10 tem <strong>{len(M1310_DESLIGADOS)} pedidos</strong> e a falha foi um <strong>502</strong>; a documentação não diz se 502 gera nova tentativa.",
        f"A janela de espera do testador é de <strong>{janela} minutos</strong>; aviso pode chegar depois.",
        "O testador <strong>não é a homologação</strong> e <strong>não dá aprovação</strong>.",
        "O teste de resistência mede <strong>só a resposta e o tempo</strong>, num <strong>endereço local</strong>; o que o app faz por dentro não é visível.",
        "<strong>Projeto independente</strong>, sem vínculo com a plataforma, sem dado de cliente.",
    ]
    lista = "".join(f"<li>{icone('info')}<span>{r}</span></li>" for r in ressalvas)
    fora = "".join(f"<li>{icone('neutro')}<span><strong>{escape(item.replace(' (soft descriptor)', '').replace('Descrição na fatura do cartão', 'Descrição que aparece na fatura do cartão'))}:</strong> {escape(porque)}</span></li>"
                   for item, porque in NAO_CONFERIVEIS)
    glossario = "".join(f'<div class="g" id="g-{k}"><dt>{escape(t)}</dt><dd>{escape(dfn)}</dd></div>' for k, t, dfn in GLOSSARIO)
    return f"""<section class="sec" id="limites">
<div class="w">
<p class="olho">Limites</p>
<h2>O que isto não prova</h2>
<p class="sub">Tudo aqui foi medido em ambiente de teste. Leia antes de tirar conclusão.</p>
<div class="duas">
<div class="card"><h3>Ressalvas</h3><ul class="lim">{lista}</ul></div>
<div class="card"><h3>O que não dá para conferir de fora</h3><ul class="lim">{fora}</ul></div>
</div>
<div class="card" id="glossario"><h3>Glossário</h3><dl class="glos">{glossario}</dl></div>
</div>
</section>"""


def rodape():
    return """<footer class="rodape"><div class="w">
<p><strong>Projeto independente de Jonas Victor Vieira Silva.</strong> Sem vínculo, patrocínio ou autorização da plataforma. Medido no sandbox do próprio app do autor, sem dado de cliente.</p>
<p class="mini">As regras de reentrega citadas vêm da documentação pública da Appmax. Nenhuma marca, imagem ou texto da plataforma é usado neste site.</p>
</div></footer>"""


CSS = """
:root{--roxo:#9B6AFA;--roxo-forte:#7444E6;--roxo-escuro:#5E30CC;--lilas:#EBE1FE;--lilas-2:#F5F0FF;
--texto:#202A44;--texto-2:#4A5370;--linha:#E4E1EE;--fundo:#FFFFFF;--fundo-2:#F7F6FB;
--ok:#1E7A46;--ok-f:#E3F5EA;--erro:#B42318;--erro-f:#FDECEA;--atencao:#8A5300;--atencao-f:#FFF3DC;
--neutro:#475467;--neutro-f:#EEF0F3;--sombra:0 1px 2px rgba(32,42,68,.06),0 8px 24px rgba(32,42,68,.07);
--mono:ui-monospace,SFMono-Regular,Consolas,"Liberation Mono",monospace;
--corpo:"Inter",system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;
--titulo:"Inter Tight","Inter",system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif}
*{box-sizing:border-box}
html{scroll-behavior:smooth;scroll-padding-top:76px}
body{margin:0;background:var(--fundo);color:var(--texto);font-family:var(--corpo);font-size:16px;line-height:1.6;overflow-wrap:break-word}
h1,h2,h3{font-family:var(--titulo);font-weight:600;line-height:1.2;margin:0 0 .4em}
h2{font-size:clamp(26px,4vw,36px)}h3{font-size:19px}
p{margin:0 0 .8em}
a{color:var(--roxo-forte)}
code{font-family:var(--mono);font-size:.88em;background:var(--lilas-2);border:1px solid var(--linha);border-radius:5px;padding:1px 5px;overflow-wrap:anywhere}
.w{max-width:1120px;margin:0 auto;padding:0 16px}
.aviso-topo{margin:0;background:var(--texto);color:#fff;font-size:13px;text-align:center;padding:7px 16px}
.aviso-topo .termo{color:#fff}
.barra{position:sticky;top:0;z-index:10;background:#fff;border-bottom:1px solid var(--linha)}
.barra-in{display:flex;align-items:center;gap:20px;min-height:64px}
.nome{font-family:var(--titulo);font-weight:700;font-size:18px;color:var(--texto);text-decoration:none;white-space:nowrap}
.barra nav{flex:1;min-width:0;overflow-x:auto;scrollbar-width:thin}
.barra ul{display:flex;gap:4px;list-style:none;margin:0;padding:0;justify-content:center}
.barra nav a{display:block;padding:8px 12px;border-radius:8px;color:var(--texto);text-decoration:none;font-size:15px;font-weight:500;white-space:nowrap}
.barra nav a:hover,.barra nav a:focus-visible{background:var(--lilas-2);color:var(--roxo-escuro)}
.btn{display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding:0 18px;border-radius:10px;background:var(--roxo-forte);color:#fff;font-weight:600;font-size:15px;text-decoration:none;white-space:nowrap;border:0}
.btn:hover{background:var(--roxo-escuro)}
.btn-branco{background:#fff;color:var(--roxo-escuro);border-radius:6px;text-transform:uppercase;font-size:15px;letter-spacing:.02em}
.btn-branco:hover{background:var(--lilas)}
.btn-lilas{background:var(--lilas);color:var(--roxo-escuro);border-radius:6px;text-transform:uppercase;font-size:15px;letter-spacing:.02em}
.btn-lilas:hover{background:#fff}
a:focus-visible,summary:focus-visible,button:focus-visible{outline:3px solid var(--roxo);outline-offset:2px}
.hero{background:radial-gradient(circle at 85% 110%,var(--roxo) 0,rgba(155,106,250,0) 55%),var(--roxo-forte);color:#fff;padding:56px 0 96px}
.hero-in{display:grid;grid-template-columns:1.05fr 1fr;gap:40px;align-items:center}
.hero h1{font-size:clamp(32px,5vw,50px);letter-spacing:-.01em}
.lead{font-size:18px;max-width:34em;color:#fff}
.acoes{display:flex;flex-wrap:wrap;gap:12px;margin-top:22px}
.hero-card{background:#fff;color:var(--texto);border-radius:20px;box-shadow:0 20px 50px rgba(30,10,80,.25);padding:24px}
.rot{font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--roxo-escuro);margin:0 0 10px}
.nums3{display:grid;gap:0}
.nums3 .num:last-child{border-bottom:0}
.nums3 .num{display:grid;grid-template-columns:auto 1fr;column-gap:16px;align-items:center;padding:12px 0;border:0;border-bottom:1px solid var(--linha);box-shadow:none;border-radius:0;background:none}
.nums3 .num .v{font-size:30px;grid-row:span 2}
.nums3 .num .f{font-size:15px}
.nums3 .num .cond{margin:2px 0 0}
.cond-faixa{display:flex;gap:8px;align-items:flex-start;margin:14px 0 0;font-size:13px;font-weight:600;color:var(--texto-2)}
.ferramentas{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:-56px;position:relative;margin-bottom:8px}
.card{background:#fff;border-radius:18px;box-shadow:var(--sombra);padding:24px;border:1px solid var(--linha);margin-bottom:20px;min-width:0}
.ferramentas .card{margin-bottom:0}
.ferr{text-decoration:none;color:var(--texto);display:block;transition:transform .15s}
.ferr:hover{transform:translateY(-2px)}
.ferr h2{font-size:24px}
.tag{display:inline-block;background:var(--lilas);color:var(--roxo-escuro);font-size:12px;font-weight:600;border-radius:999px;padding:3px 10px;margin-bottom:10px}
.ir{font-weight:600;color:var(--roxo-forte)}
.ir::after{content:" \\2193"}
.sec{padding:56px 0 36px}
.cinza{background:var(--fundo-2)}
.olho{font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:var(--roxo-escuro);margin-bottom:6px}
.sub{font-size:18px;color:var(--texto-2);max-width:44em;margin-bottom:28px}
.sub2{color:var(--texto-2);margin-top:-4px}
.duas{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.duas>.card{margin-bottom:20px}
.nums{display:grid;grid-template-columns:1.3fr 1fr 1fr;gap:20px;margin-bottom:20px}
.nums.t{grid-template-columns:1fr 1.6fr}
.num{background:#fff;border-radius:18px;box-shadow:var(--sombra);border:1px solid var(--linha);padding:22px;min-width:0}
.num .v{font-family:var(--titulo);font-weight:700;font-size:36px;line-height:1.1;color:var(--texto);white-space:nowrap}
.num.n1{background:var(--lilas-2);border-color:#D9C9FD}
.num.n1 .v{font-size:52px;color:var(--roxo-escuro)}
.num .f{font-weight:500;margin-top:6px}
.num4{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}
.num4 .num{padding:16px;display:flex;align-items:center;gap:14px}
.num4 .num .v{font-size:34px}
.num4 .num .f{margin:0}
.cond{display:flex;gap:6px;align-items:flex-start;font-size:13px;color:var(--texto-2);margin:12px 0 0;line-height:1.4}
.ic{width:16px;height:16px;flex:none;vertical-align:-3px}
.cond .ic,.cond-faixa .ic{margin-top:1px;color:var(--roxo-forte)}
.mini{display:block;font-size:13px;color:var(--texto-2);line-height:1.4;margin-top:4px}
.nota{font-size:14px;color:var(--texto-2)}
.selo{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:4px 12px 4px 9px;font-size:14px;font-weight:600;white-space:nowrap;border:1px solid transparent;line-height:1.3}
.selo.p{font-size:12.5px;padding:2px 9px 2px 7px;gap:4px}
.selo.p .ic{width:13px;height:13px;vertical-align:-2px}
.selo.ok{background:var(--ok-f);color:var(--ok);border-color:#BFE5CD}
.selo.erro{background:var(--erro-f);color:var(--erro);border-color:#F6C9C4}
.selo.atencao{background:var(--atencao-f);color:var(--atencao);border-color:#F2D9A6}
.selo.neutro{background:var(--neutro-f);color:var(--neutro);border-color:#D9DDE3}
.selo.espera{background:var(--neutro-f);color:var(--neutro);border-color:#D9DDE3;border-style:dashed}
.selo-doc{display:inline-block;background:var(--lilas);color:var(--roxo-escuro);font-weight:600;font-size:13px;border-radius:999px;padding:3px 12px}
.hip{background:var(--atencao-f);color:var(--atencao);font-weight:600;border-radius:5px;padding:0 5px}
.termo{color:inherit;text-decoration:underline dotted;text-decoration-thickness:1.5px;text-underline-offset:3px;cursor:help}
.diag-rot{font-weight:600;font-size:14px;color:var(--texto-2);margin:4px 0 10px}
.diag{display:flex;align-items:stretch;gap:10px;margin-bottom:22px}
.passo-d{flex:1;background:var(--fundo-2);border:1px solid var(--linha);border-radius:14px;padding:14px;display:flex;flex-direction:column;gap:4px;font-size:14.5px;min-width:0}
.passo-d strong{font-size:16px}
.passo-d.x{background:var(--erro-f);border-color:#F6C9C4}
.passo-d.x .bola{background:var(--erro)}
.bola{display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:50%;background:var(--roxo-forte);color:#fff;font-weight:700;font-size:14px;flex:none}
.bola .ic{width:15px;height:15px}
.seta{flex:0 0 28px;align-self:center;height:2px;background:var(--roxo);position:relative}
.seta::after{content:"";position:absolute;right:-1px;top:-5px;border:6px solid transparent;border-left-color:var(--roxo);border-right:0}
.seta.corte{background:repeating-linear-gradient(90deg,var(--erro) 0 5px,transparent 5px 9px);display:flex;align-items:center;justify-content:center}
.seta.corte::after{border-left-color:var(--erro)}
.seta.corte .ic{background:#fff;color:var(--erro);border-radius:50%;width:20px;height:20px;padding:2px;border:1.5px solid var(--erro)}
.tw{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:14px 0}
table{border-collapse:collapse;width:100%;font-size:15px}
th,td{text-align:left;padding:11px 12px;border-bottom:1px solid var(--linha);vertical-align:top}
thead th{font-size:13px;font-weight:600;color:var(--texto-2);background:var(--fundo-2)}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
tr.hist td{background:var(--lilas-2)}
.destaque{border-left:5px solid var(--roxo);background:#fff}
.estado{background:var(--atencao-f);border-radius:12px;padding:14px;margin:10px 0 14px}
.estado p{margin:8px 0 0}
.hist-l{font-size:15px;border-top:1px solid var(--linha);padding-top:12px}
.tl-f{margin:8px 0 14px}
.tl{position:relative;height:20px;margin:0 6px 10px;border-radius:2px;background:linear-gradient(var(--linha),var(--linha)) center/100% 2px no-repeat}
.tl i{position:absolute;top:50%;width:9px;height:9px;margin:-4.5px 0 0 -4.5px;border-radius:50%;background:var(--roxo-forte);opacity:.75}
.tl-r{font-size:13px;font-weight:600;margin:0 0 2px}
.tl-e{display:flex;justify-content:space-between;font-size:12px;color:var(--texto-2)}
.det{border:1px solid var(--linha);border-radius:14px;background:#fff;margin:14px 0}
.det>summary{cursor:pointer;padding:14px 18px 14px 52px;font-weight:600;list-style:none;display:block;position:relative}
.det>summary::-webkit-details-marker{display:none}
.det>summary::before{content:"+";position:absolute;left:18px;top:14px;display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;border-radius:6px;background:var(--lilas);color:var(--roxo-escuro);font-weight:700;flex:none}
.det[open]>summary::before{content:"\\2212"}
.det .res{display:block;font-weight:500;color:var(--texto-2)}
.det-c{padding:0 18px 16px}
.fixo{display:flex;gap:10px;align-items:flex-start;background:var(--lilas-2);border:1px solid #D9C9FD;border-radius:12px;padding:12px 16px;font-weight:600}
.fixo .ic{color:var(--roxo-escuro);margin-top:3px}
.fixo.alerta{background:var(--atencao-f);border-color:#F2D9A6;color:var(--atencao)}
.fixo.alerta .ic{color:var(--atencao)}
.matriz-w{background:#fff;border-radius:18px;box-shadow:var(--sombra);border:1px solid var(--linha)}
.matriz{min-width:640px;table-layout:fixed}
.matriz thead th:first-child{width:120px}
.matriz th[scope=row]{font-family:var(--titulo);font-size:16px;white-space:nowrap;width:120px}
.matriz td{padding:8px}
.matriz tbody tr:last-child>*{border-bottom:0}
.cel>summary{list-style:none;cursor:pointer;border-radius:10px;padding:8px;display:flex;flex-direction:column;gap:6px}
.cel>summary::-webkit-details-marker{display:none}
.cel>summary:hover{background:var(--lilas-2)}
.cel[open]>summary{background:var(--lilas-2)}
.docs{display:flex;flex-direction:column;gap:5px}
.doc{display:flex;align-items:center;gap:8px}
.doc-n{font-size:12px;font-weight:600;color:var(--texto-2);width:36px}
.abrir{font-size:13px;color:var(--roxo-forte);font-weight:600}
.abrir::after{content:" +"}
.cel[open] .abrir::after{content:" \\2212"}
.cel-c{padding:8px 6px 4px;font-size:14px}
.cel-t{font-weight:700;margin-bottom:6px}
.caso{border-top:1px solid var(--linha);padding-top:8px;margin-top:8px}
.caso ul{margin:2px 0 6px;padding-left:18px}
.tec{font-size:13px;color:var(--texto-2);font-family:var(--mono);background:var(--fundo-2);border-radius:8px;padding:8px}
.lit{white-space:pre-wrap;background:var(--fundo-2);border:1px solid var(--linha);border-radius:10px;padding:12px;font-size:13px;overflow-x:auto}
.lit code{background:none;border:0;padding:0}
.leg-t{margin-top:28px}
.legenda{display:grid;grid-template-columns:repeat(2,1fr);gap:16px;margin-bottom:12px}
.leg{background:#fff;border:1px solid var(--linha);border-radius:16px;padding:18px;font-size:15px}
.leg .selo{margin-bottom:10px}
.faixa-erro{display:flex;gap:12px;background:var(--erro-f);border:2px solid var(--erro);color:var(--erro);border-radius:14px;padding:16px;margin-bottom:20px}
.vazio{text-align:center;padding:40px 24px}
.vazio .ic{width:36px;height:36px;color:var(--neutro)}
.pre{max-width:52em}
.passos{list-style:none;padding:0;margin:20px 0}
.passo{display:flex;gap:16px;align-items:flex-start}
.passo .bola.g{width:40px;height:40px;font-size:18px}
.passo-c{flex:1;min-width:0}
.cmd{position:relative;margin:8px 0 12px}
.cmd pre{margin:0;background:#1C1F33;color:#F1EEFF;border-radius:12px;padding:14px 16px;overflow-x:auto;font-size:14px;line-height:1.55}
.cmd pre code{background:none;border:0;padding:0;color:inherit;font-size:inherit;overflow-wrap:normal}
.cmd.tem-copiar pre{padding-right:92px}
.copiar{position:absolute;top:8px;right:8px;min-height:32px;padding:0 12px;border-radius:8px;border:1px solid #4B4F6E;background:#2A2E48;color:#fff;font:600 13px var(--corpo);cursor:pointer}
.copiar:hover{background:var(--roxo-forte)}
.esperar{background:var(--fundo-2);border-radius:10px;padding:10px 12px;font-size:15px}
.lim{list-style:none;padding:0;margin:0}
.lim li{display:flex;gap:10px;padding:9px 0;border-bottom:1px solid var(--linha)}
.lim li:last-child{border-bottom:0}
.lim .ic{color:var(--texto-2);margin-top:4px}
.glos{display:grid;grid-template-columns:repeat(2,1fr);gap:4px 28px;margin:0}
.g{padding:10px 0;border-bottom:1px solid var(--linha)}
.g:target{background:var(--lilas);border-radius:8px;padding:10px}
.g dt{font-weight:700}
.g dd{margin:2px 0 0;color:var(--texto-2)}
.rodape{background:var(--texto);color:#E7E9F2;padding:32px 0;font-size:15px}
.rodape .mini{color:#C3C8DA}
@media (max-width:900px){
.hero-in,.duas,.nums,.nums.t,.ferramentas,.legenda,.glos{grid-template-columns:1fr}
.hero{padding:40px 0 80px}
.barra-in{gap:10px;flex-wrap:wrap;padding:8px 16px}
.barra nav{order:3;flex-basis:100%}
.barra ul{justify-content:flex-start}
.barra .btn{margin-left:auto;min-height:40px}
html{scroll-padding-top:120px}
}
@media (max-width:640px){
.diag{flex-direction:column}
.seta{flex:0 0 22px;width:2px;height:22px;align-self:center}
.seta::after{right:-5px;top:auto;bottom:-1px;border:6px solid transparent;border-top-color:var(--roxo);border-bottom:0}
.seta.corte{background:repeating-linear-gradient(180deg,var(--erro) 0 5px,transparent 5px 9px)}
.seta.corte::after{border-top-color:var(--erro);border-left-color:transparent}
.num4{grid-template-columns:1fr 1fr}
.nums3 .num{grid-template-columns:1fr}
.nums3 .num .v{grid-row:auto;font-size:28px}
.hero-card{padding:20px}
.num4 .num{flex-direction:column;align-items:flex-start;gap:6px}
.num.n1 .v{font-size:44px}
.card{padding:18px}
table.resp,table.resp tbody,table.resp tr,table.resp td{display:block;width:100%}
table.resp thead{display:none}
table.resp tr{border:1px solid var(--linha);border-radius:12px;margin-bottom:10px;padding:6px 0;background:#fff}
table.resp td{border:0;padding:6px 12px;text-align:left;white-space:normal}
table.resp td::before{content:attr(data-r);display:block;font-size:12px;font-weight:600;color:var(--texto-2)}
table.resp td.n{display:flex;justify-content:space-between;align-items:baseline;gap:12px;padding:3px 12px}
table.resp td.n::before{display:inline;font-size:13px}
.matriz{min-width:0;table-layout:auto}
.matriz,.matriz tbody,.matriz tr,.matriz td,.matriz th[scope=row]{display:block;width:100%}
.matriz thead{display:none}
.matriz tr{border-bottom:1px solid var(--linha);padding:8px 4px}
.matriz th[scope=row]{border:0;padding:8px 8px 2px}
.matriz td{border:0}
.matriz td::before{content:attr(data-r);display:block;font-size:12px;font-weight:600;color:var(--texto-2);padding:0 8px}
.docs{flex-direction:row;flex-wrap:wrap;gap:8px 14px}
.doc-n{width:auto}
.cmd.tem-copiar pre{padding-right:16px;padding-top:44px}
.passo{flex-direction:column;align-items:stretch;gap:10px}
.passo-c{width:100%}
}
"""

SCRIPT = """document.querySelectorAll('.cmd').forEach(function(c){if(!navigator.clipboard)return;var b=document.createElement('button');
b.type='button';b.className='copiar';b.textContent='Copiar';b.addEventListener('click',function(){navigator.clipboard.writeText(
c.querySelector('code').textContent).then(function(){b.textContent='Copiado';setTimeout(function(){b.textContent='Copiar'},1600)})});c.appendChild(b);c.classList.add('tem-copiar')});"""


def _documento(titulo, corpo):
    html = f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(titulo)}</title>
<meta name="description" content="Projeto independente: conferidor de avisos de pagamento e testador de cenários, medidos no sandbox do próprio app do autor.">
<link rel="icon" href="favicon.ico" sizes="any">
<link rel="icon" type="image/png" sizes="32x32" href="icone-32.png">
<link rel="apple-touch-icon" href="icone-180.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Inter+Tight:wght@600;700&display=swap">
<style>{CSS}{CSS_SESSOES}</style>
</head>
<body>
{corpo}
<script>{SCRIPT}</script>
</body>
</html>
"""
    if chr(0x2014) in html or chr(0x2013) in html:
        raise ValueError("a página contém travessão")
    return html


def gerar(dados=None):
    """Versao de pagina unica (mantida para os testes e para quem preferir rolar)."""
    d = dados if dados is not None else carregar()
    corpo = "\n".join([barra_superior(), "<main>", topo(d), problema(), conferidor(d), testador(d),
                       como_usar(d), limites(d), "</main>", rodape()])
    return _documento("Conferidor de avisos", corpo)


# ---------------------------------------------------------------- sessoes, uma pagina por assunto

SESSOES = [  # (arquivo, ancora da secao, rotulo no menu)
    ("index.html", "problema", "Início"),
    ("conferidor.html", "conferidor", "Conferidor"),
    ("testador.html", "testador", "Testador"),
    ("como-usar.html", "como-usar", "Como usar"),
    ("limites.html", "limites", "Limites"),
]

CSS_SESSOES = """
.barra nav a[aria-current=page]{color:var(--roxo-esc,#7444E6);font-weight:600;border-bottom:2px solid currentColor;padding-bottom:2px}
.seguir{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:8px 0 40px}
.seguir a{flex:1 1 220px;max-width:360px}
.seguir .vazio{flex:1 1 220px}
.seguir .prox{text-align:right;margin-left:auto}
.titulo-bloco{margin:28px 0 10px}
.duas-col{display:grid;grid-template-columns:1fr 1fr;gap:24px;align-items:start}
.duas-col>div{min-width:0}
@media (max-width:860px){.duas-col{grid-template-columns:1fr}}
"""


ATUAL = ' aria-current="page"'


def _barra(atual):
    links = "".join(
        f'<li><a href="{arq}"{ATUAL if arq == atual else ""}>{rot}</a></li>'
        for arq, _, rot in SESSOES)
    return f"""<p class="aviso-topo">Projeto independente, sem vínculo com a plataforma. Medido no {termo("sandbox", "sandbox")} do próprio app do autor, sem dado de cliente.</p>
<header class="barra">
<div class="w barra-in">
<a class="nome" href="index.html">Conferidor de avisos</a>
<nav aria-label="Sessões"><ul>{links}</ul></nav>
<a class="btn" href="como-usar.html">Como usar</a>
</div>
</header>"""


def _seguir(i):
    anterior = (f'<a class="card" href="{SESSOES[i - 1][0]}"><span class="tag">Anterior</span><h3>{SESSOES[i - 1][2]}</h3></a>'
                if i > 0 else '<span class="vazio"></span>')
    proxima = (f'<a class="card prox" href="{SESSOES[i + 1][0]}"><span class="tag">Próxima</span><h3>{SESSOES[i + 1][2]}</h3></a>'
               if i < len(SESSOES) - 1 else "")
    return f'<nav class="w seguir" aria-label="Navegação entre sessões">{anterior}{proxima}</nav>'


def _religar(paginas):
    """Troca os links internos (#ancora) pelo arquivo onde a ancora mora agora."""
    onde = {}
    for arquivo, html in paginas.items():
        for ancora in re.findall(r'id="([^"]+)"', html):
            onde.setdefault(ancora, arquivo)
    for arq, ancora, _ in SESSOES:
        onde[ancora] = arq  # a raiz de cada sessao abre a pagina, sem ancora
    if "topo" in onde:
        onde["topo"] = "index.html"

    def trocar(arquivo):
        def f(m):
            ancora = m.group(1)
            destino = onde.get(ancora)
            if destino is None or (destino == arquivo and ancora not in {a for _, a, _ in SESSOES}):
                return m.group(0)
            if ancora in {a for _, a, _ in SESSOES} or ancora == "topo":
                return f'href="{destino}"'
            return f'href="{destino}#{ancora}"' if destino != arquivo else m.group(0)
        return f

    return {arq: re.sub(r'href="#([^"]+)"', trocar(arq), html) for arq, html in paginas.items()}


def gerar_sessoes(dados=None):
    d = dados if dados is not None else carregar()
    conteudo = {
        "index.html": topo(d) + problema(),
        "conferidor.html": conferidor(d),
        "testador.html": testador(d),
        "como-usar.html": como_usar(d),
        "limites.html": limites(d),
    }
    titulos = {"index.html": "Conferidor de avisos", "conferidor.html": "Conferidor · resultados",
               "testador.html": "Testador · resultados", "como-usar.html": "Como usar",
               "limites.html": "Limites e glossário"}
    paginas = {}
    for i, (arq, _, _) in enumerate(SESSOES):
        corpo = "\n".join([_barra(arq), "<main>", conteudo[arq], _seguir(i), "</main>", rodape()])
        paginas[arq] = corpo
    paginas = _religar(paginas)
    return {arq: _documento(titulos[arq], corpo) for arq, corpo in paginas.items()}


def montar():
    SAIDA.mkdir(exist_ok=True)
    for antigo in SAIDA.glob("*.html"):
        antigo.unlink()
    for arquivo, html in gerar_sessoes().items():
        (SAIDA / arquivo).write_text(html, encoding="utf-8")
    for icone_arquivo in (RAIZ / "assets").glob("*"):  # icone do autor (aba do navegador e celular)
        shutil.copyfile(icone_arquivo, SAIDA / icone_arquivo.name)
    print("Site v2 montado em", SAIDA, "com", len(SESSOES), "sessões")
    return SAIDA


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    montar()
