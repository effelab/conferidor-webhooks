"""Monta o site estatico (pasta site/) a partir dos resultados gravados. Nenhuma chave, nada ao vivo.

    python -m conferidor.site

Paginas: index.html (medicao de 13/10), experimentos.html (deteccao, reentrega
e demora), testador.html e testador-boleto-3x.html (homologacao). Depois:
de dentro de site/, npx vercel deploy --prod --yes
"""
import json
import sys
from html import escape

from . import config
from .relatorio import moldura, selo

SITE = config.RAIZ / "site"
PAGINAS = [("index.html", "Medição de 13/10"), ("experimentos.html", "Experimentos de 14/10"),
           ("testador.html", "Testador: Pix e cartão 1x"), ("testador-boleto-3x.html", "Testador: boleto e cartão 3x")]


def navegacao(atual):
    links = " ".join(
        f'<a href="{arquivo}" style="margin-right:14px;{"font-weight:600;text-decoration:none" if arquivo == atual else ""}">'
        f"{escape(rotulo)}</a>" for arquivo, rotulo in PAGINAS)
    return f'<nav style="padding:10px 0 4px;font-size:14px">{links}</nav>'


def com_navegacao(html, atual):
    return html.replace("</header>", "</header>\n<div class=\"w\" style=\"padding-bottom:0\">" + navegacao(atual) + "</div>", 1)


def _data(iso):
    data, hora = iso.split("T")
    a, m, d = data.split("-")
    return f"{d}/{m}/{a} às {hora[:5]}"


def experimentos(dados):
    r = dados["resumo"]
    d, e = r["deteccao"], r["reentrega"]
    nome = {"derrubar": "Servidor fora do ar (o túnel devolve 502)", "falhar": "Servidor no ar respondendo erro 500",
            "demorar:7": "Servidor responde em 7 s", "demorar:12": "Servidor responde em 12 s"}
    linhas = "".join(
        f"<tr><td>{escape(nome[g])}</td><td class=n>{v['pedidos']}</td><td class=n>{v['avisos_distintos']}</td>"
        f"<td>{selo(v['reenvios'], 'r' if v['reenvios'] == 0 else 'g')}</td></tr>" for g, v in e.items())
    corpo = f"""<div class="sub"><strong>Medição real, no ambiente de teste (sandbox) da plataforma, em 14/10/2026.</strong>
75 pedidos com Pix de teste. O receptor de avisos foi programado para se comportar de um jeito diferente em cada grupo
de pedidos: normal, fora do ar, respondendo erro ou demorando para responder.</div>

<section id="deteccao">
<h2>O conferidor acha os pedidos pagos de que a loja não soube?</h2>
<div class="kpis">
<div class="kpi g"><div class="n">{d['derrubados_apontados']} de {d['derrubados']}</div><div class="l">pedidos pagos sem aviso, apontados</div></div>
<div class="kpi g"><div class="n">{d['normais_apontados_por_engano']} de {d['normais_e_pendentes']}</div><div class="l">pedidos normais ou pendentes apontados por engano</div></div>
<div class="kpi"><div class="n">{r['consultas_a_api']}</div><div class="l">consultas à API na última conferência</div></div>
</div>
<div class="card"><p>Em 20 pedidos os avisos foram derrubados de propósito. Os outros 35 tiveram o receptor normal, 5 deles
com Pix que fica pendente de propósito, para ver se o conferidor confunde "não pago" com "aviso perdido".</p></div>
</section>

<section id="reentrega">
<h2>A plataforma reenvia o aviso que falhou?</h2>
<div class="tw lg"><table><thead><tr><th>Como o receptor se comportou</th><th class=n>Pedidos</th>
<th class=n>Avisos recebidos</th><th>Reenvios</th></tr></thead><tbody>{linhas}</tbody></table></div>
<div class="card"><p>Conferido em {_data(r['avaliado_em'])}, {r['horas_desde_a_criacao']:.1f} h depois dos
pedidos. A documentação descreve até quatro tentativas, a última em até 6h30; antes desse prazo, zero reenvio ainda não é
conclusão. Em 13/10, com dois pedidos e falha 502, não houve reenvio em 12h45.</p></div>
</section>

<section id="fila">
<h2>O que a demora mostrou</h2>
<div class="card">
<p><strong>Os avisos saem em fila, um por vez.</strong> Com o receptor demorando 7 s, os avisos chegaram com 7 a 8 s de
intervalo; demorando 12 s, com 12 a 13 s. Os últimos chegaram cerca de 9,5 minutos depois do pedido criado: um app lento
atrasa todos os avisos seguintes dele.</p>
<p><strong>A plataforma esperou 12 s sem cortar e sem reenviar.</strong> A documentação fala em 5 s e o painel do app, em 10 s.
Daqui não dá para saber se o limite real é maior ou se ela corta e não reenvia.</p>
<p><strong>6 de 60 avisos desses pedidos nunca chegaram</strong>, com o receptor no ar o tempo todo. Causa desconhecida.
O conferidor apontou os 4 pedidos afetados.</p>
<p style="font-size:13px">Limites: é o ambiente de teste, que pode se comportar diferente da produção; um app só; uma rodada.</p>
</div>
</section>"""
    return moldura("Conferidor: Experimentos", "Conferidor de webhooks: experimentos no sandbox", "", [], corpo,
                   "Projeto independente. Medição no sandbox do próprio app do autor, sem dado de cliente.")


def montar():
    from testador import relatorio as relatorio_testador

    raiz = config.RAIZ
    painel = (raiz / "painel.html").read_text(encoding="utf-8")
    (SITE / "index.html").write_text(com_navegacao(painel, "index.html"), encoding="utf-8")

    dados = json.loads((raiz / "experimentos_resultado.json").read_text(encoding="utf-8"))
    (SITE / "experimentos.html").write_text(com_navegacao(experimentos(dados), "experimentos.html"), encoding="utf-8")

    resistencia = raiz / "testador_resistencia.json"
    extra = json.loads(resistencia.read_text(encoding="utf-8")) if resistencia.exists() else None
    for origem, destino in (("testador_resultado.json", "testador.html"),
                            ("testador_resultado_boleto_3x.json", "testador-boleto-3x.html")):
        resultado = json.loads((raiz / origem).read_text(encoding="utf-8"))
        html = relatorio_testador.gerar(resultado, extra if destino == "testador.html" else None)
        (SITE / destino).write_text(com_navegacao(html, destino), encoding="utf-8")
    for arquivo, _ in PAGINAS:
        texto = (SITE / arquivo).read_text(encoding="utf-8")
        assert "—" not in texto and "–" not in texto, arquivo
    print("Site montado em", SITE)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    montar()
