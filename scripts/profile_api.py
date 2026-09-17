"""Script de medição e diagnóstico de performance dos endpoints da API.

Testa os endpoints principais sob vários filtros comuns:
- Sem filtro
- municipality=Ceres-GO
- municipality=Rialma-GO
- year=2026
- kind=despesa
- q=termo comum
- filtros combinados

Imprime tempo em ms e quantidade de registros retornados.
"""

from pathlib import Path
import sys
import time
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient
from app.main import app

SCENARIOS = [
    # Summary
    ("Summary (global)", "/api/summary", {}),
    ("Summary (Ceres)", "/api/summary", {"municipality": "Ceres-GO"}),
    ("Summary (Rialma)", "/api/summary", {"municipality": "Rialma-GO"}),
    ("Summary (2026)", "/api/summary", {"year": 2026}),
    ("Summary (Despesa)", "/api/summary", {"kind": "despesa"}),
    
    # Records (paginado)
    ("Records (limit=50)", "/api/records", {"limit": 50}),
    ("Records (Ceres, limit=50)", "/api/records", {"municipality": "Ceres-GO", "limit": 50}),
    ("Records (Rialma, limit=50)", "/api/records", {"municipality": "Rialma-GO", "limit": 50}),
    ("Records (2026, limit=50)", "/api/records", {"year": 2026, "limit": 50}),
    ("Records (Despesa, limit=50)", "/api/records", {"kind": "despesa", "limit": 50}),
    ("Records (q='combustivel')", "/api/records", {"q": "combustivel", "limit": 50}),
    ("Records (q='saude')", "/api/records", {"q": "saude", "limit": 50}),
    ("Records (combinado Ceres 2026 despesa)", "/api/records", {"municipality": "Ceres-GO", "year": 2026, "kind": "despesa", "limit": 50}),
    
    # Attention
    ("Attention (limit=20)", "/api/attention", {"limit": 20}),
    ("Attention (limit=50)", "/api/attention", {"limit": 50}),
    ("Attention (Ceres, limit=20)", "/api/attention", {"municipality": "Ceres-GO", "limit": 20}),
    ("Attention (term='dispensa')", "/api/attention", {"term": "dispensa", "limit": 20}),
    ("Attention (term='combustivel')", "/api/attention", {"term": "combustivel", "limit": 20}),
    
    # Expenses Summary
    ("Expenses Summary (global)", "/api/expenses/summary", {}),
    ("Expenses Summary (Ceres 2026)", "/api/expenses/summary", {"municipality": "Ceres-GO", "year": 2026}),
    ("Expenses Summary (q='transporte')", "/api/expenses/summary", {"q": "transporte"}),
]


def profile() -> list[dict[str, Any]]:
    client = TestClient(app)
    results = []
    
    print("=" * 85)
    print(f"{'CENÁRIO':<42} | {'STATUS':<6} | {'TEMPO (ms)':<10} | {'ITENS / TOTAL'}")
    print("-" * 85)

    for label, path, params in SCENARIOS:
        start = time.perf_counter()
        res = client.get(path, params=params)
        duration_ms = (time.perf_counter() - start) * 1000.0

        item_info = "-"
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, dict):
                if "items" in data:
                    item_info = f"{len(data['items'])} items (total: {data.get('total', len(data['items']))})"
                elif "total" in data:
                    item_info = f"total: {data.get('total')}"
                elif "top_favored" in data:
                    item_info = f"{len(data['top_favored'])} top favorecidos"
                elif "totals_by_kind" in data:
                    total_kinds = sum(data["totals_by_kind"].values())
                    item_info = f"{total_kinds} total registros"
            elif isinstance(data, list):
                item_info = f"{len(data)} items"

        print(f"{label:<42} | {res.status_code:<6} | {duration_ms:>8.1f} ms | {item_info}")
        results.append({
            "scenario": label,
            "path": path,
            "params": params,
            "status_code": res.status_code,
            "duration_ms": round(duration_ms, 2),
            "item_info": item_info,
        })

    print("=" * 85)
    return results


if __name__ == "__main__":
    profile()
