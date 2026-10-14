import json
import re
import tempfile
import unittest
from pathlib import Path

from conferidor import site_v2

RAIZ = site_v2.RAIZ


def _json(nome):
    return json.loads((RAIZ / nome).read_text(encoding="utf-8"))


def _texto(html):
    sem_codigo = re.sub(r"<style.*?</style>|<script.*?</script>|<svg.*?</svg>", "", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", sem_codigo))


class TestSiteV2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = site_v2.gerar()
        cls.texto = _texto(cls.html)

    def test_pagina_gera(self):
        self.assertTrue(self.html.startswith("<!doctype html>"))
        self.assertIn('lang="pt-BR"', self.html)
        for ancora in ("problema", "conferidor", "testador", "como-usar", "limites"):
            self.assertIn(f'id="{ancora}"', self.html)

    def test_sem_travessao(self):
        self.assertNotIn(chr(0x2014), self.html)
        self.assertNotIn(chr(0x2013), self.html)

    def test_numeros_do_conferidor_vem_do_json(self):
        det = _json("experimentos_resultado.json")["resumo"]["deteccao"]
        self.assertIn(f"{det['derrubados_apontados']} de {det['derrubados']} pedidos pagos sem aviso", self.texto)
        self.assertIn(f"{det['normais_apontados_por_engano']} de {det['normais_e_pendentes']} pedidos normais", self.texto)
        self.assertIn("20 de 20", self.texto)

    def test_grupos_batem_com_o_resumo_do_json(self):
        exp = _json("experimentos_resultado.json")
        grupos = site_v2.grupos_do_conferidor(exp)
        for chave, resumo in exp["resumo"]["reentrega"].items():
            self.assertEqual(grupos[chave]["pedidos"], resumo["pedidos"], chave)
            self.assertEqual(grupos[chave]["tentativas"], resumo["avisos_distintos"], chave)
            self.assertEqual(grupos[chave]["novas"], resumo["reenvios"], chave)
        self.assertIn(f"{len(exp['pedidos'])} pedidos de teste", self.texto)

    def test_contagem_do_testador_vem_do_json(self):
        linhas = _json("testador_resultado.json")["linhas"] + _json("testador_resultado_boleto_3x.json")["linhas"]
        falhou = sum(1 for x in linhas if x["resultado"] == "falhou")
        self.assertIn(f"{falhou} de {len(linhas)} cenários falharam", self.texto)
        for resultado, palavra in (("passou", "Passou"), ("inconclusivo", "Inconclusivo"), ("não executado", "Não executado")):
            n = sum(1 for x in linhas if x["resultado"] == resultado)
            self.assertIn(f"{n} {palavra}", self.texto)

    def test_aviso_de_projeto_independente_no_topo_e_no_rodape(self):
        self.assertIn('class="aviso-topo">Projeto independente', self.html)
        self.assertIn("Projeto independente de Jonas Victor Vieira Silva", self.texto)
        self.assertIn("Sem vínculo, patrocínio ou autorização da plataforma", self.texto)

    def test_ressalvas_visiveis(self):
        for trecho in ("não é a homologação", "Um app só", "Janela de reentrega ainda aberta", "Em observação",
                       "Causa desconhecida", "Segundo a documentação pública", "suposição"):
            self.assertIn(trecho, self.texto)

    def test_sem_link_externo_alem_das_fontes(self):
        externos = set(re.findall(r'(?:href|src)="(https?://[^"/]+)', self.html))
        self.assertEqual(externos, {"https://fonts.googleapis.com", "https://fonts.gstatic.com"})

    def test_estado_vazio_sem_resultados(self):
        with tempfile.TemporaryDirectory() as pasta:
            html = site_v2.gerar(site_v2.carregar(Path(pasta)))
        self.assertEqual(html.count("Ainda não há resultado"), 2)
        self.assertNotIn(chr(0x2014), html)


if __name__ == "__main__":
    unittest.main()
