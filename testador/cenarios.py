"""A lista de cenarios que a plataforma publica para homologar apps.

Fonte: guia "Publicacao em producao", secao "Cenarios de teste avaliados":
compra, estorno total e estorno parcial, em cartao com juros, cartao sem
juros, Pix e boleto, testando com CPF e com CNPJ.

Os eventos esperados vem do guia "Webhooks", secao "Testar no sandbox"
(Pix e boleto) e "Fluxo Temporal dos Eventos" (cartao).

Projeto independente. Sem vinculo com a Appmax.
"""
from dataclasses import dataclass, field

MEIOS = ("pix", "cartao_avista", "cartao_parcelado", "boleto")
DOCUMENTOS = ("cpf", "cnpj")
ACOES = ("compra", "estorno_total", "estorno_parcial")

NOME_DO_MEIO = {
    "pix": "Pix",
    "boleto": "Boleto",
    # SUPOSICAO: a lista fala em "cartao com juros" e "sem juros". Quem define se
    # ha juros e a configuracao da loja; aqui o teste usa 1x e 3x.
    "cartao_avista": "Cartão 1x",
    "cartao_parcelado": "Cartão 3x",
}
NOME_DA_ACAO = {"compra": "Compra", "estorno_total": "Estorno total", "estorno_parcial": "Estorno parcial"}

# Sandbox: qualquer CPF ou CNPJ valido aprova Pix e boleto em cerca de 5 segundos.
CPF_DE_TESTE = "19100000000"  # o exemplo da propria documentacao


def _digito_cnpj(numeros):
    pesos = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2][-len(numeros):]
    resto = sum(int(n) * p for n, p in zip(numeros, pesos)) % 11
    return "0" if resto < 2 else str(11 - resto)


def cnpj_valido(base12):
    """Completa os dois digitos verificadores de um CNPJ."""
    primeiro = _digito_cnpj(base12)
    return base12 + primeiro + _digito_cnpj(base12 + primeiro)


CNPJ_DE_TESTE = cnpj_valido("112223330001")
DOCUMENTO = {"cpf": CPF_DE_TESTE, "cnpj": CNPJ_DE_TESTE}

# Cartao de teste "aprovado e capturado" (guia de cartao, secao "Cartoes de teste").
CARTAO_APROVADO = "4000000000000010"

_COMPRA = {
    "pix": ["order_pix_created", "order_paid_by_pix", "order_approved"],
    "boleto": ["order_billet_created", "order_paid", "order_approved"],
    "cartao": ["order_approved", "order_paid"],
}
_ESTORNO = {"estorno_total": "order_refund", "estorno_parcial": "order_partial_refund"}


def metodo(meio):
    """O metodo como o conferidor o conhece: pix, boleto ou cartao."""
    return "cartao" if meio.startswith("cartao") else meio


@dataclass(frozen=True)
class Cenario:
    meio: str
    documento: str
    acao: str
    eventos_da_compra: tuple = field(default=())
    evento_do_estorno: str = ""

    @property
    def id(self):
        return f"{self.meio}-{self.documento}-{self.acao}"

    @property
    def nome(self):
        return f"{NOME_DA_ACAO[self.acao]} · {NOME_DO_MEIO[self.meio]} · {self.documento.upper()}"

    @property
    def status_final_esperado(self):
        # SUPOSICAO: depois de estorno parcial o pedido continua pago; a doc nao diz o status.
        return "estornado" if self.acao == "estorno_total" else None


def montar(meios=MEIOS, documentos=DOCUMENTOS, acoes=ACOES):
    cenarios = []
    for meio in meios:
        if meio not in MEIOS:
            raise ValueError(f"meio desconhecido: {meio!r}. Use: {', '.join(MEIOS)}")
        for documento in documentos:
            if documento not in DOCUMENTOS:
                raise ValueError(f"documento desconhecido: {documento!r}. Use: cpf, cnpj")
            for acao in acoes:
                cenarios.append(Cenario(meio, documento, acao, tuple(_COMPRA[metodo(meio)]),
                                        _ESTORNO.get(acao, "")))
    return cenarios


# O que a lista de homologacao pede e um teste de fora nao consegue conferir.
NAO_CONFERIVEIS = [
    ("Código de rastreio", "A consulta de pedido não devolve o rastreio cadastrado."),
    ("Descrição na fatura do cartão (soft descriptor)", "A consulta de pedido não devolve esse campo."),
    ("IP do comprador", "Coletado pelo script da plataforma no navegador; a consulta de pedido não devolve."),
    ("URL de instalação", "A plataforma já oferece uma ferramenta própria para testar (guia \"Valide sua URL de validação\")."),
    ("Logo, descrição e e-mail de suporte do app", "Conferência visual, feita pela equipe da plataforma."),
]
