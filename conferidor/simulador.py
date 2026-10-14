"""Bancada de teste: uma plataforma simulada e uma loja com endpoint instavel.

A plataforma aqui NAO e a Appmax. E a minha leitura da documentacao publica
dela, com dado 100% sintetico. Serve para o conferidor ter um gabarito:
como o simulador sabe quais avisos descartou, da para medir o que o
conferidor encontra, em quanto tempo e a que custo.

Todas as proporcoes abaixo sao SUPOSICAO declarada, nao dado da Appmax.
"""
import bisect
import math
import random
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from statistics import median

from .conciliador import Conciliador, EstadoPedido
from .contrato import (D, ESTAGIO, EXPIRACAO_PIX_S, H, LIMITE_REQ_POR_S, MIN, PRAZO_BOLETO_S,
                       QUOTA_MENSAL, STATUS_PAGO, horarios_das_tentativas)
from .registro import Registro

MIX_DE_METODO = (("pix", 0.45), ("cartao", 0.45), ("boleto", 0.10))
P_PIX_PAGO = 0.72
P_CARTAO_NAO_AUTORIZADO = 0.14
P_RECUSA_POR_RISCO = 0.03
P_BOLETO_PAGO = 0.45
P_PENDENTE_INTEGRACAO = 0.01
P_ESTORNO = 0.02
P_CHARGEBACK = 0.004
TICKET_MEDIANO_CENTAVOS = 18_000
AVISOS_DE_PAGAMENTO = {"order_paid_by_pix", "order_paid", "order_approved"}


@dataclass(frozen=True)
class Cenario:
    chave: str
    nome: str
    descricao: str
    quedas: tuple = ()            # (inicio, fim) em segundos: endpoint de webhook fora do ar
    leitura: str = "anterior"     # como contar os intervalos de retentativa
    pedidos: int = 20_000
    dias: int = 30
    p_lento: float = 0.005        # resposta acima de 5 s: a loja processa, a plataforma reenvia
    p_yampi: float = 0.06
    intervalo_varredura_s: int = 15 * MIN
    semente: int = 7


def cenarios():
    rng = random.Random(11)
    inicios = sorted(rng.uniform(0, 30 * D) for _ in range(6))
    oscilacoes = tuple((ini, ini + rng.uniform(3, 20) * MIN) for ini in inicios)
    madrugada = (11 * D + 2 * H, 11 * D + 10 * H)
    fim_de_semana = (19 * D + 20 * H, 21 * D + 2 * H)
    return [
        Cenario("normal", "Operação normal",
                "Seis oscilações de 3 a 20 minutos no mês e 0,5% de respostas lentas.",
                quedas=oscilacoes),
        Cenario("incidente", "Incidente de 8 horas",
                "O mesmo mês, mais uma madrugada com o endpoint de webhook fora do ar por 8 horas. "
                "Retentativas contadas da tentativa anterior (janela de 6h30).",
                quedas=oscilacoes + (madrugada,)),
        Cenario("incidente_4h", "Incidente de 8 horas, janela de 4 h",
                "O mesmo incidente, com as retentativas contadas da tentativa original (janela de 4 horas). "
                "A documentação não diz qual das duas leituras vale.",
                quedas=oscilacoes + (madrugada,), leitura="original"),
        Cenario("fim_de_semana", "Fim de semana sem plantão",
                "O endpoint cai no sábado à noite e só volta 30 horas depois.",
                quedas=oscilacoes + (fim_de_semana,)),
    ]


