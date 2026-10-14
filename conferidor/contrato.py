"""Contrato publico da plataforma, como descrito na documentacao.

Tudo aqui vem de https://docs.appmax.com.br (guias "Webhooks", "Status de
pedidos", "Rate Limit" e a referencia "Consultar dados de um pedido").
Onde a documentacao nao e explicita, a escolha esta marcada como SUPOSICAO.

Projeto independente. Sem vinculo com a Appmax.
"""

MIN, H, D = 60, 3600, 86400

# --- Entrega de webhook (guia Webhooks, secao "Politica de Retry") ---------
TIMEOUT_WEBHOOK_S = 5
MAX_TENTATIVAS = 4
INTERVALOS_RETRY_S = (30 * MIN, 2 * H, 4 * H)  # "+30 minutos", "+2 horas", "+4 horas"


def horarios_das_tentativas(leitura="anterior"):
    """Segundos, a partir do evento, em que cada tentativa acontece.

    A documentacao lista os intervalos sem dizer a partir de que eles contam.
    As duas leituras possiveis dao janelas diferentes:
      "anterior": cada intervalo conta da tentativa anterior -> 0, 30min, 2h30, 6h30
      "original": cada intervalo conta da primeira tentativa -> 0, 30min, 2h, 4h
    """
    if leitura == "original":
        return (0, *INTERVALOS_RETRY_S)
    if leitura == "anterior":
        horarios, t = [0], 0
        for intervalo in INTERVALOS_RETRY_S:
            t += intervalo
            horarios.append(t)
        return tuple(horarios)
    raise ValueError(f"leitura desconhecida: {leitura!r}")


# O conferidor usa sempre a janela mais longa: so declara um aviso como
# perdido quando ele nao pode mais chegar em nenhuma das duas leituras.
JANELA_RETRY_S = horarios_das_tentativas("anterior")[-1]

# --- Limites da API (guia Rate Limit) ---------------------------------------
LIMITE_REQ_POR_S = 5
QUOTA_MENSAL = 100_000

# --- Status de pedido (guia Status de pedidos) -------------------------------
# Estagio no ciclo de vida. Como a ordem de chegada dos eventos nao e
# garantida, o status que a loja conhece e o do evento de maior estagio.
ESTAGIO = {
    "pendente": 1,
    "autorizado": 2,
    "aprovado": 3,
    "cancelado": 3,
    "recusado_por_risco": 3,
    "pendente_integracao": 4,
    "pendente_integracao_em_analise": 4,
    "integrado": 5,
    "estornado": 6,
    "chargeback_em_tratativa": 7,
    "chargeback_em_disputa": 8,
    "chargeback_perdido": 9,
    "chargeback_vencido": 9,
}
SEM_PROXIMO_EVENTO = {
    "cancelado", "recusado_por_risco", "estornado",
    "chargeback_perdido", "chargeback_vencido",
}
STATUS_PAGO = {
    "aprovado", "integrado", "pendente_integracao", "pendente_integracao_em_analise",
}

# Status que cada evento implica. O payload do webhook ja traz `data.status`,
# entao esta tabela e so a reserva para quando o campo nao vier. SUPOSICAO.
EVENTO_STATUS = {
    "order_pix_created": "pendente",
    "order_billet_created": "pendente",
    "order_billet_overdue": "pendente",
    "order_authorized": "autorizado",
    "order_authorized_with_delay": "autorizado",
    "order_approved": "aprovado",
    "order_paid": "aprovado",
    "order_paid_by_pix": "aprovado",
    "order_pending_integration": "pendente_integracao",
    "order_integrated": "integrado",
    "order_pix_expired": "cancelado",
    "payment_not_authorized": "cancelado",
    "order_refused_by_risk": "recusado_por_risco",
    "order_refund": "estornado",
    "order_chargeback_in_treatment": "chargeback_em_tratativa",
    "order_charge_back_gain": "chargeback_vencido",
}
EVENTOS_QUE_ENCERRAM = {"order_billet_overdue"}

EXPIRACAO_PIX_S = 30 * MIN  # o exemplo de payload mostra 15:05 -> 15:35
PRAZO_BOLETO_S = 3 * D      # SUPOSICAO: vencimento em 3 dias

# Eventos que a loja deveria ter recebido para um pedido estar em cada status
# (guia Webhooks, secao "Fluxo Temporal dos Eventos").
_ATE_O_STATUS = {
    "pix": {
        "pendente": ["order_pix_created"],
        "aprovado": ["order_pix_created", "order_paid_by_pix", "order_approved"],
        "cancelado": ["order_pix_created", "order_pix_expired"],
    },
    "boleto": {
        "pendente": ["order_billet_created"],
        "aprovado": ["order_billet_created", "order_paid", "order_approved"],
    },
    "cartao": {
        "autorizado": ["order_authorized"],
        "aprovado": ["order_authorized", "order_approved", "order_paid"],
        "cancelado": ["payment_not_authorized"],
        "recusado_por_risco": ["order_authorized", "order_refused_by_risk"],
    },
}
_DEPOIS_DE_APROVADO = {
    "integrado": ["order_integrated"],
    "pendente_integracao": ["order_pending_integration"],
    "estornado": ["order_refund"],
    "chargeback_em_tratativa": ["order_chargeback_in_treatment"],
}


def eventos_esperados(metodo, status, idade_do_pedido_s=0.0):
    """Eventos que ja deveriam ter chegado para um pedido neste status."""
    base = _ATE_O_STATUS.get(metodo, {})
    if status in base:
        eventos = list(base[status])
        boleto_vencido = idade_do_pedido_s > PRAZO_BOLETO_S + JANELA_RETRY_S
        if metodo == "boleto" and status == "pendente" and boleto_vencido:
            eventos.append("order_billet_overdue")
        return eventos
    if status in _DEPOIS_DE_APROVADO:
        return base.get("aprovado", []) + _DEPOIS_DE_APROVADO[status]
    return []


def prazo_de_silencio(metodo, status, n=0):
    """Quanto tempo a loja tolera sem novidade antes de consultar a API.

    E o que mantem o custo baixo: pedido saudavel, que recebe os avisos no
    prazo, nunca e consultado. So o silencio dispara consulta. Os prazos sao
    SUPOSICAO e devem ser calibrados com dado real. Devolve None quando nao
    ha mais nada a esperar.
    """
    if status is None:
        base = 10 * MIN
    elif status in SEM_PROXIMO_EVENTO:
        return None
    elif status == "integrado":
        # auditoria esparsa: estorno e chargeback chegam sem aviso previo
        return (7 * D, 21 * D)[n] if n < 2 else None
    elif status == "pendente":
        if metodo == "boleto":
            return 24 * H  # uma vez por dia, sem espacar: o conferidor para sozinho depois do vencimento
        base = EXPIRACAO_PIX_S + 15 * MIN if metodo == "pix" else 15 * MIN
    elif status == "autorizado":
        base = 45 * MIN
    elif status == "aprovado":
        base = 12 * H
    elif status.startswith("pendente_integracao"):
        base = 36 * H
    else:
        base = 15 * D
    return min(base * 2 ** n, 7 * D)


def metodo_pelo_evento(evento):
    if "pix" in evento:
        return "pix"
    if "billet" in evento:
        return "boleto"
    return "cartao"
