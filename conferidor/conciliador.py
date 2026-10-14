"""O conferidor: cruza o que a loja recebeu com o que a plataforma informa.

A ideia inteira cabe em tres regras:
  1. Pedido que recebe os avisos no prazo nunca e consultado. O que dispara
     a consulta e o silencio (ver contrato.prazo_de_silencio).
  2. Na consulta, o status da API vira a verdade da loja na hora. Ela para
     de depender do aviso para saber que o cliente pagou.
  3. Um aviso so e declarado perdido depois que a janela de retentativas da
     plataforma se fechou. Antes disso ele ainda pode chegar sozinho.

Nenhum modelo de linguagem participa. E comparacao de conjuntos e relogio.
"""
from dataclasses import dataclass
from typing import Optional, Protocol

from .contrato import (D, JANELA_RETRY_S, MIN, PRAZO_BOLETO_S, eventos_esperados,
                       prazo_de_silencio)

ORIGENS_SEM_WEBHOOK = {"yampi"}  # guia Webhooks: "Comportamento intencional para pedidos originados da Yampi"


@dataclass(frozen=True)
class EstadoPedido:
    order_id: int
    status: str
    atualizado_em: Optional[float]  # `data.order.updated_at` da consulta de pedido


class FonteDeEstado(Protocol):
    def consultar_pedido(self, order_id: int) -> Optional[EstadoPedido]: ...


@dataclass(frozen=True)
class Achado:
    order_id: int
    tipo: str            # aviso_perdido | em_janela | supressao_intencional
    evento: str
    status_da_loja: Optional[str]
    status_na_api: str
    valor_centavos: int
    detectado_em: float


class Conciliador:
    def __init__(self, registro, fonte, janela_s=JANELA_RETRY_S, margem_s=5 * MIN,
                 respeitar_origens_sem_webhook=True):
        self.registro = registro
        self.fonte = fonte
        self.espera_s = janela_s + margem_s
        self.respeitar_origens = respeitar_origens_sem_webhook
        self.consultas = 0
        self.sincronizacoes = []  # (order_id, status, mudou_em, soube_em): o que a loja aprendeu pela API

    def varrer(self, agora, limite=None):
        """Confere os pedidos em silencio. Devolve so o que e novidade."""
        achados = []
        for pedido in self.registro.vencidos(agora, limite):
            achados.extend(self.conferir(pedido, agora))
        return achados

    def conferir(self, pedido, agora):
        order_id, metodo = pedido["order_id"], pedido["metodo"]
        estado = self.fonte.consultar_pedido(order_id)
        self.consultas += 1
        if estado is None:  # a plataforma nao conhece o pedido: tenta de novo em 7 dias
            self.registro.reagendar(order_id, agora + 7 * D, pedido["n"] + 1)
            return []

        sem_webhook = self.respeitar_origens and pedido["origem"] in ORIGENS_SEM_WEBHOOK
        mudou_em = estado.atualizado_em if estado.atualizado_em is not None else pedido["criado_em"]
        idade_do_pedido = agora - pedido["criado_em"]
        recebidos = self.registro.eventos_recebidos(order_id)
        faltando = [evento for evento in eventos_esperados(metodo, estado.status, idade_do_pedido)
                    if evento not in recebidos]

        divergia = pedido["status"] != estado.status
        if divergia:
            self.registro.sincronizar(order_id, estado.status)
            self.sincronizacoes.append((order_id, estado.status, mudou_em, agora))

        janela_fechada = agora - mudou_em >= self.espera_s
        if sem_webhook:
            tipo = "supressao_intencional"
        elif janela_fechada:
            tipo = "aviso_perdido"
        else:
            tipo = "em_janela"
        achados = [
            Achado(order_id, tipo, evento, pedido["status"], estado.status,
                   pedido["valor_centavos"], agora)
            for evento in faltando if self.registro.apontar(order_id, evento, tipo)
        ]

        n = 0 if divergia else pedido["n"] + 1
        silencio = prazo_de_silencio(metodo, estado.status, n)
        boleto_morto = (metodo == "boleto" and estado.status == "pendente"
                        and idade_do_pedido > PRAZO_BOLETO_S + self.espera_s)
        proximo = agora + silencio if silencio and not boleto_morto else None
        if faltando and not sem_webhook and not janela_fechada:
            confirmar_em = mudou_em + self.espera_s + 1  # volta para confirmar a perda
            proximo = min(proximo, confirmar_em) if proximo else confirmar_em
        self.registro.reagendar(order_id, proximo, n)
        return achados
