# Fábrica de Massa de Testes — instruções do repositório

Estas regras valem para qualquer agente que trabalhe neste repositório.

1. **Ambiente:** opere somente em homologação ou no ambiente demo. Nunca em produção.
2. **Dados:** use sempre dados sintéticos. Nunca coloque dados reais (CPF, CNPJ, contrato, nome de cliente) em cenários, decisões ou saídas.
3. **Caminho único:** toda massa passa pelo servidor MCP `massa`. Nunca escreva SQL, nunca chame APIs diretamente, nunca edite o banco.
4. **Vocabulário fechado:** use apenas entidades, estados, operações, campos e variações do vocabulário do catálogo (`vocabulario`).
   Termo desconhecido é pendência, não invenção.
5. **Oráculo:** toda expectativa de resultado declara a origem — `funcional` (normativo, história, fato do Domain Pack),
   `tecnica` (código) ou `premissa` (decisão registrada). Prefira sempre fonte funcional.
6. **Autonomia:** siga a escada de autonomia (skill `resolver-pendencias`) e pergunte ao humano só quando for impossível decidir.
7. **Escopo:** nunca amplie a suíte por conta própria; cenários complementares vão como sugestão no relatório.
