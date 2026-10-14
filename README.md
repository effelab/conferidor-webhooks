# Conferidor de webhooks

> **Projeto independente de Jonas Victor Vieira Silva. Sem vínculo, patrocínio ou autorização da Appmax.**
> Construído sobre a documentação pública, dado sintético e o sandbox do próprio app do autor. Não usa marca, logo nem dado de cliente da Appmax.

Um exercício: descobrir quais avisos de pagamento uma loja deixou de receber, cruzando o que chegou com o que a plataforma informa.

**Primeira vez aqui?** Siga o [guia de primeiros passos](PRIMEIROS-PASSOS.md): do zero (instalar o Python, criar a conta de desenvolvedor e o app no sandbox, ligar o túnel) até o primeiro teste. Para conferir a configuração a qualquer momento: `python -m conferidor.sandbox verificar`. Para só ver o que o conferidor faz, sem instalar nada, use a sessão Experimente do site.

## O ponto de partida

A [documentação pública de webhooks](https://docs.appmax.com.br/guides/webhooks) descreve o seguinte, nas seções "Política de Retry" e "Erros e Troubleshooting":

- Um aviso (webhook) é tentado quatro vezes. Cada tentativa espera até 5 segundos pela resposta.
- Depois da quarta falha, "o webhook é descartado permanentemente. Não há notificação ao desenvolvedor."
- A recuperação é "solicitar reenvio ao suporte".

Para pedir o reenvio, a loja precisa saber o que perdeu. O conferidor responde a essa pergunta.

## O que ele mostrou, na bancada de teste

Mês simulado de 20.000 pedidos, quatro cenários. Semente fixa, os números se repetem.

| Cenário | Avisos perdidos | Pedidos pagos sem aviso | Estado errado sem conferidor | Com conferidor | Cobertura | Atraso mediano | Consultas à API |
|---|---:|---:|---:|---:|---:|---:|---:|
| Operação normal | 0 | 0 | 0 | 0 | n/d | n/d | 17.361 |
| Incidente de 8 horas (janela de 6h30) | 116 | 25 | 42 | 0 | 98,3% | 13 min | 17.660 |
| Incidente de 8 horas (janela de 4 h) | 357 | 80 | 100 | 1 | 99,4% | 14 min | 17.713 |
| Fim de semana sem plantão, 30 horas | 2.122 | 459 | 580 | 4 | 99,6% | 13 min | 19.036 |

Quatro leituras:

1. **Em operação normal a perda foi zero.** A retentativa da plataforma resolve queda curta sozinha. O problema aparece quando a queda dura mais que a janela.
2. **A mesma queda de 8 horas perde 116 ou 357 avisos**, dependendo de os intervalos de retentativa contarem da tentativa anterior ou da primeira. A documentação não diz qual vale.
3. **A loja fica sabendo do pagamento em cerca de 13 minutos.** Sem o conferidor, no incidente de 8 horas, 6 dos 25 pedidos pagos terminam o mês sem a loja saber, e os outros 19 ela só descobre umas 8 horas depois, por um aviso posterior. No fim de semana sem plantão, 412 de 459 nunca chegam ao conhecimento dela.
4. **O custo cabe na quota.** Entre 17% e 19% das 100.000 requisições mensais documentadas. Conferir todos os pedidos de hora em hora custaria 7,2 milhões de chamadas, 72 vezes a quota.

O relatório completo, com gráficos, está em `relatorio.html`.

## Como rodar

Python 3.10 ou mais novo. Nenhuma dependência.

```bash
python -m conferidor.demo
```

```bash
python -m unittest
```

O primeiro comando roda os quatro cenários em poucos segundos e regrava `relatorio.html` e `resultado.json`.

## Como funciona

Três regras, todas em `conferidor/conciliador.py`:

1. **Pedido que recebe os avisos no prazo nunca é consultado.** O que dispara a consulta é o silêncio: um Pix sem novidade 45 minutos depois de gerado, por exemplo. É isso que mantém o custo baixo.
2. **Na consulta, o status da API vira a verdade da loja.** Ela libera o pedido sem esperar o aviso.
3. **Um aviso só é declarado perdido depois que a janela de retentativa fechou.** Antes disso ele ainda pode chegar sozinho, e o conferidor volta para confirmar.

Nenhum modelo de linguagem participa. É comparação de conjuntos e relógio.

| Arquivo | Papel |
|---|---|
| `conferidor/contrato.py` | O contrato público: status, eventos, política de retentativa, limites. Cada suposição está marcada |
| `conferidor/registro.py` | O que a loja sabe. SQLite, só inserção, gravação idempotente |
| `conferidor/conciliador.py` | O conferidor. Fala com uma interface, então serve para a bancada e para a API real |
| `conferidor/simulador.py` | A bancada: plataforma simulada, endpoint instável e o gabarito do que foi descartado |
| `conferidor/relatorio.py` | Gera o relatório em HTML |
| `conferidor/receptor.py` | Receptor real de webhook, com um modo que falha de propósito para medir as retentativas |
| `conferidor/api.py` | Adaptador da API real. **Ainda não testado contra o sandbox** |
| `conferidor/sandbox.py` | Comandos para instalar o app, criar Pix de teste e conferir, no sandbox |

## Detalhes do contrato que o código respeita

- **Ordem não garantida.** O status que a loja conhece é o do evento de maior estágio no ciclo de vida, não o do último a chegar.
- **Reentrega.** A chave `(order_id, evento)` torna a gravação idempotente.
- **Resposta em menos de 5 segundos.** O receptor grava e responde, sem processar nada pesado.
- **Limite de 5 requisições por segundo e quota de 100.000 por mês.** O adaptador espaça as chamadas e respeita o `Retry-After`.
- **Pedidos originados na Yampi não geram webhook, de propósito.** O conferidor acompanha esses pedidos por consulta e não dá alarme. No mês simulado isso evita 3.870 alarmes falsos.
- **Valores no webhook vêm em reais com decimal. Na API, em centavos.**

## Limites, ditos antes que perguntem

- **É simulação.** A plataforma da bancada é a minha leitura da documentação, não o sistema real. Volume, mix de meios de pagamento e taxas de aprovação são suposições declaradas em `simulador.py`.
- **A precisão de 100% não prova muito.** O conferidor e o simulador seguem a mesma leitura do contrato, então era esperado que concordassem. Cobertura, atraso e custo dependem do desenho e são os números que importam.
- **A cobertura não é total.** Ficam de fora avisos cuja perda foi encoberta por um aviso posterior que chegou, ou que só a auditoria de 7 dias alcança, como um estorno em pedido já integrado. Nesses casos a loja costuma ter o status certo, mas o histórico fica incompleto.
- **Os prazos de silêncio são suposição** e precisam ser calibrados com dado real.
- **O boleto é conferido uma vez por dia**, por custo. O atraso mediano nele fica entre 8 e 15 horas, contra 12 a 30 minutos em Pix e cartão.
- **Ainda não rodou contra o sandbox.**

## Rodando contra o sandbox, com um app próprio

Os comandos abaixo rodaram contra o sandbox real da plataforma em 13 e 14/10/2026, com um app privado e uma loja de teste do autor.

1. Copie `.env.exemplo` para `.env` e preencha o endereço público do túnel e os dados do aplicativo.
2. Deixe o receptor rodando: `python -m conferidor.receptor`
3. Instale o app numa loja de teste: `python -m conferidor.sandbox instalar`
4. Crie pedidos com Pix de teste: `python -m conferidor.sandbox pix --quantos 3`
5. Pare o receptor, crie mais pedidos, e confira: `python -m conferidor.sandbox conferir`

O passo 5 é a demonstração: o conferidor lista os pedidos pagos de que a loja não ficou sabendo.

Para medir os horários reais das retentativas, rode o receptor com `--falhar`. Ele responde 500 aos avisos e anota cada tentativa em `tentativas.csv`.

Use somente com o seu próprio app, no sandbox. Nada aqui deve ser apontado para o ambiente de produção de terceiros.

### O que foi medido no sandbox

- **Detecção (13/10):** quatro Pix de teste. Em dois, o receptor foi derrubado de propósito. O conferidor achou os dois pedidos pagos de que a loja não soube, com 4 consultas à API.
- **Reentrega (13 e 14/10):** os avisos que falharam com 502 não foram reenviados em pelo menos 12h45 com o endereço no ar. A documentação descreve até quatro tentativas, a última em até 6h30. Ressalvas: é o sandbox, foram dois pedidos e a falha foi um 502.

## Testador de homologação

Usa o conferidor como base para rodar, no **seu** sandbox, a lista pública de cenários que a plataforma avalia na homologação de apps (guia "Publicação em produção"): compra, estorno total e estorno parcial, por meio de pagamento, com CPF e com CNPJ. Isto não é a homologação da plataforma e não dá aprovação: mostra o que dá para conferir de fora.

Para cada cenário, ele cria o pedido e paga pela API (só cartões de teste publicados, nunca cartão real), espera os avisos chegarem ao receptor e dá um veredito por regra fixa:

| Resultado | Quando |
|---|---|
| **passou** | todos os avisos esperados chegaram e o status na API é o esperado |
| **falhou** | a API mostra que o fato aconteceu e o aviso não chegou na janela |
| **inconclusivo** | a plataforma ainda não processou o fato (por exemplo, estorno em análise), então a falta do aviso é esperada |
| **não executado** | a plataforma recusou uma etapa; não é falha do app |

```
python -m conferidor.receptor                       (em outro terminal, com o túnel no ar)
python -m testador rodar                            Pix e cartão 1x, CPF e CNPJ, compra e estornos (12 cenários)
python -m testador rodar --meios boleto,cartao_parcelado --nome boleto_3x
python -m testador rejulgar [--nome boleto_3x]      confere de novo uma rodada, sem criar pedidos
python -m testador resistencia --alvo URL           avisos repetidos, fora de ordem e tempo de resposta
python -m testador relatorio [--nome boleto_3x]     regrava o HTML a partir da rodada gravada
```

Meios: `pix`, `cartao_avista`, `cartao_parcelado`, `boleto`. O relatório também lista o que não dá para conferir de fora (rastreio, descrição na fatura, IP), porque a consulta de pedido não devolve esses dados.

O teste de resistência faz o papel da plataforma e manda avisos sintéticos direto para o endereço do app (pedidos a partir de 900000000). Não aponte para o receptor do conferidor em uso, para não misturar pedidos fictícios no caderno: use um segundo receptor com `--porta 8081 --banco outro.db`.

### O que o testador mostrou no sandbox (14/10/2026, 36 pedidos)

| Meio | Compra | Estorno total | Estorno parcial |
|---|---|---|---|
| Pix | passou, avisos em 2 a 12 s | inconclusivo: o pedido vai para análise manual | inconclusivo: status não muda e nenhum aviso em 10 min |
| Cartão 1x e 3x | passou, avisos em 3 a 6 s | passou, aviso em 3 a 5 s | passou, aviso em 2 a 5 s |
| Boleto | passou, avisos em 3 a 12 s | não executado: a API recusa (HTTP 400) | não executado: a API recusa (HTTP 400) |

Nenhum cenário falhou: todo aviso que a plataforma emitiu chegou ao receptor. Resultados em `testador.html` e `testador_boleto_3x.html`.

### Resumo por IA, e o limite dele

O parágrafo de resumo no topo do relatório é escrito por um modelo de linguagem via OpenRouter, se houver `OPENROUTER_API_KEY` no `.env` (modelo em `MODELO_RESUMO`, padrão `google/gemini-2.5-flash-lite`, cerca de US$ 0,00005 por resumo). Sem chave, ou com o provedor fora do ar, o resumo sai de um texto fixo e o relatório fica igual. Para o provedor vai só a tabela de motivos, sem credencial nem dado de cliente.

O modelo não conta nem decide. Na primeira versão ele recebia a tabela inteira e errou a contagem (escreveu 7 e 5 onde eram 8 e 4) e atribuiu um motivo ao grupo errado. Desde então, a frase com os números é escrita pelo código e os motivos chegam ao modelo já agrupados por operação e meio; ele só reescreve em linguagem simples.
