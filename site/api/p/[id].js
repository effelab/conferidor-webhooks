// O porteiro: recebe o aviso da plataforma, entrega a aplicacao da pessoa e anota a resposta.
// POST /api/p/<id>   o endereco que a pessoa cola no painel do app, como URL de webhook
// GET  /api/p/<id>   so diz se o endereco existe (util para conferir se colou certo)

const { rpc, lerCorpo, json, idValido, SEGREDO, TEMPO_MAXIMO_MS } = require("../_lib");

module.exports = async (req, res) => {
  const id = req.query.id;
  if (!idValido(id)) return json(res, 404, { erro: "endereco_desconhecido" });

  const endereco = await rpc("appmax_endereco", { p_id: id });
  if (!endereco.ok || !endereco.dados) return json(res, 404, { erro: "endereco_desconhecido_ou_expirado" });

  if (req.method === "GET") return json(res, 200, { status: "porteiro no ar", expira_em: endereco.dados.expira_em });
  if (req.method !== "POST") return json(res, 405, { erro: "use_post" });

  let corpo;
  try { corpo = await lerCorpo(req); } catch (_) { return json(res, 413, { erro: "aviso_grande_demais" }); }

  // So repassa JSON (objeto). Aceita os dois formatos da plataforma: o da AppStore (event, event_type)
  // e o do webhook do painel da loja, cujo formato a documentacao publica nao detalha.
  let aviso;
  try { aviso = JSON.parse(corpo.toString("utf8")); } catch (_) { aviso = null; }
  if (!aviso || typeof aviso !== "object" || Array.isArray(aviso)) {
    return json(res, 400, { erro: "o aviso precisa ser um objeto JSON" });
  }
  const nomeDoEvento = [aviso.event, aviso.evento, aviso.type, aviso.event_name, aviso.webhook]
    .find((v) => typeof v === "string" && v.length > 0) || "aviso sem nome";
  const formato = typeof aviso.event_type === "string" ? aviso.event_type
    : `painel: ${Object.keys(aviso).slice(0, 6).join(",")}`; // so os nomes dos campos, nunca os valores

  const inicio = Date.now();
  let statusApp = null, erro = null;
  try {
    const r = await fetch(endereco.dados.app_url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "User-Agent": req.headers["user-agent"] || "porteiro" },
      body: corpo,
      redirect: "manual",
      signal: AbortSignal.timeout(TEMPO_MAXIMO_MS),
    });
    statusApp = r.status;
  } catch (e) {
    erro = e.name === "TimeoutError" ? "a aplicação não respondeu em 9 s" : `não foi possível entregar (${e.cause?.code || e.name})`;
  }
  const ms = Date.now() - inicio;
  const resposta = statusApp ?? (erro && erro.includes("9 s") ? 504 : 502);

  const dados = (aviso.data && typeof aviso.data === "object") ? aviso.data : aviso;
  const pedido = Number.parseInt(dados.order_id ?? dados.id ?? aviso.order_id, 10);
  // Grava o minimo: nada de dados do lojista nem do comprador.
  await rpc("appmax_registrar_aviso", {
    p_segredo: SEGREDO, p_id: id, p_evento: nomeDoEvento, p_tipo: formato.slice(0, 40),
    p_order_id: Number.isFinite(pedido) ? pedido : null,
    p_status_pedido: typeof dados.status === "string" ? dados.status : null,
    p_status_app: statusApp, p_ms_app: ms, p_erro: erro, p_resposta_plataforma: resposta,
  });

  return json(res, resposta, statusApp !== null ? { repassado: true } : { repassado: false, erro });
};
