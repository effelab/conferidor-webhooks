"""Experimentos no sandbox do proprio app: deteccao, reentrega com erro 500 e reentrega com demora.

    python -m conferidor.experimento criar       cria os pedidos e marca o comportamento de cada um
    python -m conferidor.experimento avaliar     confere os pedidos e mede reentregas (pode repetir depois)

Precisa do receptor ligado (python -m conferidor.receptor) e do tunel no ar. O
comportamento de cada pedido fica em comportamento.json, que o receptor le a
cada aviso:

    deteccao: lotes alternados de pedidos normais e de pedidos "derrubar"
              (o receptor fecha a conexao; o tunel devolve 502, como servidor
              fora do ar). Mais alguns Pix que ficam pendentes de proposito.
              Pergunta: o conferidor acha todos os pagos sem aviso, e so eles?
    falhar:   o receptor responde 500 a todo aviso. Pergunta: a plataforma
              reenvia quando o servidor esta no ar mas responde erro?
    demorar:  o receptor grava, espera N segundos e responde 200. Pergunta: o
              limite de resposta e 5 s (documentacao) ou 10 s (painel)? Se
              passar do limite, a plataforma trata como falha e reenvia.

Use somente com o seu app, no sandbox.
"""
import argparse
import csv
import json
import sys
import time
from collections import defaultdict
from datetime import datetime

from . import config
from .api import ClienteDaAPI, ErroDaAPI
from .conciliador import Conciliador
from .receptor import BANCO, COMPORTAMENTO, EXPERIMENTOS
from .registro import Registro
from .sandbox import CPF_QUE_APROVA, CPF_QUE_PENDE

MANIFESTO = config.RAIZ / "experimentos.json"
VALOR = 12300

PLANO = (
    [("normal", 10), ("derrubar", 10)] * 2 + [("normal", 10), ("pendente", 5)]
    + [("falhar", 10), ("demorar:7", 10), ("demorar:12", 5)]
)


def _criar_pix(api, documento):
    cliente = api.chamar("POST", "/v1/customers", {
        "first_name": "Cliente", "last_name": "Experimento", "email": "cliente.experimento@example.com",
        "phone": "51999999999", "ip": "127.0.0.1"})
    pedido = api.chamar("POST", "/v1/orders", {
        "customer_id": cliente["data"]["customer"]["id"],
        "products": [{"sku": "EXP-001", "name": "Pedido de experimento", "quantity": 1,
                      "unit_value": VALOR, "type": "digital"}]})
    return int(pedido["data"]["order"]["id"])


def _marcar(order_id, regra):
    atual = json.loads(COMPORTAMENTO.read_text(encoding="utf-8")) if COMPORTAMENTO.exists() else {}
    atual[str(order_id)] = regra
    COMPORTAMENTO.write_text(json.dumps(atual, indent=1), encoding="utf-8")


def criar(_):
    api, registro = ClienteDaAPI.do_merchant(), Registro(BANCO)
    manifesto = json.loads(MANIFESTO.read_text(encoding="utf-8")) if MANIFESTO.exists() else {"pedidos": {}}
    manifesto.setdefault("criado_em", datetime.now().isoformat(timespec="seconds"))
    for grupo, quantos in PLANO:
        print(f"Lote {grupo}: {quantos} Pix", flush=True)
        for _ in range(quantos):
            order_id = _criar_pix(api, CPF_QUE_PENDE if grupo == "pendente" else CPF_QUE_APROVA)
            if grupo not in ("normal", "pendente"):
                _marcar(order_id, grupo)  # antes do pagamento: os avisos so saem depois dele
            registro.registrar_pedido(order_id, "pix", time.time(), origem="experimento", valor_centavos=VALOR)
            registro.db.commit()
            api.chamar("POST", "/v1/payments/pix", {
                "order_id": order_id,
                "payment_data": {"pix": {"document_number": CPF_QUE_PENDE if grupo == "pendente" else CPF_QUE_APROVA}}})
            manifesto["pedidos"][str(order_id)] = {"grupo": grupo, "criado_em": time.time()}
            MANIFESTO.write_text(json.dumps(manifesto, indent=1), encoding="utf-8")
        if grupo == "derrubar":
            time.sleep(20)  # o lote seguinte so comeca depois que os avisos deste ja sairam
    print(f"\n{len(manifesto['pedidos'])} pedidos no manifesto. Espere uns minutos e rode: python -m conferidor.experimento avaliar")


