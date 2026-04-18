"""
RPA — Distribuição de Passageiros em Ônibus de Excursão
========================================================
Uso:
    python main.py
    python main.py --entrada input/planilha.xlsx
    python main.py --entrada input/planilha.xlsx --saida output/resultado.xlsx
"""

import argparse
import sys
import os

# Garante que o projeto está no path independente de onde é executado
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.orchestrator.orchestrator import Orchestrator
from src.utils.logger import setup_logger

logger = setup_logger("Main")


def parse_args():
    parser = argparse.ArgumentParser(
        description="RPA - Distribuição de passageiros em ônibus de excursão"
    )
    parser.add_argument(
        "--entrada",
        type=str,
        default="input/inscricoes.xlsx",
        help="Caminho para a planilha de entrada (default: input/inscricoes.xlsx)",
    )
    parser.add_argument(
        "--saida",
        type=str,
        default=None,
        help="Caminho para o arquivo de saída (default: output/distribuicao_onibus_TIMESTAMP.xlsx)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    logger.info(f"Arquivo de entrada : {args.entrada}")
    logger.info(f"Arquivo de saída   : {args.saida or 'gerado automaticamente'}")

    orchestrator = Orchestrator(
        caminho_entrada=args.entrada,
        caminho_saida=args.saida,
    )

    resultado = orchestrator.executar()

    if resultado["status"] == "SUCESSO":
        print("\n✅ RPA executado com sucesso!")
        print(f"   📁 Arquivo gerado : {resultado['arquivo_saida']}")
        print(f"   👥 Passageiros    : {resultado['total_passageiros']}")
        print(f"   🚌 Ônibus         : {resultado['total_onibus']}")
        print(f"   🤝 Grupos         : {resultado['total_grupos']}")
        print(f"   ⏱  Duração        : {resultado['duracao_segundos']}s")
        sys.exit(0)
    else:
        print("\n❌ RPA falhou!")
        for erro in resultado["erros"]:
            print(f"   Erro: {erro}")
        sys.exit(1)


if __name__ == "__main__":
    main()
