"""Sessao "Experimente": uma simulacao do conferidor que roda so no navegador do visitante.

Nada aqui fala com a plataforma, nem usa chave. Serve para qualquer pessoa ver, em
30 segundos, o que o conferidor faz. Os numeros medidos de verdade ficam nas outras sessoes.
"""

CSS = """
.sim-aviso{display:flex;gap:10px;align-items:flex-start;background:var(--atencao-f);color:var(--atencao);border:1px solid #f1d9a8;border-radius:12px;padding:12px 14px;margin:16px 0}
.sim-passos{counter-reset:p;list-style:none;padding:0;margin:0 0 16px;display:grid;gap:8px}
.sim-passos li{counter-increment:p;display:flex;gap:10px;align-items:baseline}
.sim-passos li::before{content:counter(p);flex:0 0 26px;height:26px;border-radius:50%;background:var(--lilas);color:var(--roxo-escuro);font-weight:700;display:inline-flex;align-items:center;justify-content:center;font-size:13px}
.sim-controles{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:8px 0 18px}
.sim-controles button{font:inherit;font-weight:600;font-size:14px;border-radius:10px;padding:10px 16px;cursor:pointer;border:1px solid transparent}
.sim-primario{background:var(--roxo-forte);color:#fff}
.sim-primario:hover{background:var(--roxo-escuro)}
.sim-secundario{background:var(--lilas);color:var(--roxo-escuro)}
.sim-chave{background:#fff;border-color:var(--linha)!important;color:var(--texto)}
.sim-chave[aria-pressed=false]{background:var(--erro-f);color:var(--erro);border-color:#f3c3be!important}
.sim-chave[aria-pressed=true]{background:var(--ok-f);color:var(--ok);border-color:#bfe3cd!important}
.sim-colunas{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.sim-colunas>div{min-width:0}
.sim-lista{list-style:none;margin:0;padding:0;display:grid;gap:8px;min-height:60px}
.sim-lista li{background:#fff;border:1px solid var(--linha);border-radius:12px;padding:10px 12px;font-size:14px}
.sim-lista li.perdido{border-color:#f3c3be;background:var(--erro-f)}
.sim-lista small{display:block;color:var(--texto-2);margin-top:2px}
.sim-vazio{color:var(--texto-2);font-size:14px}
.sim-resultado{margin-top:18px}
.sim-log{font-family:var(--mono);font-size:12px;background:#151a2c;color:#d6dcf5;border-radius:12px;padding:12px;max-height:180px;overflow:auto;margin-top:14px;white-space:pre-wrap}
@media (max-width:760px){.sim-colunas{grid-template-columns:1fr}}
"""

