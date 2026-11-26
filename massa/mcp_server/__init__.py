"""Servidor MCP `massa`: expõe o motor ao agente QA Lead.

- Credenciais e conexões ficam aqui; nenhuma ferramenta devolve credencial ou SQL.
- Não há ferramenta de SQL livre nem de escrita direta no banco.
- O Guardião é aplicado dentro do servidor (vale para qualquer cliente: Copilot, Cline, Claude Code).

Execução:  python -m massa.mcp_server            (stdio)
           python -m massa.mcp_server --http     (HTTP streamable)
"""
from __future__ import annotations

import sys
from typing import Any

try:  # SDK MCP 2.x
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:  # SDK MCP 1.x
    from mcp.server.fastmcp import FastMCP

from massa.planejamento.servico import Servico


def criar_servidor(servico: Servico) -> FastMCP:
    mcp = FastMCP("massa", instructions=(
        "Motor determinístico da Fábrica de Massa de Testes. Fluxo: vocabulario -> planejar_suite -> simular_plano -> "
        "pendencias -> registrar_decisao/registrar_perguntas -> (solicitar_aprovacao) -> executar_plano -> relatorio."))

    @mcp.tool()
    def vocabulario() -> dict:
        """Vocabulário fechado do catálogo: entidades, estados (com sinônimos), operações, campos e variações."""
        return servico.vocabulario()

    @mcp.tool()
    def consultar_catalogo(entidade: str | None = None, estado: str | None = None) -> dict:
        """Regras de campo (com fontes), fatos de negócio e conflitos de uma entidade, ou detalhes de um estado."""
        return servico.consultar_catalogo(entidade, estado)

    @mcp.tool()
    def validar_especificacao(especificacao: dict) -> dict:
        """Valida uma EspecificacaoCenario antes de planejar."""
        return servico.validar_especificacao(especificacao)

    @mcp.tool()
    def planejar_suite(suite: dict) -> dict:
        """Cria o plano em fases para uma suíte (lista de especificações). Determinístico."""
        return servico.planejar_suite(suite)

    @mcp.tool()
    def simular_plano(plano_id: str) -> dict:
        """Plano a seco: só leituras. Resolve fato/convenção/precedente e devolve as pendências para o QA Lead."""
        return servico.simular_plano(plano_id)

    @mcp.tool()
    def pendencias(plano_id: str) -> list:
        """Pendências ainda sem decisão."""
        return servico.pendencias(plano_id)

    @mcp.tool()
    def registrar_decisao(plano_id: str, pendencia_id: str, escolha: Any, degrau: str, justificativa: str,
                          evidencias: list[str] | None = None, confianca: float = 0.7, reversivel: bool = True) -> dict:
        """Registra a decisão do QA Lead (degraus: premissa, duas_leituras, parcial, humano)."""
        return servico.registrar_decisao(plano_id, pendencia_id, escolha, degrau, justificativa, evidencias,
                                         confianca, reversivel)

    @mcp.tool()
    def registrar_interpretacao(plano_id: str, cenarios: list[str], duvida: str, escolha: Any, degrau: str,
                                justificativa: str, confianca: float = 0.7) -> dict:
        """Registra decisões de interpretação (ex.: duas_leituras) tomadas antes do plano."""
        return servico.registrar_interpretacao(plano_id, cenarios, duvida, escolha, degrau, justificativa, confianca)

    @mcp.tool()
    def registrar_perguntas(plano_id: str, perguntas: list[dict]) -> dict:
        """Registra as perguntas feitas ao humano (todas juntas), para métricas e auditoria."""
        return servico.registrar_perguntas(plano_id, perguntas)

    @mcp.tool()
    def solicitar_aprovacao(plano_id: str) -> dict:
        """Resumo do que exige aprovação única e das ações previstas."""
        return servico.solicitar_aprovacao(plano_id)

    @mcp.tool()
    def aprovar_plano(plano_id: str, aprovador: str) -> dict:
        """Registra a aprovação humana do plano (somente após confirmação explícita do usuário)."""
        return servico.aprovar_plano(plano_id, aprovador)

    @mcp.tool()
    def executar_plano(plano_id: str) -> dict:
        """Executa o plano de ponta a ponta com checkpoint por passo."""
        return servico.executar_plano(plano_id)

    @mcp.tool()
    def status_plano(plano_id: str) -> dict:
        """Fases e passos concluídos, reservas e falhas."""
        return servico.status_plano(plano_id)

    @mcp.tool()
    def retomar_plano(plano_id: str) -> dict:
        """Retoma um plano interrompido a partir do último checkpoint válido."""
        return servico.retomar_plano(plano_id)

    @mcp.tool()
    def relatorio(plano_id: str) -> dict:
        """Relatório final: massa, verificações, decisões por degrau, pendências abertas e alertas."""
        return servico.relatorio(plano_id)

    @mcp.tool()
    def liberar_reservas(plano_id: str) -> dict:
        """Libera as reservas do plano antes do prazo."""
        return servico.liberar_reservas(plano_id)

    return mcp


def main() -> None:
    from massa.motor.contexto import Contexto
    servico = Servico(Contexto.do_ambiente())
    mcp = criar_servidor(servico)
    mcp.run("streamable-http" if "--http" in sys.argv else "stdio")


if __name__ == "__main__":
    main()
