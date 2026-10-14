"""Testador de homologacao: roda a lista publica de cenarios no SEU sandbox.

    python -m testador rodar                          Pix e cartao 1x, CPF e CNPJ, compra e estornos
    python -m testador rodar --meios pix --acoes compra
    python -m testador rodar --meios pix,cartao_avista,cartao_parcelado,boleto
    python -m testador rejulgar                       confere de novo a ultima rodada, sem criar pedidos
    python -m testador resistencia --alvo URL         avisos repetidos, fora de ordem e tempo de resposta
    python -m testador relatorio                      regrava o HTML a partir da ultima rodada

Antes de rodar: tunel no ar, URL atualizada no painel do app e o receptor
ligado (python -m conferidor.receptor), como no conferidor. O testador cria
pedidos de teste na loja de sandbox e espera os avisos chegarem ao receptor.

Meios: pix, cartao_avista, cartao_parcelado, boleto. Documentos: cpf, cnpj.
Acoes: compra, estorno_total, estorno_parcial.
"""
import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime

from conferidor import config
from conferidor.api import ClienteDaAPI, ErroDaAPI
from conferidor.receptor import BANCO
from conferidor.registro import Registro

from . import cenarios as lista
from . import relatorio, resistencia, resumo
from .executor import ExecutorDireto
from .veredito import julgar

RESULTADO = config.RAIZ / "testador_resultado.json"
PAGINA = config.RAIZ / "testador.html"


def arquivos(nome=""):
    """(json, html) de uma rodada. Sem nome: testador_resultado.json e testador.html."""
    if not nome:
        return RESULTADO, PAGINA
    return config.RAIZ / f"testador_resultado_{nome}.json", config.RAIZ / f"testador_{nome}.html"
RESISTENCIA = config.RAIZ / "testador_resistencia.json"


def recebidos(order_id):
    """Avisos gravados pelo receptor para um pedido. Conexao nova, para ver o que ele acabou de gravar."""
    with sqlite3.connect(BANCO) as db:
        return {e: t for e, t in db.execute(
            "SELECT evento, recebido_em FROM eventos WHERE order_id=?", (order_id,))}


def esperados(cenario):
    return set(cenario.eventos_da_compra) | ({cenario.evento_do_estorno} - {""})


def esperar_avisos(pares, espera_s, relogio=time.time, dormir=time.sleep, ler=recebidos):
    """Espera ate todos os avisos esperados chegarem ou a janela fechar."""
    limite = relogio() + espera_s
    while True:
        faltam = sum(1 for c, e in pares if e["order_id"] and not esperados(c) <= set(ler(e["order_id"])))
        if not faltam or relogio() >= limite:
            return faltam
        print(f"  esperando avisos: {faltam} cenário(s) incompletos, {(limite - relogio()) / 60:.0f} min restantes",
              flush=True)
        dormir(15)


def rodar(args):
    cenarios = lista.montar(args.meios.split(","), args.documentos.split(","), args.acoes.split(","))
    api, registro = ClienteDaAPI.do_merchant(), Registro(BANCO)
    executor = ExecutorDireto(api, registro)
    print(f"{len(cenarios)} cenários. Confirme que o receptor está ligado e o túnel no ar.\n", flush=True)

    pares = []
    for i, cenario in enumerate(cenarios, 1):
        execucao = executor.executar(cenario)
        pares.append((cenario, execucao))
        situacao = f"erro na etapa {execucao['erro']}" if execucao["erro"] else "ok"
        print(f"[{i}/{len(cenarios)}] {cenario.nome}: pedido {execucao['order_id']} ({situacao})", flush=True)

    print("")
    esperar_avisos(pares, args.espera * 60)

    linhas = julgar_rodada(pares, api, executor, args.espera * 60)
    resultado = {"executado_em": datetime.now().strftime("%d/%m/%Y %H:%M"), "modo": "direto",
                 "espera_s": args.espera * 60, "chamadas": executor.chamadas, "linhas": linhas}
    gravar(resultado, args.sem_resumo, args.nome)


def julgar_rodada(pares, api, executor, espera_s):
    linhas = []
    for cenario, execucao in pares:
        status = None
        if execucao["order_id"]:
            executor.chamadas += 1
            try:
                estado = api.consultar_pedido(execucao["order_id"])
                status = estado.status if estado else None
            except ErroDaAPI as erro:
                status = f"erro ao consultar: {erro}"
        veredito = julgar(cenario, execucao, recebidos(execucao["order_id"]) if execucao["order_id"] else {},
                          status, espera_s)
        linhas.append({"id": cenario.id, "nome": cenario.nome, "order_id": execucao["order_id"],
                       "status_api": status, "execucao": execucao, **veredito})
    return linhas


