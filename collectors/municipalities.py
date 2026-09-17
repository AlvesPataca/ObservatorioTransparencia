from dataclasses import dataclass


@dataclass(frozen=True)
class MunicipalityConfig:
    key: str
    name: str
    expenses_url: str
    endpoint_api: str
    expenses_action: str = "sgdespesas/listar"


MUNICIPALITIES = {
    "ceres": MunicipalityConfig(
        key="ceres",
        name="Ceres-GO",
        expenses_url="https://acessoainformacao.ceres.go.gov.br/cidadao/transparencia/sgdespesas",
        endpoint_api="https://acessoainformacao.ceres.go.gov.br/api",
        expenses_action="sgdespesas/listar",
    ),
    "rialma": MunicipalityConfig(
        key="rialma",
        name="Rialma-GO",
        expenses_url="https://acessoainformacao.rialma.go.gov.br/cidadao/transparencia/mgdespesas",
        endpoint_api="https://acessoainformacao.rialma.go.gov.br/api",
        expenses_action="megasoft/empenhos",
    ),
}

