# Decisões tomadas durante a construção

| # | Dúvida | Escolha | Degrau | Alternativas | Por quê |
|---|---|---|---|---|---|
| 1 | Onde guardar reservas (precisam de checagem atômica) | Tabela `reservas` no mesmo SQLite do motor, com todo evento espelhado no registro de eventos | premissa | Só eventos | Concorrência exige trava atômica; o registro de eventos continua sendo a fonte de auditoria |
| 2 | Banco da demo | SQLite | convenção | Postgres via Docker | Zero dependência externa; adaptador real é configurável |
| 3 | Marca de massa | Registro no ledger (eventos `registro_criado`), sem alterar as APIs | premissa | Campo/cabeçalho na API | APIs reais não aceitam marcador; o ledger funciona com qualquer sistema |
| 4 | Domínio de `motivo_bloqueio` diverge entre código (JUD, ADM, FRA) e normativo (JUD, ADM) | Mantido de propósito na demo como conflito funcional × técnico | fato | — | Exercita o tratamento de conflito e o problema do oráculo |
