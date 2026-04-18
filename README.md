🚌 rpa-excursao

Automação RPA para distribuição inteligente de passageiros em ônibus de excursão

Python 3.10+
RPA
openpyxl · pandas
MIT License
Ativo
Sobre o projeto

Este projeto automatiza o processo de organização de excursões: lê a planilha de inscrições gerada por um Google Forms, agrupa os participantes por afinidade (quem quer viajar com quem), respeita as regras de rota de cada ônibus e gera uma planilha de saída formatada, pronta para uso operacional.

O fluxo é totalmente orquestrado — com retry automático, log detalhado e detecção de conflitos —, seguindo boas práticas de arquitetura RPA com separação clara entre Input, Processing e Output.

Arquitetura

Orchestrator
controle de fluxo
retry 3×
→
Input Robot
lê · valida
normaliza
→
Processing Robot
Union-Find
Best-Fit Dec.
→
Output Robot
gera Excel
3 abas
Funcionalidades

👥
Agrupamento por afinidade

Algoritmo Union-Find conecta cadeias de amizade (A→B→C) e mantém grupos juntos no mesmo ônibus.

🚑
Regras de rota por ônibus

Cada tipo de ônibus tem pontos prioritários e permitidos, configuráveis via YAML sem alterar código.

⚙
Best-Fit Decreasing

Minimiza desperdício de assentos alocando grupos do maior ao menor no ônibus com menor sobra.

⚠
Resolução de conflitos

Detecta grupos com rotas incompatíveis e os separa inteligentemente, com aviso detalhado no log.

📄
Planilha de saída rica

Gera Excel com aba de resumo, uma aba por ônibus (colorida por rota) e lista completa filtrável.

🔄
Retry automático

Cada etapa tem até 3 tentativas automáticas com delay configurável antes de falhar definitivamente.

Regras de rota

Ônibus	Pontos prioritários	Pode complementar com	Comportamento
Jaboatão	Jaboatão Velho	Derby, Pe-15, Pelópidas, Igarassu	Único ônibus — todos juntos
Piedade	Piedade	Boa Viagem, Derby	Lota com Piedade, completa por afinidade
Derby	Derby	Pe-15, Pelópidas, Igarassu	Lota com Derby, completa por afinidade
