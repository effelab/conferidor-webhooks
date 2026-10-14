"""Gera o relatorio em HTML, autocontido, a partir dos resultados da bancada."""
from datetime import datetime
from html import escape

from .contrato import QUOTA_MENSAL

CHAMADAS_POR_PEDIDO = 3  # SUPOSICAO: criar cliente, criar pedido e pagar

NOMES_DE_EVENTO = {
    "order_paid_by_pix": "Pix pago", "order_paid": "pedido pago", "order_approved": "pedido aprovado",
    "order_integrated": "pedido integrado", "order_authorized": "cartão autorizado",
    "order_pix_created": "Pix gerado", "order_pix_expired": "Pix expirado",
    "order_refund": "estorno", "order_billet_created": "boleto gerado",
    "order_billet_overdue": "boleto vencido", "payment_not_authorized": "cartão não autorizado",
    "order_refused_by_risk": "recusado por risco", "order_pending_integration": "integração pendente",
    "order_chargeback_in_treatment": "chargeback",
}

CSS = """
:root{color-scheme:light;--bg:#f5f6fa;--pn:#fff;--pn2:#f3f4f9;--ln:#e4e6ee;--tx:#171a23;--tx2:#565d70;
--tx3:#8b92a4;--ac:#6d4aff;--acb:#f4f1ff;--acl:#d9cfff;--tl:#0d9488;--tlb:#effcfa;--tll:#a7e8df;
--bd:#c92a2a;--bdb:#fff1f1;--bdl:#f5c6c6;--gd:#15803d;--gdb:#f0fdf4;--gdl:#bbe7c9;--wn:#b45309;
--wnb:#fff8eb;--wnl:#f3ddb0;--mono:ui-monospace,Menlo,Consolas,monospace;--lat:248px;
--sm:0 1px 2px rgba(23,26,35,.04),0 1px 3px rgba(23,26,35,.04)}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--tx);-webkit-font-smoothing:antialiased;
font:15px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.lat{position:fixed;top:0;bottom:0;left:0;width:var(--lat);z-index:20;background:var(--pn);
border-right:1px solid var(--ln);display:flex;flex-direction:column;padding:20px 14px;overflow-y:auto}
.marca{display:flex;align-items:center;gap:11px;padding:0 8px 18px;margin-bottom:14px;border-bottom:1px solid var(--ln);
color:inherit;text-decoration:none}
.marca svg{width:34px;height:34px;flex:none}
.marca b{display:block;font-size:16px;line-height:1.2;letter-spacing:-.2px}
.marca small{display:block;font-size:11.5px;line-height:1.3;color:var(--tx3)}
.nav{display:flex;flex-direction:column;gap:2px}
.nav .t{font-size:10.5px;letter-spacing:1.2px;text-transform:uppercase;color:var(--tx3);padding:4px 10px 6px}
.nav a{display:flex;align-items:center;gap:10px;padding:8px 10px;border-radius:8px;color:var(--tx2);
text-decoration:none;font-size:13.5px;font-weight:500;line-height:1.3;white-space:nowrap}
.nav a::before{content:"";width:6px;height:6px;border-radius:50%;background:var(--acl);flex:none}
.nav a:hover,.nav a:focus-visible{background:var(--acb);color:var(--ac);outline:0}
.nav a:hover::before,.nav a:focus-visible::before{background:var(--ac)}
.pr{margin-left:var(--lat);min-width:0}
.topo{position:sticky;top:0;z-index:10;background:var(--pn);border-bottom:1px solid var(--ln);
display:flex;align-items:center;justify-content:space-between;gap:8px 16px;flex-wrap:wrap;padding:14px 28px}
h1{margin:0;font-size:18px;line-height:1.3;letter-spacing:-.2px}
.data{font-size:12.5px;color:var(--tx2);background:var(--pn2);border:1px solid var(--ln);border-radius:999px;padding:3px 12px}
.w{max-width:1120px;margin:0 auto;padding:22px 28px 64px}
.sub{color:var(--tx2);font-size:14.5px;max-width:760px;margin-top:14px}
section{scroll-margin-top:72px}
h2{font-size:17px;line-height:1.3;letter-spacing:-.2px;color:var(--tx);margin:38px 0 14px}
h3{font-size:15.5px;margin:0 0 8px}
p{margin:0 0 11px}
.aviso{background:var(--wnb);border:1px solid var(--wnl);border-left:4px solid var(--wn);border-radius:10px;
padding:13px 16px;font-size:13.5px;color:#6b3a06}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(185px,1fr));gap:14px}
.kpi{background:var(--pn);border:1px solid var(--ln);border-top:3px solid var(--ac);border-radius:12px;padding:16px;box-shadow:var(--sm)}
.kpi .n{font-size:25px;font-weight:680;letter-spacing:-.6px;color:var(--ac);line-height:1.2}
.kpi .l{font-size:12.5px;color:var(--tx2);margin-top:5px;line-height:1.45}
.kpi.r{border-top-color:var(--bd)}.kpi.g{border-top-color:var(--gd)}
.kpi.r .n{color:var(--bd)}.kpi.g .n{color:var(--gd)}
.card{background:var(--pn);border:1px solid var(--ln);border-radius:12px;padding:18px;margin-bottom:14px;box-shadow:var(--sm)}
.card p{font-size:14px;color:var(--tx2)}.card p:last-child{margin:0}
.card.ac{border-left:3px solid var(--ac)}.card.g{border-left:3px solid var(--gd)}.card.r{border-left:3px solid var(--bd)}
.g2{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(310px,100%),1fr));gap:14px}
.g2>*{min-width:0}
.tw{overflow-x:auto;background:var(--pn);border:1px solid var(--ln);border-radius:12px;box-shadow:var(--sm)}
table{width:100%;border-collapse:collapse;font-size:13.5px}
.tw.lg table{min-width:820px}
th,td{text-align:left;padding:11px 14px;border-bottom:1px solid var(--ln);vertical-align:top}
th{background:var(--pn2);color:var(--tx2);font-size:10.5px;text-transform:uppercase;letter-spacing:1px}
tbody tr:last-child td{border-bottom:0}
tbody tr:hover td{background:#fafaff}
td.n,th.n{text-align:right;font-family:var(--mono);font-size:12.5px;white-space:nowrap}
.selo{display:inline-flex;align-items:center;gap:6px;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600;
line-height:1.5;white-space:nowrap;color:var(--tx2);background:var(--pn2);border:1px solid var(--ln)}
.selo::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor}
.selo.g{color:var(--gd);background:var(--gdb);border-color:var(--gdl)}
.selo.r{color:var(--bd);background:var(--bdb);border-color:var(--bdl)}
.selo.w{color:var(--wn);background:var(--wnb);border-color:var(--wnl)}
.selo.a{color:var(--ac);background:var(--acb);border-color:var(--acl)}
.ped{display:inline-flex;align-items:center;gap:8px;font-family:var(--mono);font-weight:600;white-space:nowrap}
.ped::before{content:"";width:8px;height:8px;border-radius:50%;background:var(--gd)}
.ped.r::before{background:var(--bd)}
code{font-family:var(--mono);font-size:12.5px;background:var(--pn2);border:1px solid var(--ln);border-radius:4px;padding:1px 5px}
pre{background:#12141c;color:#e7e9f0;border-radius:8px;padding:14px;overflow-x:auto;font-family:var(--mono);font-size:13px}
ul{margin:0 0 10px;padding-left:20px;color:var(--tx2);font-size:14px}li{margin-bottom:6px}li strong{color:var(--tx)}
.fig{overflow-x:auto}.fig svg{display:block;width:100%;height:auto;min-width:560px}
svg text{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.rot{font-size:12.5px;fill:#171a23}.val{font-size:12px;fill:#565d70;font-family:ui-monospace,Menlo,Consolas,monospace}
footer{margin-top:48px;padding-top:20px;border-top:1px solid var(--ln);font-size:12.5px;color:var(--tx3)}
@media (max-width:900px){
.lat{position:sticky;bottom:auto;width:auto;flex-direction:row;align-items:center;gap:14px;padding:8px 12px;
border-right:0;border-bottom:1px solid var(--ln);overflow:visible}
.marca{padding:0;margin:0;border:0;flex:none}
.marca svg{width:30px;height:30px}
.nav{flex-direction:row;flex:1;min-width:0;overflow-x:auto;gap:4px}
.nav .t{display:none}
.nav a{padding:7px 10px}
.pr{margin-left:0}
.topo{position:static;padding:12px 16px}
.w{padding:16px 16px 56px}
section{scroll-margin-top:62px}
h2{margin-top:30px}
}
"""


