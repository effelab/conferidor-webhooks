"""O juiz: decide, para cada cenario, o resultado. Regra fixa, sem modelo de linguagem.

A regra e a mesma do conferidor: so e falha quando a API mostra que o fato
aconteceu e o aviso dele nao chegou. Se a plataforma ainda nao processou o
fato (estorno em analise, por exemplo), a falta do aviso e esperada e o
cenario fica "inconclusivo", com o motivo.

Aviso que nao chegou na janela e reportado como "nao chegou em X min", nunca
como perdido: a plataforma ainda pode reenviar por retentativa.
"""
from conferidor.contrato import STATUS_PAGO

PASSOU, FALHOU, INCONCLUSIVO, NAO_EXECUTADO = "passou", "falhou", "inconclusivo", "não executado"

# Guia "Status de pedidos": "Aprovado que recebeu pedido de estorno antes de integrar. Analise manual."
ESTORNO_EM_ANALISE = "pendente_integracao_em_analise"
PAGO_OU_DEPOIS = STATUS_PAGO | {"estornado"}


def julgar(cenario, execucao, recebidos, status_api, espera_s):
    """recebidos: {evento: instante em que chegou} para o pedido do cenario."""
    if execucao.get("erro"):
        return {"resultado": NAO_EXECUTADO, "motivos": [execucao["erro"]], "atrasos": {}, "extras": []}

    minutos = f"{espera_s / 60:.0f} min"
    falhas, pendencias, atrasos = [], [], {}

    for evento in cenario.eventos_da_compra:
        if evento in recebidos:
            atrasos[evento] = max(0.0, recebidos[evento] - execucao["pago_em"])
        elif status_api in PAGO_OU_DEPOIS:
            falhas.append(f"a API informa {status_api}, mas o aviso {evento} não chegou em {minutos}")
        else:
            pendencias.append(f"o pagamento ainda não consta na API (status {status_api}); o aviso {evento} não era esperado ainda")

    evento = cenario.evento_do_estorno
    if evento:
        if evento in recebidos:
            atrasos[evento] = max(0.0, recebidos[evento] - execucao["estornado_em"])
        elif status_api == ESTORNO_EM_ANALISE:
            pendencias.append(f"a plataforma aceitou o pedido de estorno e o colocou em análise manual"
                              f" (status {status_api}); o aviso {evento} só vem depois")
        elif cenario.acao == "estorno_total" and status_api == "estornado":
            falhas.append(f"a API informa estornado, mas o aviso {evento} não chegou em {minutos}")
        elif cenario.acao == "estorno_total":
            pendencias.append(f"a plataforma ainda não processou o estorno (status {status_api});"
                              f" o aviso {evento} não chegou em {minutos}")
        else:
            pendencias.append(f"o aviso {evento} não chegou em {minutos}, e a API não mostra estorno parcial"
                              f" no status (continua {status_api}); não dá para saber se a plataforma já processou")

    if (cenario.status_final_esperado and status_api != cenario.status_final_esperado
            and evento in recebidos):
        falhas.append(f"o aviso {evento} chegou, mas a API informa {status_api}")

    esperados = set(cenario.eventos_da_compra) | ({evento} - {""})
    resultado = FALHOU if falhas else INCONCLUSIVO if pendencias else PASSOU
    return {"resultado": resultado, "motivos": falhas + pendencias, "atrasos": atrasos,
            "extras": sorted(set(recebidos) - esperados)}
