"""Aplicacao de exemplo: faz o papel da aplicacao de quem quer ser testado.

    python exemplos/app_exemplo.py                       saudavel: responde 200 na hora
    python exemplos/app_exemplo.py --modo lento          demora 7 s para responder
    python exemplos/app_exemplo.py --modo quebrado       responde 500 a todo aviso
    python exemplos/app_exemplo.py --modo estorno        responde 500 so aos avisos de estorno

Ouve em http://localhost:3000/webhook (troque com --porta). Use com o porteiro:
    python -m conferidor.receptor --repassar http://localhost:3000/webhook

Serve para ver o testador apontando problema numa aplicacao. Nao guarda nada.
"""
import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ESTORNOS = {"order_refund", "order_partial_refund"}


def criar_handler(modo, espera_s=7.0):
    class App(BaseHTTPRequestHandler):
        def do_POST(self):
            corpo = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            try:
                evento = json.loads(corpo or b"{}").get("event", "?")
            except json.JSONDecodeError:
                evento = "?"
            if modo == "lento":
                time.sleep(espera_s)
            quebrou = modo == "quebrado" or (modo == "estorno" and evento in ESTORNOS)
            codigo = 500 if quebrou else 200
            print(f"aplicação de exemplo ({modo}): {evento} -> {codigo}", flush=True)
            self.send_response(codigo)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *_):
            pass

    return App


def main():
    opcoes = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    opcoes.add_argument("--porta", type=int, default=3000)
    opcoes.add_argument("--modo", choices=("saudavel", "lento", "quebrado", "estorno"), default="saudavel")
    args = opcoes.parse_args()
    print(f"Aplicação de exemplo em http://localhost:{args.porta}/webhook, modo {args.modo}.", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.porta), criar_handler(args.modo)).serve_forever()


if __name__ == "__main__":
    main()
