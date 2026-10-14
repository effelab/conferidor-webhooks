import io
import json
import unittest
from unittest import mock

from conferidor.api import ErroDaAPI
from conferidor.conciliador import EstadoPedido
from conferidor.registro import Registro
from testador import cenarios, relatorio, resistencia, resumo
from testador.__main__ import esperar_avisos
from testador.executor import ExecutorDireto
from testador.veredito import FALHOU, INCONCLUSIVO, NAO_EXECUTADO, PASSOU, julgar


class Relogio:
    def __init__(self):
        self.agora = 1000.0

    def __call__(self):
        return self.agora

    def dormir(self, s):
        self.agora += s


class ApiFalsa:
    """Responde no formato da documentacao. Paga na hora, a nao ser que mandem nao pagar."""

    def __init__(self, paga=True, recusa_estorno=False):
        self.paga, self.recusa_estorno = paga, recusa_estorno
        self.pedidos, self.proximo, self.feitas = {}, 500, []

    def chamar(self, metodo, caminho, corpo=None):
        self.feitas.append((metodo, caminho, corpo))
        if caminho == "/v1/customers":
            return {"data": {"customer": {"id": 7}}}
        if caminho == "/v1/orders":
            self.proximo += 1
            self.pedidos[self.proximo] = "pendente"
            return {"data": {"order": {"id": self.proximo, "status": "pendente"}}}
        if caminho == "/v1/payments/tokenize":
            return {"data": {"token": "tok"}}
        if caminho.startswith("/v1/payments/"):
            if self.paga:
                self.pedidos[corpo["order_id"]] = "aprovado"
            return {"data": {"order": {"id": corpo["order_id"]}}}
        if caminho == "/v1/orders/refund-request":
            if self.recusa_estorno:
                raise ErroDaAPI("POST /v1/orders/refund-request respondeu HTTP 400: regra de negocio")
            self.pedidos[corpo["order_id"]] = "estornado" if corpo["type"] == "total" else "aprovado"
            return {"data": {"message": "Refund request accepted"}}
        raise AssertionError(caminho)

    def consultar_pedido(self, order_id):
        return EstadoPedido(order_id, self.pedidos[order_id], None)


def cenario(meio="pix", acao="compra", documento="cpf"):
    return cenarios.montar([meio], [documento], [acao])[0]


class Cenarios(unittest.TestCase):
    def test_matriz_padrao(self):
        self.assertEqual(len(cenarios.montar(["pix", "cartao_avista"])), 12)
        self.assertEqual(len(cenarios.montar()), 24)

    def test_cnpj_de_teste_e_valido(self):
        self.assertEqual(cenarios.CNPJ_DE_TESTE, "11222333000181")

    def test_meio_desconhecido(self):
        with self.assertRaises(ValueError):
            cenarios.montar(["cheque"])

    def test_estorno_espera_o_evento_certo(self):
        self.assertEqual(cenario(acao="estorno_parcial").evento_do_estorno, "order_partial_refund")
        self.assertEqual(cenario(acao="estorno_total").status_final_esperado, "estornado")


class Executor(unittest.TestCase):
    def montar(self, **opcoes):
        relogio, registro = Relogio(), Registro()
        api = ApiFalsa(**opcoes)
        return api, registro, ExecutorDireto(api, registro, relogio, relogio.dormir, espera_pagamento_s=60)

    def test_compra_pix_registra_o_pedido_no_caderno(self):
        api, registro, executor = self.montar()
        execucao = executor.executar(cenario())
        self.assertIsNone(execucao["erro"])
        self.assertEqual(registro.pedido(execucao["order_id"])["origem"], "testador")
        self.assertEqual(api.feitas[-1][1], "/v1/payments/pix")

    def test_cartao_tokeniza_e_paga_em_3x(self):
        api, _, executor = self.montar()
        executor.executar(cenario("cartao_parcelado"))
        caminhos = [c for _, c, _ in api.feitas]
        self.assertEqual(caminhos[-2:], ["/v1/payments/tokenize", "/v1/payments/credit-card"])
        self.assertEqual(api.feitas[-1][2]["payment_data"]["credit_card"]["installments"], 3)
        self.assertEqual(api.feitas[-2][2]["payment_data"]["credit_card"]["number"], cenarios.CARTAO_APROVADO)

    def test_estorno_parcial_pede_metade(self):
        api, _, executor = self.montar()
        executor.executar(cenario(acao="estorno_parcial"))
        self.assertEqual(api.feitas[-1][2], {"order_id": 501, "type": "partial", "value": 6150})

    def test_nao_pede_estorno_se_o_pedido_nao_ficou_pago(self):
        api, _, executor = self.montar(paga=False)
        execucao = executor.executar(cenario(acao="estorno_total"))
        self.assertIn("não ficou pago", execucao["erro"])
        self.assertNotIn("/v1/orders/refund-request", [c for _, c, _ in api.feitas])

    def test_estorno_recusado_vira_erro_e_nao_quebra_a_rodada(self):
        _, _, executor = self.montar(recusa_estorno=True)
        execucao = executor.executar(cenario(acao="estorno_total"))
        self.assertTrue(execucao["erro"].startswith("estorno:"))


