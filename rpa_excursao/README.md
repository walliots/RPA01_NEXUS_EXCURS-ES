# 🚌 RPA — Distribuição de Passageiros em Ônibus de Excursão

Automação responsável por **ler a planilha de inscrições**, **agrupar passageiros por afinidade** e **distribuir nos ônibus** respeitando a capacidade máxima de 48 pessoas por veículo.

---

## 📁 Estrutura do Projeto

```
rpa_excursao/
├── main.py                          # Ponto de entrada da automação
├── requirements.txt                 # Dependências Python
├── config/
│   └── config.yaml                  # Configurações (capacidade, colunas, logs)
├── input/
│   └── inscricoes.xlsx              # ⬅️ Planilha de entrada (coloque aqui)
├── output/
│   └── distribuicao_onibus.xlsx     # ⬅️ Planilha gerada automaticamente
├── logs/
│   └── rpa_excursao.log             # Log de execução
└── src/
    ├── orchestrator/
    │   └── orchestrator.py          # Orquestrador — controla o fluxo e retries
    ├── robots/
    │   ├── input_robot.py           # Leitura, validação e normalização dos dados
    │   ├── processing_robot.py      # Agrupamento por afinidade + distribuição
    │   └── output_robot.py          # Geração da planilha de saída formatada
    └── utils/
        ├── logger.py                # Configuração de logs (arquivo + console)
        └── config_loader.py         # Carregamento do config.yaml
```

---

## ⚙️ Como Usar

### 1. Instalar dependências
```bash
pip install -r requirements.txt
```

### 2. Colocar a planilha na pasta `input/`
```
input/inscricoes.xlsx
```

### 3. Executar
```bash
# Uso padrão (lê de input/inscricoes.xlsx, salva em output/)
python main.py

# Com caminhos personalizados
python main.py --entrada "caminho/planilha.xlsx" --saida "caminho/saida.xlsx"
```

---

## 🔄 Fluxo do RPA

```
┌─────────────────────────────────────────────────────────────┐
│                        ORCHESTRATOR                         │
│  Controla o fluxo, retries (3x por etapa) e logging        │
└──────────────────┬──────────────────────────────────────────┘
                   │
          ┌────────▼────────┐
          │   INPUT ROBOT   │
          │                 │
          │ • Valida arquivo │
          │ • Lê planilha   │
          │ • Normaliza CPF │
          │ • Normaliza nome│
          │ • Parseia emails│
          │   de amigos     │
          │ • Alerta CPFs   │
          │   duplicados    │
          └────────┬────────┘
                   │ DataFrame limpo
          ┌────────▼─────────────┐
          │   PROCESSING ROBOT   │
          │                      │
          │ • Union-Find para    │
          │   conectar cadeias   │
          │   de amizade (A→B→C) │
          │                      │
          │ • Best-Fit Decreasing│
          │   para alocar grupos │
          │   nos ônibus         │
          │                      │
          │ • Divide grupos      │
          │   maiores que 48     │
          └────────┬─────────────┘
                   │ DataFrame com ônibus
          ┌────────▼────────┐
          │  OUTPUT ROBOT   │
          │                 │
          │ • Aba Resumo    │
          │ • Aba por ônibus│
          │ • Aba completa  │
          │ • Formatação    │
          │   profissional  │
          └─────────────────┘
```

---

## 🧠 Algoritmos

### Agrupamento por Afinidade — Union-Find
O campo `Email dos amigos com quem vai viajar` pode criar cadeias de amizade:
- Ana indicou Bob e Carlos
- Bob indicou Dana

Com Union-Find, **todos ficam no mesmo grupo** automaticamente, mesmo que não se conheçam diretamente.

### Distribuição nos Ônibus — Best-Fit Decreasing
- Ordena grupos do maior para o menor
- Para cada grupo, busca o ônibus com **menor espaço sobrando** que ainda comporta o grupo
- Se nenhum comportar, **abre um novo ônibus**
- Minimiza desperdício de assentos e fragmentação de grupos

---

## 📊 Planilha de Saída

A planilha gerada contém **3 abas**:

| Aba | Conteúdo |
|-----|----------|
| 📊 Resumo | Totais gerais + tabela de ocupação por ônibus |
| 🚌 Ônibus XX | Uma aba por ônibus com lista de passageiros agrupados por afinidade |
| 📋 Lista Completa | Todos os passageiros com filtros, ordenados por ônibus e grupo |

---

## ⚠️ Alertas e Validações

| Situação | Comportamento |
|----------|---------------|
| CPFs duplicados | Log de **WARNING** com nomes afetados |
| Email de amigo não encontrado | Log de **DEBUG** (pessoa pode ter indicado alguém que não se inscreveu) |
| Grupo maior que 48 pessoas | Log de **WARNING** + divisão automática em sub-grupos |
| Arquivo não encontrado | Erro com mensagem clara |
| Coluna ausente na planilha | Erro listando as colunas faltantes |
| Falha em qualquer etapa | Retry automático até 3 vezes |

---

## 🛠️ Configurações (`config/config.yaml`)

```yaml
onibus:
  capacidade_maxima: 48      # Altere aqui para mudar a capacidade
  prefixo_nome: "Ônibus"     # Ex: "Bus" ou "Van"
```

---

## 💡 Sugestões de Melhoria Futura

1. **Balanceamento por ponto de embarque** — tentar manter passageiros do mesmo ponto no mesmo ônibus para otimizar a rota
2. **Interface web simples** — upload de planilha via browser (Flask/Streamlit)
3. **Envio automático por e-mail** — notificar passageiros com o ônibus designado
4. **Validação de CPF** — checar dígitos verificadores
5. **Agendamento** — executar via cron ou task scheduler para processar inscrições diariamente
6. **Painel de monitoramento** — histórico de execuções e métricas
