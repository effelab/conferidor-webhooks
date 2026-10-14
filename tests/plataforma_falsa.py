"""Plataforma falsa local, so para testar os comandos de sandbox sem conta real.

Responde no formato que a documentacao publica descreve. NAO e a Appmax e
nao prova que o sandbox real se comporta igual: serve para pegar defeito no
nosso codigo antes de gastar tempo no ambiente de verdade.

    python tests/plataforma_falsa.py 8899
"""
import json
import sys
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FUSO = timezone(timedelta(hours=-3))
ESTADO = {"callback": "", "validacao": "", "webhook": "", "pedidos": {}, "proximo": 5001}


def _post(url, corpo):
    requisicao = urllib.request.Request(url, json.dumps(corpo).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(requisicao, timeout=5) as r:
        return r.status, json.load(r)


def _avisar(order_id, eventos):
    for evento, status in eventos:
        try:
            _post(ESTADO["webhook"], {"event": evento, "event_type": "order",
                                      "data": {"order_id": order_id, "status": status, "total": 123.0}})
        except Exception:
            pass  # endpoint fora do ar: nesta versao falsa o aviso simplesmente se perde


class Handler(BaseHTTPRequestHandler):
    def _json(self, codigo, corpo):
        dados = json.dumps(corpo).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def do_GET(self):
        if self.path.startswith("/v1/orders/"):
            pedido = ESTADO["pedidos"].get(int(self.path.rsplit("/", 1)[1]))
            if not pedido:
                return self._json(404, {"error": {"message": "Order not found"}})
            return self._json(200, {"data": {"order": pedido}})
        self._json(200, {})

    def do_POST(self):
        bruto = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        corpo = json.loads(bruto) if bruto[:1] == b"{" else {}
        agora = datetime.now(FUSO).strftime("%Y-%m-%d %H:%M:%S")
        if self.path == "/oauth2/token":
            return self._json(200, {"access_token": "token-falso", "token_type": "Bearer", "expires_in": 3600})
        if self.path == "/app/authorize":
            base = corpo["url_callback"].rsplit("/", 1)[0]
            ESTADO.update(callback=corpo["url_callback"], validacao=base + "/validacao", webhook=base + "/webhook")
            # faz o papel do lojista: "autoriza" 1 segundo depois e volta para o callback
            threading.Timer(1, lambda: urllib.request.urlopen(ESTADO["callback"] + "?token=HASH-FALSO", timeout=5)).start()
            return self._json(200, {"data": {"token": "HASH-FALSO"}})
        if self.path == "/app/client/generate":
            codigo, resposta = _post(ESTADO["validacao"], {"app_id": 123, "client_id": "loja-falsa", "client_secret": "segredo-falso"})
            if codigo != 200 or len(resposta.get("external_id", "")) != 36:
                return self._json(500, {"error": {"message": "health check falhou"}})
            return self._json(200, {"data": {"client": {"client_id": "loja-falsa", "client_secret": "segredo-falso"}}})
        if self.path == "/v1/customers":
            return self._json(201, {"data": {"customer": {"id": 1}}})
        if self.path == "/v1/orders":
            order_id, ESTADO["proximo"] = ESTADO["proximo"], ESTADO["proximo"] + 1
            ESTADO["pedidos"][order_id] = {"id": order_id, "status": "pendente", "created_at": agora, "updated_at": agora}
            return self._json(201, {"data": {"order": {"id": order_id, "status": "pendente"}}})
        if self.path == "/v1/payments/pix":
            order_id = corpo["order_id"]
            eventos = [("order_pix_created", "pendente")]
            if corpo["payment_data"]["pix"]["document_number"] != "40827365144":
                ESTADO["pedidos"][order_id].update(status="integrado", updated_at=agora)
                eventos += [("order_paid_by_pix", "aprovado"), ("order_approved", "aprovado"), ("order_integrated", "integrado")]
            threading.Thread(target=_avisar, args=(order_id, eventos)).start()
            return self._json(200, {"data": {"order": {"id": order_id, "status": "pendente"}}})
        self._json(404, {})

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    porta = int(sys.argv[1]) if len(sys.argv) > 1 else 8899
    print(f"Plataforma falsa na porta {porta}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", porta), Handler).serve_forever()
