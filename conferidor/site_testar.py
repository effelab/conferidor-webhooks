"""Sessao "Testar minha aplicacao": assistente para quem quer testar a propria aplicacao, sem instalar nada.

Caminho escolhido para vibe coders: o webhook do PAINEL da loja (menu API > Webhooks), que nao exige
instalar app nem ter URL de validacao. O app no painel de desenvolvedor so e criado uma vez, para liberar
o acesso ao sandbox. A pessoa nunca cola chave nenhuma aqui: so enderecos.

Prints do painel da plataforma, tirados no sandbox do autor em 16/10/2026, com credenciais borradas.
"""

CSS = """
.tm-passo{display:grid;grid-template-columns:44px 1fr;gap:16px;padding:22px 0;border-top:1px solid var(--linha)}
.tm-passo:first-of-type{border-top:0}
.tm-num{width:40px;height:40px;border-radius:50%;background:var(--roxo-forte);color:#fff;font-weight:700;display:flex;align-items:center;justify-content:center;font-size:17px}
.tm-passo h3{margin:6px 0 6px}
.tm-passo ol,.tm-passo ul{margin:8px 0 8px 20px;padding:0}
.tm-passo li{margin:4px 0}
.tm-prints{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin:12px 0}
.tm-prints a{display:block;border:1px solid var(--linha);border-radius:12px;overflow:hidden;background:#fff}
.tm-prints img{display:block;width:100%;height:auto}
.tm-prints figcaption{font-size:12.5px;color:var(--texto-2);padding:6px 10px}
.tm-nota{font-size:13.5px;color:var(--texto-2)}
.tm-caixa{background:var(--lilas-2);border:1px solid var(--lilas);border-radius:14px;padding:16px;margin:12px 0}
.tm-linha{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.tm-linha input{flex:1 1 320px;min-width:0;font:inherit;font-size:15px;padding:11px 12px;border:1px solid var(--linha);border-radius:10px;background:#fff;color:var(--texto)}
.tm-linha button,.tm-btn{font:inherit;font-weight:600;font-size:14.5px;border-radius:10px;padding:11px 16px;cursor:pointer;border:0;background:var(--roxo-forte);color:#fff}
.tm-linha button.sec,.tm-btn.sec{background:var(--lilas);color:var(--roxo-escuro)}
.tm-endereco{font-family:var(--mono);font-size:14px;word-break:break-all;background:#fff;border:1px solid var(--linha);border-radius:10px;padding:10px 12px;flex:1 1 320px;min-width:0}
.tm-erro{color:var(--erro);font-size:14px;margin-top:8px}
.tm-status{display:flex;gap:10px;align-items:center;padding:14px 16px;border-radius:14px;font-weight:600;margin:12px 0}
.tm-status::before{content:"";width:12px;height:12px;border-radius:50%;background:currentColor;flex:0 0 12px}
.tm-status.esperando{background:var(--atencao-f);color:var(--atencao)}
.tm-status.ok{background:var(--ok-f);color:var(--ok)}
.tm-status.ruim{background:var(--erro-f);color:var(--erro)}
.tm-avisos{list-style:none;margin:0;padding:0;display:grid;gap:10px}
.tm-avisos li{background:#fff;border:1px solid var(--linha);border-left:4px solid var(--ok);border-radius:0 12px 12px 0;padding:12px 14px}
.tm-avisos li.ruim{border-left-color:var(--erro)}
.tm-avisos li.lento{border-left-color:var(--atencao)}
.tm-avisos .meta{font-size:12.5px;color:var(--texto-2)}
.tm-avisos .corrigir{margin-top:8px;font-size:13.5px}
.tm-prompt{font-family:var(--mono);font-size:12.5px;white-space:pre-wrap;background:#151a2c;color:#d6dcf5;border-radius:12px;padding:14px;margin:8px 0;max-height:320px;overflow:auto}
@media (max-width:640px){.tm-passo{grid-template-columns:1fr}.tm-num{width:34px;height:34px}}
"""