class Juiz(unittest.TestCase):
    execucao = {"erro": None, "pago_em": 100.0, "estornado_em": 200.0}

    def test_passou_com_os_tres_avisos_do_pix(self):
        recebidos = {"order_pix_created": 101, "order_paid_by_pix": 106, "order_approved": 106, "order_paid": 106}
        veredito = julgar(cenario(), self.execucao, recebidos, "aprovado", 600)
        self.assertEqual(veredito["resultado"], PASSOU)
        self.assertEqual(veredito["atrasos"]["order_paid_by_pix"], 6)
        self.assertEqual(veredito["extras"], ["order_paid"])

    def test_falhou_quando_a_api_diz_estornado_e_o_aviso_nao_veio(self):
        recebidos = {"order_pix_created": 101, "order_paid_by_pix": 106, "order_approved": 106}
        veredito = julgar(cenario(acao="estorno_total"), self.execucao, recebidos, "estornado", 600)
        self.assertEqual(veredito["resultado"], FALHOU)
        self.assertIn("order_refund não chegou em 10 min", veredito["motivos"][0])

    def test_estorno_em_analise_manual_e_inconclusivo(self):
        recebidos = {"order_pix_created": 101, "order_paid_by_pix": 106, "order_approved": 106}
        veredito = julgar(cenario(acao="estorno_total"), self.execucao, recebidos,
                          "pendente_integracao_em_analise", 600)
        self.assertEqual(veredito["resultado"], INCONCLUSIVO)
        self.assertIn("análise manual", veredito["motivos"][0])

    def test_estorno_parcial_sem_aviso_e_inconclusivo(self):
        recebidos = {"order_pix_created": 101, "order_paid_by_pix": 106, "order_approved": 106}
        veredito = julgar(cenario(acao="estorno_parcial"), self.execucao, recebidos, "aprovado", 600)
        self.assertEqual(veredito["resultado"], INCONCLUSIVO)

    def test_falhou_quando_pago_na_api_sem_aviso_de_pagamento(self):
        veredito = julgar(cenario(), self.execucao, {"order_pix_created": 101}, "aprovado", 600)
        self.assertEqual(veredito["resultado"], FALHOU)
        self.assertEqual(len(veredito["motivos"]), 2)

    def test_pix_ainda_pendente_e_inconclusivo(self):
        veredito = julgar(cenario(), self.execucao, {"order_pix_created": 101}, "pendente", 600)
        self.assertEqual(veredito["resultado"], INCONCLUSIVO)

    def test_falhou_com_status_errado_mesmo_com_aviso(self):
        recebidos = {"order_pix_created": 1, "order_paid_by_pix": 1, "order_approved": 1, "order_refund": 201}
        veredito = julgar(cenario(acao="estorno_total"), self.execucao, recebidos, "aprovado", 600)
        self.assertEqual(veredito["resultado"], FALHOU)
        self.assertEqual(veredito["atrasos"]["order_refund"], 1)

    def test_erro_de_execucao_nao_vira_falha_do_app(self):
        veredito = julgar(cenario(), {"erro": "pagamento: HTTP 422"}, {}, None, 600)
        self.assertEqual(veredito["resultado"], NAO_EXECUTADO)


class Espera(unittest.TestCase):
    def test_para_quando_todos_os_avisos_chegaram(self):
        relogio = Relogio()
        pares = [(cenario(), {"order_id": 1})]
        chegaram = {1: {"order_pix_created": 0, "order_paid_by_pix": 0, "order_approved": 0}}
        with mock.patch("builtins.print"):
            faltam = esperar_avisos(pares, 600, relogio, relogio.dormir, lambda o: chegaram[o])
        self.assertEqual(faltam, 0)
        self.assertEqual(relogio.agora, 1000.0)

    def test_desiste_quando_a_janela_fecha(self):
        relogio = Relogio()
        with mock.patch("builtins.print"):
            faltam = esperar_avisos([(cenario(), {"order_id": 1})], 60, relogio, relogio.dormir, lambda o: {})
        self.assertEqual(faltam, 1)
        self.assertGreaterEqual(relogio.agora, 1060)