def inteiro(n):
    return f"{n:,.0f}".replace(",", ".")


def reais(centavos):
    return "R$ " + f"{centavos / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct(x, casas=1):
    return "n/d" if x is None else f"{x * 100:.{casas}f}%".replace(".", ",")


def duracao(minutos):
    if minutos is None:
        return "n/d"
    if minutos < 90:
        return f"{minutos:.0f} min"
    return f"{minutos / 60:.1f} h".replace(".", ",")


def barras(itens, rotulo_w=250, teto=None):
    """Barras horizontais em SVG. itens: (rotulo, valor, texto, cor)."""
    maximo = teto or max((v for _, v, _, _ in itens), default=1) or 1
    area, alt = 440, 34
    linhas = []
    for i, (rotulo, valor, texto, cor) in enumerate(itens):
        y = 8 + i * alt
        largura = max(2, min(area, area * valor / maximo))
        linhas.append(
            f'<text class="rot" x="0" y="{y + 16}">{escape(rotulo)}</text>'
            f'<rect x="{rotulo_w}" y="{y + 2}" width="{largura:.0f}" height="20" rx="4" fill="{cor}"/>'
            f'<text class="val" x="{rotulo_w + largura + 8:.0f}" y="{y + 16}">{escape(texto)}</text>')
    altura = 16 + len(itens) * alt
    return (f'<div class="fig"><svg viewBox="0 0 {rotulo_w + area + 190} {altura}" role="img">'
            + "".join(linhas) + "</svg></div>")


