from pathlib import Path

from app.models import PublicRecord
from collectors.base.expenses_http import ExpensesHttpCollector

PROJECT_ROOT = Path(__file__).resolve().parents[2]
NETWORK_PATH = PROJECT_ROOT / "data" / "network" / "ceres_despesas_2026_requests.json"
CERES_EXPENSES_URL = "https://acessoainformacao.ceres.go.gov.br/cidadao/transparencia/sgdespesas"


class CeresExpensesHttpCollector:
    def __init__(self, network_path: Path = NETWORK_PATH, year: int = 2026) -> None:
        self.network_path = network_path
        self.source_url = CERES_EXPENSES_URL
        self.year = year
        self._collector = ExpensesHttpCollector(
            municipality_key="ceres",
            year=year,
            network_path=network_path,
        )

    def collect(self, length: int = 1000) -> tuple[list[PublicRecord], int]:
        return self._collector.collect(length=length)

