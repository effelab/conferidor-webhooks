// Aplicacao de exemplo publicada, para quem quer ver o porteiro funcionando antes de usar a sua.
// POST /api/exemplo/saudavel   responde 200 na hora
// POST /api/exemplo/lento      demora 7 s (passa do limite de 5 s da documentacao)
// POST /api/exemplo/quebrado   responde 500 a todo aviso
// POST /api/exemplo/estorno    responde 500 so aos avisos de estorno

const ESTORNOS = new Set(["order_refund", "order_partial_refund"]);
const MODOS = new Set(["saudavel", "lento", "quebrado", "estorno"]);

module.exports = async (req, res) => {
  const modo = req.query.modo;
  if (!MODOS.has(modo)) { res.statusCode = 404; return res.end(); }
  if (req.method !== "POST") { res.statusCode = 200; return res.end(`aplicacao de exemplo, modo ${modo}`); }
  const evento = (req.body && req.body.event) || "?";
  if (modo === "lento") await new Promise((r) => setTimeout(r, 7000));
  const quebrou = modo === "quebrado" || (modo === "estorno" && ESTORNOS.has(evento));
  res.statusCode = quebrou ? 500 : 200;
  res.end();
};
