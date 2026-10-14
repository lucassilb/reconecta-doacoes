"""Reconsulta CNPJs legados e atualiza os perfis; sem argumentos, não toca o banco.

Uso: python scripts/atualizar_perfis.py --database-url URL [--aplicar]
Sem --aplicar, apenas mostra o plano. Não executa sobre Supabase automaticamente.
"""

import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cnpj_service import ConsultaCNPJError, consultar_cnpj  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--aplicar", action="store_true")
    argumentos = parser.parse_args()
    engine = create_engine(argumentos.database_url)
    with engine.connect() as conexao:
        contas = conexao.execute(text("SELECT id, cnpj FROM estabelecimentos ORDER BY id")).all()
    falhas = []
    for conta in contas:
        try:
            dados = consultar_cnpj(conta.cnpj)
        except ConsultaCNPJError as erro:
            falhas.append((conta.id, erro.codigo))
            print(f"id={conta.id} consulta={erro.codigo}")
            continue
        natureza = dados["natureza_juridica"]["codigo"] or None
        ong = bool(dados["ativo"] and dados["sem_fins_lucrativos"])
        alimentar = bool(dados["ativo"] and dados["relacionado_alimentacao"])
        print(f"id={conta.id} natureza={natureza} ong={ong} alimentar={alimentar}")
        if argumentos.aplicar:
            with engine.begin() as conexao:
                conexao.execute(text("""UPDATE estabelecimentos SET
                    natureza_juridica_codigo=:natureza,
                    sem_fins_lucrativos=:ong,
                    atividade_alimentar=:alimentar WHERE id=:id"""),
                    {"natureza": natureza, "ong": ong, "alimentar": alimentar, "id": conta.id})
    print(f"processados={len(contas) - len(falhas)} falhas={len(falhas)} aplicado={argumentos.aplicar}")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
