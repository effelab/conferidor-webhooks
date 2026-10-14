# Primeiros passos: do zero ao primeiro teste

Este guia é para quem nunca usou o projeto. No fim, você terá rodado um teste de verdade no **seu** ambiente de teste (sandbox) da plataforma e visto o resultado "passou".

**Tempo estimado:** de 30 a 60 minutos na primeira vez (estimativa, não medido). Depois, um teste leva 1 minuto.

**Regra que não muda:** use só com o seu próprio app, no sandbox. Nunca aponte para a produção de outra pessoa. Nunca compartilhe o seu arquivo `.env`: ele guarda as suas chaves.

> Projeto independente, sem vínculo com a Appmax. Ele usa a documentação pública e o sandbox que a plataforma oferece a desenvolvedores.

---

## Como as peças se encaixam (leia uma vez)

```
Você cria um pedido de teste ──> a plataforma processa ──> ela manda um AVISO (webhook)
                                                                  │
                                         internet ──> TÚNEL ──> RECEPTOR (no seu computador)
                                                                  │
            CONFERIDOR / TESTADOR comparam os avisos que chegaram com o que a API da plataforma informa
```

- **Receptor:** a "caixa de correio" no seu computador. Recebe e anota cada aviso.
- **Túnel:** um programa gratuito que dá ao seu computador um endereço público na internet, para os avisos chegarem.
- **Conferidor:** aponta os pedidos pagos de que a loja não ficou sabendo.
- **Testador:** roda a lista de cenários de homologação (compra e estornos) e dá um selo para cada um.

Você vai precisar de **três janelas do PowerShell** abertas ao mesmo tempo: uma para o túnel, uma para o receptor e uma para os comandos.

---

## Passo 1: instalar o Python

1. Baixe em https://www.python.org/downloads/ (versão 3.10 ou mais nova).
2. **No Windows, na primeira tela do instalador, marque "Add python.exe to PATH".** Sem isso, os comandos não funcionam.
3. Confira, num PowerShell novo:
   ```
   python --version
   ```
   Deve aparecer algo como `Python 3.12.x`. No Mac, use `python3` no lugar de `python` em todos os comandos.

O projeto não precisa de nenhuma biblioteca extra.

## Passo 2: baixar o código

Na página do repositório no GitHub, clique em **Code > Download ZIP** e descompacte numa pasta, por exemplo `Documentos\conferidor-webhooks`. Ou, se você usa git:

```
git clone https://github.com/effelab/conferidor-webhooks.git
```

Daqui para a frente, **todo comando roda de dentro dessa pasta**. Ao abrir um PowerShell, entre nela primeiro (troque pelo seu caminho):

```
cd C:\Users\SEU_USUARIO\Documentos\conferidor-webhooks
```

## Passo 3: instalar e ligar o túnel (janela 1)

1. Instale o cloudflared. No Windows:
   ```
   winget install --id Cloudflare.cloudflared
   ```
   No Mac: `brew install cloudflared`. Feche e abra o PowerShell depois de instalar.
2. Ligue o túnel e **deixe esta janela aberta**:
   ```
   cloudflared tunnel --url http://localhost:8080
   ```
3. Na saída, procure um endereço terminado em **trycloudflare.com** (algo como `https://palavras-aleatorias.trycloudflare.com`). **Copie e guarde.** Vamos chamá-lo de SEU_TUNEL.

Atenção: **toda vez que o túnel reinicia, o endereço muda.** Aí é preciso atualizar o `.env` e o painel do app (veja "Problemas comuns").

## Passo 4: ligar o receptor (janela 2)

Abra outro PowerShell, entre na pasta e rode:

```
python -m conferidor.receptor
```

Deve aparecer `Escutando na porta 8080`. **Deixe esta janela aberta.** Cada aviso que chegar vai aparecer aqui, numa linha.

## Passo 5: criar a conta de desenvolvedor e o app no sandbox

1. Entre no painel de desenvolvedores da plataforma (`appstore.appmax.com.br`) e crie a sua conta de desenvolvedor. A documentação pede **CNPJ ativo**; MEI foi aceito no teste do autor. Não há cobrança, e o acesso ao sandbox é liberado na hora.
2. Crie um aplicativo do tipo **privado** (não passa por homologação). O formulário pede nome, e-mail de suporte, descrição curta e uma imagem quadrada de 1200 x 1200 px (PNG ou JPG).
3. Em eventos, marque **pelo menos os de pedido (Order) e de cliente (Customer)**. Sem isso, os avisos não chegam.
4. Na configuração de URLs do app, preencha com o SEU_TUNEL:

   | Campo | O que colocar |
   |---|---|
   | URL de webhook (avisos) | `SEU_TUNEL/webhook` |
   | URL do sistema (link que aparece para o lojista) | `SEU_TUNEL` |
   | URL de validação (usada na instalação) | `SEU_TUNEL/validacao` |

   Os nomes dos campos podem variar um pouco no painel. Salve as configurações.
5. Abra o app em **Consultar Aplicativo > Desenvolver** e anote: o **App UUID** (o identificador longo, com traços; **não** o número curto), o **Client ID** e o **Client Secret** do app.
6. Na seção **Sandbox** do app, anote o **endereço da loja de teste** (algo como `https://minhaloja.sandboxappmax.com.br`) e os **dados de acesso**: o e-mail e a **senha gerada**, que você copia pelo botão. Use essa senha, não a da sua conta.

