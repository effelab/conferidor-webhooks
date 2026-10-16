// Funcoes compartilhadas do porteiro hospedado. Arquivos com "_" nao viram rota no Vercel.
// Banco: projeto Supabase de teste, esquema appmax, acessado so por funcoes (RPC) controladas.

const SUPABASE_URL = process.env.SUPABASE_URL;
const SUPABASE_CHAVE = process.env.SUPABASE_PUBLISHABLE_KEY; // chave publica: so chama as funcoes appmax_*
const SEGREDO = process.env.PORTEIRO_SEGREDO;              // prova ao banco que quem grava e o porteiro

const LIMITE_DOC_MS = 5000;   // documentacao: responder ao aviso em ate 5 s
const TEMPO_MAXIMO_MS = 9000; // o porteiro desiste antes e responde 504 a plataforma
const CORPO_MAXIMO = 64 * 1024;

async function rpc(funcao, corpo) {
  const r = await fetch(`${SUPABASE_URL}/rest/v1/rpc/${funcao}`, {
    method: "POST",
    headers: { apikey: SUPABASE_CHAVE, "Content-Type": "application/json" },
    body: JSON.stringify(corpo),
  });
  const texto = await r.text();
  let dados = null;
  try { dados = JSON.parse(texto); } catch (_) { dados = texto; }
  return { ok: r.ok, status: r.status, dados };
}

function lerCorpo(req) {
  return new Promise((resolve, reject) => {
    const partes = [];
    let tamanho = 0;
    req.on("data", (p) => {
      tamanho += p.length;
      if (tamanho > CORPO_MAXIMO) { reject(new Error("corpo_grande")); req.destroy(); return; }
      partes.push(p);
    });
    req.on("end", () => resolve(Buffer.concat(partes)));
    req.on("error", reject);
  });
}

function json(res, status, corpo) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  res.end(JSON.stringify(corpo));
}

function idValido(id) {
  return typeof id === "string" && /^[0-9a-f]{18}$/.test(id);
}

module.exports = { rpc, lerCorpo, json, idValido, SEGREDO, LIMITE_DOC_MS, TEMPO_MAXIMO_MS };
