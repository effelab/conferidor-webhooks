"""Teste de resistencia do endereco de avisos (webhook) de um app.

Manda avisos sinteticos, no envelope da documentacao, para o endereco do SEU
app e mede como ele responde. Nao passa pela plataforma: e o testador fazendo
o papel dela, para provocar o que a documentacao diz que pode acontecer.

    Guia Webhooks: resposta em ate 5 segundos (o painel do app mostra 10),
    sucesso e qualquer 2xx, reentregas acontecem (idempotencia), e a ordem
    dos eventos nao e garantida.

Os pedidos usam numeros a partir de 900000000, para nao se misturar com
pedidos reais da loja de teste. So o codigo de resposta e o tempo sao
medidos: o que o app faz por dentro com o aviso nao e visivel daqui.
"""
import json
import random
import statistics
import time
import urllib.error
import urllib.request

LIMITE_DOC_S = 5      # guia Webhooks, "Politica de Retry"
LIMITE_PAINEL_S = 10  # o que o painel do app mostra (visto em 13/10/2026)
PRIMEIRO_PEDIDO_SINTETICO = 900_000_000


def envelope(evento, order_id, status, tipo="order"):
    return {"event": evento, "event_type": tipo, "site_id": "teste-resistencia", "app_id": "teste-resistencia",
            "client_key": None, "external_key": None,
            "data": {"order_id": order_id, "id": order_id, "status": status, "total": 123.0,
                     "payment_method": "pix"},
            "partner_merchant": {"merchant_email": "teste@example.com", "merchant_document_number": None,
                                 "merchant_phone": None}}


def enviar(url, corpo, timeout=LIMITE_PAINEL_S + 5, abrir=urllib.request.urlopen, relogio=time.perf_counter):
    """Devolve (codigo HTTP ou None, segundos). Se identifica como a plataforma se identifica."""
    requisicao = urllib.request.Request(url, json.dumps(corpo).encode(), {
        "Content-Type": "application/json", "User-Agent": "GuzzleHttp/7 (testador-de-resistencia)"})
    inicio = relogio()
    try:
        with abrir(requisicao, timeout=timeout) as r:
            return r.status, relogio() - inicio
    except urllib.error.HTTPError as erro:
        return erro.code, relogio() - inicio
    except (urllib.error.URLError, TimeoutError, OSError):
        return None, relogio() - inicio


def _ok(codigo):
    return codigo is not None and 200 <= codigo < 300


def rodar(url, quantos=20, envio=enviar, semente=None):
    sorteio = random.Random(semente)
    base = PRIMEIRO_PEDIDO_SINTETICO + sorteio.randrange(1_000_000)
    provas = []

    tempos, codigos = [], []
    for i in range(quantos):
        codigo, s = envio(url, envelope("order_pix_created", base + i, "pendente"))
        codigos.append(codigo)
        tempos.append(s)
    lentos = sum(1 for t in tempos if t > LIMITE_DOC_S)
    provas.append({
        "nome": f"Tempo de resposta ({quantos} avisos)",
        "passou": all(_ok(c) for c in codigos) and lentos == 0,
        "detalhe": (f"{sum(_ok(c) for c in codigos)} de {quantos} com 2xx; mediana {statistics.median(tempos):.2f} s,"
                    f" pior {max(tempos):.2f} s; {lentos} acima de {LIMITE_DOC_S} s (limite da documentação;"
                    f" o painel do app fala em {LIMITE_PAINEL_S} s)")})

    pedido = base + quantos
    primeira, _ = envio(url, envelope("order_paid_by_pix", pedido, "aprovado"))
    segunda, _ = envio(url, envelope("order_paid_by_pix", pedido, "aprovado"))
    provas.append({
        "nome": "Aviso repetido (reentrega)",
        "passou": _ok(primeira) and _ok(segunda),
        "detalhe": f"primeiro envio: {primeira}; repetição: {segunda}. Responder 2xx à repetição evita"
                   " retentativa à toa. Se o app processa duas vezes por dentro, isso não é visível daqui."})

    pedido += 1
    sequencia = [("order_integrated", "integrado"), ("order_approved", "aprovado"),
                 ("order_paid_by_pix", "aprovado"), ("order_pix_created", "pendente")]
    respostas = [envio(url, envelope(e, pedido, s))[0] for e, s in sequencia]
    provas.append({
        "nome": "Avisos fora de ordem",
        "passou": all(_ok(c) for c in respostas),
        "detalhe": "integrado, aprovado, pago e só depois Pix gerado: respostas "
                   + ", ".join(str(c) for c in respostas)})

    pedido += 1
    saque = envelope("withdraw_request_paid", None, None, tipo="withdraw")
    saque["data"] = {"withdraw_request_id": pedido, "net_value": 98400, "withdraw_tax": 367, "status": "paid"}
    novo, _ = envio(url, saque)
    provas.append({
        "nome": "Tipo de aviso que o app talvez não trate (saque)",
        "passou": _ok(novo),
        "informativo": True,
        "detalhe": f"resposta {novo}. Não é exigência da documentação; responder erro faz a plataforma retentar."})

    return {"alvo": url, "pedidos_sinteticos": f"{base} a {pedido}", "provas": provas}
