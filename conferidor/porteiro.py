"""Porteiro: o receptor repassa cada aviso para a SUA aplicacao e anota como ela respondeu.

    python -m conferidor.receptor --repassar http://127.0.0.1:3000/webhook

A plataforma manda o aviso para o receptor (pelo tunel); o receptor grava, entrega
o mesmo corpo para a aplicacao e devolve a plataforma a resposta da aplicacao. Assim
a plataforma ve exatamente o que veria sem o porteiro no meio (inclusive erro e
demora), e o testador consegue julgar a aplicacao: recebeu? respondeu 2xx? a tempo?

O que fica fora do alcance: o que a aplicacao faz por dentro com o aviso.
"""
import time
import urllib.error
import urllib.request

LIMITE_DOC_S = 5           # guia Webhooks: responder em ate 5 segundos (o painel do app fala em 10)
TEMPO_MAXIMO_S = 15        # o porteiro desiste depois disso e responde 504 a plataforma


def repassar(url, corpo, cabecalhos, abrir=urllib.request.urlopen, relogio=time.perf_counter):
    """Entrega o aviso. Devolve (codigo HTTP ou None, segundos, erro ou None)."""
    enviados = {"Content-Type": cabecalhos.get("Content-Type", "application/json"),
                "User-Agent": cabecalhos.get("User-Agent", "porteiro")}
    url = url.replace("://localhost:", "://127.0.0.1:").replace("://localhost/", "://127.0.0.1/")  # Windows: evita ~2 s
    inicio = relogio()
    try:
        with abrir(urllib.request.Request(url, corpo, enviados), timeout=TEMPO_MAXIMO_S) as r:
            return r.status, relogio() - inicio, None
    except urllib.error.HTTPError as erro:
        return erro.code, relogio() - inicio, None
    except (urllib.error.URLError, TimeoutError, OSError) as erro:
        motivo = getattr(erro, "reason", erro)
        return None, relogio() - inicio, f"{type(motivo).__name__}: {motivo}"[:200]


def resposta_para_a_plataforma(codigo, erro):
    """O que o porteiro devolve a plataforma: a resposta da aplicacao, ou um erro de gateway."""
    if codigo is not None:
        return codigo
    return 504 if erro and "timed out" in erro.lower() else 502


def julgar_entrega(entrega):
    """Uma entrega, em palavras. Devolve (ok, texto)."""
    if entrega is None:
        return False, "não foi entregue à aplicação"
    codigo, segundos, erro = entrega["status_app"], entrega["segundos_app"], entrega["erro"]
    if codigo is None:
        return False, f"a aplicação não respondeu ({erro or 'sem resposta'})"
    if not 200 <= codigo < 300:
        return False, f"a aplicação respondeu {codigo}"
    if segundos > LIMITE_DOC_S:
        return False, f"a aplicação demorou {segundos:.1f} s (a documentação pede até {LIMITE_DOC_S} s)"
    return True, f"a aplicação respondeu {codigo} em {segundos:.2f} s"
