"""Comandos para usar o conferidor com um app proprio, no ambiente de sandbox.

    python -m conferidor.sandbox verificar          diz o que esta pronto e o que falta, passo a passo
    python -m conferidor.sandbox instalar           instala o app numa loja de teste
    python -m conferidor.sandbox pix                cria um pedido e paga com Pix de teste
    python -m conferidor.sandbox pix --quantos 5    cria cinco de uma vez
    python -m conferidor.sandbox pix --pendente     cria um Pix que fica sem pagamento
    python -m conferidor.sandbox conferir           cruza os avisos recebidos com a API

Rodado contra o sandbox real em 13, 14 e 16/10/2026. Se algum passo responder
diferente do esperado, o comando mostra a resposta da plataforma.
"""
import argparse
import sys
import time
import webbrowser

from . import config, painel
from .api import ClienteDaAPI, ErroDaAPI
from .conciliador import Conciliador
from .receptor import BANCO
from .registro import Registro
from .relatorio import NOMES_DE_EVENTO, reais

CPF_QUE_APROVA = "19100000000"   # sandbox: aprovado sozinho em cerca de 5 segundos
CPF_QUE_PENDE = "40827365144"    # sandbox: fica pendente, o pagamento nao e confirmado


def instalar(_):
    dados = config.exigir("APP_UUID", "APP_CLIENT_ID", "APP_CLIENT_SECRET", "URL_PUBLICA")
    base = dados["URL_PUBLICA"].rstrip("/")
    app = ClienteDaAPI.do_aplicativo()
    config.gravar("TOKEN_INSTALACAO", "")

    print("1/3  Pedindo a autorizacao de instalacao...")
    resposta = app.chamar("POST", "/app/authorize", {
        "app_id": dados["APP_UUID"],            # o UUID do app, nunca o ID numerico
        "external_key": "conferidor-teste",
        "url_callback": base + "/callback",
    })
    hash_de_autorizacao = resposta["data"]["token"]
    painel = app.urls["URL_PAINEL"].rstrip("/") or config.exigir("URL_PAINEL")["URL_PAINEL"].rstrip("/")
    link = f"{painel}/appstore/integration/{hash_de_autorizacao}"
    print("2/3  Abra este endereco, entre com a sua conta e autorize a instalacao:\n     " + link)
    webbrowser.open(link)

    print("     Esperando voce autorizar (ate 15 minutos; o receptor precisa estar rodando)...")
    token, limite = "", time.time() + 15 * 60
    while not token and time.time() < limite:
        time.sleep(2)
        token = config.ler().get("TOKEN_INSTALACAO", "")
    if not token:
        print("     O callback nao chegou. Tentando com o hash da autorizacao.")
        token = hash_de_autorizacao

    print("3/3  Gerando as credenciais da loja (a plataforma vai chamar /validacao no receptor)...")
    cliente = app.chamar("POST", "/app/client/generate", {"token": token})["data"]["client"]
    config.gravar("MERCHANT_CLIENT_ID", cliente["client_id"])
    config.gravar("MERCHANT_CLIENT_SECRET", cliente["client_secret"])
    print("Instalado. As credenciais da loja foram gravadas no .env (nao aparecem na tela).")


def pix(args):
    api, registro = ClienteDaAPI.do_merchant(), Registro(BANCO)
    documento = CPF_QUE_PENDE if args.pendente else CPF_QUE_APROVA
    for _ in range(args.quantos):
        cliente = api.chamar("POST", "/v1/customers", {
            "first_name": "Cliente", "last_name": "Teste", "email": "cliente.teste@example.com",
            "phone": "51999999999", "ip": "127.0.0.1"})
        pedido = api.chamar("POST", "/v1/orders", {
            "customer_id": cliente["data"]["customer"]["id"],
            "products": [{"sku": "TESTE-001", "name": "Pedido de teste do conferidor",
                          "quantity": 1, "unit_value": args.valor, "type": "digital"}]})
        order_id = int(pedido["data"]["order"]["id"])
        registro.registrar_pedido(order_id, "pix", time.time(), valor_centavos=args.valor)
        registro.db.commit()
        api.chamar("POST", "/v1/payments/pix", {
            "order_id": order_id, "payment_data": {"pix": {"document_number": documento}}})
        print(f"Pedido {order_id} criado, Pix de {reais(args.valor)} gerado"
              f" ({'vai ficar pendente' if args.pendente else 'deve aprovar em uns 5 segundos'}).")


