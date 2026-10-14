"""Roda a bancada inteira: python -m conferidor.demo"""
import json
import sys
from pathlib import Path

from .relatorio import duracao, gerar, inteiro, pct, reais
from .simulador import cenarios, rodar


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raiz = Path(__file__).resolve().parent.parent
    resultados = []
    for cenario in cenarios():
        r = rodar(cenario)
        resultados.append(r)
        print(f"\n{r['nome']}  ({r['segundos']} s)")
        print(f"  avisos perdidos ............ {inteiro(r['avisos_perdidos'])}")
        print(f"  pedidos pagos sem aviso .... {inteiro(r['pedidos_pagos_sem_aviso'])}  ({reais(r['valor_pago_sem_aviso'])})")
        print(f"  estado errado sem / com .... {inteiro(r['errados_sem_conferidor'])} / {inteiro(r['errados_com_conferidor'])}")
        print(f"  cobertura .................. {pct(r['cobertura'])}")
        print(f"  atraso mediano ............. {duracao(r['atraso_mediano_min'])}")
        print(f"  consultas a API ............ {inteiro(r['consultas'])}  ({pct(r['consultas_pct_da_quota'], 0)} da quota)")
    (raiz / "relatorio.html").write_text(gerar(resultados), encoding="utf-8")
    (raiz / "resultado.json").write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nRelatorio: {raiz / 'relatorio.html'}")


if __name__ == "__main__":
    main()
