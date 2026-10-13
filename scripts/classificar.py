"""Classifica nomes de alimentos no terminal com o modelo treinado.

Uso:  python scripts/classificar.py "leite integral 1L" "pao frances"
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import classificador  # noqa: E402
from llm_service import _categoria, _categoria_item  # noqa: E402


def main(textos):
    modelo = classificador.modelo_padrao()
    if not modelo:
        print("Modelo não encontrado: rode python scripts/treinar_modelo.py")
        return 1
    if not textos:
        print(__doc__.strip())
        return 2
    dados = modelo.metadados
    print(f"Modelo: {dados.get('algoritmo')} | treinado em {dados.get('treinado_em')} "
          f"com {dados.get('exemplos_no_modelo_final')} exemplos | limiar {modelo.limiar}")
    for texto in textos:
        pontos = modelo.pontuar(texto)
        print(f"\n\"{texto}\"")
        if not pontos:
            print("  sem atributo conhecido: o modelo não opina")
        for categoria, confianca in pontos[:3]:
            print(f"  {confianca:.3f}  {categoria}")
        print(f"  regra de palavras-chave: {_categoria(texto)}")
        print(f"  categoria usada pela aplicação: {_categoria_item(texto)}")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