def _linha_do_tempo(metodo, t0, rng):
    """Eventos reais de um pedido: (instante, evento, status depois dele)."""
    if metodo == "pix":
        eventos = [(t0, "order_pix_created", "pendente")]
        if rng.random() >= P_PIX_PAGO:
            return eventos + [(t0 + EXPIRACAO_PIX_S, "order_pix_expired", "cancelado")]
        pago = t0 + rng.uniform(20, 25 * MIN)
        eventos += [(pago, "order_paid_by_pix", "aprovado"), (pago, "order_approved", "aprovado")]
    elif metodo == "cartao":
        if rng.random() < P_CARTAO_NAO_AUTORIZADO:
            return [(t0, "payment_not_authorized", "cancelado")]
        eventos = [(t0, "order_authorized", "autorizado")]
        if rng.random() < P_RECUSA_POR_RISCO:
            return eventos + [(t0 + rng.uniform(MIN, 20 * MIN), "order_refused_by_risk", "recusado_por_risco")]
        pago = t0 + rng.uniform(5, 10 * MIN)
        eventos += [(pago, "order_approved", "aprovado"), (pago, "order_paid", "aprovado")]
    else:
        eventos = [(t0, "order_billet_created", "pendente")]
        if rng.random() >= P_BOLETO_PAGO:
            return eventos + [(t0 + PRAZO_BOLETO_S, "order_billet_overdue", "pendente")]
        pago = t0 + rng.uniform(4 * H, PRAZO_BOLETO_S - H)
        eventos += [(pago, "order_paid", "aprovado"), (pago, "order_approved", "aprovado")]

    if rng.random() < P_PENDENTE_INTEGRACAO:
        travou = pago + rng.uniform(5 * MIN, H)
        eventos.append((travou, "order_pending_integration", "pendente_integracao"))
        integrado = travou + rng.uniform(2 * H, 30 * H)
    else:
        integrado = pago + rng.uniform(5 * MIN, 3 * H)
    eventos.append((integrado, "order_integrated", "integrado"))
    if rng.random() < P_ESTORNO:
        eventos.append((integrado + rng.uniform(H, 10 * D), "order_refund", "estornado"))
    elif metodo == "cartao" and rng.random() < P_CHARGEBACK:
        eventos.append((integrado + rng.uniform(5 * D, 25 * D),
                        "order_chargeback_in_treatment", "chargeback_em_tratativa"))
    return eventos


def gerar_pedidos(c, rng):
    fim = c.dias * D
    metodos, pesos = zip(*MIX_DE_METODO)
    pedidos = []
    for t0 in sorted(rng.uniform(0, fim) for _ in range(c.pedidos)):
        metodo = rng.choices(metodos, pesos)[0]
        pedidos.append({
            "order_id": 100_001 + len(pedidos),
            "t0": t0,
            "metodo": metodo,
            "origem": "yampi" if rng.random() < c.p_yampi else "propria",
            "valor": int(TICKET_MEDIANO_CENTAVOS * math.exp(rng.gauss(0, 0.7))),
            "eventos": [e for e in _linha_do_tempo(metodo, t0, rng) if e[0] <= fim],
        })
    return pedidos


class PlataformaSimulada:
    """Responde como a consulta de pedido: status atual e quando ele mudou."""

    def __init__(self, pedidos):
        self.agora = 0.0
        self._linhas = {p["order_id"]: p["eventos"] for p in pedidos}

    def status_em(self, order_id, instante):
        status, mudou_em = None, None
        for t, _, novo in self._linhas.get(order_id, ()):
            if t > instante:
                break
            if novo != status:
                status, mudou_em = novo, t
        return status, mudou_em

    def consultar_pedido(self, order_id):
        status, mudou_em = self.status_em(order_id, self.agora)
        return EstadoPedido(order_id, status, mudou_em) if status else None


def _fora_do_ar(t, quedas):
    return any(ini <= t < fim for ini, fim in quedas)


def entregar(c, pedidos, rng):
    """Aplica a politica de retentativa. Devolve o que chegou e o gabarito do que nao chegou."""
    fim = c.dias * D
    tentativas = horarios_das_tentativas(c.leitura)
    entregas, perdidos, suprimidos, em_aberto = [], [], 0, 0
    for p in pedidos:
        for t, evento, status in p["eventos"]:
            if p["origem"] == "yampi":
                suprimidos += 1
                continue
            chegou = aceito = False
            for atraso in tentativas:
                instante = t + atraso
                if instante > fim:
                    break
                if _fora_do_ar(instante, c.quedas):
                    continue
                entregas.append((instante, p["order_id"], evento, status))
                chegou = True
                if rng.random() >= c.p_lento:  # respondeu a tempo: a plataforma para de tentar
                    aceito = True
                    break
            if not chegou:
                if t + tentativas[-1] <= fim:
                    perdidos.append({"order_id": p["order_id"], "evento": evento, "t": t,
                                     "status": status, "valor": p["valor"]})
                elif not aceito:
                    em_aberto += 1
    return entregas, perdidos, suprimidos, em_aberto


