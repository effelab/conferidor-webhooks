// GET /api/avisos?id=...  ->  os avisos que passaram pelo porteiro deste endereco (so os dele)

const { rpc, json, idValido } = require("./_lib");

module.exports = async (req, res) => {
  const id = req.query.id;
  if (!idValido(id)) return json(res, 404, { erro: "Endereço de teste não encontrado." });
  const endereco = await rpc("appmax_endereco", { p_id: id });
  if (!endereco.ok || !endereco.dados) return json(res, 404, { erro: "Endereço de teste não encontrado ou expirado." });
  const avisos = await rpc("appmax_listar_avisos", { p_id: id });
  return json(res, 200, { endereco: endereco.dados, avisos: avisos.ok ? avisos.dados : [] });
};