SELO_DE_STATUS = {
    "aprovado": "g", "pago": "g", "integrado": "g", "autorizado": "g",
    "pendente": "w", "pendente_integracao": "w",
    "cancelado": "r", "estornado": "r", "recusado": "r", "recusado_por_risco": "r", "chargeback": "r",
}

MARCA = ('<svg viewBox="0 0 34 34" aria-hidden="true"><rect width="34" height="34" rx="9" fill="#6d4aff"/>'
         '<path d="M9.5 17.5l5 5 10-11" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>')


def selo(texto, cor=""):
    """Selo colorido. cor: g (verde), r (vermelho), w (ambar), a (roxo) ou vazio (neutro)."""
    return f'<span class="selo {cor}">{escape(str(texto))}</span>'


def selo_status(status):
    return selo(status, SELO_DE_STATUS.get(str(status).strip().lower(), ""))


def moldura(titulo_aba, titulo, data, navegacao, corpo, rodape):
    """A casca de painel: barra lateral com ancoras, barra superior e area de conteudo.

    navegacao: lista de (id_da_secao, rotulo). corpo e rodape ja vem em HTML.
    """
    links = "".join(f'<a href="#{escape(i)}">{escape(r)}</a>' for i, r in navegacao)
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(titulo_aba)}</title><style>{CSS}</style></head><body>
<div class="pr" id="topo" style="margin-left:0">
<header class="topo"><h1>{escape(titulo)}</h1></header>
<main class="w">
{corpo}
<footer>{rodape}</footer>
</main></div></body></html>"""


def gerar(resultados):
    por_chave = {r["chave"]: r for r in resultados}
    normal, inc, inc4, fds = (por_chave[k] for k in ("normal", "incidente", "incidente_4h", "fim_de_semana"))
    uso_normal = inc["pedidos"] * CHAMADAS_POR_PEDIDO

    descricoes = "".join(f"<li><strong>{escape(r['nome'])}:</strong> {escape(r['descricao'])}</li>" for r in resultados)
    linhas_cenarios = "".join(
        f"<tr><td style='white-space:nowrap'><strong>{escape(r['nome'])}</strong></td>"
        f"<td class=n>{inteiro(r['avisos_perdidos'])}</td>"
        f"<td class=n>{inteiro(r['pedidos_pagos_sem_aviso'])}</td>"
        f"<td class=n>{reais(r['valor_pago_sem_aviso'])}</td>"
        f"<td class=n>{inteiro(r['errados_sem_conferidor'])}</td>"
        f"<td class=n>{inteiro(r['errados_com_conferidor'])}</td>"
        f"<td class=n>{pct(r['cobertura'])}</td>"
        f"<td class=n>{duracao(r['atraso_mediano_min'])}</td>"
        f"<td class=n>{inteiro(r['consultas'])}</td></tr>"
        for r in resultados)

    linhas_suporte = "".join(
        f"<tr><td class=n>{x['order_id']}</td><td>{selo_status(x['status'])}</td>"
        f"<td>{escape(', '.join(NOMES_DE_EVENTO.get(e, e) for e in x['eventos']))}</td>"
        f"<td class=n>{reais(x['valor'])}</td></tr>"
        for x in inc["para_o_suporte"])

    por_metodo = "".join(
        f"<tr><td>{rotulo}</td><td class=n>{duracao(inc['atraso_mediano_por_metodo_min'].get(m))}</td>"
        f"<td class=n>{duracao(fds['atraso_mediano_por_metodo_min'].get(m))}</td></tr>"
        for m, rotulo in (("pix", "Pix"), ("cartao", "Cartão"), ("boleto", "Boleto")))

    nao_apontados = ", ".join(f"{NOMES_DE_EVENTO.get(e, e)} ({n})" for e, n in fds["nao_apontados_por_evento"].items()) or "nenhum"

    grafico_perda = barras([
        (r["nome"], r["avisos_perdidos"], f"{inteiro(r['avisos_perdidos'])} avisos, {inteiro(r['pedidos_pagos_sem_aviso'])} pedidos pagos",
         "#15803d" if r["avisos_perdidos"] == 0 else "#c92a2a") for r in resultados])
    grafico_estado = barras([
        ("Incidente de 8 h, sem conferidor", inc["errados_sem_conferidor"], inteiro(inc["errados_sem_conferidor"]) + " pedidos", "#c92a2a"),
        ("Incidente de 8 h, com conferidor", inc["errados_com_conferidor"], inteiro(inc["errados_com_conferidor"]) + " pedidos", "#15803d"),
        ("Fim de semana, sem conferidor", fds["errados_sem_conferidor"], inteiro(fds["errados_sem_conferidor"]) + " pedidos", "#c92a2a"),
        ("Fim de semana, com conferidor", fds["errados_com_conferidor"], inteiro(fds["errados_com_conferidor"]) + " pedidos", "#15803d"),
    ])
    grafico_custo = barras([
        ("Quota mensal documentada", QUOTA_MENSAL, inteiro(QUOTA_MENSAL), "#b6a6ff"),
        ("Operação da loja (estimativa)", uso_normal, inteiro(uso_normal), "#cfd4e0"),
        ("Conferidor, no pior cenário", fds["consultas"], f"{inteiro(fds['consultas'])} ({pct(fds['consultas_pct_da_quota'], 0)} da quota)", "#6d4aff"),
        ("Conferir tudo de hora em hora", QUOTA_MENSAL * 1.05,
         f"{inteiro(inc['consultas_varredura_ingenua'])} ({inc['consultas_varredura_ingenua'] / QUOTA_MENSAL:.0f}x a quota)", "#c92a2a"),
    ], teto=QUOTA_MENSAL * 1.05)

    corpo = f"""<div class="aviso"><strong>Isto é uma simulação.</strong> Os números abaixo vêm de uma bancada de teste com dado 100% sintético, que reproduz o comportamento descrito na documentação pública da plataforma. Não são medições do sistema real. A medição real, feita no ambiente de teste, está na página <a href="sandbox.html">Resultado no sandbox</a>.</div>
