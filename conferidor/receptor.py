"""Receptor real: o endereco que a plataforma chama no seu computador.

    python -m conferidor.receptor               grava cada aviso e responde 200
    python -m conferidor.receptor --falhar      responde 500 aos avisos e anota cada tentativa

Atende tres coisas:
    POST /validacao   o "health check" da instalacao: responde com um external_id novo
    GET  /callback    para onde o navegador volta depois que voce autoriza a instalacao
    POST /webhook     os avisos de pedido (qualquer outro caminho tambem serve)

O modo --falhar existe para medir, no sandbox, os horarios reais das
retentativas: a documentacao lista +30 min, +2 h e +4 h sem dizer se contam
da primeira tentativa ou da anterior. As tentativas ficam em tentativas.csv.

A plataforma precisa alcancar este endereco, entao rode atras de um tunel
HTTPS publico. Use somente com o SEU app, no ambiente de sandbox.
"""
import argparse
import csv
import json
import time
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from . import config
from .registro import Registro

BANCO = config.RAIZ / "eventos.db"
TENTATIVAS = config.RAIZ / "tentativas.csv"


def _hora(instante):
    return datetime.fromtimestamp(instante).strftime("%H:%M:%S")


def criar_handler(registro, falhar):
    primeira_tentativa = {}

    class Handler(BaseHTTPRequestHandler):
        def _responder(self, codigo, corpo, tipo="application/json"):
            dados = corpo if isinstance(corpo, bytes) else json.dumps(corpo).encode()
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)

        def do_GET(self):
            url = urlparse(self.path)
            if url.path.rstrip("/") == "/callback":
                token = (parse_qs(url.query).get("token") or [""])[0]
                if token:
                    config.gravar("TOKEN_INSTALACAO", token)
                print(f"{_hora(time.time())}  callback da instalacao recebido"
                      f"{'' if token else ' SEM token na URL'}", flush=True)
                self._responder(200, "<h2>Autorizado. Pode voltar ao terminal.</h2>".encode(), "text/html; charset=utf-8")
            else:
                painel = config.RAIZ / "painel.html"  # o link do app no painel do lojista abre esta pagina
                if url.path in ("", "/") and painel.exists():
                    return self._responder(200, painel.read_bytes(), "text/html; charset=utf-8")
                self._responder(200, {"status": "no ar"})

        def do_POST(self):
            agora = time.time()
            corpo = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            try:
                aviso = json.loads(corpo or b"{}")
            except json.JSONDecodeError:
                aviso = {}

            if urlparse(self.path).path.rstrip("/") == "/validacao":
                external_id = str(uuid.uuid4())  # precisa ser um UUID novo a cada instalacao
                config.gravar("EXTERNAL_ID", external_id)
                for chave, destino in (("client_id", "MERCHANT_CLIENT_ID"), ("client_secret", "MERCHANT_CLIENT_SECRET")):
                    if aviso.get(chave):  # campos opcionais do health check
                        config.gravar(destino, aviso[chave])
                print(f"{_hora(agora)}  health check da instalacao respondido (external_id gravado no .env)", flush=True)
                return self._responder(200, {"external_id": external_id})

            dados = aviso.get("data") or {}
            evento, order_id = aviso.get("event", "?"), dados.get("order_id")
            if falhar:
                desde = agora - primeira_tentativa.setdefault((order_id, evento), agora)
                with open(TENTATIVAS, "a", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerow([datetime.fromtimestamp(agora).isoformat(timespec="seconds"),
                                            order_id, evento, round(desde)])
                print(f"{_hora(agora)}  {evento}  pedido {order_id}  +{desde / 60:.1f} min desde a 1a tentativa  -> 500", flush=True)
                return self._responder(500, {})
            novo = False
            if order_id is not None:
                novo = registro.registrar_evento(int(order_id), evento, dados.get("status"), agora, aviso)
                registro.db.commit()
            print(f"{_hora(agora)}  {evento}  pedido {order_id}  {'gravado' if novo else 'repetido, ignorado'}  -> 200", flush=True)
            self._responder(200, {})

        def log_message(self, *_):
            pass

    return Handler


def main():
    opcoes = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    opcoes.add_argument("--porta", type=int, default=8080)
    opcoes.add_argument("--falhar", action="store_true", help="responde 500 aos avisos e registra cada tentativa")
    opcoes.add_argument("--banco", default=str(BANCO), help="arquivo SQLite (padrao: eventos.db)")
    args = opcoes.parse_args()

    if args.falhar and not TENTATIVAS.exists():
        TENTATIVAS.write_text("recebido_em,order_id,evento,segundos_desde_a_primeira\n", encoding="utf-8")
    registro = None if args.falhar else Registro(args.banco)
    # uma thread so: o SQLite fica na thread que o abriu e o handler responde na hora
    servidor = HTTPServer(("0.0.0.0", args.porta), criar_handler(registro, args.falhar))
    print(f"Escutando na porta {args.porta}. Modo: {'falhar de proposito' if args.falhar else 'gravar e responder 200'}.", flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrado.")


if __name__ == "__main__":
    main()
