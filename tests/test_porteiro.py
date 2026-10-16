import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "exemplos"))

import app_exemplo  # noqa: E402
from conferidor import porteiro  # noqa: E402
from conferidor.receptor import criar_handler  # noqa: E402
from conferidor.registro import Registro  # noqa: E402
from testador import cenarios  # noqa: E402
from testador.veredito import FALHOU, PASSOU, julgar  # noqa: E402


def subir(handler):
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    return servidor, f"http://127.0.0.1:{servidor.server_address[1]}"


def postar(url, corpo):
    requisicao = urllib.request.Request(url, json.dumps(corpo).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(requisicao, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as erro:
        return erro.code


def aviso(evento, order_id=501, status="aprovado"):
    return {"event": evento, "event_type": "order", "data": {"order_id": order_id, "status": status}}


class Repassar(unittest.TestCase):
    def test_aplicacao_saudavel_quebrada_e_fora_do_ar(self):
        ok, url_ok = subir(app_exemplo.criar_handler("saudavel"))
        ruim, url_ruim = subir(app_exemplo.criar_handler("quebrado"))
        try:
            corpo, cab = json.dumps(aviso("order_paid")).encode(), {"Content-Type": "application/json"}
            self.assertEqual(porteiro.repassar(url_ok + "/webhook", corpo, cab)[0], 200)
            self.assertEqual(porteiro.repassar(url_ruim + "/webhook", corpo, cab)[0], 500)
            codigo, _, erro = porteiro.repassar("http://127.0.0.1:9/webhook", corpo, cab)
            self.assertIsNone(codigo)
            self.assertTrue(erro)
            self.assertEqual(porteiro.resposta_para_a_plataforma(None, erro), 502)
        finally:
            ok.shutdown()
            ruim.shutdown()


class ReceptorComoPorteiro(unittest.TestCase):
    def test_grava_repassa_e_devolve_a_resposta_da_aplicacao(self):
        app, url_app = subir(app_exemplo.criar_handler("estorno"))
        registro = Registro()
        receptor, url_receptor = subir(criar_handler(registro, False, url_app + "/webhook"))
        try:
            self.assertEqual(postar(url_receptor + "/webhook", aviso("order_paid")), 200)
            self.assertEqual(postar(url_receptor + "/webhook", aviso("order_refund", status="estornado")), 500)
            entregas = registro.entregas(501)
            self.assertEqual(entregas["order_paid"]["status_app"], 200)
            self.assertEqual(entregas["order_refund"]["status_app"], 500)
            self.assertEqual(registro.eventos_recebidos(501), {"order_paid", "order_refund"})
        finally:
            receptor.shutdown()
            app.shutdown()


class JuizComAplicacao(unittest.TestCase):
    execucao = {"erro": None, "pago_em": 100.0, "estornado_em": 200.0}
    recebidos = {"order_pix_created": 101, "order_paid_by_pix": 106, "order_approved": 106}

    def entrega(self, status, segundos=0.05, erro=None):
        return {"status_app": status, "segundos_app": segundos, "erro": erro}

    def test_aplicacao_saudavel_passa(self):
        entregas = {e: self.entrega(200) for e in self.recebidos}
        cenario = cenarios.montar(["pix"], ["cpf"], ["compra"])[0]
        veredito = julgar(cenario, self.execucao, self.recebidos, "aprovado", 600, entregas)
        self.assertEqual(veredito["resultado"], PASSOU)
        self.assertTrue(all(a["ok"] for a in veredito["aplicacao"]))

    def test_aplicacao_que_responde_erro_reprova_o_cenario(self):
        entregas = {e: self.entrega(200) for e in self.recebidos}
        entregas["order_paid_by_pix"] = self.entrega(500)
        cenario = cenarios.montar(["pix"], ["cpf"], ["compra"])[0]
        veredito = julgar(cenario, self.execucao, self.recebidos, "aprovado", 600, entregas)
        self.assertEqual(veredito["resultado"], FALHOU)
        self.assertIn("a aplicação respondeu 500", veredito["motivos"][0])

    def test_aplicacao_lenta_reprova_e_diz_o_limite(self):
        entregas = {e: self.entrega(200, segundos=7.2) for e in self.recebidos}
        cenario = cenarios.montar(["pix"], ["cpf"], ["compra"])[0]
        veredito = julgar(cenario, self.execucao, self.recebidos, "aprovado", 600, entregas)
        self.assertEqual(veredito["resultado"], FALHOU)
        self.assertIn("demorou 7.2 s", veredito["motivos"][0])

    def test_sem_porteiro_nada_muda(self):
        cenario = cenarios.montar(["pix"], ["cpf"], ["compra"])[0]
        veredito = julgar(cenario, self.execucao, self.recebidos, "aprovado", 600)
        self.assertEqual(veredito["resultado"], PASSOU)
        self.assertEqual(veredito["aplicacao"], [])


if __name__ == "__main__":
    unittest.main()