def gravar(resultado, sem_resumo=False, nome=""):
    linhas = resultado["linhas"]
    saida, pagina = arquivos(nome)
    if sem_resumo:
        texto, origem, custo = resumo.texto_fixo(linhas), "texto fixo (--sem-resumo)", 0.0
    else:
        texto, origem, custo = resumo.escrever(linhas)
    resultado.update(resumo=texto, origem_resumo=origem, custo_resumo_usd=custo)
    saida.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    pagina.write_text(relatorio.gerar(resultado, _ler(RESISTENCIA)), encoding="utf-8")
    print("")
    for x in linhas:
        print(f"{x['resultado']:>14}  {x['nome']}" + (f"  ({'; '.join(x['motivos'])})" if x["motivos"] else ""))
    print(f"\nResumo ({origem}): {texto}")
    print(f"\n{resultado['chamadas']} chamadas à API. Relatório: {pagina}")


def rejulgar(args):
    """Confere de novo a ultima rodada: avisos que chegaram depois e o status atual na API. Nao cria pedido."""
    saida, _ = arquivos(args.nome)
    if not saida.exists():
        raise SystemExit(f"Rodada não encontrada: {saida.name}")
    resultado = json.loads(saida.read_text(encoding="utf-8"))
    if any("execucao" not in x for x in resultado["linhas"]):
        raise SystemExit("Esta rodada foi gravada por uma versão antiga, sem os horários de cada etapa. Rode de novo.")
    por_id = {c.id: c for c in lista.montar()}
    pares = [(por_id[x["id"]], x["execucao"]) for x in resultado["linhas"]]
    api = ClienteDaAPI.do_merchant()
    contador = ExecutorDireto(api, None)
    resultado["linhas"] = julgar_rodada(pares, api, contador, resultado["espera_s"])
    resultado["chamadas"] += contador.chamadas
    resultado["rejulgado_em"] = datetime.now().strftime("%d/%m/%Y %H:%M")
    gravar(resultado, args.sem_resumo, args.nome)


def _ler(arquivo):
    return json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.exists() else None


def provar_resistencia(args):
    print("Mandando avisos sintéticos para o endereço informado...")
    dados = resistencia.rodar(args.alvo, args.quantos)
    dados["executado_em"] = datetime.now().strftime("%d/%m/%Y %H:%M")
    dados["alvo"] = args.alvo
    RESISTENCIA.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    for prova in dados["provas"]:
        marca = "passou" if prova["passou"] else ("atenção" if prova.get("informativo") else "falhou")
        print(f"{marca:>8}  {prova['nome']}: {prova['detalhe']}")
    for saida in config.RAIZ.glob("testador_resultado*.json"):
        nome = saida.stem.removeprefix("testador_resultado").removeprefix("_")
        regravar(argparse.Namespace(nome=nome))


def regravar(args):
    saida, pagina = arquivos(args.nome)
    if not saida.exists():
        raise SystemExit(f"Rodada não encontrada: {saida.name}")
    resultado = json.loads(saida.read_text(encoding="utf-8"))
    pagina.write_text(relatorio.gerar(resultado, _ler(RESISTENCIA)), encoding="utf-8")
    print(f"Relatório regravado: {pagina}")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    opcoes = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    comandos = opcoes.add_subparsers(dest="comando", required=True)
    comando = comandos.add_parser("rodar")
    comando.add_argument("--meios", default="pix,cartao_avista")
    comando.add_argument("--documentos", default="cpf,cnpj")
    comando.add_argument("--acoes", default="compra,estorno_total,estorno_parcial")
    comando.add_argument("--espera", type=int, default=10, help="minutos de espera pelos avisos")
    comando.add_argument("--sem-resumo", action="store_true", help="não chama o modelo de linguagem")
    comando.add_argument("--nome", default="", help="nome da rodada, para não sobrescrever outra (ex.: boleto)")
    comando.set_defaults(acao=rodar)
    comando = comandos.add_parser("rejulgar", help="confere de novo a última rodada, sem criar pedidos")
    comando.add_argument("--sem-resumo", action="store_true")
    comando.add_argument("--nome", default="")
    comando.set_defaults(acao=rejulgar)
    comando = comandos.add_parser("resistencia", help="manda avisos sintéticos ao endereço do app")
    comando.add_argument("--alvo", required=True,
                         help="endereço de avisos do app; não use o receptor do conferidor, para não misturar pedidos fictícios no caderno")
    comando.add_argument("--quantos", type=int, default=20)
    comando.set_defaults(acao=provar_resistencia)
    comando = comandos.add_parser("relatorio")
    comando.add_argument("--nome", default="")
    comando.set_defaults(acao=regravar)
    args = opcoes.parse_args()
    try:
        args.acao(args)
    except ValueError as erro:
        raise SystemExit(str(erro))


if __name__ == "__main__":
    main()
