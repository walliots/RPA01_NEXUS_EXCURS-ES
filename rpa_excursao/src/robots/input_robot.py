import pandas as pd
import os
import re
from src.utils.logger import setup_logger
from src.utils.config_loader import load_config

logger = setup_logger("InputRobot")


class InputRobot:
    """
    Responsável por ler, validar e normalizar os dados da planilha de entrada.
    """

    def __init__(self):
        self.config = load_config()
        self.cols = self.config["colunas_entrada"]

    def executar(self, caminho_arquivo: str) -> pd.DataFrame:
        logger.info(f"[INPUT] Iniciando leitura do arquivo: {caminho_arquivo}")
        self._validar_arquivo(caminho_arquivo)
        df = self._ler_planilha(caminho_arquivo)
        df = self._validar_colunas(df)
        df = self._limpar_dados(df)
        logger.info(f"[INPUT] {len(df)} registros válidos carregados.")
        return df

    def _validar_arquivo(self, caminho: str):
        if not os.path.exists(caminho):
            raise FileNotFoundError(f"Arquivo não encontrado: {caminho}")
        if not caminho.lower().endswith((".xlsx", ".xls")):
            raise ValueError(f"Formato inválido. Esperado .xlsx ou .xls: {caminho}")
        logger.info("[INPUT] Arquivo validado com sucesso.")

    def _ler_planilha(self, caminho: str) -> pd.DataFrame:
        df = pd.read_excel(caminho, dtype=str)
        df = df.dropna(how="all")
        # Remove linhas com erro do Excel (ex: #VALUE!)
        df = df[~df.apply(lambda row: row.astype(str).str.startswith("#").any(), axis=1)]
        logger.info(f"[INPUT] Planilha lida: {len(df)} linhas brutas.")
        return df

    def _validar_colunas(self, df: pd.DataFrame) -> pd.DataFrame:
        colunas_esperadas = [
            self.cols["email"], self.cols["nome"], self.cols["cpf"],
            self.cols["ponto_embarque"], self.cols["amigos"], self.cols["whatsapp"],
        ]
        faltando = [c for c in colunas_esperadas if c not in df.columns]
        if faltando:
            raise ValueError(f"Colunas ausentes na planilha: {faltando}")
        logger.info("[INPUT] Todas as colunas obrigatórias encontradas.")
        return df

    def _limpar_dados(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        # Normaliza nome
        col_nome = self.cols["nome"]
        df[col_nome] = df[col_nome].str.strip().str.upper()

        # Normaliza CPF
        col_cpf = self.cols["cpf"]
        df[col_cpf] = df[col_cpf].apply(self._normalizar_cpf)

        # Normaliza email (lowercase, strip)
        col_email = self.cols["email"]
        df[col_email] = df[col_email].str.strip().str.lower()

        # Normaliza ponto de embarque
        col_embarque = self.cols["ponto_embarque"]
        df[col_embarque] = df[col_embarque].str.strip().str.title()

        # Normaliza WhatsApp
        col_wpp = self.cols["whatsapp"]
        df[col_wpp] = df[col_wpp].apply(self._normalizar_telefone)

        # Normaliza emails de amigos → lista limpa
        col_amigos = self.cols["amigos"]
        df["__amigos_lista"] = df[col_amigos].apply(self._parsear_emails_amigos)

        # Alerta de CPF duplicado
        duplicados = df[col_cpf].duplicated(keep=False)
        if duplicados.any():
            nomes_dup = df.loc[duplicados, col_nome].tolist()
            logger.warning(f"[INPUT] CPFs duplicados encontrados: {nomes_dup}")

        # Remove linhas sem nome ou email
        antes = len(df)
        df = df.dropna(subset=[col_nome, col_email])
        df = df[df[col_nome].str.strip() != ""]
        depois = len(df)
        if antes != depois:
            logger.warning(f"[INPUT] {antes - depois} linhas removidas por nome/email vazio.")

        return df.reset_index(drop=True)

    def _normalizar_cpf(self, cpf: str) -> str:
        if pd.isna(cpf):
            return ""
        apenas_numeros = re.sub(r"\D", "", str(cpf))
        if len(apenas_numeros) == 11:
            return f"{apenas_numeros[:3]}.{apenas_numeros[3:6]}.{apenas_numeros[6:9]}-{apenas_numeros[9:]}"
        return str(cpf).strip()

    def _normalizar_telefone(self, tel: str) -> str:
        if pd.isna(tel):
            return ""
        return re.sub(r"[^\d]", "", str(tel))

    def _parsear_emails_amigos(self, valor: str) -> list:
        if pd.isna(valor) or str(valor).strip() == "":
            return []
        emails_brutos = re.split(r"[,;\s]+", str(valor).strip().lower())
        return [e.strip() for e in emails_brutos if "@" in e and e.strip()]
