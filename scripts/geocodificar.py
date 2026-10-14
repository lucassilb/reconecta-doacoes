"""Preenche o cache de coordenadas das organizações já cadastradas.

Uso (lê DATABASE_URL como o app):
    python scripts/geocodificar.py              # só quem ainda não tem coordenada
    python scripts/geocodificar.py --refinar    # tenta de novo quem ficou no centróide
    python scripts/geocodificar.py --sem-rede   # só centróide do município (offline)

Respeita a política do Nominatim (1 consulta/s, User-Agent próprio) e nunca apaga dados:
só insere ou melhora linhas de `geolocalizacoes`.
"""

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("GEO_EXTERNO", "0")  # sem fila em segundo plano: este script consulta direto

from app import app  # noqa: E402
import geo  # noqa: E402
from models import Estabelecimento, db  # noqa: E402


def main(argv=None):
    opcoes = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    opcoes.add_argument("--refinar", action="store_true",
                        help="consulta de novo endereços que estão só no centróide do município")
    opcoes.add_argument("--sem-rede", action="store_true", help="não consulta Nominatim nem BrasilAPI")
    args = opcoes.parse_args(argv)
    contagem = Counter()
    with app.app_context():
        enderecos = sorted({e for (e,) in db.session.query(Estabelecimento.endereco).all() if e})
        for endereco in enderecos:
            atual = geo.Geolocalizacao.query.filter_by(chave=geo.chave(endereco)).first()
            if atual and not (args.refinar and atual.precisao == "municipio"):
                contagem["ja_tinha_" + atual.precisao] += 1
                continue
            resultado = geo.geocodificar(endereco, externo=not args.sem_rede)
            if not resultado:
                contagem["sem_localizacao"] += 1
                continue
            linha = geo.gravar(endereco, resultado)
            db.session.commit()
            contagem[linha.precisao] += 1
    print(f"{len(enderecos)} endereço(s):", dict(sorted(contagem.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