def _indica_pagamento(status):
    return ESTAGIO.get(status, 0) >= ESTAGIO["aprovado"] and status not in ("cancelado", "recusado_por_risco")


def _percentil(valores, q):
    if not valores:
        return None
    ordenados = sorted(valores)
    return ordenados[min(len(ordenados) - 1, int(q * len(ordenados)))]


def rodar(c):
    inicio = time.perf_counter()
    rng = random.Random(c.semente)
    fim = c.dias * D
    pedidos = gerar_pedidos(c, rng)
    por_id = {p["order_id"]: p for p in pedidos}
    entregas, perdidos, suprimidos, em_aberto = entregar(c, pedidos, rng)

    plataforma = PlataformaSimulada(pedidos)
    registro = Registro()
    conciliador = Conciliador(registro, plataforma)

    fila = [(p["t0"], 0, i, p) for i, p in enumerate(pedidos)]
    fila += [(e[0], 1, i, e) for i, e in enumerate(entregas)]
    fila.sort(key=lambda item: item[:3])

    achados, i, t = [], 0, c.intervalo_varredura_s
    por_varredura = LIMITE_REQ_POR_S * c.intervalo_varredura_s
    while t <= fim:
        while i < len(fila) and fila[i][0] <= t:
            _, tipo, _, item = fila[i]
            if tipo == 0:
                registro.registrar_pedido(item["order_id"], item["metodo"], item["t0"],
                                          item["origem"], item["valor"])
            else:
                registro.registrar_evento(item[1], item[2], item[3], item[0])
            i += 1
        plataforma.agora = t
        achados.extend(conciliador.varrer(t, por_varredura))
        t += c.intervalo_varredura_s

    # --- sem o conferidor: o que a loja saberia so pelos avisos ---------------
    so_avisos = {}
    for _, order_id, _, status in entregas:
        if ESTAGIO[status] >= ESTAGIO.get(so_avisos.get(order_id), 0):
            so_avisos[order_id] = status
    proprios = [p for p in pedidos if p["origem"] != "yampi"]
    verdade = {p["order_id"]: plataforma.status_em(p["order_id"], fim)[0] for p in proprios}
    errados_sem = [p for p in proprios if so_avisos.get(p["order_id"]) != verdade[p["order_id"]]]
    invisiveis = [p for p in errados_sem
                  if verdade[p["order_id"]] in STATUS_PAGO and so_avisos.get(p["order_id"]) not in STATUS_PAGO]
    errados_com = [p for p in proprios
                   if registro.pedido(p["order_id"])["status"] != verdade[p["order_id"]]]

    # --- com o conferidor: comparacao com o gabarito --------------------------
    gabarito = {(x["order_id"], x["evento"]): x for x in perdidos}
    confirmaveis = {k for k, x in gabarito.items() if x["t"] <= fim - conciliador.espera_s - c.intervalo_varredura_s}
    apontados = {(a.order_id, a.evento) for a in achados if a.tipo == "aviso_perdido"}
    # Quando a loja soube que o pedido estava pago: por um aviso posterior que
    # chegou (por exemplo o de "integrado") ou pela consulta do conferidor.
    pagou_em = {}
    for x in perdidos:
        if x["evento"] in AVISOS_DE_PAGAMENTO:
            pagou_em.setdefault(x["order_id"], x["t"])
    soube_por_aviso, soube_pela_api = {}, {}
    for instante, order_id, _, status in entregas:
        if order_id in pagou_em and _indica_pagamento(status):
            soube_por_aviso[order_id] = min(instante, soube_por_aviso.get(order_id, instante))
    for order_id, status, _, soube_em in conciliador.sincronizacoes:
        if order_id in pagou_em and _indica_pagamento(status):
            soube_pela_api.setdefault(order_id, soube_em)
    atrasos, atrasos_por_metodo, atrasos_sem = [], defaultdict(list), []
    for order_id, pago in pagou_em.items():
        momentos = [m[order_id] for m in (soube_por_aviso, soube_pela_api) if order_id in m]
        if momentos:
            atrasos.append(min(momentos) - pago)
            atrasos_por_metodo[por_id[order_id]["metodo"]].append(atrasos[-1])
        if order_id in soube_por_aviso:
            atrasos_sem.append(soube_por_aviso[order_id] - pago)
    pagos_sem_aviso = {x["order_id"] for x in perdidos if x["evento"] in AVISOS_DE_PAGAMENTO}

    para_o_suporte = defaultdict(list)
    for a in achados:
        if a.tipo == "aviso_perdido":
            para_o_suporte[a.order_id].append(a.evento)
    lista = sorted(para_o_suporte.items(), key=lambda kv: -por_id[kv[0]]["valor"])[:10]

    criados = [p["t0"] for p in pedidos]
    consultas_ingenuas = sum(bisect.bisect_right(criados, h * H) for h in range(1, c.dias * 24 + 1))

    return {
        "chave": c.chave, "nome": c.nome, "descricao": c.descricao, "leitura": c.leitura,
        "janela_h": horarios_das_tentativas(c.leitura)[-1] / H,
        "horas_fora_do_ar": sum(f - i for i, f in c.quedas) / H,
        "pedidos": len(pedidos),
        "eventos_emitidos": sum(len(p["eventos"]) for p in pedidos),
        "duplicados_absorvidos": registro.duplicados,
        "avisos_perdidos": len(perdidos),
        "perdidos_por_evento": dict(Counter(x["evento"] for x in perdidos).most_common()),
        "pedidos_pagos_sem_aviso": len(pagos_sem_aviso),
        "valor_pago_sem_aviso": sum(por_id[o]["valor"] for o in pagos_sem_aviso),
        "errados_sem_conferidor": len(errados_sem),
        "invisiveis_sem_conferidor": len(invisiveis),
        "valor_invisivel_sem_conferidor": sum(p["valor"] for p in invisiveis),
        "errados_com_conferidor": len(errados_com),
        "apontados": len(apontados),
        "precisao": len(apontados & gabarito.keys()) / len(apontados) if apontados else None,
        "cobertura": len(apontados & confirmaveis) / len(confirmaveis) if confirmaveis else None,
        "nao_apontados_por_evento": dict(Counter(k[1] for k in confirmaveis - apontados).most_common()),
        "atraso_mediano_min": median(atrasos) / MIN if atrasos else None,
        "atraso_p95_min": _percentil(atrasos, 0.95) / MIN if atrasos else None,
        "atraso_mediano_por_metodo_min": {m: median(v) / MIN for m, v in sorted(atrasos_por_metodo.items())},
        "sem_conferidor_nunca_souberam": len(pagou_em) - len(atrasos_sem),
        "sem_conferidor_atraso_mediano_min": median(atrasos_sem) / MIN if atrasos_sem else None,
        "com_conferidor_ainda_sem_saber": len(pagou_em) - len(atrasos),
        "recuperados_por_retentativa": registro.recuperados_por_retentativa(),
        "consultas": conciliador.consultas,
        "consultas_pct_da_quota": conciliador.consultas / QUOTA_MENSAL,
        "consultas_varredura_ingenua": consultas_ingenuas,
        "pedidos_yampi": len(pedidos) - len(proprios),
        "avisos_suprimidos_yampi": suprimidos,
        "alarmes_falsos_evitados": sum(1 for a in achados if a.tipo == "supressao_intencional"),
        "avisos_ainda_em_retentativa": em_aberto,
        "para_o_suporte": [{"order_id": o, "eventos": evs, "valor": por_id[o]["valor"],
                            "status": verdade.get(o)} for o, evs in lista],
        "segundos": round(time.perf_counter() - inicio, 1),
    }
