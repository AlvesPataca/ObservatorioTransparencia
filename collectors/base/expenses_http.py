import json
from pathlib import Path
from typing import Any

import httpx

from app.models import PublicRecord
from collectors.base.expense_api import (
    build_expense_body,
    deduplicate_api_records,
    find_list_request,
    parse_expense_api_response,
    request_params,
)
from collectors.municipalities import MUNICIPALITIES

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ExpensesHttpCollector:
    def __init__(
        self,
        municipality_key: str,
        year: int,
        network_path: Path | None = None,
    ) -> None:
        if municipality_key not in MUNICIPALITIES:
            raise ValueError(f"Município desconhecido: {municipality_key}")
        self.municipality_key = municipality_key
        self.year = int(year)
        self.config = MUNICIPALITIES[municipality_key]
        self.endpoint_api = self.config.endpoint_api
        self.source_url = self.config.expenses_url
        self.municipality_name = self.config.name
        self.network_path = network_path or self._resolve_network_path()

    def _resolve_network_path(self) -> Path:
        year_path = PROJECT_ROOT / "data" / "network" / f"{self.municipality_key}_despesas_{self.year}_requests.json"
        if year_path.exists():
            return year_path
        fallback_path = PROJECT_ROOT / "data" / "network" / f"{self.municipality_key}_despesas_2026_requests.json"
        if fallback_path.exists():
            return fallback_path
        return year_path

    def _load_template_and_params(self) -> tuple[dict[str, Any], dict[str, Any]]:
        action = self.config.expenses_action or "sgdespesas/listar"
        if self.network_path.exists():
            network_data = json.loads(self.network_path.read_text(encoding="utf-8"))
            try:
                template = find_list_request(network_data, action_name=action)
                params = request_params(template, action_name=action)
                return template, params
            except ValueError:
                pass

        # Template sintético baseado na action configurada
        template = {
            "url": self.endpoint_api,
            "headers": {
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            },
        }
        if action == "megasoft/empenhos":
            params = {"acao": "megasoft/empenhos", "codigoDoOrgao": "10"}
        else:
            params = {"acao": "sgdespesas/listar", "order": {}}
        return template, params


    def collect(self, length: int = 1000) -> tuple[list[PublicRecord], int]:
        template, params = self._load_template_and_params()
        headers = {
            "User-Agent": template.get("headers", {}).get("user-agent", "Mozilla/5.0"),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": self.source_url,
        }

        records: list[PublicRecord] = []
        expected_total = 0
        start = 0

        with httpx.Client(headers=headers, timeout=60, follow_redirects=True) as client:
            while True:
                body = build_expense_body(params, start=start, length=length, year=self.year)
                response = client.post(self.endpoint_api, data=body)
                response.raise_for_status()

                page_total, page_records = parse_expense_api_response(
                    response.json(),
                    self.municipality_name,
                    self.source_url,
                    year=self.year,
                )
                expected_total = page_total
                records = deduplicate_api_records(records + page_records)

                print(
                    f"[despesas-http] {self.municipality_key} ano={self.year} "
                    f"start={start} length={length} coletados={len(records)} "
                    f"total_esperado={expected_total}"
                )

                if not page_records or len(records) >= expected_total:
                    break
                start += length

        return records, expected_total