PROMPT_APP = """Crie na minha aplicação uma rota para receber avisos de pagamento (webhooks) da Appmax:

1. Rota POST pública, por exemplo /api/webhooks/appmax, que aceita JSON.
2. Responda 200 imediatamente (em menos de 5 segundos) e faça o processamento depois. Nunca deixe um erro no processamento virar resposta 500.
3. Aceite os dois formatos de aviso da Appmax: o do painel da loja ({"environment", "event": "OrderPaid", "data": {...}}) e o de aplicativo ({"event": "order_paid", "event_type": "order", "data": {...}}). O número do pedido vem em data.id ou data.order_id.
4. O mesmo aviso pode chegar mais de uma vez: guarde evento + número do pedido e ignore repetidos.
5. Os avisos não têm assinatura. Antes de liberar um produto, confirme o status do pedido consultando a API da Appmax (GET /v1/orders/{id}) com as minhas credenciais guardadas em variáveis de ambiente.
6. Não grave nem registre em log dados pessoais do cliente que vierem no aviso.
7. Esta rota não pode exigir login nem token: a Appmax não envia nenhum."""

SCRIPT = r"""
(function(){
var raiz=document.getElementById('testar'); if(!raiz) return;
var $=function(s){return raiz.querySelector(s)};
var NOMES={OrderPixCreated:'Pix gerado',OrderPaidByPix:'Pix pago',OrderPaid:'Pedido pago',OrderApproved:'Pedido aprovado',
  OrderRefund:'Pedido estornado',OrderPartialRefund:'Pedido estornado parcialmente',CustomerCreated:'Cliente criado',
  OrderBilletCreated:'Boleto gerado',OrderIntegrated:'Pedido integrado',order_pix_created:'Pix gerado',order_paid_by_pix:'Pix pago',
  order_paid:'Pedido pago',order_approved:'Pedido aprovado',order_refund:'Pedido estornado',order_partial_refund:'Pedido estornado parcialmente',
  customer_created:'Cliente criado'};
var LIMITE=5000, id=null, timer=null;
function guardar(v){try{localStorage.setItem('porteiro_id',v)}catch(e){}}
function lembrar(){try{return localStorage.getItem('porteiro_id')}catch(e){return null}}
function copiar(texto,botao){if(!navigator.clipboard){return}navigator.clipboard.writeText(texto).then(function(){var t=botao.textContent;botao.textContent='Copiado';setTimeout(function(){botao.textContent=t},1500)})}
function diagnostico(a){
  if(a.status_app===null||a.status_app===undefined){return {cls:'ruim',txt:'Sua aplicação não respondeu'+(a.erro?' ('+a.erro+')':'')+'.',
    fazer:'Confira se a aplicação está publicada e se o endereço está certo (abra-o no navegador). Peça à sua IA: "minha rota de webhook não está acessível pela internet; verifique se ela está publicada e aceita POST".'}}
  if(a.status_app>=200&&a.status_app<300){
    if(a.ms_app>LIMITE){return {cls:'lento',txt:'Sua aplicação respondeu '+a.status_app+', mas demorou '+(a.ms_app/1000).toFixed(1)+' s (a documentação pede até 5 s).',
      fazer:'Peça à sua IA: "minha rota de webhook demora mais de 5 segundos; faça ela responder 200 na hora e processar o aviso depois".'}}
    return {cls:'',txt:'Sua aplicação respondeu '+a.status_app+' em '+a.ms_app+' ms. Tudo certo.'}}
  if(a.status_app===404){return {cls:'ruim',txt:'Sua aplicação respondeu 404: o endereço não existe.',fazer:'Confira o endereço da rota (troque abaixo) ou peça à sua IA para criar a rota com o prompt deste passo.'}}
  if(a.status_app===401||a.status_app===403){return {cls:'ruim',txt:'Sua aplicação respondeu '+a.status_app+': ela está pedindo login ou token.',
    fazer:'A Appmax não manda token. Peça à sua IA: "libere a rota de webhook sem login; para confiar no aviso, consulte o pedido na API da Appmax".'}}
  if(a.status_app===405){return {cls:'ruim',txt:'Sua aplicação respondeu 405: a rota não aceita POST.',fazer:'Peça à sua IA: "a rota de webhook precisa aceitar POST com JSON".'}}
  return {cls:'ruim',txt:'Sua aplicação respondeu '+a.status_app+' (erro).',
    fazer:'Peça à sua IA: "minha rota de webhook respondeu '+a.status_app+' ao receber o aviso '+a.evento+' da Appmax; responda 200 na hora, processe depois e registre o erro sem quebrar a resposta".'}}
function hora(iso){return new Date(iso).toLocaleTimeString('pt-BR')}
function desenhar(dados){
  var lista=$('#tm-lista'), st=$('#tm-status'), av=dados.avisos||[];
  if(!av.length){st.className='tm-status esperando';st.textContent='Esperando o primeiro aviso. Clique em Testar na Appmax (passo 5) ou faça uma compra de teste.';lista.innerHTML='';return}
  var ruins=av.filter(function(a){return diagnostico(a).cls}).length;
  st.className='tm-status '+(ruins?'ruim':'ok');
  st.textContent=ruins?(ruins+' de '+av.length+' aviso(s) com problema na sua aplicação. Veja o que fazer em cada um.'):(av.length+' aviso(s) recebido(s) e entregue(s) à sua aplicação. A configuração está certa.');
  lista.innerHTML=av.map(function(a){var d=diagnostico(a);
    return '<li class="'+d.cls+'"><strong>'+(NOMES[a.evento]||a.evento)+'</strong> '+(a.order_id?'· pedido '+a.order_id:'')+
      '<div>'+d.txt+'</div><div class="meta">'+hora(a.recebido_em)+' · nome técnico: '+a.evento+(a.status_pedido?' · status: '+a.status_pedido:'')+'</div>'+
      (d.fazer?'<div class="corrigir"><strong>O que fazer:</strong> '+d.fazer+'</div>':'')+'</li>'}).join('');
}
function acompanhar(){
  clearTimeout(timer); if(!id) return;
  fetch('/api/avisos?id='+encodeURIComponent(id),{cache:'no-store'}).then(function(r){return r.json().then(function(j){return [r.status,j]})}).then(function(x){
    if(x[0]!==200){$('#tm-status').className='tm-status ruim';$('#tm-status').textContent='Este endereço de teste não existe mais (eles valem 24 horas). Crie outro no passo 4.';return}
    $('#tm-validade').textContent='Vale até '+new Date(x[1].endereco.expira_em).toLocaleString('pt-BR')+'. Depois disso, tudo é apagado.';
    $('#tm-app-atual').textContent=x[1].endereco.app_url;
    desenhar(x[1]); timer=setTimeout(acompanhar,4000);
  }).catch(function(){timer=setTimeout(acompanhar,8000)});
}
function mostrar(novoId,endereco){
  id=novoId; guardar(id);
  var url=new URL(location.href); url.searchParams.set('id',id); history.replaceState(null,'',url);
  $('#tm-pronto').hidden=false; $('#tm-endereco').textContent=endereco||(location.origin+'/api/p/'+id);
  acompanhar();
}
function criar(appUrl,trocar){
  var erro=$('#tm-erro'); erro.textContent='';
  if(!/^https:\/\//i.test(appUrl)){erro.textContent='Use o endereço público da sua aplicação, começando com https://';return}
  var corpo={app_url:appUrl}; if(trocar&&id) corpo.id=id;
  fetch('/api/criar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(corpo)}).then(function(r){return r.json().then(function(j){return [r.status,j]})}).then(function(x){
    if(x[0]!==200){erro.textContent=x[1].erro||'Não deu certo. Tente de novo.';return}
    if(trocar&&id){acompanhar();return}
    mostrar(x[1].id,x[1].endereco_webhook);
  }).catch(function(){erro.textContent='Sem conexão. Tente de novo.'});
}
$('#tm-criar').addEventListener('click',function(){criar($('#tm-app').value.trim(),false)});
$('#tm-exemplo').addEventListener('click',function(){$('#tm-app').value=location.origin+'/api/exemplo/saudavel';criar($('#tm-app').value,false)});
$('#tm-copiar').addEventListener('click',function(){copiar($('#tm-endereco').textContent,this)});
$('#tm-copiar-prompt').addEventListener('click',function(){copiar($('#tm-prompt').textContent,this)});
$('#tm-trocar').addEventListener('click',function(){criar($('#tm-app-novo').value.trim(),true)});
$('#tm-novo').addEventListener('click',function(){id=null;try{localStorage.removeItem('porteiro_id')}catch(e){};$('#tm-pronto').hidden=true;clearTimeout(timer);
  var url=new URL(location.href);url.searchParams.delete('id');history.replaceState(null,'',url)});
var inicial=new URL(location.href).searchParams.get('id')||lembrar();
if(inicial&&/^[0-9a-f]{18}$/.test(inicial)) mostrar(inicial);
})();
"""


