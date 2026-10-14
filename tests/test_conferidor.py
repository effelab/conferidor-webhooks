import unittest

from conferidor.conciliador import Conciliador, EstadoPedido
from conferidor.contrato import H, JANELA_RETRY_S, MIN, horarios_das_tentativas
from conferidor.registro import Registro


class PlataformaDeTeste:
    def __init__(self):
        self.pedidos = {}

    def definir(self, order_id, status, atualizado_em):
        self.pedidos[order_id] = EstadoPedido(order_id, status, atualizado_em)

    def consultar_pedido(self, order_id):
        return self.pedidos.get(order_id)


def montar(**opcoes):
    registro, plataforma = Registro(), PlataformaDeTeste()
    return registro, plataforma, Conciliador(registro, plataforma, **opcoes)


class Contrato(unittest.TestCase):
    def test_as_duas_leituras_da_janela_de_retentativa(self):
        self.assertEqual(horarios_das_tentativas("original"), (0, 30 * MIN, 2 * H, 4 * H))
        self.assertEqual(horarios_das_tentativas("anterior"), (0, 30 * MIN, 2.5 * H, 6.5 * H))
        self.assertEqual(JANELA_RETRY_S, 6.5 * H)


class RegistroDeEventos(unittest.TestCase):
    def test_reentrega_nao_duplica(self):
        registro = Registro()
        registro.registrar_pedido(1, "pix", 0)
        self.assertTrue(registro.registrar_evento(1, "order_pix_created", "pendente", 1))
        self.assertFalse(registro.registrar_evento(1, "order_pix_created", "pendente", 99))
        self.assertEqual(registro.duplicados, 1)

    def test_aviso_fora_de_ordem_nao_rebaixa_o_status(self):
        registro = Registro()
        registro.registrar_pedido(1, "pix", 0)
        registro.registrar_evento(1, "order_integrated", "integrado", 10)
        registro.registrar_evento(1, "order_pix_created", "pendente", 20)
        self.assertEqual(registro.pedido(1)["status"], "integrado")

    def test_pedido_com_avisos_em_dia_nao_e_consultado(self):
        registro, plataforma, conciliador = montar()
        registro.registrar_pedido(1, "pix", 0)
        registro.registrar_evento(1, "order_pix_created", "pendente", 1)
        conciliador.varrer(20 * MIN)
        self.assertEqual(conciliador.consultas, 0)


class Conferencia(unittest.TestCase):
    def pix_pago_sem_aviso(self, **opcoes):
        registro, plataforma, conciliador = montar(**opcoes)
        registro.registrar_pedido(1, "pix", 0, valor_centavos=9900)
        registro.registrar_evento(1, "order_pix_created", "pendente", 1)
        plataforma.definir(1, "aprovado", 5 * MIN)
        return registro, plataforma, conciliador

    def test_a_loja_fica_sabendo_do_pagamento_antes_de_confirmar_a_perda(self):
        registro, _, conciliador = self.pix_pago_sem_aviso()
        achados = conciliador.varrer(50 * MIN)
        self.assertEqual(registro.pedido(1)["status"], "aprovado")
        self.assertEqual({a.tipo for a in achados}, {"em_janela"})

    def test_perda_so_e_confirmada_depois_da_janela(self):
        _, _, conciliador = self.pix_pago_sem_aviso()
        conciliador.varrer(50 * MIN)
        self.assertEqual(conciliador.varrer(5 * H), [])
        achados = conciliador.varrer(5 * MIN + JANELA_RETRY_S + 10 * MIN)
        self.assertEqual({a.tipo for a in achados}, {"aviso_perdido"})
        self.assertEqual({a.evento for a in achados}, {"order_paid_by_pix", "order_approved"})

    def test_aviso_recuperado_por_retentativa_nao_vira_alarme(self):
        registro, _, conciliador = self.pix_pago_sem_aviso()
        conciliador.varrer(50 * MIN)
        registro.registrar_evento(1, "order_paid_by_pix", "aprovado", 3 * H)
        registro.registrar_evento(1, "order_approved", "aprovado", 3 * H)
        self.assertEqual(conciliador.varrer(8 * H), [])
        self.assertEqual(registro.recuperados_por_retentativa(), 2)

    def test_cada_aviso_perdido_e_apontado_uma_vez_so(self):
        _, _, conciliador = self.pix_pago_sem_aviso()
        conciliador.varrer(8 * H)
        self.assertEqual(conciliador.varrer(30 * H), [])

    def test_pedido_da_yampi_nao_gera_alarme(self):
        registro, plataforma, conciliador = montar()
        registro.registrar_pedido(1, "pix", 0, origem="yampi")
        plataforma.definir(1, "aprovado", 5 * MIN)
        achados = conciliador.varrer(10 * H)
        self.assertEqual({a.tipo for a in achados}, {"supressao_intencional"})
        self.assertEqual(registro.pedido(1)["status"], "aprovado")

    def test_sem_a_regra_da_yampi_o_alarme_seria_falso(self):
        registro, plataforma, conciliador = montar(respeitar_origens_sem_webhook=False)
        registro.registrar_pedido(1, "pix", 0, origem="yampi")
        plataforma.definir(1, "aprovado", 5 * MIN)
        self.assertEqual({a.tipo for a in conciliador.varrer(10 * H)}, {"aviso_perdido"})


if __name__ == "__main__":
    unittest.main()
