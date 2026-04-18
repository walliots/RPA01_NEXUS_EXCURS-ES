import pandas as pd
from collections import defaultdict
from src.utils.logger import setup_logger
from src.utils.config_loader import load_config

logger = setup_logger("ProcessingRobot")


class ProcessingRobot:
    """
    Agrupa passageiros por afinidade (Union-Find) e distribui nos ônibus
    respeitando regras de rota e capacidade máxima.

    Fluxo de distribuição:
      1. Ônibus Jaboatão  → todos de Jaboatão Velho em UM único ônibus
                            (pode completar com Derby/Pe-15/Pelópidas/Igarassu se sobrar)
      2. Ônibus Piedade   → prioriza Piedade, completa com Boa Viagem/Derby por afinidade
      3. Ônibus Derby     → prioriza Derby, completa com Pe-15/Pelópidas/Igarassu por afinidade
      4. Conflito afinidade x rota → mantém grupo junto (com log de aviso)
    """

    def __init__(self):
        self.config = load_config()
        self.cols = self.config["colunas_entrada"]
        self.capacidade = self.config["onibus"]["capacidade_maxima"]
        self.rotas = self.config["rotas"]
        self.col_embarque = self.cols["ponto_embarque"]
        self._pontos_norm = self._build_normalizer()

    # ──────────────────────────────────────────────────────────────────────
    # PONTO DE ENTRADA
    # ──────────────────────────────────────────────────────────────────────

    def executar(self, df: pd.DataFrame) -> pd.DataFrame:
        logger.info("[PROCESSING] Iniciando agrupamento por afinidade...")
        email_para_idx = self._mapear_email_para_indice(df)
        grupos = self._construir_grupos_afinidade(df, email_para_idx)
        df = self._atribuir_grupos(df, grupos)
        df = self._normalizar_pontos(df)
        df = self._distribuir_com_rotas(df)
        total = int(df["__onibus_num"].max())
        logger.info(f"[PROCESSING] Distribuição concluída. Total de ônibus: {total}")
        return df

    # ──────────────────────────────────────────────────────────────────────
    # UNION-FIND — agrupamento por afinidade
    # ──────────────────────────────────────────────────────────────────────

    def _mapear_email_para_indice(self, df: pd.DataFrame) -> dict:
        col_email = self.cols["email"]
        return {row[col_email]: idx for idx, row in df.iterrows()}

    def _construir_grupos_afinidade(self, df: pd.DataFrame, email_para_idx: dict) -> dict:
        parent = {i: i for i in df.index}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x, y):
            rx, ry = find(x), find(y)
            if rx != ry:
                parent[rx] = ry

        for idx, row in df.iterrows():
            for email_amigo in row.get("__amigos_lista", []):
                if email_amigo in email_para_idx:
                    union(idx, email_para_idx[email_amigo])
                else:
                    logger.debug(f"[PROCESSING] Email não encontrado: {email_amigo}")

        grupos = defaultdict(list)
        for idx in df.index:
            grupos[find(idx)].append(idx)

        logger.info(f"[PROCESSING] {len(grupos)} grupos de afinidade identificados.")
        return grupos

    def _atribuir_grupos(self, df: pd.DataFrame, grupos: dict) -> pd.DataFrame:
        df = df.copy()
        df["__grupo_id"] = -1
        for grupo_id, (_, membros) in enumerate(grupos.items(), start=1):
            for idx in membros:
                df.at[idx, "__grupo_id"] = grupo_id
        return df

    # ──────────────────────────────────────────────────────────────────────
    # NORMALIZAÇÃO DE PONTOS
    # ──────────────────────────────────────────────────────────────────────

    def _build_normalizer(self) -> dict:
        canonicos = set()
        for rota in self.rotas.values():
            canonicos.update(rota["pontos_prioritarios"])
            canonicos.update(rota["pontos_permitidos"])
        return {self._simplificar(nome): nome for nome in canonicos}

    def _simplificar(self, texto: str) -> str:
        import unicodedata
        sem_acento = unicodedata.normalize("NFD", str(texto))
        sem_acento = "".join(c for c in sem_acento if unicodedata.category(c) != "Mn")
        return sem_acento.strip().lower()

    def _normalizar_pontos(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        def mapear(ponto):
            chave = self._simplificar(str(ponto))
            canonico = self._pontos_norm.get(chave)
            if canonico is None:
                logger.warning(f"[PROCESSING] Ponto desconhecido: '{ponto}' — mantido como está.")
                return ponto
            return canonico

        df[self.col_embarque] = df[self.col_embarque].apply(mapear)
        return df

    # ──────────────────────────────────────────────────────────────────────
    # DISTRIBUIÇÃO COM REGRAS DE ROTA
    # ──────────────────────────────────────────────────────────────────────

    def _distribuir_com_rotas(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["__onibus_num"] = -1
        df["__onibus_tipo"] = ""
        self._proximo_num = [1]

        df = self._resolver_conflitos_afinidade(df)

        rotas_ordenadas = sorted(self.rotas.items(), key=lambda x: x[1]["prioridade"])
        for rota_key, rota_cfg in rotas_ordenadas:
            if rota_cfg["onibus_unico"]:
                df = self._alocar_onibus_unico(df, rota_key, rota_cfg)
            else:
                df = self._alocar_rota_prioritaria(df, rota_key, rota_cfg)

        restantes = df[df["__onibus_num"] == -1].index.tolist()
        if restantes:
            logger.info(f"[PROCESSING] {len(restantes)} passageiros sem rota definida → alocação genérica.")
            df = self._alocar_genericos(df, restantes)

        return df

    def _novo_onibus(self, tipo: str) -> int:
        num = self._proximo_num[0]
        self._proximo_num[0] += 1
        logger.info(f"[PROCESSING] Novo ônibus aberto: Ônibus {num:02d} [{tipo}]")
        return num

    # ── CONFLITOS DE AFINIDADE ─────────────────────────────────────────────

    def _resolver_conflitos_afinidade(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Estratégia de resolução de conflitos em 3 níveis:

        1. Sem conflito → mantém grupo intacto.

        2. Rotas COMPATÍVEIS entre si (ex: Derby + Pe-15 + Igarassu, que cabem
           no mesmo ônibus) → mantém grupo intacto, atribui rota dominante.

        3. Rotas INCOMPATÍVEIS (ex: Piedade + Jaboatão, que NUNCA andam juntos)
           → QUEBRA o grupo em sub-grupos por rota, emitindo aviso detalhado.
           Pessoas em minoria viram sub-grupo separado da sua própria rota.
        """
        df = df.copy()
        df["__rota_pessoa"] = df[self.col_embarque].apply(self._rota_do_ponto)

        # Pré-computa compatibilidade entre rotas: duas rotas são compatíveis se
        # existe pelo menos uma rota cujos pontos_permitidos contém pontos de ambas.
        compat = self._matriz_compatibilidade()

        proximo_grupo_id = df["__grupo_id"].max() + 1

        for grupo_id, grupo_df in df.groupby("__grupo_id"):
            rotas_no_grupo = grupo_df["__rota_pessoa"].unique().tolist()

            if len(rotas_no_grupo) == 1:
                continue  # sem conflito

            # Verifica se TODAS as rotas do grupo são compatíveis entre si
            todas_compat = all(
                compat.get((r1, r2), False)
                for r1 in rotas_no_grupo
                for r2 in rotas_no_grupo
                if r1 != r2
            )

            if todas_compat:
                # Apenas atribui rota dominante e mantém juntos
                rota_dominante = grupo_df["__rota_pessoa"].value_counts().idxmax()
                logger.info(
                    f"[PROCESSING] Grupo {grupo_id} tem rotas compatíveis "
                    f"({rotas_no_grupo}) → rota dominante: '{rota_dominante}'."
                )
                for idx in grupo_df.index:
                    df.at[idx, "__rota_pessoa"] = rota_dominante
            else:
                # Há rotas incompatíveis → quebra o grupo por rota
                logger.warning(
                    f"[PROCESSING] ⚠️  Grupo {grupo_id} tem rotas INCOMPATÍVEIS: "
                    f"{rotas_no_grupo}. Quebrando em sub-grupos por rota."
                )

                # Sub-grupo por rota — cada rota vira um grupo independente
                for rota in rotas_no_grupo:
                    membros_rota = grupo_df[grupo_df["__rota_pessoa"] == rota].index.tolist()
                    nomes = grupo_df.loc[membros_rota, self.cols["nome"]].tolist()

                    if rota == grupo_df["__rota_pessoa"].value_counts().idxmax():
                        # Maioria fica com o grupo_id original
                        logger.warning(
                            f"[PROCESSING]   → Sub-grupo dominante ({rota}): {nomes} "
                            f"[mantém grupo_id {grupo_id}]"
                        )
                    else:
                        # Minoria ganha novo grupo_id
                        logger.warning(
                            f"[PROCESSING]   → Sub-grupo separado ({rota}): {nomes} "
                            f"[novo grupo_id {proximo_grupo_id}]"
                        )
                        for idx in membros_rota:
                            df.at[idx, "__grupo_id"] = proximo_grupo_id
                        proximo_grupo_id += 1

        return df

    def _matriz_compatibilidade(self) -> dict:
        """
        Duas rotas são compatíveis se os pontos de uma aparecem nos
        pontos_permitidos da outra (podem compartilhar o mesmo ônibus).
        Ex: 'derby' e 'jaboatao' são compatíveis pois Derby está em
        pontos_permitidos de Jaboatão.
        Ex: 'piedade' e 'jaboatao' são INcompatíveis.
        """
        compat = {}
        rotas = list(self.rotas.items())
        for rota_a, cfg_a in rotas:
            for rota_b, cfg_b in rotas:
                if rota_a == rota_b:
                    continue
                # Compatível se os pontos prioritários de A cabem nos permitidos de B, ou vice-versa
                prio_a = set(cfg_a["pontos_prioritarios"])
                prio_b = set(cfg_b["pontos_prioritarios"])
                perm_a = set(cfg_a["pontos_permitidos"])
                perm_b = set(cfg_b["pontos_permitidos"])

                sao_compat = bool(prio_a & perm_b) or bool(prio_b & perm_a)
                compat[(rota_a, rota_b)] = sao_compat
                compat[(rota_b, rota_a)] = sao_compat

        # Log da matriz para auditoria
        for (a, b), v in compat.items():
            if a < b:
                logger.debug(f"[PROCESSING] Compatibilidade {a} ↔ {b}: {'✅' if v else '❌'}")

        return compat

    def _rota_do_ponto(self, ponto: str) -> str:
        """
        Rota natural da pessoa = ponto prioritario da rota.
        pontos_permitidos sao apenas complementos, nao definem rota da pessoa.
        Ex: Derby e prioritario de 'derby', nao de 'jaboatao'.
        """
        # 1a passagem: pontos_prioritarios (rota natural)
        for rota_key, rota_cfg in sorted(self.rotas.items(), key=lambda x: x[1]["prioridade"]):
            if ponto in rota_cfg["pontos_prioritarios"]:
                return rota_key
        # 2a passagem: pontos_permitidos (fallback)
        for rota_key, rota_cfg in sorted(self.rotas.items(), key=lambda x: x[1]["prioridade"]):
            if ponto in rota_cfg["pontos_permitidos"]:
                return rota_key
        return "generico"

    # ── ÔNIBUS ÚNICO (Jaboatão) ────────────────────────────────────────────

    def _alocar_onibus_unico(self, df: pd.DataFrame, rota_key: str, rota_cfg: dict) -> pd.DataFrame:
        label = rota_cfg["label"]
        mask = (df["__rota_pessoa"] == rota_key) & (df["__onibus_num"] == -1)
        indices = df[mask].index.tolist()

        if not indices:
            logger.info(f"[PROCESSING] Nenhum passageiro para rota '{label}'.")
            return df

        if len(indices) <= self.capacidade:
            num = self._novo_onibus(label)
            for idx in indices:
                df.at[idx, "__onibus_num"] = num
                df.at[idx, "__onibus_tipo"] = label
            logger.info(f"[PROCESSING] Ônibus {num:02d} [{label}] → {len(indices)} passageiros.")
        else:
            logger.warning(
                f"[PROCESSING] ⚠️  Rota '{label}' tem {len(indices)} passageiros "
                f"(acima de {self.capacidade}). Dividindo em múltiplos ônibus."
            )
            for i in range(0, len(indices), self.capacidade):
                sub = indices[i:i + self.capacidade]
                num = self._novo_onibus(label)
                for idx in sub:
                    df.at[idx, "__onibus_num"] = num
                    df.at[idx, "__onibus_tipo"] = label
                logger.info(f"[PROCESSING] Ônibus {num:02d} [{label}] → {len(sub)} passageiros.")

        return df

    # ── ROTAS PRIORITÁRIAS (Piedade / Derby) ──────────────────────────────

    def _alocar_rota_prioritaria(self, df: pd.DataFrame, rota_key: str, rota_cfg: dict) -> pd.DataFrame:
        label = rota_cfg["label"]
        pontos_prio = set(rota_cfg["pontos_prioritarios"])

        mask_rota = (df["__rota_pessoa"] == rota_key) & (df["__onibus_num"] == -1)
        nao_alocados = df[mask_rota]

        if nao_alocados.empty:
            logger.info(f"[PROCESSING] Nenhum passageiro para rota '{label}'.")
            return df

        mask_prio = nao_alocados[self.col_embarque].isin(pontos_prio)
        idx_prio = nao_alocados[mask_prio].index.tolist()
        idx_comp = nao_alocados[~mask_prio].index.tolist()

        logger.info(f"[PROCESSING] Rota '{label}': {len(idx_prio)} prioritários, {len(idx_comp)} complementares.")

        grupos_prio = self._grupos_de(df, idx_prio)
        grupos_comp = self._grupos_de(df, idx_comp)

        grupos_prio_ord = sorted(grupos_prio.items(), key=lambda x: len(x[1]), reverse=True)
        grupos_comp_ord = sorted(grupos_comp.items(), key=lambda x: len(x[1]), reverse=True)

        onibus_abertos: list = []

        # Fase 1: prioritários
        for _, membros in grupos_prio_ord:
            nao_aloc = [m for m in membros if df.at[m, "__onibus_num"] == -1]
            if nao_aloc:
                self._fit_grupo(df, nao_aloc, label, onibus_abertos)

        # Fase 2: complementares (só em ônibus já abertos desta rota)
        for _, membros in grupos_comp_ord:
            nao_aloc = [m for m in membros if df.at[m, "__onibus_num"] == -1]
            if not nao_aloc:
                continue
            encaixou = self._fit_grupo(df, nao_aloc, label, onibus_abertos, apenas_existentes=True)
            if not encaixou:
                # Não coube em nenhum ônibus existente → abre novo
                self._fit_grupo(df, nao_aloc, label, onibus_abertos)

        total_rota = sum(1 for _, row in df.iterrows() if row["__onibus_tipo"] == label)
        logger.info(f"[PROCESSING] Rota '{label}' concluída: {total_rota} passageiros em {len(onibus_abertos)} ônibus.")
        return df

    def _grupos_de(self, df: pd.DataFrame, indices: list) -> dict:
        grupos_ids = df.loc[indices, "__grupo_id"].unique() if indices else []
        return {gid: df[df["__grupo_id"] == gid].index.tolist() for gid in grupos_ids}

    def _fit_grupo(self, df: pd.DataFrame, membros: list, tipo: str,
                   onibus_abertos: list, apenas_existentes: bool = False) -> bool:
        tamanho = len(membros)
        melhor_i, menor_sobra = None, self.capacidade + 1

        for i, onibus in enumerate(onibus_abertos):
            if onibus["tipo"] != tipo:
                continue
            sobra = self.capacidade - onibus["ocupacao"]
            if sobra >= tamanho and sobra < menor_sobra:
                melhor_i, menor_sobra = i, sobra

        if melhor_i is not None:
            onibus_abertos[melhor_i]["ocupacao"] += tamanho
            num = onibus_abertos[melhor_i]["num"]
            for idx in membros:
                df.at[idx, "__onibus_num"] = num
                df.at[idx, "__onibus_tipo"] = tipo
            return True

        if apenas_existentes:
            return False

        # Abre novo(s) ônibus
        if tamanho > self.capacidade:
            logger.warning(f"[PROCESSING] ⚠️  Grupo com {tamanho} pessoas excede capacidade. Dividindo...")
            for i in range(0, tamanho, self.capacidade):
                sub = membros[i:i + self.capacidade]
                num = self._novo_onibus(tipo)
                onibus_abertos.append({"num": num, "tipo": tipo, "ocupacao": len(sub)})
                for idx in sub:
                    df.at[idx, "__onibus_num"] = num
                    df.at[idx, "__onibus_tipo"] = tipo
        else:
            num = self._novo_onibus(tipo)
            onibus_abertos.append({"num": num, "tipo": tipo, "ocupacao": tamanho})
            for idx in membros:
                df.at[idx, "__onibus_num"] = num
                df.at[idx, "__onibus_tipo"] = tipo

        return True

    # ── GENÉRICOS ──────────────────────────────────────────────────────────

    def _alocar_genericos(self, df: pd.DataFrame, indices: list) -> pd.DataFrame:
        grupos = self._grupos_de(df, indices)
        grupos_ord = sorted(grupos.items(), key=lambda x: len(x[1]), reverse=True)
        onibus_abertos: list = []
        for _, membros in grupos_ord:
            nao_aloc = [m for m in membros if df.at[m, "__onibus_num"] == -1]
            if nao_aloc:
                self._fit_grupo(df, nao_aloc, "Genérico", onibus_abertos)
        return df
