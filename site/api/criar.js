// POST /api/criar  {"app_url": "https://..."}  ->  cria o endereco de teste da pessoa (vale 24 h)
// POST /api/criar  {"id": "...", "app_url": "https://..."}  ->  troca o endereco da aplicacao

const { rpc, json, idValido } = require("./_lib");

const MENSAGENS = {
  endereco_invalido: "Use um endereço público que comece com https:// (não vale localhost nem rede interna).",
  limite_por_hora: "Muitos endereços criados na última hora. Tente de novo mais tarde.",
};

module.exports = async (req, res) => {
  if (req.method !== "POST") return json(res, 405, { erro: "use_post" });
  const corpo = req.body || {};
  const appUrl = typeof corpo.app_url === "string" ? corpo.app_url.trim() : "";
  if (!appUrl) return json(res, 400, { erro: "Informe o endereço da sua aplicação." });

  if (corpo.id) {
    if (!idValido(corpo.id)) return json(res, 404, { erro: "Endereço de teste não encontrado." });
    const r = await rpc("appmax_trocar_app_url", { p_id: corpo.id, p_app_url: appUrl });
    if (!r.ok) return json(res, 400, { erro: MENSAGENS[r.dados?.message] || "Não deu para trocar o endereço." });
    return json(res, r.dados ? 200 : 404, r.dados ? { ok: true } : { erro: "Endereço de teste não encontrado ou expirado." });
  }

  const r = await rpc("appmax_criar_endereco", { p_app_url: appUrl });
  if (!r.ok) return json(res, 400, { erro: MENSAGENS[r.dados?.message] || "Não deu para criar o endereço." });
  const base = `https://${req.headers.host}`;
  return json(res, 200, {
    id: r.dados.id,
    expira_em: r.dados.expira_em,
    endereco_webhook: `${base}/api/p/${r.dados.id}`,
    acompanhar: `${base}/testar.html?id=${r.dados.id}`,
  });
};