def _prints(*itens):
    figuras = "".join(
        f'<figure><a href="{arq}" target="_blank" rel="noopener"><img src="{arq}" alt="{legenda}" loading="lazy"></a>'
        f'<figcaption>{legenda}</figcaption></figure>' for arq, legenda in itens)
    return f'<div class="tm-prints">{figuras}</div>'


def testar(icone, escape):
    return f"""<section class="sec" id="testar">
<div class="w">
<p class="olho">Testar minha aplicação</p>
<h2>A sua aplicação recebe os avisos de pagamento da Appmax?</h2>
<p class="sub">Descubra em poucos minutos, sem instalar nada. Você cola dois endereços e acompanha tudo nesta tela.</p>

<div class="card">
<p><strong>Você vai precisar de:</strong></p>
<ul>
<li>uma conta de desenvolvedor na Appmax. <strong>Ela pede CNPJ ou MEI</strong>; sem isso não dá para seguir;</li>
<li>a sua aplicação publicada na internet, com um endereço <code>https://</code> que recebe avisos. Ainda não tem essa rota? O passo 4 traz um texto pronto para pedir à sua IA (Lovable, Bolt, Cursor, Replit...).</li>
</ul>
<p class="tm-nota">{icone("info")} <strong>Você nunca cola chave nem senha aqui</strong>, só endereços. Guardamos só o nome do aviso, o número do pedido, o status e a resposta da sua aplicação, nada de dados de cliente, e <strong>apagamos tudo em 24 horas</strong>. Use só o sandbox (ambiente de teste) da Appmax. Projeto independente, sem vínculo com a Appmax; as telas abaixo são da plataforma, usadas só para orientar.</p>
</div>

<div class="tm-passo"><div class="tm-num">1</div><div>
<h3>Crie a sua conta de desenvolvedor na Appmax</h3>
<ol><li>Entre em <a href="https://appstore.appmax.com.br" target="_blank" rel="noopener">appstore.appmax.com.br</a> e clique em <strong>Desenvolva seu aplicativo</strong>.</li>
<li>Faça o cadastro (pede CNPJ ou MEI). Não há cobrança.</li></ol>
{_prints(("print-01-area-desenvolvedor.jpg", "Área do desenvolvedor, depois de entrar"))}
</div></div>

<div class="tm-passo"><div class="tm-num">2</div><div>
<h3>Crie um aplicativo privado (só para liberar o ambiente de teste)</h3>
<p>Você não vai programar nada nele. Ele existe só para a Appmax liberar a sua loja de teste.</p>
<ol><li>No topo, clique em <strong>Criar um Aplicativo</strong> e escolha <strong>Aplicativo privado</strong> (não precisa de aprovação).</li>
<li><strong>Nome</strong>, <strong>e-mail de suporte</strong> e <strong>descrição</strong>: pode escrever qualquer coisa, por exemplo "Teste da minha loja".</li>
<li><strong>Imagem</strong>: precisa ser quadrada, 1200 x 1200. <a href="imagem-app-1200.png" download>Baixe esta pronta</a>.</li>
<li><strong>Configurações</strong>: os campos Host, URL do sistema e URL de validação não são usados neste caminho, mas o formulário pede. Coloque o endereço da sua aplicação nos três. Nos eventos, pode clicar em <strong>Selecionar todas</strong>.</li>
<li>Conclua o cadastro.</li></ol>
{_prints(("print-02-criar-app-privado.jpg", "Criar um Aplicativo: escolha Aplicativo privado"))}
</div></div>

<div class="tm-passo"><div class="tm-num">3</div><div>
<h3>Entre na sua loja de teste (sandbox)</h3>
<ol><li>Em <strong>Meus aplicativos</strong>, clique na <strong>setinha</strong> da linha do seu app e em <strong>Exibir credenciais</strong>.</li>
<li>Desça até <strong>Dados de acesso</strong>: lá estão o <strong>endereço da sua loja de teste</strong>, o <strong>e-mail</strong> e uma <strong>senha gerada</strong> (use o botão de copiar; não é a senha da sua conta).</li>
<li>Abra o endereço da loja de teste e entre com esse e-mail e essa senha.</li></ol>
{_prints(("print-03-meus-aplicativos.jpg", "Meus aplicativos: setinha > Exibir credenciais"),
          ("print-04-credenciais.jpg", "Dados de acesso: e-mail e senha do sandbox (borrados aqui)"),
          ("print-05-login-sandbox.jpg", "Login da loja de teste"))}
</div></div>

<div class="tm-passo"><div class="tm-num">4</div><div>
<h3>Crie o seu endereço de teste</h3>
<p>Cole o endereço da rota da sua aplicação que recebe avisos. Nós criamos um endereço que fica no meio: ele anota cada aviso, entrega para a sua aplicação e mostra como ela respondeu.</p>
<div class="tm-caixa">
<label for="tm-app"><strong>Endereço da sua aplicação</strong></label>
<div class="tm-linha" style="margin-top:6px"><input id="tm-app" type="url" placeholder="https://minha-loja.lovable.app/api/webhooks/appmax" autocomplete="off">
<button type="button" id="tm-criar">Criar meu endereço</button></div>
<p class="tm-nota" style="margin:8px 0 0">Ainda não tem aplicação? <button type="button" class="tm-btn sec" id="tm-exemplo" style="padding:6px 10px;font-size:13px">Usar a aplicação de exemplo</button></p>
<div class="tm-erro" id="tm-erro" role="alert"></div>
<div id="tm-pronto" hidden>
<p style="margin:14px 0 6px"><strong>Seu endereço de teste</strong> (é ele que vai na Appmax):</p>
<div class="tm-linha"><span class="tm-endereco" id="tm-endereco"></span><button type="button" id="tm-copiar">Copiar</button></div>
<p class="tm-nota" id="tm-validade"></p>
</div>
</div>
<details><summary><strong>Ainda não tem a rota que recebe avisos? Copie este texto para a sua IA</strong></summary>
<div class="tm-prompt" id="tm-prompt">{escape(PROMPT_APP)}</div>
<button type="button" class="tm-btn sec" id="tm-copiar-prompt">Copiar texto</button>
</details>
</div></div>

<div class="tm-passo"><div class="tm-num">5</div><div>
<h3>Cole o endereço na Appmax e clique em Testar</h3>
<ol><li>Na sua loja de teste, no menu da esquerda, clique em <strong>API</strong> e depois na aba <strong>Webhooks</strong>.</li>
<li><strong>Loja</strong>: escolha a sua loja de teste. <strong>URL de destino</strong>: cole o seu endereço de teste (passo 4).</li>
<li><strong>Eventos</strong>: marque pelo menos <strong>Pedido aprovado</strong>, <strong>Pedido pago</strong>, <strong>Pix Gerado</strong>, <strong>Pix Pago</strong> e <strong>Pedido Estornado</strong>.</li>
<li>Clique em <strong>Salvar webhook</strong>. Ele aparece em <strong>Webhooks cadastrados</strong>: clique em <strong>Testar</strong>.</li></ol>
{_prints(("print-06-menu-api.jpg", "Menu API, na loja de teste"),
          ("print-08-webhooks-preenchido.jpg", "Aba Webhooks: loja, URL de destino e eventos"),
          ("print-09-webhook-cadastrado-testar.jpg", "Webhook cadastrado: clique em Testar"))}
</div></div>

<div class="tm-passo"><div class="tm-num">6</div><div>
<h3>Acompanhe aqui, ao vivo</h3>
<p>Esta parte atualiza sozinha a cada 4 segundos. Quando o aviso do botão Testar chegar, fica verde.</p>
<div class="tm-status esperando" id="tm-status" aria-live="polite">Crie o seu endereço no passo 4 para começar.</div>
<ul class="tm-avisos" id="tm-lista"></ul>
<details style="margin-top:12px"><summary>Trocar o endereço da aplicação ou começar de novo</summary>
<p class="tm-nota">Endereço atual da aplicação: <span id="tm-app-atual"></span></p>
<div class="tm-linha"><input id="tm-app-novo" type="url" placeholder="https://..." autocomplete="off"><button type="button" id="tm-trocar">Trocar</button>
<button type="button" class="sec" id="tm-novo">Começar de novo</button></div>
</details>
</div></div>

<div class="tm-passo"><div class="tm-num">7</div><div>
<h3>Faça uma compra de teste</h3>
<p>Com o botão Testar funcionando, faça uma compra de verdade no ambiente de teste, pelo checkout da sua aplicação, pagando com <strong>Pix</strong>. No sandbox, o Pix é aprovado sozinho em cerca de 5 segundos com qualquer CPF válido (por exemplo <code>19100000000</code>), sem pagar nada.</p>
<p>Você deve ver chegar, em segundos: <strong>Pix gerado</strong>, <strong>Pedido pago</strong>, <strong>Pedido aprovado</strong> e <strong>Pix pago</strong>. Cada um mostra se a sua aplicação recebeu e em quanto tempo respondeu.</p>
<p class="tm-nota">Medido pelo autor no sandbox em 16/10/2026: compra com Pix, quatro avisos em 8 segundos, todos entregues. O endereço de teste acrescenta cerca de 1 segundo ao caminho (ele consulta e grava no banco); o tempo mostrado é só o da sua aplicação.</p>
</div></div>

</div>
</section>"""