## Passo 6: preencher o arquivo .env

1. Na pasta do projeto, copie o arquivo `.env.exemplo` e renomeie a cópia para `.env`.
2. Abra o `.env` no Bloco de Notas:
   ```
   notepad .env
   ```
3. Preencha, sem espaços e sem aspas:
   ```
   URL_PUBLICA=SEU_TUNEL
   APP_UUID=o App UUID do passo 5
   APP_CLIENT_ID=o Client ID do app
   APP_CLIENT_SECRET=o Client Secret do app
   URL_PAINEL=o endereço da loja de teste do passo 5
   ```
   Deixe `MERCHANT_CLIENT_ID` e `MERCHANT_CLIENT_SECRET` em branco: o próximo passo preenche sozinho.
4. Opcional: `OPENROUTER_API_KEY=` com uma chave da OpenRouter, para o resumo do relatório ser escrito por IA. Sem ela, tudo funciona igual e o resumo sai de um texto fixo.

## Passo 7: instalar o app na sua loja de teste (janela 3)

Abra um terceiro PowerShell, entre na pasta e rode:

```
python -m conferidor.sandbox instalar
```

O navegador abre uma página da plataforma. Entre na loja de teste com o e-mail e a **senha gerada** do passo 5 e **autorize a instalação**. Volte ao PowerShell: em alguns segundos aparece "Instalado". As credenciais da loja foram gravadas no `.env` (não aparecem na tela).

## Passo 8: conferir se está tudo pronto

```
python -m conferidor.sandbox verificar
```

Ele confere cada peça na ordem deste guia e mostra `[ok]` ou `[FALTA]`, com o que fazer. Resolva de cima para baixo até aparecer "Tudo pronto".

## Passo 9: o primeiro teste (1 minuto)

```
python -m testador rodar --meios pix --documentos cpf --acoes compra --espera 3 --nome rapido
```

Você vai ver:

1. `[1/1] Compra · Pix · CPF: pedido 12345 (ok)`: o pedido de teste foi criado.
2. `esperando avisos...`: a plataforma está mandando os avisos. Olhe a janela do receptor: eles aparecem lá.
3. `passou  Compra · Pix · CPF`: **todos os avisos chegaram. Funcionou.**

Para ver o relatório no navegador:

```
start testador_rapido.html
```

(No Mac: `open testador_rapido.html`.) O `--nome rapido` guarda este teste num arquivo próprio, sem apagar as rodadas maiores.

---

## Depois do primeiro teste

| Quero... | Comando | Quanto tempo |
|---|---|---|
| Rodar a lista completa: Pix e cartão, CPF e CNPJ, compra e estornos (12 cenários) | `python -m testador rodar` | cerca de 15 min |
| Boleto e cartão parcelado | `python -m testador rodar --meios boleto,cartao_parcelado --nome boleto_3x` | cerca de 15 min |
| Conferir de novo uma rodada, sem criar pedidos (ex.: estorno que estava em análise) | `python -m testador rejulgar` | segundos |
| Ver o conferidor achando aviso perdido | crie Pix com `python -m conferidor.sandbox pix --quantos 3`, **pare o receptor** (Ctrl+C na janela 2), crie mais 2, ligue o receptor de novo e rode `python -m conferidor.sandbox conferir` | 2 min |
| Abrir o painel do conferidor | `start painel.html` | segundos |

## O que cada resultado quer dizer

| Selo | Significado | O que fazer |
|---|---|---|
| **Passou** | Todos os avisos esperados chegaram e a API confirma o status | Nada |
| **Falhou** | A API mostra que o fato aconteceu, mas o aviso não chegou em 10 min | Veja se o receptor e o túnel estavam no ar; depois rode `rejulgar` |
| **Inconclusivo** | A plataforma ainda não terminou de processar (ex.: estorno de Pix em análise); a falta do aviso é esperada | Espere e rode `rejulgar` |
| **Não executado** | A plataforma recusou uma etapa (ex.: estorno de boleto pela API) | Não é falha sua; leia o motivo |

## Problemas comuns

| O que aparece | Causa provável | Solução |
|---|---|---|
| `python` não é reconhecido | Python fora do PATH | Reinstale marcando "Add python.exe to PATH", ou use `py` no lugar de `python` |
| `Falta preencher no arquivo .env: ...` | Campo vazio no `.env` | Preencha o campo indicado (passo 6) |
| Fica em "esperando avisos" até o fim | Túnel ou receptor desligado, URL errada no painel, ou eventos não marcados no app | Rode `verificar`; confira as URLs e os eventos do passo 5 |
| O túnel reiniciou | O endereço mudou | Copie o novo endereço para `URL_PUBLICA` no `.env` e para as três URLs no painel do app |
| `HTTP 422` no `instalar` | Foi usado o número curto do app em vez do App UUID | Use o identificador longo, com traços |
| Instalação falha com erro 500 | A plataforma não alcançou a URL de validação | Receptor e túnel precisam estar no ar durante o `instalar` |
| `503` ou `504` | O sandbox fica instável às vezes (a documentação avisa) | Espere alguns minutos e rode de novo |

## O que não fazer

- Não use com a produção nem com o app de outra pessoa.
- Não publique nem envie o seu `.env`.
- Não deixe um site público ligado às suas chaves: os avisos da plataforma não têm assinatura, e qualquer pessoa poderia mandar aviso falso.
