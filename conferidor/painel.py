"""Painel em HTML do resultado real: o que a loja recebeu contra o que a API informa."""
from datetime import datetime
from html import escape

from .relatorio import NOMES_DE_EVENTO, moldura, reais, selo, selo_status

ORIGEM = {"webhook": "aviso da plataforma", "api": "conferidor"}
COR_DA_ORIGEM = {"webhook": "g", "api": "a"}


def gerar(linhas, consultas):
    sem_aviso = [x for x in linhas if x["faltando"]]
    pedidos = "".join(f"""
<tr><td><span class="ped {'r' if x['faltando'] else ''}">{x['order_id']}</span></td>
<td class=n>{reais(x['valor'])}</td>
<td>{selo_status(x['status_api'])}</td>
<td class=n>{x['recebidos']}</td>
<td>{selo(ORIGEM.get(x['fonte'], 'ainda não sabe'), COR_DA_ORIGEM.get(x['fonte'], 'r'))}</td>
<td>{escape(', '.join(NOMES_DE_EVENTO.get(e, e) + (' (perdido)' if t == 'aviso_perdido' else ' (pode chegar por retentativa)') for e, t in x['faltando'])) or 'nenhum'}</td></tr>""" for x in linhas)
    corpo = f"""<div class="sub"><strong>Medição real, no ambiente de teste (sandbox) da plataforma.</strong> Quatro pedidos com Pix de teste. Em dois deles o receptor de avisos foi desligado de propósito, para ver se o conferidor perceberia.</div>

<section id="reentrega">
<h2>A plataforma reenviou os avisos que falharam?</h2>
<div class="kpis">
<div class="kpi r"><div class="n">0</div><div class="l">reentregas recebidas</div></div>
<div class="kpi"><div class="n">12h45</div><div class="l">com o endereço no ar, esperando</div></div>
<div class="kpi"><div class="n">até 6h30</div><div class="l">é a janela de reentrega que a documentação descreve</div></div>
</div>
<div class="card"><p>Os avisos dos pedidos 27517 e 27518 falharam em 13/10/2026 às 17h55, porque o receptor estava desligado. Às 17h56 ele voltou ao ar, em modo de registro, e ficou disponível até 14/10 às 6h41. Nenhuma reentrega chegou.</p>
<p>A documentação descreve até quatro tentativas, a última em até 6h30. Limites desta observação: é o ambiente de teste, que pode se comportar diferente da produção, são dois pedidos, e a falha devolveu o erro 502, que a documentação trata como "servidor fora do ar" sem dizer se gera nova tentativa.</p></div>
</section>

<section id="como-ler">
<h2>Como ler</h2>
<div class="card"><ul>
<li><strong>Status na API:</strong> o que a plataforma de pagamento diz sobre o pedido quando perguntamos a ela. É a verdade.</li>
<li><strong>Avisos recebidos:</strong> quantos avisos automáticos (webhooks) sobre esse pedido chegaram ao sistema da loja.</li>
<li><strong>Como a loja soube:</strong> "aviso da plataforma" é o caminho normal. "conferidor" quer dizer que o aviso não chegou e a loja só ficou sabendo porque o conferidor perguntou à API.</li>
<li><strong>Avisos que não chegaram:</strong> os avisos que a loja deveria ter recebido para esse status e não recebeu.</li>
</ul></div>
</section>

<section id="visao-geral">
<h2>Resumo</h2><div class="kpis">
<div class="kpi"><div class="n">{len(linhas)}</div><div class="l">pedidos conferidos</div></div>
<div class="kpi r"><div class="n">{len(sem_aviso)}</div><div class="l">pedidos com aviso que não chegou</div></div>
<div class="kpi r"><div class="n">{reais(sum(x['valor'] for x in sem_aviso))}</div><div class="l">em pedidos que a loja só conhece pelo conferidor</div></div>
<div class="kpi"><div class="n">{consultas}</div><div class="l">consultas à API nesta conferência</div></div></div>
</section>

<section id="pedidos">
<h2>Pedido a pedido</h2>
<div class="tw lg"><table>
<thead><tr><th>Pedido</th><th class=n>Valor</th><th>Status na API</th><th class=n>Avisos recebidos</th>
<th>Como a loja soube</th><th>Avisos que não chegaram</th></tr></thead>
<tbody>{pedidos}</tbody></table></div>
</section>"""
    rodape = "Verde: os avisos chegaram. Vermelho: a plataforma informa um status que a loja não recebeu por aviso."
    return moldura("Conferidor: Sandbox", "Conferidor de webhooks: resultado no sandbox",
                   "",
                   [("visao-geral", "Visão geral"), ("pedidos", "Pedidos")], corpo, rodape)
