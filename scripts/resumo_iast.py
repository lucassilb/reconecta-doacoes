"""Agrupa relatórios por PID do sensor IAST e falha quando há achado alto."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path


def resumir(pasta):
    arquivos = sorted(pasta.glob("iast-*.json"))
    eventos = Counter()
    achados = []
    for arquivo in arquivos:
        registro = json.loads(arquivo.read_text(encoding="utf-8"))
        eventos.update(registro["eventos"])
        achados.extend(registro["achados"])
    return {"ferramenta": "sensor IAST ReConecta 1", "data": datetime.now(timezone.utc).isoformat(),
            "processos": len(arquivos), "eventos": dict(eventos), "achados": achados,
            "por_severidade": dict(Counter(a["severidade"] for a in achados))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pasta", type=Path)
    parser.add_argument("--saida", type=Path, default=Path("relatorios/seguranca/iast.json"))
    args = parser.parse_args()
    resultado = resumir(args.pasta)
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
    print(f"IAST: {resultado['processos']} processos, {resultado['eventos']}, "
          f"{resultado['por_severidade']}")
    if not resultado["processos"]:
        raise SystemExit("IAST: nenhum processo instrumentado; verifique RECONECTA_IAST=1")
    if resultado["por_severidade"].get("ALTA", 0):
        raise SystemExit("IAST: achado ALTA bloqueia o gate")


if __name__ == "__main__":
    main()
