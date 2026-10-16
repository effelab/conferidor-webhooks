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

1. Rota POST pública que aceita JSON. Se o projeto usa Supabase (Lovable, Bolt), crie uma Edge Function chamada appmax-webhook e desative a verificação de JWT (verify_jwt = false). Se usa Next.js ou parecido, use /api/webhooks/appmax.
2. A rota não pode exigir login nem token, e não pode redirecionar (nada de 301 ou 302). A Appmax não envia token nenhum.
3. Ao receber, grave o aviso numa tabela (evento, número do pedido, status, data) e responda 200 em menos de 5 segundos. Processe depois, a partir da tabela. Um erro no processamento nunca pode virar resposta 500.
4. Aceite os dois formatos da Appmax: o do painel da loja ({"environment", "event": "OrderPaid", "data": {...}}) e o de aplicativo ({"event": "order_paid", "event_type": "order", "data": {...}}). O número do pedido vem em data.id ou data.order_id. Responda 200 também para eventos que você não usa.
5. O mesmo aviso pode chegar mais de uma vez: use evento + número do pedido para ignorar repetidos.
6. Os avisos não têm assinatura. Deixe preparada uma consulta ao pedido na API da Appmax antes de liberar um produto, lendo as credenciais de variáveis de ambiente. Se elas ainda não estiverem configuradas, só registre o aviso e responda 200; não me peça as chaves agora.
7. Não grave nem registre em log dados pessoais do cliente.
8. No final, publique e me diga o endereço completo da rota na versão publicada, começando com https://."""

