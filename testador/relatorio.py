"""Relatorio do testador em HTML, no mesmo formato do painel do conferidor."""
from html import escape

from conferidor.relatorio import NOMES_DE_EVENTO, moldura, selo

from .cenarios import NAO_CONFERIVEIS

COR = {"passou": "g", "falhou": "r", "inconclusivo": "w", "não executado": ""}
NOMES = {**NOMES_DE_EVENTO, "order_partial_refund": "estorno parcial"}


def _tempos(atrasos):
    if not atrasos:
        return "nenhum"
    return ", ".join(f"{NOMES.get(e, e)} em {s:.0f} s" for e, s in atrasos.items())


def _resistencia(dados):
    if not dados:
        return ""
    linhas = "".join(f"""
<tr><td>{escape(p['nome'])}</td>
<td>{selo('passou' if p['passou'] else ('atenção' if p.get('informativo') else 'falhou'), 'g' if p['passou'] else ('w' if p.get('informativo') else 'r'))}</td>
<td>{escape(p['detalhe'])}</td></tr>""" for p in dados["provas"])
    return f"""
<section id="resistencia">
<h2>Resistência do endereço de avisos</h2>
<div class="card"><p>O testador fez o papel da plataforma e mandou avisos sintéticos direto para o endereço do app,
em {escape(dados['executado_em'])}: repetidos, fora de ordem e de um tipo que o app talvez não trate. Pedidos fictícios
{escape(dados['pedidos_sinteticos'])}. Endereço testado: {escape(dados['alvo'])}. Mede só a resposta e o tempo; o que o app
faz por dentro não é visível daqui. Endereço local mede o app sem a internet no meio; pelo túnel, o tempo inclui a rede.</p></div>
<div class="tw lg"><table><thead><tr><th>Prova</th><th>Resultado</th><th>Detalhe</th></tr></thead>
<tbody>{linhas}</tbody></table></div>
</section>"""


def gerar(resultado, resistencia=None):
    linhas = resultado["linhas"]
    conta = {r: sum(1 for x in linhas if x["resultado"] == r) for r in COR}
    tabela = "".join(f"""
<tr><td>{escape(x['nome'])}</td>
<td class=n>{x['order_id'] or 'n/d'}</td>
<td>{selo(x['resultado'], COR[x['resultado']])}</td>
<td>{escape(_tempos(x['atrasos']))}</td>
<td>{escape('; '.join(x['motivos']) or 'nenhum')}</td></tr>""" for x in linhas)
    fora = "".join(f"<li><strong>{escape(item)}:</strong> {escape(porque)}</li>" for item, porque in NAO_CONFERIVEIS)
    custo = resultado.get("custo_resumo_usd") or 0.0
    corpo = f"""<div class="sub"><strong>Execução real no ambiente de teste (sandbox) da plataforma,
em {escape(resultado['executado_em'])}.</strong> Modo {escape(resultado['modo'])}. O app testado é o receptor
do próprio conferidor. Isto não é a homologação da plataforma e não dá aprovação: mostra o que dá para conferir de fora.</div>

<section id="resumo">
<h2>Resumo</h2>
<div class="kpis">
<div class="kpi g"><div class="n">{conta['passou']}</div><div class="l">cenários passaram</div></div>
<div class="kpi r"><div class="n">{conta['falhou']}</div><div class="l">cenários falharam</div></div>
<div class="kpi"><div class="n">{conta['inconclusivo']}</div><div class="l">inconclusivos (a plataforma ainda não processou)</div></div>
<div class="kpi"><div class="n">{conta['não executado']}</div><div class="l">não foram executados</div></div>
</div>
<div class="card"><p>{escape(resultado['resumo'])}</p>
<p style="font-size:12px;opacity:.75">Resumo escrito por: {escape(resultado['origem_resumo'])}.
Custo do resumo: US$ {custo:.6f}. Chamadas à API nesta rodada: {resultado['chamadas']}. O resultado de cada cenário foi decidido por regra fixa, antes do resumo.</p></div>
</section>

<section id="cenarios">
<h2>Cenário a cenário</h2>
<div class="tw lg"><table>
<thead><tr><th>Cenário</th><th class=n>Pedido</th><th>Resultado</th><th>Tempo até cada aviso</th><th>Motivo</th></tr></thead>
<tbody>{tabela}</tbody></table></div>
<p style="font-size:13px">Janela de espera pelos avisos: {resultado['espera_s'] / 60:.0f} min. Aviso que não chegou nessa janela
ainda pode chegar depois, por retentativa da plataforma. Só conta como falha quando a API mostra que o fato
aconteceu e o aviso não chegou; se a plataforma ainda não processou o fato, o cenário fica inconclusivo.</p>
</section>

{_resistencia(resistencia)}

<section id="fora">
<h2>O que não dá para conferir de fora</h2>
<div class="card"><ul>{fora}</ul></div>
</section>"""
    rodape = ("Projeto independente. Sem vínculo com a plataforma. Cenários tirados da lista pública de homologação;"
              " cartão 1x e 3x representam \"sem juros\" e \"com juros\" (suposição: os juros dependem da configuração da loja).")
    return moldura("Testador: Sandbox", "Testador de homologação: resultado no sandbox", "",
                   [("resumo", "Resumo"), ("cenarios", "Cenários"), ("resistencia", "Resistência"), ("fora", "Fora do alcance")], corpo, rodape)
