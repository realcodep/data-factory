"""Contratos de dados da Fábrica de Massa de Testes.

Estes esquemas são a fronteira entre a camada com IA (QA Lead) e o motor determinístico.
O motor só aceita o que valida aqui.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# ───────────────────────── enumerações ─────────────────────────

Operacao = Literal["inclusao", "associacao", "bloqueio", "desassociacao", "exclusao", "consulta", "alteracao"]
TipoCenario = Literal["positivo", "negativo", "limite"]
ModoExecucao = Literal["somente_massa", "payload", "api", "tela"]
Uso = Literal["compartilhavel", "consumivel"]
OrigemExpectativa = Literal["funcional", "tecnica", "premissa"]
OrigemFonte = Literal["copybook", "java", "banco", "openapi", "domain_pack", "funcional", "convencao"]

VARIACOES_INVALIDAS = {"abaixo_minimo", "acima_maximo", "vazio", "tamanho_excedido", "fora_dominio", "formato_invalido"}
VARIACOES_LIMITE = {"limite_inferior", "limite_superior"}
Variacao = Literal[
    "valido", "limite_inferior", "limite_superior", "abaixo_minimo", "acima_maximo",
    "vazio", "tamanho_excedido", "fora_dominio", "formato_invalido",
]


class Degrau(str, Enum):
    FATO = "fato"
    CONVENCAO = "convencao"
    PRECEDENTE = "precedente"
    PREMISSA = "premissa"
    DUAS_LEITURAS = "duas_leituras"
    PARCIAL = "parcial"
    HUMANO = "humano"


# ───────────────────────── especificação do cenário ─────────────────────────

class Precondicao(BaseModel):
    estado: str                      # id de estado do catálogo, ex.: "garantias:garantia_imobiliaria.associada"
    uso: Uso = "compartilhavel"
    papel: str | None = None         # nome lógico na suíte, ex.: "garantia", "contrato"


class VariacaoCampo(BaseModel):
    campo: str
    regra: Variacao


class ResultadoEsperado(BaseModel):
    descricao: str
    verificacao: dict[str, Any]      # ex.: {"http_status": 422} ou {"estado": "garantias:...bloqueada", "papel": "garantia"}
    origem: OrigemExpectativa
    fonte: str | None = None         # id de fato funcional, arquivo:linha ou id de decisão


class EspecificacaoCenario(BaseModel):
    id: str
    titulo: str
    origem_texto: str | None = None
    operacao: Operacao
    entidade: str
    tipo: TipoCenario
    precondicoes: list[Precondicao] = Field(default_factory=list)
    entradas: dict[str, Any] = Field(default_factory=dict)
    variacoes: list[VariacaoCampo] = Field(default_factory=list)
    resultado_esperado: list[ResultadoEsperado] = Field(default_factory=list)
    modo_execucao: ModoExecucao = "api"
    seed: int = 42

    @model_validator(mode="after")
    def _coerencia(self) -> "EspecificacaoCenario":
        if self.tipo in ("negativo", "limite") and not self.variacoes:
            raise ValueError("cenário negativo/limite exige ao menos uma variação")
        if self.tipo == "negativo" and not any(v.regra in VARIACOES_INVALIDAS for v in self.variacoes):
            raise ValueError("cenário negativo exige variação inválida")
        return self

    @property
    def avisos(self) -> list[str]:
        avisos = []
        if self.resultado_esperado and all(r.origem == "tecnica" for r in self.resultado_esperado):
            avisos.append("oraculo_nao_independente")
        if not self.resultado_esperado and self.modo_execucao in ("api", "tela"):
            avisos.append("sem_resultado_esperado")
        return avisos


class Suite(BaseModel):
    id: str
    historia: str | None = None
    cluster: str = "garantias"
    autor: str | None = None
    cenarios: list[EspecificacaoCenario]

    @field_validator("cenarios")
    @classmethod
    def _ids_unicos(cls, v: list[EspecificacaoCenario]):
        ids = [c.id for c in v]
        if len(ids) != len(set(ids)):
            raise ValueError("ids de cenário repetidos na suíte")
        return v


# ───────────────────────── catálogo ─────────────────────────

class Fonte(BaseModel):
    origem: OrigemFonte
    referencia: str
    trecho: str = ""


class RegraCampo(BaseModel):
    entidade: str | None = None
    campo: str
    tipo: Literal["str", "int", "decimal", "date", "bool", "enum"] = "str"
    tamanho: int | None = None
    decimais: int | None = None
    obrigatorio: bool = False
    minimo: float | None = None
    maximo: float | None = None
    padrao: str | None = None
    dominio: list[Any] | None = None
    semantica: str | None = None
    fontes: list[Fonte] = Field(default_factory=list)
    conflito: dict[str, Any] | None = None   # preenchido quando fontes funcionais e técnicas divergem


class Filtro(BaseModel):
    tabela: str
    chave_local: str
    chave_remota: str
    filtros: dict[str, Any] = Field(default_factory=dict)
    trazer: dict[str, str] = Field(default_factory=dict)   # atributo -> coluna da tabela relacionada


class Predicado(BaseModel):
    tabela: str
    chave: str
    filtros: dict[str, Any] = Field(default_factory=dict)
    existe: list[Filtro] = Field(default_factory=list)
    nao_existe: list[Filtro] = Field(default_factory=list)


class Estado(BaseModel):
    id: str                                   # "cluster:entidade.estado"
    cluster: str
    entidade: str
    descricao: str
    predicado: Predicado | None = None        # None => estado virtual (ex.: inexistente)
    propagacao_max_s: float = 0.0
    sinonimos: list[str] = Field(default_factory=list)
    somente_garimpo: bool = False             # estado que não tem receita: só pode ser obtido por garimpo


class PassoReceita(BaseModel):
    tipo: Literal["api", "transacao", "job"] = "api"
    interface: str                            # id da operação no mapa de interfaces
    campos_gerados: list[str] = Field(default_factory=list)
    parametros: dict[str, str] = Field(default_factory=dict)  # nome -> "papel.chave" (ex.: "id_contrato": "contrato.id")
    devolve: str | None = None                # chave do registro criado/afetado, ex.: "id_garantia"
    registra: dict[str, str] = Field(default_factory=dict)  # atributo da instância -> "papel.chave"


class Receita(BaseModel):
    id: str
    cluster: str
    entidade: str
    operacao: str | None = None               # operação de negócio que esta receita representa
    origem: str
    destino: str
    requer: dict[str, str] = Field(default_factory=dict)  # papel -> estado exigido de outra entidade
    passos: list[PassoReceita]
    efeito: Literal["cria", "transforma", "consome"]
    custo: int = 1
    aprovada: bool = True


class CampoInterface(BaseModel):
    campo: str
    caminho_json: str | None = None
    seletor: str | None = None


class InterfaceApi(BaseModel):
    id: str
    metodo: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    caminho: str
    campos: list[CampoInterface] = Field(default_factory=list)
    status_sucesso: list[int] = Field(default_factory=lambda: [200, 201])
    tela: dict[str, Any] | None = None        # {"rota", "botao", "sucesso", "erro", "campos": [{campo, seletor}]}


# ───────────────────────── plano, decisões, reservas ─────────────────────────

class Decisao(BaseModel):
    pendencia_id: str
    assinatura: str                           # chave estável para precedentes
    duvida: str
    degrau: Degrau
    escolha: Any
    alternativas: list[Any] = Field(default_factory=list)
    justificativa: str
    evidencias: list[str] = Field(default_factory=list)
    confianca: float = 1.0
    reversivel: bool = True


class Pendencia(BaseModel):
    id: str
    tipo: Literal["termo_desconhecido", "conflito_regra", "oraculo_sem_fonte", "receita_nao_aprovada",
                  "sem_caminho", "aprovacao", "lacuna_catalogo", "falha_caminho", "falha_politica"]
    assinatura: str
    cenarios: list[str] = Field(default_factory=list)
    duvida: str
    opcoes: list[Any] = Field(default_factory=list)
    evidencias: list[str] = Field(default_factory=list)
    afeta_resultado: bool = False
    custo_cobrir_todas: Literal["baixo", "alto"] = "alto"
    reversivel: bool = True
    decisao: Decisao | None = None


class Passo(BaseModel):
    id: str
    fase: str
    acao: Literal["validar", "garimpar", "reservar", "provisionar", "gerar_entrada", "montar", "executar",
                  "verificar", "entregar"]
    cenario: str | None = None
    instancia: str | None = None              # instância de pré-condição (compartilhada ou não)
    dados: dict[str, Any] = Field(default_factory=dict)
    depende_de: list[str] = Field(default_factory=list)


class Fase(BaseModel):
    id: Literal["F0", "F1", "F2", "F3", "F4", "F5", "F6", "F7"]
    nome: str
    criterio_saida: str
    risco: Literal["baixo", "medio", "alto"] = "baixo"
    tentativas: int = 3
    compensacao: str | None = None
    passos: list[Passo] = Field(default_factory=list)


class Instancia(BaseModel):
    id: str
    estado: str
    uso: Uso
    cenarios: list[str]
    estrategia: Literal["garimpar", "pool", "provisionar"] = "garimpar"
    caminho: list[str] = Field(default_factory=list)   # ids de receitas


class Plano(BaseModel):
    id: str
    versao: int = 1
    suite_id: str
    catalogo_hash: str
    instancias: list[Instancia] = Field(default_factory=list)
    fases: list[Fase] = Field(default_factory=list)
    pendencias: list[Pendencia] = Field(default_factory=list)
    aprovacao_necessaria: bool = False
    aprovado: bool = False
    acoes_previstas: list[str] = Field(default_factory=list)
    paralelizavel: list[list[str]] = Field(default_factory=list)


class Reserva(BaseModel):
    registro: str                             # "tabela:id"
    estado: str
    plano_id: str
    cenario: str | None = None
    uso: Uso
    expira_em: datetime