<div class="sub">Um exercício: descobrir quais avisos de pagamento a loja deixou de receber, cruzando o que chegou com o que a plataforma informa.</div>

<section id="resultado">
<h2>O resultado em um incidente de 8 horas</h2>
<div class="kpis">
<div class="kpi r"><div class="n">{inteiro(inc['avisos_perdidos'])}</div><div class="l">avisos descartados sem notificação, em {inteiro(inc['pedidos'])} pedidos no mês</div></div>
<div class="kpi r"><div class="n">{inteiro(inc['pedidos_pagos_sem_aviso'])}</div><div class="l">pedidos pagos cujo aviso de pagamento nunca chegou, somando {reais(inc['valor_pago_sem_aviso'])}</div></div>
<div class="kpi g"><div class="n">{pct(inc['cobertura'])}</div><div class="l">dos avisos perdidos foram apontados pelo conferidor</div></div>
<div class="kpi g"><div class="n">{duracao(inc['atraso_mediano_min'])}</div><div class="l">é o tempo mediano até a loja saber de um pagamento cujo aviso se perdeu</div></div>
<div class="kpi"><div class="n">{pct(inc['consultas_pct_da_quota'], 0)}</div><div class="l">da quota mensal de API consumida, com {inteiro(inc['consultas'])} consultas</div></div>
</div>
</section>

