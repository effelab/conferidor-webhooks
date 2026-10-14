"""Modo direto: o testador faz cada compra e cada estorno pela API.

Usa o mesmo cliente da API e o mesmo caderno de avisos do conferidor. Os
avisos que chegam sao gravados pelo receptor (python -m conferidor.receptor)
no mesmo banco; o testador so le.

Apenas cartoes de teste publicados pela plataforma. Nunca cartao real.
"""
import time

from conferidor.api import ErroDaAPI
from conferidor.contrato import STATUS_PAGO

from .cenarios import CARTAO_APROVADO, DOCUMENTO, metodo

VALOR_CENTAVOS = 12300
ESPERA_PAGAMENTO_S = 180   # quanto esperar o pedido ficar pago antes de pedir o estorno
INTERVALO_CONSULTA_S = 5


class ExecutorDireto:
    def __init__(self, api, registro, relogio=time.time, dormir=time.sleep,
                 espera_pagamento_s=ESPERA_PAGAMENTO_S):
        self.api, self.registro = api, registro
        self.relogio, self.dormir = relogio, dormir
        self.espera_pagamento_s = espera_pagamento_s
        self.chamadas = 0

    def _chamar(self, metodo_http, caminho, corpo=None):
        self.chamadas += 1
        return self.api.chamar(metodo_http, caminho, corpo)

    def executar(self, cenario):
        """Roda um cenario. Devolve um dicionario com o que aconteceu, inclusive o erro."""
        execucao = {"cenario": cenario.id, "order_id": None, "pago_em": None,
                    "estornado_em": None, "erro": None, "etapa": "cliente"}
        documento = DOCUMENTO[cenario.documento]
        try:
            cliente = self._chamar("POST", "/v1/customers", {
                "first_name": "Cliente", "last_name": "Testador", "email": "cliente.testador@example.com",
                "phone": "51999999999", "ip": "127.0.0.1", "document_number": documento})
            execucao["etapa"] = "pedido"
            customer_id = cliente["data"]["customer"]["id"]
            pedido = self._chamar("POST", "/v1/orders", {
                "customer_id": customer_id,
                "products": [{"sku": "TESTADOR-001", "name": "Pedido de teste do testador",
                              "quantity": 1, "unit_value": VALOR_CENTAVOS, "type": "digital"}]})
            order_id = int(pedido["data"]["order"]["id"])
            execucao["order_id"] = order_id
            self.registro.registrar_pedido(order_id, metodo(cenario.meio), self.relogio(),
                                           origem="testador", valor_centavos=VALOR_CENTAVOS)
            self.registro.db.commit()

            execucao["etapa"] = "pagamento"
            execucao["pago_em"] = self.relogio()
            self._pagar(cenario, order_id, customer_id, documento)

            if cenario.acao != "compra":
                execucao["etapa"] = "esperando o pagamento ser confirmado"
                status = self._esperar_pago(order_id)
                if status not in STATUS_PAGO:
                    raise ErroDaAPI(f"o pedido não ficou pago em {self.espera_pagamento_s // 60} min"
                                    f" (status: {status}); estorno não pedido")
                execucao["etapa"] = "estorno"
                corpo = {"order_id": order_id, "type": "total"}
                if cenario.acao == "estorno_parcial":
                    corpo = {"order_id": order_id, "type": "partial", "value": VALOR_CENTAVOS // 2}
                execucao["estornado_em"] = self.relogio()
                self._chamar("POST", "/v1/orders/refund-request", corpo)
            execucao["etapa"] = "concluído"
        except (ErroDaAPI, KeyError, TypeError) as erro:
            execucao["erro"] = f"{execucao['etapa']}: {erro}"
        return execucao

    def _pagar(self, cenario, order_id, customer_id, documento):
        if cenario.meio in ("pix", "boleto"):
            self._chamar("POST", f"/v1/payments/{cenario.meio}", {
                "order_id": order_id, "payment_data": {cenario.meio: {"document_number": documento}}})
            return
        token = self._chamar("POST", "/v1/payments/tokenize", {"payment_data": {"credit_card": {
            "number": CARTAO_APROVADO, "cvv": "123", "expiration_month": "12",
            "expiration_year": "30", "holder_name": "Cliente Testador"}}})["data"]["token"]
        self._chamar("POST", "/v1/payments/credit-card", {
            "order_id": order_id, "customer_id": customer_id,
            "payment_data": {"credit_card": {
                "token": token, "holder_document_number": documento, "holder_name": "Cliente Testador",
                "installments": 3 if cenario.meio == "cartao_parcelado" else 1,
                "soft_descriptor": "TESTADOR"}}})

    def _esperar_pago(self, order_id):
        limite, status = self.relogio() + self.espera_pagamento_s, None
        while True:
            self.chamadas += 1
            estado = self.api.consultar_pedido(order_id)
            status = estado.status if estado else None
            if status in STATUS_PAGO or self.relogio() >= limite:
                return status
            self.dormir(INTERVALO_CONSULTA_S)