def conferir(_):
    registro = Registro(BANCO)
    conciliador = Conciliador(registro, ClienteDaAPI.do_merchant())
    pedidos = registro.db.execute("SELECT * FROM pedidos ORDER BY order_id").fetchall()
    if not pedidos:
        raise SystemExit("Nenhum pedido registrado ainda. Crie um com: python -m conferidor.sandbox pix")
    agora, com_falta, linhas = time.time(), 0, []
    for pedido in pedidos:
        order_id = pedido["order_id"]
        conciliador.conferir(pedido, agora)
        recebidos = registro.eventos_recebidos(order_id)
        apontados = registro.db.execute(
            "SELECT evento, tipo FROM apontados WHERE order_id=?", (order_id,)).fetchall()
        faltando = [(e, t) for e, t in apontados if e not in recebidos]
        status_api = registro.pedido(order_id)["status"]
        linhas.append({"order_id": order_id, "valor": pedido["valor_centavos"], "status_api": status_api,
                       "recebidos": len(recebidos), "fonte": registro.pedido(order_id)["fonte_status"],
                       "faltando": faltando})
        print(f"\nPedido {order_id}  ({reais(pedido['valor_centavos'])})")
        origem = {"api": " (soube pelo conferidor, nao por aviso)", "webhook": " (soube por aviso)"}
        print(f"  a loja sabia ......... {pedido['status'] or 'nada, nenhum aviso chegou'}"
              f"{origem.get(pedido['fonte_status'], '') if pedido['status'] else ''}")
        print(f"  a API informa ........ {status_api}")
        print(f"  avisos recebidos ..... {len(recebidos)}")
        if faltando:
            com_falta += 1
            for evento, tipo in faltando:
                situacao = "PERDIDO, a janela de retentativa ja fechou" if tipo == "aviso_perdido" else "ainda pode chegar por retentativa"
                print(f"  faltando ............. {NOMES_DE_EVENTO.get(evento, evento)} ({evento}): {situacao}")
        else:
            print("  faltando ............. nada")
    registro.db.commit()
    arquivo = config.RAIZ / "painel.html"
    arquivo.write_text(painel.gerar(linhas, conciliador.consultas), encoding="utf-8")
    print("")
    print(f"Painel gravado em: {arquivo}")
    print(f"\n{len(pedidos)} pedidos conferidos, {com_falta} com aviso faltando, {conciliador.consultas} consultas a API.")


def verificar(_):
    """Confere a configuracao na ordem do guia PRIMEIROS-PASSOS.md e diz o proximo passo."""
    import urllib.request
    dados, faltas = config.ler(), 0

    def item(ok, texto, dica=""):
        nonlocal faltas
        faltas += 0 if ok else 1
        print(f"  [{'ok' if ok else 'FALTA'}] {texto}" + ("" if ok or not dica else f"\n         -> {dica}"))
        return ok

    def responde(url):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "verificar"}), timeout=10) as r:
                return r.status == 200
        except Exception:
            return False

    print("Configuração (arquivo .env):")
    item(config.ARQUIVO.exists(), "arquivo .env existe", "copie .env.exemplo para .env (passo 6 do guia)")
    for chave, dica in (("APP_UUID", "copie do painel do app, em Meus aplicativos > Exibir credenciais (passo 5)"),
                        ("APP_CLIENT_ID", "idem, credenciais do app (passo 5)"),
                        ("APP_CLIENT_SECRET", "idem, credenciais do app (passo 5)"),
                        ("URL_PAINEL", "endereço da sua loja de teste, por exemplo https://minhaloja.sandboxappmax.com.br (passo 5)"),
                        ("URL_PUBLICA", "endereço que o túnel mostrou, terminado em trycloudflare.com (passo 3)")):
        item(bool(dados.get(chave)), f"{chave} preenchido", dica)

    print("\nPeças ligadas:")
    item(responde("http://127.0.0.1:8080/"), "receptor ligado na porta 8080",
         "abra outro PowerShell, entre na pasta e rode: python -m conferidor.receptor (passo 4)")
    if dados.get("URL_PUBLICA"):
        item(responde(dados["URL_PUBLICA"].rstrip("/") + "/"), "túnel no ar e chegando ao receptor",
             "ligue o túnel (passo 3); se ele reiniciou, o endereço mudou: atualize URL_PUBLICA e as URLs no painel do app")

    print("\nLoja de teste:")
    if item(bool(dados.get("MERCHANT_CLIENT_ID") and dados.get("MERCHANT_CLIENT_SECRET")),
            "app instalado numa loja de teste", "rode: python -m conferidor.sandbox instalar (passo 7)"):
        try:
            ClienteDaAPI.do_merchant()._autenticar()
            item(True, "a plataforma aceitou as credenciais da loja")
        except Exception as erro:
            item(False, "a plataforma aceitou as credenciais da loja",
                 f"ela respondeu: {str(erro)[:120]}. Se você reinstalou o app, rode instalar de novo")

    print("\nOpcional:")
    print(f"  [{'ok' if dados.get('OPENROUTER_API_KEY') else 'sem'}] chave da OpenRouter para o resumo por IA"
          " (sem ela, o resumo sai de texto fixo)")
    print("\n" + ("Tudo pronto. Faça o teste rápido: python -m testador rodar --meios pix --documentos cpf --acoes compra --espera 3 --nome rapido"
                  if not faltas else f"{faltas} item(ns) faltando. Resolva de cima para baixo e rode verificar de novo."))
    if faltas:
        raise SystemExit(1)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    opcoes = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    comandos = opcoes.add_subparsers(dest="comando", required=True)
    comandos.add_parser("verificar").set_defaults(acao=verificar)
    comandos.add_parser("instalar").set_defaults(acao=instalar)
    comando_pix = comandos.add_parser("pix")
    comando_pix.add_argument("--quantos", type=int, default=1)
    comando_pix.add_argument("--valor", type=int, default=12300, help="em centavos")
    comando_pix.add_argument("--pendente", action="store_true")
    comando_pix.set_defaults(acao=pix)
    comandos.add_parser("conferir").set_defaults(acao=conferir)
    args = opcoes.parse_args()
    try:
        args.acao(args)
    except ErroDaAPI as erro:
        raise SystemExit(f"\nA plataforma respondeu diferente do esperado:\n  {erro}")


if __name__ == "__main__":
    main()
