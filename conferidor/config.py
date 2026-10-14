"""Configuracao local, lida do arquivo .env na raiz do projeto.

O .env fica so na sua maquina (esta no .gitignore). As credenciais nunca
entram no codigo nem aparecem na tela.
"""
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARQUIVO = RAIZ / ".env"


def ler():
    dados = {}
    if ARQUIVO.exists():
        for linha in ARQUIVO.read_text(encoding="utf-8").splitlines():
            if "=" in linha and not linha.lstrip().startswith("#"):
                chave, valor = linha.split("=", 1)
                dados[chave.strip()] = valor.strip()
    for chave in list(dados) + ["URL_PUBLICA", "APP_UUID", "APP_CLIENT_ID", "APP_CLIENT_SECRET"]:
        if os.environ.get(chave):
            dados[chave] = os.environ[chave]
    return dados


def exigir(*chaves):
    dados = ler()
    faltando = [c for c in chaves if not dados.get(c)]
    if faltando:
        raise SystemExit(f"Falta preencher no arquivo .env: {', '.join(faltando)}\nArquivo: {ARQUIVO}")
    return dados


def gravar(chave, valor):
    linhas = ARQUIVO.read_text(encoding="utf-8").splitlines() if ARQUIVO.exists() else []
    nova, achou = f"{chave}={valor}", False
    for i, linha in enumerate(linhas):
        if linha.split("=", 1)[0].strip() == chave:
            linhas[i], achou = nova, True
    if not achou:
        linhas.append(nova)
    ARQUIVO.write_text("\n".join(linhas) + "\n", encoding="utf-8")
