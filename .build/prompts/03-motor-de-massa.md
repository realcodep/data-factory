# Etapa 3 de 5 — Motor de massa: garimpar, reservar, provisionar, montar, verificar

Antes de tudo, leia e siga `.build/prompts/00-protocolo.md`. Depois leia `.build/ESTADO.md` e `.build/DECISOES.md`.
Confirme que as etapas 1 e 2 estão concluídas; se não estiverem, termine-as primeiro.

## Objetivo

Construir as operações determinísticas do motor (sem LLM), cada uma idempotente e gravando eventos
no registro único da etapa 1. Estas operações serão orquestradas pelo planejador e expostas via MCP na etapa 4.

## Itens da etapa

### 3.1 Resolvedor de regras (`massa/motor/regras.py`)
- Dado `entidade + campo`, devolve a regra consolidada do catálogo com todas as fontes.
- Se o campo tem conflito pendente (`catalogo/conflitos.yaml`), devolve a regra marcada como `conflito`
  em vez de escolher — quem decide é o planejamento (etapa 4).
- Recusa operar se o catálogo estiver desatualizado (defasagem detectada na etapa 2).

### 3.2 Gerador de valores (`massa/motor/gerador.py`)
- Determinístico: mesma regra + mesma estratégia + mesma `seed` → mesmo valor.
- Estratégias = as variações da especificação (`valido`, `limite_inferior`, `limite_superior`, `abaixo_minimo`,
  `acima_maximo`, `vazio`, `tamanho_excedido`, `fora_dominio`, `formato_invalido`).
- Semânticas: CPF e CNPJ sintéticos com dígito verificador válido (ou inválido, para `formato_invalido`),
  datas relativas a uma data-base fixa configurável, valores monetários respeitando decimais, padrões regex simples.
- Todo valor gerado carrega `estrategia` e `fontes` da regra que o originou (rastreabilidade campo → regra → fonte).
- **Dados de entrada inválidos nunca vão para o banco**: o gerador marca o destino do valor (`precondicao` ou `entrada`)
  e o provisionador recusa gravar valor marcado como inválido.

### 3.3 Garimpo e reserva (`massa/motor/garimpo.py`, `massa/motor/reserva.py`)
- **Garimpar**: executa o predicado do estado pedido (somente leitura, sempre com limite de linhas) e devolve candidatos
  **não reservados** e **com marca de massa** permitida (configurável: só massa criada pela fábrica, ou também dados preexistentes de homologação).
- **Reservar**: reserva com prazo (`expira_em`) e uso (`compartilhavel` permite vários cenários de leitura no mesmo registro;
  `consumivel` é exclusivo). Reserva concorrente no mesmo registro consumível falha de forma limpa.
- **Liberar** e **expirar**: liberação explícita e expiração automática.
- Antes de usar um registro reservado, **reconfere o estado** (ele pode ter mudado); se mudou, libera e garimpa outro.

### 3.4 Provisionador por receitas (`massa/motor/provisionador.py`)
- Dado estado de destino, encontra no grafo do catálogo o **caminho de menor custo** a partir de um estado disponível
  (garimpado, do pool ou `inexistente`).
- Executa cada passo da receita pela interface declarada (API demo nesta construção), preenchendo campos com o gerador
  (estratégia `valido`, destino `precondicao`).
- Cada passo tem chave de idempotência (plano + passo + entidade): reexecutar não duplica; se o evento
  `registro_criado` já existe, reaproveita o resultado.
- Toda massa criada recebe **marca de origem** (ex.: campo de observação ou tabela de marcação) com plano e cenário.
- Recusa receitas com `aprovada: false` (a aprovação é tratada no planejamento).

### 3.5 Montador (`massa/motor/montador.py`)
- **Payload**: a partir da interface da operação + IDs das pré-condições + dados de entrada (incluindo inválidos de propósito).
  Valida contra o contrato: payload de cenário positivo precisa ser válido; de negativo precisa violar exatamente a variação pedida.
- **Roteiro de tela**: gera script Playwright determinístico a partir do mapa da tela (seletores estáveis), com captura de evidência
  (screenshot + texto de retorno). O roteiro é salvo como arquivo reexecutável.
- **Pacote de massa** (modo `somente_massa`): JSON com IDs, estados, valores e rastreabilidade.

### 3.6 Executor e verificador (`massa/motor/executor.py`, `massa/motor/verificador.py`)
- Executor: envia o payload (API) ou roda o roteiro (tela), grava `chamada_executada` com request, response e evidências.
- Falhas classificadas: `transitoria` (timeout, 5xx, lock) → nova tentativa com espera crescente (limite configurável);
  `dado` (pré-condição mudou) → sinaliza para regarimpar; `caminho` (receita quebrada, contrato divergente) e `politica` → devolvidas ao planejamento.
- Verificador: checa cada `resultado_esperado` **respeitando o tempo de propagação** do estado (consulta repetida até o limite),
  e registra `verificacao_concluida` com resultado, evidência e a **origem da expectativa** (funcional/técnica/premissa).

### 3.7 Época do ambiente (`massa/motor/epoca.py`)
- Calcula assinatura dos registros-sentinela. Se mudou desde o último evento `epoca_detectada`,
  invalida reservas e referências a IDs da época anterior (decisões por conceito permanecem).
- Teste: `make demo-reset` muda a época e invalida reservas.

## Critérios de saída
- [ ] Gerador determinístico comprovado por teste (mesma seed → mesmo resultado) e CPF/CNPJ com DV validados.
- [ ] Reserva consumível concorrente falha; compartilhável aceita múltiplos leitores; expiração funciona.
- [ ] Provisionador leva `inexistente` → `garantia_imobiliaria.bloqueada` passando por `credito:contrato.ativo`,
      e reexecutar o mesmo plano não duplica registros.
- [ ] Payload negativo viola exatamente a variação pedida; valor inválido nunca é gravado no banco.
- [ ] Roteiro de tela gerado executa contra a tela demo e salva evidência.
- [ ] Verificador espera a propagação assíncrona da API demo e passa; com espera desligada, falha (prova do mecanismo).
- [ ] Época: reset da demo invalida reservas.
- [ ] `.build/ESTADO.md` atualizado e commit `etapa 3: concluída`.

Ao concluir, siga o encadeamento do protocolo: abra `.build/prompts/04-planejamento-execucao.md` e execute.