def _tentativas():
    contagem = defaultdict(list)
    if EXPERIMENTOS.exists():
        with open(EXPERIMENTOS, encoding="utf-8") as f:
            for linha in csv.DictReader(f):
                contagem[(linha["order_id"], linha["evento"])].append(linha)
    return contagem


def avaliar(_):
    if not MANIFESTO.exists():
        raise SystemExit("Nenhum experimento criado. Rode: python -m conferidor.experimento criar")
    manifesto = json.loads(MANIFESTO.read_text(encoding="utf-8"))
    registro, api = Registro(BANCO), ClienteDaAPI.do_merchant()
    conciliador = Conciliador(registro, api)
    agora, tentativas = time.time(), _tentativas()
    linhas = []
    for order_id, info in manifesto["pedidos"].items():
        pedido = registro.pedido(int(order_id))
        conciliador.conferir(pedido, agora)
        recebidos = registro.eventos_recebidos(int(order_id))
        apontados = [e for e, _ in registro.db.execute(
            "SELECT evento, tipo FROM apontados WHERE order_id=?", (int(order_id),)) if e not in recebidos]
        envios = {evento: len(v) for (o, evento), v in tentativas.items() if o == order_id}
        linhas.append({"order_id": int(order_id), "grupo": info["grupo"],
                       "status_api": registro.pedido(int(order_id))["status"],
                       "recebidos": sorted(recebidos), "apontados": apontados,
                       "envios_por_evento": envios,
                       "reenvios": sum(n - 1 for n in envios.values())})
    registro.db.commit()

    def grupo(nome):
        return [x for x in linhas if x["grupo"] == nome]

    pagos = {"aprovado", "integrado", "pendente_integracao"}
    derrubados = grupo("derrubar")
    normais = grupo("normal") + grupo("pendente")
    resumo = {
        "avaliado_em": datetime.now().isoformat(timespec="seconds"),
        "horas_desde_a_criacao": round((agora - manifesto["pedidos"][min(manifesto["pedidos"])]["criado_em"]) / 3600, 2),
        "consultas_a_api": conciliador.consultas,
        "deteccao": {
            "derrubados": len(derrubados),
            "derrubados_pagos_na_api": sum(1 for x in derrubados if x["status_api"] in pagos),
            "derrubados_apontados": sum(1 for x in derrubados if x["apontados"]),
            "normais_e_pendentes": len(normais),
            "normais_apontados_por_engano": sum(1 for x in normais if x["apontados"]),
            "derrubados_que_receberam_aviso_depois": sum(1 for x in derrubados if x["recebidos"]),
        },
        "reentrega": {g: {"pedidos": len(grupo(g)),
                          "avisos_distintos": sum(len(x["envios_por_evento"]) for x in grupo(g)),
                          "reenvios": sum(x["reenvios"] for x in grupo(g))}
                      for g in ("derrubar", "falhar", "demorar:7", "demorar:12")},
    }
    (config.RAIZ / "experimentos_resultado.json").write_text(
        json.dumps({"resumo": resumo, "pedidos": linhas}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(resumo, ensure_ascii=False, indent=1))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    opcoes = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    comandos = opcoes.add_subparsers(dest="comando", required=True)
    comandos.add_parser("criar").set_defaults(acao=criar)
    comandos.add_parser("avaliar").set_defaults(acao=avaliar)
    args = opcoes.parse_args()
    try:
        args.acao(args)
    except ErroDaAPI as erro:
        raise SystemExit(f"\nA plataforma respondeu diferente do esperado:\n  {erro}")


if __name__ == "__main__":
    main()