class Resistencia(unittest.TestCase):
    def test_app_saudavel_passa_em_tudo(self):
        enviados = []

        def envio(url, corpo):
            enviados.append(corpo)
            return 200, 0.05

        dados = resistencia.rodar("http://app/webhook", quantos=3, envio=envio, semente=1)
        self.assertTrue(all(p["passou"] for p in dados["provas"]))
        self.assertEqual(len(enviados), 3 + 2 + 4 + 1)
        self.assertGreaterEqual(enviados[0]["data"]["order_id"], resistencia.PRIMEIRO_PEDIDO_SINTETICO)
        self.assertEqual(enviados[3], enviados[4])  # a reentrega e identica

    def test_resposta_lenta_e_erro_na_repeticao_falham(self):
        respostas = iter([(200, 6.0), (200, 0.1), (200, 0.1), (500, 0.1)] + [(200, 0.1)] * 10)
        dados = resistencia.rodar("http://app/webhook", quantos=3, envio=lambda u, c: next(respostas), semente=1)
        resultado = {p["nome"]: p["passou"] for p in dados["provas"]}
        self.assertFalse(resultado["Tempo de resposta (3 avisos)"])
        self.assertFalse(resultado["Aviso repetido (reentrega)"])
        self.assertTrue(resultado["Avisos fora de ordem"])

    def test_endereco_fora_do_ar_nao_quebra(self):
        import urllib.error

        def abrir(*_, **__):
            raise urllib.error.URLError("recusado")

        self.assertEqual(resistencia.enviar("http://x", {}, abrir=abrir)[0], None)


LINHAS = [{"nome": "Compra · Pix · CPF", "order_id": 1, "resultado": "passou", "motivos": [], "atrasos": {"order_approved": 5.2}},
          {"nome": "Estorno total · Pix · CPF", "order_id": 2, "resultado": "falhou",
           "motivos": ["o aviso order_refund não chegou em 10 min"], "atrasos": {}}]


class Resumo(unittest.TestCase):
    def test_sem_chave_usa_texto_fixo(self):
        with mock.patch("conferidor.config.ler", return_value={}):
            texto, origem, custo = resumo.escrever(LINHAS)
        self.assertIn("1 de 2 cenários passaram, 1 falharam, 0 ficaram inconclusivos", texto)
        self.assertTrue(origem.startswith("texto fixo"))
        self.assertEqual(custo, 0.0)

    def test_com_chave_usa_o_modelo_e_registra_o_custo(self):
        resposta = {"choices": [{"message": {"content": "Um passou — um falhou."}}], "usage": {"cost": 0.00012}}
        enviado = {}

        def abrir(requisicao, timeout):
            enviado.update(json.loads(requisicao.data))
            return io.BytesIO(json.dumps(resposta).encode())

        with mock.patch("conferidor.config.ler", return_value={"OPENROUTER_API_KEY": "CHAVE-SECRETA-123"}):
            texto, origem, custo = resumo.escrever(LINHAS, abrir)
        self.assertEqual(texto, "1 de 2 cenários passaram, 1 falharam, 0 ficaram inconclusivos e 0 não foram executados. Um passou , um falhou.")
        self.assertEqual(origem, resumo.MODELO_PADRAO)
        self.assertAlmostEqual(custo, 0.00012)
        self.assertNotIn("CHAVE-SECRETA-123", json.dumps(enviado))  # a chave nao vai no conteudo

    def test_provedor_fora_do_ar_nao_derruba_o_relatorio(self):
        import urllib.error

        def abrir(*_ , **__):
            raise urllib.error.URLError("sem rede")

        with mock.patch("conferidor.config.ler", return_value={"OPENROUTER_API_KEY": "CHAVE-SECRETA-123"}):
            texto, origem, _ = resumo.escrever(LINHAS, abrir)
        self.assertIn("1 de 2", texto)
        self.assertIn("provedor falhou", origem)


class Relatorio(unittest.TestCase):
    def test_gera_html_com_os_tres_blocos(self):
        html = relatorio.gerar({"executado_em": "14/10/2026 20:00", "modo": "direto", "espera_s": 600,
                                "chamadas": 30, "linhas": [{**x, "id": str(i)} for i, x in enumerate(LINHAS)],
                                "resumo": "texto", "origem_resumo": "texto fixo", "custo_resumo_usd": 0.0})
        for trecho in ("cenários passaram", "Cenário a cenário", "não dá para conferir de fora", "Código de rastreio"):
            self.assertIn(trecho, html)
        self.assertNotIn("—", html)


if __name__ == "__main__":
    unittest.main()
