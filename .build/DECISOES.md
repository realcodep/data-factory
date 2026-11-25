# Decisões tomadas durante a construção

| # | Dúvida | Escolha | Degrau | Alternativas | Por quê |
|---|---|---|---|---|---|
| 1 | Onde guardar reservas (precisam de checagem atômica) | Tabela `reservas` no mesmo SQLite do motor, com todo evento espelhado no registro de eventos | premissa | Só eventos | Concorrência exige trava atômica; o registro de eventos continua sendo a fonte de auditoria |
| 2 | Banco da demo | SQLite | convenção | Postgres via Docker | Zero dependência externa; adaptador real é configurável |
| 3 | Marca de massa | Registro no ledger (eventos `registro_criado`), sem alterar as APIs | premissa | Campo/cabeçalho na API | APIs reais não aceitam marcador; o ledger funciona com qualquer sistema |
| 4 | Domínio de `motivo_bloqueio` diverge entre código (JUD, ADM, FRA) e normativo (JUD, ADM) | Mantido de propósito na demo como conflito funcional × técnico | fato | — | Exercita o tratamento de conflito e o problema do oráculo |
| 5 | Estado sem receita (contrato liquidado) quebrava a validação de alcançabilidade | Atributo `somente_garimpo: true` no estado | premissa | Criar API fictícia de liquidação | Em ambientes reais há estados que só se obtêm por garimpo; o modelo precisa representar isso |
| 6 | Divergência entre fonte funcional e técnica | Vira conflito, não é resolvido pelo build | fato (especificação 2.2) | Mais restritiva vence | A divergência define o oráculo; resolver sozinho mascararia um possível defeito |
| 7 | Contrato da API (OpenAPI) | Exportado da API demo para `catalogo/*/openapi.json` e versionado | premissa | Ler do servidor em tempo de build | Build reprodutível e sem dependência de serviço no ar |
| 8 | Valor válido de campo com conflito de domínio | Usa a interseção funcional ∩ técnica | convenção | Escolher uma das fontes | Valor válido para ambas dispensa decisão; o conflito só vira pendência quando o teste depende dele |
| 9 | Retomada de provisionamento: entidade já avançou além do estado intermediário | Em replay, só o destino final é reconferido | premissa | Reconferir tudo | Reconferir intermediários falharia sempre numa retomada legítima |
| 10 | Execução de roteiro de tela | Script Playwright salvo em arquivo e executado como subprocesso | premissa | Executar in-process | O roteiro fica reexecutável fora do motor (cenário executável, pipeline) |
| 11 | SDK MCP instalado é 2.x (FastMCP renomeado para MCPServer) | Import com fallback 2.x → 1.x | duas_leituras | Fixar mcp<2 | Funciona nas duas versões sem custo |
| 12 | Grupos paralelizáveis | O plano expõe os grupos; o condutor executa em série | premissa | Executar em threads | Série é mais simples de auditar; paralelismo pode ser ligado depois sem mudar o plano |
| 13 | Cenário negativo de regra de estado (ex.: desassociar garantia bloqueada) não tem variação de campo | Negativo exige variação inválida OU pré-condição explícita | fato (domínio) | Exigir sempre variação | Regras de negócio negativas são, em geral, de estado e não de campo |
| 14 | Verificação "foi rejeitado" sem código HTTP definido | Verificações `aceito` (2xx) e `rejeitado` (4xx) além de `http_status` | premissa | Só código exato | Normativos dizem "rejeitar", não qual código; evita inventar oráculo técnico |
| 15 | Degraus 1–3 informados pelo agente | `registrar_decisao` recusa fato/convenção/precedente vindos do agente | fato (arquitetura) | Aceitar | Esses degraus são do motor; o agente decide a partir de premissa |