SCRIPT = r"""
(function(){
var raiz=document.getElementById('simulador'); if(!raiz) return;
var estado={pedidos:[],ligado:true,proximo:1001};
var AVISOS=['Pix gerado','Pix pago','Pedido aprovado'];
function $(s){return raiz.querySelector(s)}
function log(t){var l=$('#sim-log');var h=new Date().toLocaleTimeString('pt-BR');l.textContent=h+'  '+t+'\n'+l.textContent}
function aviso(p,nome){
  if(estado.ligado){p.recebidos.push(nome);log('aviso "'+nome+'" do pedido '+p.id+' chegou ao receptor')}
  else{p.perdidos.push(nome);log('aviso "'+nome+'" do pedido '+p.id+' se perdeu (receptor desligado)')}
  desenhar();
}
function criar(n){
  for(var i=0;i<n;i++){
    var p={id:estado.proximo++,status:'aguardando pagamento',recebidos:[],perdidos:[]};
    estado.pedidos.push(p); log('pedido '+p.id+' criado');
    aviso(p,AVISOS[0]);
    (function(p,atraso){setTimeout(function(){p.status='pago';log('a plataforma confirmou o pagamento do pedido '+p.id);
      aviso(p,AVISOS[1]);aviso(p,AVISOS[2])},atraso)})(p,1200+i*500);
  }
  $('#sim-resultado').innerHTML='';desenhar();
}
function desenhar(){
  var api=$('#sim-api'),loja=$('#sim-loja');
  if(!estado.pedidos.length){api.innerHTML=loja.innerHTML='<li class="sim-vazio">Nenhum pedido ainda.</li>';return}
  api.innerHTML=estado.pedidos.map(function(p){return '<li><strong>Pedido '+p.id+'</strong><small>'+p.status+'</small></li>'}).join('');
  loja.innerHTML=estado.pedidos.map(function(p){
    var falta=p.perdidos.length>0;
    return '<li class="'+(falta?'perdido':'')+'"><strong>Pedido '+p.id+'</strong><small>'+
      (p.recebidos.length?'recebeu: '+p.recebidos.join(', '):'nenhum aviso recebido')+'</small></li>'}).join('');
}
function conferir(){
  var pagos=estado.pedidos.filter(function(p){return p.status==='pago'});
  var semAviso=pagos.filter(function(p){return p.recebidos.indexOf('Pix pago')<0||p.recebidos.indexOf('Pedido aprovado')<0});
  var r=$('#sim-resultado');
  if(!estado.pedidos.length){r.innerHTML='<p class="sim-vazio">Crie alguns pedidos primeiro.</p>';return}
  log('conferidor perguntou à plataforma sobre '+estado.pedidos.length+' pedido(s) e comparou com os avisos');
  if(!semAviso.length){r.innerHTML='<div class="card"><p><strong>Nenhum pedido pago sem aviso.</strong> A loja sabe de todas as vendas pagas. Desligue o receptor, crie mais pedidos e confira de novo.</p></div>';return}
  r.innerHTML='<div class="card" style="border-left:3px solid var(--erro);border-radius:0 12px 12px 0"><p><strong>'+semAviso.length+' pedido(s) pago(s) de que a loja não ficou sabendo:</strong> '+
    semAviso.map(function(p){return p.id}).join(', ')+'.</p><p>A plataforma diz que foram pagos, mas os avisos não chegaram. Sem o conferidor, esses produtos não seriam enviados. Com a lista, a loja pode agir e pedir o reenvio ao suporte.</p></div>';
}
$('#sim-chave').addEventListener('click',function(){estado.ligado=!estado.ligado;this.setAttribute('aria-pressed',estado.ligado);
  this.textContent=estado.ligado?'Receptor ligado':'Receptor desligado';log(estado.ligado?'receptor ligado':'receptor desligado')});
$('#sim-criar').addEventListener('click',function(){criar(3)});
$('#sim-conferir').addEventListener('click',conferir);
$('#sim-zerar').addEventListener('click',function(){estado={pedidos:[],ligado:true,proximo:1001};var c=$('#sim-chave');c.setAttribute('aria-pressed','true');c.textContent='Receptor ligado';
  $('#sim-resultado').innerHTML='';$('#sim-log').textContent='';desenhar()});
desenhar();
})();
"""


def experimente(icone):
    return f"""<section class="sec" id="experimente">
<div class="w">
<p class="olho">Experimente</p>
<h2>O conferidor em 30 segundos, sem instalar nada</h2>
<p class="sub">Crie pedidos, desligue a caixa de correio da loja e veja o conferidor achar as vendas que se perderam.</p>
<p class="sim-aviso">{icone("atencao")}<span><strong>Isto é uma simulação no seu navegador.</strong> Nada aqui fala com a plataforma nem usa chave.
O que foi medido de verdade, no sandbox, está nas sessões Conferidor e Testador.</span></p>
<div class="card" id="simulador">
<ol class="sim-passos">
<li>Clique em <strong>Criar 3 pedidos com Pix</strong>. Com o receptor ligado, os avisos chegam.</li>
<li>Clique em <strong>Receptor ligado</strong> para desligá-lo e crie mais 3 pedidos. Os avisos desses se perdem.</li>
<li>Clique em <strong>Rodar o conferidor</strong> e veja quais vendas pagas a loja não ficou sabendo.</li>
</ol>
<div class="sim-controles">
<button type="button" class="sim-chave" id="sim-chave" aria-pressed="true">Receptor ligado</button>
<button type="button" class="sim-secundario" id="sim-criar">Criar 3 pedidos com Pix</button>
<button type="button" class="sim-primario" id="sim-conferir">Rodar o conferidor</button>
<button type="button" class="sim-secundario" id="sim-zerar">Recomeçar</button>
</div>
<div class="sim-colunas">
<div><h3>O que a plataforma sabe</h3><p class="sim-vazio">A verdade: o status de cada pedido.</p><ul class="sim-lista" id="sim-api"></ul></div>
<div><h3>O que a loja recebeu</h3><p class="sim-vazio">Os avisos que chegaram ao receptor.</p><ul class="sim-lista" id="sim-loja"></ul></div>
</div>
<div class="sim-resultado" id="sim-resultado" aria-live="polite"></div>
<div class="sim-log" id="sim-log" aria-label="Registro da simulação"></div>
</div>
<noscript><p>A simulação precisa de JavaScript ligado no navegador.</p></noscript>
</div>
</section>"""