<section id="pergunta">
<h2>A pergunta</h2>
<div class="card ac">
<p>A documentação pública diz que um aviso de pagamento (webhook) é tentado quatro vezes e depois descartado sem notificação, e que a recuperação é pedindo reenvio ao suporte.</p>
<p><strong>Para pedir o reenvio, a loja precisa saber o que perdeu.</strong> O conferidor responde a essa pergunta: ele compara os avisos recebidos com o status de cada pedido na API e aponta as divergências.</p>
</div>
</section>

<section id="cenarios">
<h2>Os quatro cenários</h2>
<div class="tw lg"><table>
<thead><tr><th>Cenário</th><th class=n>Avisos perdidos</th><th class=n>Pedidos pagos sem aviso</th><th class=n>Valor</th>
<th class=n>Estado errado sem conferidor</th><th class=n>Com conferidor</th><th class=n>Cobertura</th><th class=n>Atraso mediano</th><th class=n>Consultas</th></tr></thead>
<tbody>{linhas_cenarios}</tbody></table></div>
<p style="font-size:13px;color:var(--tx3);margin-top:10px">Estado errado: pedidos em que, no fim do mês, a loja acredita em um status diferente do real. Cobertura: parcela dos avisos perdidos que o conferidor apontou, entre os que já podiam ser confirmados.</p>
<div class="card" style="margin-top:14px"><h3>O que é cada cenário</h3><ul>{descricoes}</ul></div>
</section>

<section id="perda">
<h2>Quanto se perde</h2>
<div class="card">{grafico_perda}</div>
<div class="g2">
<div class="card g"><h3>Em operação normal, a perda foi zero</h3>
<p>Com oscilações de até 20 minutos, a política de retentativa da plataforma recuperou tudo sozinha. No cenário de incidente ela ainda recuperou <strong>{inteiro(inc['recuperados_por_retentativa'])} avisos</strong> que o conferidor tinha visto faltar.</p>
<p>O problema não é a retentativa ser ruim. É o que acontece quando a queda dura mais que a janela.</p></div>
<div class="card r"><h3>A mesma queda perde {inteiro(inc['avisos_perdidos'])} ou {inteiro(inc4['avisos_perdidos'])} avisos</h3>
<p>A documentação lista os intervalos de retentativa (+30 min, +2 h, +4 h) sem dizer se contam da tentativa anterior ou da primeira. Na primeira leitura a janela é de 6h30, na segunda é de 4 horas.</p>
<p>Para o mesmo incidente de 8 horas, isso muda a perda em <strong>{f"{inc4['avisos_perdidos'] / max(1, inc['avisos_perdidos']):.1f}".replace(".", ",")} vezes</strong>. É uma pergunta que só quem opera a plataforma responde.</p></div>
</div>
</section>

<section id="conferidor">
<h2>O que muda com o conferidor</h2>
<div class="card">{grafico_estado}</div>
<div class="g2">
<div class="card"><h3>Tempo até a loja saber do pagamento</h3>
<div class="tw" style="box-shadow:none"><table><thead><tr><th>Meio</th><th class=n>Incidente de 8 h</th><th class=n>Fim de semana</th></tr></thead>
<tbody>{por_metodo}</tbody></table></div>
<p style="margin-top:10px">Mediana entre o pagamento real e a loja ficar sabendo, só para pedidos cujo aviso de pagamento foi descartado. O boleto é mais lento porque é conferido uma vez por dia, uma escolha de custo.</p>
<p><strong>Sem o conferidor</strong>, no incidente de 8 horas, {inteiro(inc['sem_conferidor_nunca_souberam'])} dos {inteiro(inc['pedidos_pagos_sem_aviso'])} pedidos terminam o mês sem a loja saber que foram pagos, e os demais ela só descobre por um aviso posterior, em mediana de {duracao(inc['sem_conferidor_atraso_mediano_min'])}. No fim de semana, {inteiro(fds['sem_conferidor_nunca_souberam'])} de {inteiro(fds['pedidos_pagos_sem_aviso'])} nunca chegam ao conhecimento dela.</p></div>
<div class="card"><h3>Como ele decide quem consultar</h3>
<ul>
<li><strong>Pedido que recebe os avisos no prazo nunca é consultado.</strong> O gatilho é o silêncio: um Pix sem novidade 45 minutos depois de gerado, por exemplo.</li>
<li><strong>Na consulta, o status da API vira a verdade da loja na hora.</strong> Ela libera o pedido sem esperar o aviso.</li>
<li><strong>Um aviso só é declarado perdido depois que a janela de retentativa fechou.</strong> Antes disso ele ainda pode chegar sozinho.</li>
</ul>
<p>Nenhum modelo de linguagem participa. É comparação de conjuntos e relógio.</p></div>
</div>
</section>

