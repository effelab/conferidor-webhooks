"""Adaptador da API real, usado pelo conferidor e pelos comandos de sandbox.

ATENCAO: escrito a partir da documentacao publica e AINDA NAO TESTADO contra
o sandbox. Segue os guias de autenticacao, instalacao e rate limit e a
referencia "Consultar dados de um pedido".

Aponta para o SANDBOX por padrao. As credenciais vem do arquivo .env.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from . import config
from .conciliador import EstadoPedido
from .contrato import LIMITE_REQ_POR_S

SANDBOX = {
    "URL_AUTH": "https://auth.sandboxappmax.com.br",
    "URL_API": "https://api.sandboxappmax.com.br",
    "URL_PAINEL": "",  # o endereco da SUA loja de teste vem do .env (cada pessoa tem o seu)
}
# SUPOSICAO: `updated_at` vem em horario de Brasilia. A documentacao nao informa o fuso.
FUSO = timezone(timedelta(hours=-3))
# O identificador padrao do Python (Python-urllib) e barrado pela protecao na frente da API
# (HTTP 403, codigo 1010). O cliente se apresenta com nome proprio.
IDENTIFICACAO = "conferidor-webhooks/0.1"


def enderecos():
    dados = config.ler()
    return {chave: dados.get(chave, padrao) for chave, padrao in SANDBOX.items()}


class ErroDaAPI(RuntimeError):
    pass


class ClienteDaAPI:
    def __init__(self, client_id, client_secret):
        self.client_id, self.client_secret = client_id, client_secret
        self.urls = enderecos()
        self._token, self._expira_em, self._ultima = None, 0.0, 0.0

    @classmethod
    def do_aplicativo(cls):
        dados = config.exigir("APP_CLIENT_ID", "APP_CLIENT_SECRET")
        return cls(dados["APP_CLIENT_ID"], dados["APP_CLIENT_SECRET"])

    @classmethod
    def do_merchant(cls):
        dados = config.exigir("MERCHANT_CLIENT_ID", "MERCHANT_CLIENT_SECRET")
        return cls(dados["MERCHANT_CLIENT_ID"], dados["MERCHANT_CLIENT_SECRET"])

    def _autenticar(self):
        corpo = urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }).encode()
        resposta = self._abrir(urllib.request.Request(
            self.urls["URL_AUTH"] + "/oauth2/token", corpo,
            {"User-Agent": IDENTIFICACAO, "Accept": "application/json",
             "Content-Type": "application/x-www-form-urlencoded"}))
        self._token = resposta["access_token"]
        self._expira_em = time.time() + resposta.get("expires_in", 3600) - 60  # o token dura 1 hora

    @staticmethod
    def _abrir(requisicao):
        with urllib.request.urlopen(requisicao, timeout=30) as r:
            return json.load(r)

    def chamar(self, metodo, caminho, corpo=None, tentativas=3):
        """Devolve o JSON da resposta, ou None em 404."""
        for _ in range(tentativas):
            try:
                if time.time() >= self._expira_em:
                    self._autenticar()
                time.sleep(max(0.0, self._ultima + 1 / LIMITE_REQ_POR_S - time.time()))  # 5 req/s
                self._ultima = time.time()
                requisicao = urllib.request.Request(
                    self.urls["URL_API"] + caminho, method=metodo,
                    data=json.dumps(corpo).encode() if corpo is not None else None,
                    headers={"Authorization": f"Bearer {self._token}", "Accept": "application/json",
                             "Content-Type": "application/json", "User-Agent": IDENTIFICACAO})
                return self._abrir(requisicao)
            except urllib.error.HTTPError as erro:
                detalhe = erro.read().decode("utf-8", "replace")[:400]
                if erro.code == 404:
                    return None
                if erro.code == 401 and self._token:
                    self._expira_em = 0.0  # token vencido: autentica de novo
                elif erro.code == 429:
                    time.sleep(int(erro.headers.get("Retry-After") or 2))
                else:
                    raise ErroDaAPI(f"{metodo} {caminho} respondeu HTTP {erro.code}: {detalhe}") from None
        raise ErroDaAPI(f"{metodo} {caminho}: sem resposta valida depois de {tentativas} tentativas")

    def consultar_pedido(self, order_id):
        resposta = self.chamar("GET", f"/v1/orders/{int(order_id)}")
        if not resposta:
            return None
        pedido = resposta["data"]["order"]
        atualizado = pedido.get("updated_at")
        instante = (datetime.strptime(atualizado, "%Y-%m-%d %H:%M:%S").replace(tzinfo=FUSO).timestamp()
                    if atualizado else None)
        return EstadoPedido(int(pedido["id"]), pedido["status"], instante)
