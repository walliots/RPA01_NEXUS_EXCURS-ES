import os
import time
import traceback
from datetime import datetime
from src.robots.input_robot import InputRobot
from src.robots.processing_robot import ProcessingRobot
from src.robots.output_robot import OutputRobot
from src.utils.logger import setup_logger
from src.utils.config_loader import load_config

logger = setup_logger("Orchestrator")


class Orchestrator:
    """
    Orquestrador principal do RPA de distribuição de excursão.

    Fluxo:
        1. InputRobot   → leitura e validação da planilha de entrada
        2. ProcessingRobot → agrupamento por afinidade + distribuição nos ônibus
        3. OutputRobot  → geração da planilha de saída formatada
    """

    MAX_TENTATIVAS = 3

    def __init__(self, caminho_entrada: str, caminho_saida: str = None):
        self.config = load_config()
        self.caminho_entrada = caminho_entrada

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.caminho_saida = caminho_saida or f"output/distribuicao_onibus_{timestamp}.xlsx"

        self.input_robot = InputRobot()
        self.processing_robot = ProcessingRobot()
        self.output_robot = OutputRobot()

    def executar(self) -> dict:
        logger.info("=" * 60)
        logger.info("  INICIANDO RPA — Distribuição de Excursão")
        logger.info("=" * 60)

        resultado = {
            "status": "ERRO",
            "arquivo_saida": None,
            "total_passageiros": 0,
            "total_onibus": 0,
            "total_grupos": 0,
            "erros": [],
            "inicio": datetime.now().isoformat(),
            "fim": None,
            "duracao_segundos": None,
        }

        inicio = time.time()

        try:
            # ── ETAPA 1: INPUT ──────────────────────────────────────────
            df = self._executar_com_retry(
                etapa="INPUT",
                func=lambda: self.input_robot.executar(self.caminho_entrada),
            )

            # ── ETAPA 2: PROCESSAMENTO ──────────────────────────────────
            df = self._executar_com_retry(
                etapa="PROCESSING",
                func=lambda: self.processing_robot.executar(df),
            )

            # ── ETAPA 3: OUTPUT ─────────────────────────────────────────
            caminho_gerado = self._executar_com_retry(
                etapa="OUTPUT",
                func=lambda: self.output_robot.executar(df, self.caminho_saida),
            )

            # ── RESULTADO FINAL ─────────────────────────────────────────
            resultado.update({
                "status": "SUCESSO",
                "arquivo_saida": caminho_gerado,
                "total_passageiros": len(df),
                "total_onibus": int(df["__onibus_num"].max()),
                "total_grupos": df["__grupo_id"].nunique(),
            })

            logger.info("=" * 60)
            logger.info("  RPA CONCLUÍDO COM SUCESSO ✅")
            logger.info(f"  Passageiros : {resultado['total_passageiros']}")
            logger.info(f"  Ônibus      : {resultado['total_onibus']}")
            logger.info(f"  Grupos      : {resultado['total_grupos']}")
            logger.info(f"  Arquivo     : {caminho_gerado}")
            logger.info("=" * 60)

        except Exception as e:
            resultado["erros"].append(str(e))
            logger.error(f"[ORCHESTRATOR] Falha crítica: {e}")
            logger.error(traceback.format_exc())

        fim = time.time()
        resultado["fim"] = datetime.now().isoformat()
        resultado["duracao_segundos"] = round(fim - inicio, 2)

        return resultado

    def _executar_com_retry(self, etapa: str, func, tentativas: int = MAX_TENTATIVAS):
        for tentativa in range(1, tentativas + 1):
            try:
                logger.info(f"[{etapa}] Tentativa {tentativa}/{tentativas}...")
                resultado = func()
                logger.info(f"[{etapa}] ✅ Concluído com sucesso.")
                return resultado
            except Exception as e:
                logger.warning(f"[{etapa}] ⚠️  Tentativa {tentativa} falhou: {e}")
                if tentativa == tentativas:
                    raise RuntimeError(f"Etapa [{etapa}] falhou após {tentativas} tentativas. Último erro: {e}")
                time.sleep(self.config["retries"]["delay_segundos"])