SCRIPT = r"""
(function(){
var raiz=document.getElementById('testar'); if(!raiz) return;
var $=function(s){return raiz.querySelector(s)};
var NOMES={OrderPixCreated:'Pix gerado',OrderPaidByPix:'Pix pago',OrderPaid:'Pedido pago',OrderApproved:'Pedido aprovado',
  OrderRefund:'Pedido estornado',OrderPartialRefund:'Pedido estornado parcialmente',CustomerCreated:'Cliente criado',
  OrderBilletCreated:'Boleto gerado',OrderIntegrated:'Pedido integrado',order_pix_created:'Pix gerado',order_paid_by_pix:'Pix pago',
  order_paid:'Pedido pago',order_approved:'Pedido aprovado',order_refund:'Pedido estornado',order_partial_refund:'Pedido estornado parcialmente',
  customer_created:'Cliente criado'};
var LIMITE=5000, id=null, timer=null, inicioEspera=Date.now();
function guardar(v){try{localStorage.setItem('porteiro_id',v)}catch(e){}}
function lembrar(){try{return localStorage.getItem('porteiro_id')}catch(e){return null}}
function copiar(texto,botao){if(!navigator.clipboard){return}navigator.clipboard.writeText(texto).then(function(){var t=botao.textContent;botao.textContent='Copiado';setTimeout(function(){botao.textContent=t},1500)})}
function diagnostico(a){
  if(a.status_app===null||a.status_app===undefined){
    if(a.erro&&a.erro.indexOf('9 s')>=0){return {cls:'ruim',txt:'Sua aplicação demorou mais de 9 segundos e não chegou a responder. A Appmax espera só 5. Isso é comum em planos grátis que "dormem" quando ninguém usa.',
      fazer:'Mande o aviso de novo. Se passar na segunda vez, a aplicação estava dormindo. Peça à sua IA: "minha rota de webhook demora mais de 5 segundos; faça ela responder 200 na hora e processar o aviso depois".'}}
    return {cls:'ruim',txt:'Não conseguimos chegar na sua aplicação. O endereço pode estar errado ou a aplicação não está publicada.',
      fazer:'Confira se o endereço é o da versão publicada (não o do preview). Não adianta abrir no navegador: rotas de aviso costumam dar erro quando abertas assim, e isso é normal. Peça à sua IA: "minha rota de webhook não está acessível pela internet na versão publicada; confira se ela foi publicada e aceita POST sem login, e me diga o endereço completo".'}}
  if(a.status_app>=300&&a.status_app<400){return {cls:'ruim',txt:'Sua aplicação respondeu '+a.status_app+': ela mandou o aviso para outro endereço. A Appmax não segue esse desvio, e o aviso se perde.',
    fazer:'Use o endereço final, exatamente como aparece no navegador (com ou sem www, com ou sem barra no final). Ou peça à sua IA: "minha rota de webhook está redirecionando; ela precisa responder 200 direto, sem redirecionar".'}}
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
  if(!av.length){st.className='tm-status esperando';st.textContent='Esperando o primeiro aviso. Clique em Testar na Appmax (passo 5) ou use o botão Mandar um aviso de teste (passo 4).';lista.innerHTML='';
    if(Date.now()-inicioEspera>120000){$('#tm-ajuda').open=true}return}
  var ruins=av.filter(function(a){return diagnostico(a).cls}).length;
  st.className='tm-status '+(ruins?'ruim':'ok');
    var compra=av.some(function(a){return a.order_id&&a.order_id>1&&a.tipo&&a.tipo.indexOf('teste daqui')<0});
  st.textContent=ruins?(ruins+' de '+av.length+' aviso(s) com problema na sua aplicação. Veja o que fazer em cada um.'):
    (compra?('Funcionando: '+av.length+' aviso(s) chegaram e a sua aplicação respondeu bem, inclusive de uma compra de teste. Agora siga para o passo 8.'):
    ('O caminho está funcionando: '+av.length+' aviso(s) chegaram e a sua aplicação respondeu bem. Falta a compra de teste (passo 7).'));
  $('#tm-ajuda').open=false;
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
$('#tm-aviso-teste').addEventListener('click',function(){var b=this;b.disabled=true;b.textContent='Mandando...';
  fetch($('#tm-endereco').textContent,{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({environment:'teste daqui',event:'OrderPaid',data:{id:1,status:'aprovado'}})})
  .finally(function(){b.disabled=false;b.textContent='Mandar um aviso de teste';acompanhar()})});
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
<p class="sub">Sem instalar nada: você cola dois endereços e acompanha tudo nesta tela.</p>

<div class="card">
<p><strong>Antes de começar.</strong> Leva cerca de 30 minutos na primeira vez, a maior parte no cadastro da Appmax. Depois, testar de novo leva 2 minutos.</p>
<p><strong>Você vai precisar de:</strong></p>
<ul>
<li><strong>CNPJ ou MEI e um e-mail</strong> para a conta de desenvolvedor da Appmax. Sem CNPJ ou MEI não dá para seguir;</li>
<li><strong>a sua aplicação publicada</strong> (não vale o link de preview do Lovable ou do Bolt);</li>
<li><strong>uma rota que recebe avisos</strong> na sua aplicação. Ainda não tem? Faça isto primeiro: copie o texto pronto do passo 4 para a sua IA e anote o endereço que ela devolver.</li>
</ul>
<p>Quer só ver como a tela funciona? No passo 4, clique em "Usar a aplicação de exemplo".</p>
<p class="tm-nota">{icone("info")} <strong>Você nunca cola chave nem senha aqui</strong>, só endereços. Guardamos só o nome do aviso, o número do pedido, o status e a resposta da sua aplicação, nada de dados de cliente, e <strong>apagamos tudo em 24 horas</strong>. Use só o ambiente de teste (sandbox) da Appmax. Ferramenta gratuita e independente, sem vínculo com a Appmax; as telas abaixo são da plataforma, usadas só para orientar.</p>
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
<li><strong>Configurações</strong>: o formulário pede Host, URL do sistema e URL de validação, mas este teste não usa nenhum deles. Coloque nos três o endereço principal do seu site (por exemplo <code>https://minha-loja.lovable.app</code>). Nos eventos, clique em <strong>Selecionar todas</strong>.</li>
<li>Conclua o cadastro. O app aparece em <strong>Meus aplicativos</strong>; a situação pode ser "Publicado" ou outra, e para este teste tanto faz.</li></ol>
{_prints(("print-02-criar-app-privado.jpg", "Tela 1 de 3: escolha Aplicativo privado. Imagem e endereços ficam nas telas 2 e 3"))}
</div></div>

<div class="tm-passo"><div class="tm-num">3</div><div>
<h3>Entre na sua loja de teste (sandbox)</h3>
<ol><li>Em <strong>Meus aplicativos</strong>, clique na <strong>setinha</strong> da linha do seu app e em <strong>Exibir credenciais</strong>.</li>
<li>Desça até <strong>Dados de acesso</strong>: lá estão o <strong>endereço da sua loja de teste</strong>, o <strong>e-mail</strong> e uma <strong>senha gerada</strong> (use o botão de copiar; não é a senha da sua conta).</li>
<li>Abra o endereço da loja de teste e entre com esse e-mail e essa senha.</li></ol>
<p><strong>Cuidados neste passo:</strong></p>
<ul><li>Se aparecer "Client secret já visualizado", tudo bem: você não precisa dele para este teste.</li>
<li>A janela também mostra credenciais de <strong>Produção</strong>, mais abaixo. Não mexa nelas agora.</li>
<li>A tela de login da loja de teste é igual à da Appmax normal. Entre com o e-mail e a senha de <strong>Dados de acesso</strong> e não clique em "Criar conta agora".</li>
<li>Se aparecer uma verificação da Cloudflare, é normal; espere ela ficar verde.</li></ul>
{_prints(("print-03-meus-aplicativos.jpg", "Meus aplicativos: setinha > Exibir credenciais"),
          ("print-04-credenciais.jpg", "Dados de acesso: e-mail e senha do sandbox (borrados aqui)"),
          ("print-05-login-sandbox.jpg", "Login da loja de teste"))}
</div></div>

<div class="tm-passo"><div class="tm-num">4</div><div>
<h3>Crie o seu endereço de teste</h3>
<p><strong>Primeiro: peça a rota para a sua IA.</strong> Se a sua aplicação ainda não tem um endereço que recebe avisos, copie este texto para o Lovable, Bolt, Cursor ou Replit. No fim, ela devolve o endereço da rota.</p>
<div class="tm-prompt" id="tm-prompt">{escape(PROMPT_APP)}</div>
<button type="button" class="tm-btn sec" id="tm-copiar-prompt">Copiar texto</button>
<p style="margin-top:16px">Agora cole o endereço dessa rota. Nós criamos um endereço que fica no meio: ele anota cada aviso, entrega para a sua aplicação e mostra como ela respondeu.</p>
<div class="tm-caixa">
<label for="tm-app"><strong>Endereço da sua aplicação</strong></label>
<div class="tm-linha" style="margin-top:6px"><input id="tm-app" type="url" placeholder="https://minha-loja.lovable.app/api/webhooks/appmax" autocomplete="off">
<button type="button" id="tm-criar">Criar meu endereço</button></div>
<p class="tm-nota" style="margin:8px 0 0">Ainda não tem aplicação? <button type="button" class="tm-btn sec" id="tm-exemplo" style="padding:6px 10px;font-size:13px">Usar a aplicação de exemplo</button>
A aplicação de exemplo é de mentira e sempre responde OK. Serve só para você ver como esta tela funciona.</p>
<div class="tm-erro" id="tm-erro" role="alert"></div>
<div id="tm-pronto" hidden>
<p style="margin:14px 0 6px"><strong>Seu endereço de teste</strong> (é ele que vai na Appmax):</p>
<div class="tm-linha"><span class="tm-endereco" id="tm-endereco"></span><button type="button" id="tm-copiar">Copiar</button></div>
<p class="tm-nota" id="tm-validade"></p>
<p style="margin:12px 0 6px"><strong>Quer testar já, sem a Appmax?</strong> Nós mandamos para a sua aplicação um aviso de exemplo, no mesmo formato da Appmax ("Pedido pago", pedido de teste). O resultado aparece no passo 6. Isso confere se a sua rota responde; não confere se a Appmax está configurada (para isso, siga os passos 1, 2, 3 e 5).</p>
<button type="button" class="tm-btn" id="tm-aviso-teste">Mandar um aviso de teste</button>
</div>
</div>
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
<details id="tm-ajuda" style="margin-top:12px"><summary><strong>Ainda nada? Confira, nesta ordem</strong></summary>
<ol><li>Na Appmax, em Webhooks cadastrados, a URL começa com <code>https://conferidor-webhooks.vercel.app/api/p/</code>? Se aparecer o endereço da sua aplicação, você colou o endereço errado: apague e cadastre de novo com o endereço de teste do passo 4.</li>
<li>Você clicou em <strong>Salvar webhook</strong> antes de Testar? O webhook precisa aparecer na lista de cadastrados.</li>
<li>A loja escolhida é a sua loja de teste?</li>
<li>O endereço de teste ainda vale? Veja a data em "Vale até", no passo 4.</li></ol>
<p>Se tudo estiver certo, clique em Testar de novo e espere 10 segundos.</p></details>
<details style="margin-top:12px"><summary>Trocar o endereço da aplicação ou começar de novo</summary>
<p class="tm-nota">Endereço atual da aplicação: <span id="tm-app-atual"></span></p>
<div class="tm-linha"><input id="tm-app-novo" type="url" placeholder="https://..." autocomplete="off"><button type="button" id="tm-trocar">Trocar</button>
<button type="button" class="sec" id="tm-novo">Começar de novo</button></div>
</details>
</div></div>

<div class="tm-passo"><div class="tm-num">7</div><div>
<h3>Faça uma compra de teste</h3>
<p>Com o botão Testar funcionando, faça uma compra no ambiente de teste pelo checkout da sua aplicação, pagando com <strong>Pix</strong>. No teste, o Pix é aprovado sozinho em cerca de 5 segundos com qualquer CPF válido (por exemplo <code>19100000000</code>), sem pagar nada.</p>
<p>Em menos de 10 segundos devem chegar aqui: <strong>Pix gerado</strong>, <strong>Pedido pago</strong>, <strong>Pedido aprovado</strong> e <strong>Pix pago</strong>. Cada um mostra se a sua aplicação recebeu e em quanto tempo respondeu.</p>
<p class="tm-nota">Sua aplicação ainda não tem checkout? Use o botão "Mandar um aviso de teste" do passo 4 para conferir a rota, e faça a compra quando o checkout existir.</p>
</div></div>

<div class="tm-passo"><div class="tm-num">8</div><div>
<h3>Deu certo? Agora troque o endereço na Appmax</h3>
<p>O endereço de teste só vale 24 horas. Depois disso, os avisos param de chegar e ninguém é avisado.</p>
<ol><li>Na loja de teste, volte em <strong>API</strong> e depois <strong>Webhooks</strong>.</li>
<li>Em <strong>Webhooks cadastrados</strong>, apague o que aponta para <code>conferidor-webhooks.vercel.app</code> (ícone da lixeira).</li>
<li>Cadastre de novo com a <strong>URL de destino</strong> igual ao endereço da sua aplicação (o mesmo que você colou no passo 4), com os mesmos eventos.</li>
<li>Clique em <strong>Testar</strong> e confira no painel da sua aplicação que o aviso chegou.</li></ol>
<p>Quando for vender de verdade, repita isso na sua loja de produção.</p>
</div></div>

</div>
</section>"""