<section id="custo">
<h2>O custo em chamadas de API</h2>
<div class="card">{grafico_custo}
<p style="margin-top:12px">A quota documentada é de {inteiro(QUOTA_MENSAL)} requisições por mês por credencial. Uma loja com {inteiro(inc['pedidos'])} pedidos já consome perto de {inteiro(uso_normal)} só para operar (estimativa de {CHAMADAS_POR_PEDIDO} chamadas por pedido). <strong>Conferir todos os pedidos de hora em hora estouraria a quota {inc['consultas_varredura_ingenua'] / QUOTA_MENSAL:.0f} vezes.</strong> Consultando só o que está em silêncio, o conferidor cabe no que sobra.</p></div>
</section>

<section id="suporte">
<h2>A lista para pedir reenvio ao suporte</h2>
<div class="tw"><table><thead><tr><th class=n>Pedido</th><th>Status na API</th><th>Avisos que não chegaram</th><th class=n>Valor</th></tr></thead>
<tbody>{linhas_suporte}</tbody></table></div>
<p style="font-size:13px;color:var(--tx3);margin-top:10px">Os dez maiores do cenário de incidente. Identificadores e valores são sintéticos.</p>
</section>

<section id="alarme-falso">
<h2>Uma regra que evita alarme falso</h2>
<div class="card"><p>A documentação registra que pedidos originados na Yampi não geram webhook, de propósito. No mês simulado isso representou {inteiro(inc['avisos_suprimidos_yampi'])} avisos de {inteiro(inc['pedidos_yampi'])} pedidos. O conferidor acompanha esses pedidos por consulta e <strong>deixa de emitir {inteiro(inc['alarmes_falsos_evitados'])} alarmes falsos</strong> que um monitor desavisado emitiria.</p></div>
</section>

<section id="limites">
<h2>Limites deste resultado</h2>
<div class="card"><ul>
<li><strong>É simulação.</strong> A plataforma da bancada é a minha leitura da documentação pública, não o sistema real. O volume, o mix de meios de pagamento e as taxas de aprovação são suposições declaradas no código.</li>
<li><strong>A precisão de {pct(inc['precisao'], 0)} não prova muito.</strong> O conferidor e o simulador seguem a mesma leitura do contrato, então era esperado que concordassem. A cobertura, o atraso e o custo dependem do desenho e são os números que importam.</li>
<li><strong>A cobertura não é total.</strong> No pior cenário ficaram sem apontar: {escape(nao_apontados)}. São avisos cuja perda foi encoberta por um aviso posterior que chegou, ou que só a auditoria de 7 dias alcança. Nesses casos a loja costuma ter o status certo, mas o histórico fica incompleto.</li>
<li><strong>Os prazos de silêncio são suposição.</strong> Quanto tempo uma integração leva, ou quando um boleto vence, precisa ser calibrado com dado real.</li>
<li><strong>Ainda não foi testado contra o sandbox.</strong> O adaptador para a API real está escrito e o próximo passo é rodá-lo lá, inclusive para medir os horários reais das retentativas.</li>
</ul></div>
</section>

<section id="reproduzir">
<h2>Como reproduzir</h2>
<div class="card"><p>Python 3.10 ou mais novo, sem nenhuma dependência.</p>
<pre>python -m conferidor.demo
python -m unittest</pre>
<p>O primeiro comando roda os quatro cenários em poucos segundos e regrava este relatório. A semente é fixa, então os números se repetem.</p></div>
</section>
"""
    navegacao = [
        ("resultado", "Resultado"), ("pergunta", "A pergunta"), ("cenarios", "Os quatro cenários"),
        ("perda", "Quanto se perde"), ("conferidor", "Com o conferidor"), ("custo", "Custo de API"),
        ("suporte", "Lista para o suporte"), ("alarme-falso", "Alarme falso evitado"),
        ("limites", "Limites"), ("reproduzir", "Como reproduzir"),
    ]
    rodape = ("Simulação construída sobre documentação pública e dado sintético. Jonas Victor Vieira Silva.")
    return moldura("Conferidor de Webhooks", "Conferidor de webhooks",
                   "Gerado em " + datetime.now().strftime("%d/%m/%Y"), navegacao, corpo, rodape)
