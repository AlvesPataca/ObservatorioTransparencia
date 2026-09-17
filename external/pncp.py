"""Adaptador para o Portal Nacional de Contratações Públicas (PNCP).

Permite consulta de contratações e atas registradas por CNPJ de credor ou município.
Possui cache local persistente e tratamento gracioso de falhas e rate limits.
"""

import json
import logging
from pathlib import Path
from typing import Any

import httpx

from analytics.document_normalizer import clean_digits

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "cache" / "pncp"
PNCP_BASE_URL = "https://pncp.gov.br/api/consulta/v1"


def _get_cache_path(key: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{key}.json"


def query_supplier_contracts_pncp(cnpj: str | None, page: int = 1) -> dict[str, Any]:
    """Consulta contratos no PNCP para um determinado CNPJ de fornecedor."""
    digits = clean_digits(cnpj)
    if not digits or len(digits) != 14:
        return {
            "cnpj": cnpj,
            "total": 0,
            "items": [],
            "checked": False,
            "source": "invalid_cnpj",
            "message": "CNPJ inválido ou não informado para consulta no PNCP.",
        }

    cache_file = _get_cache_path(f"cnpj_{digits}_p{page}")
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    try:
        with httpx.Client(timeout=6.0) as client:
            url = f"{PNCP_BASE_URL}/contratos"
            params = {"cnpjContratado": digits, "pagina": page, "tamanhoPagina": 10}
            resp = client.get(url, params=params)

            if resp.status_code == 200:
                data = resp.json()
                result = {
                    "cnpj": cnpj,
                    "total": data.get("totalRegistros", 0),
                    "items": data.get("data", []),
                    "checked": True,
                    "source": "pncp_api",
                    "message": "Consulta realizada com sucesso.",
                }
                try:
                    cache_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
                return result
            else:
                return {
                    "cnpj": cnpj,
                    "total": 0,
                    "items": [],
                    "checked": False,
                    "source": f"http_{resp.status_code}",
                    "message": f"PNCP retornou status {resp.status_code}",
                }
    except Exception as exc:
        logger.warning("Falha ao consultar PNCP para CNPJ %s: %s", digits, exc)
        return {
            "cnpj": cnpj,
            "total": 0,
            "items": [],
            "checked": False,
            "source": "error",
            "message": f"Serviço PNCP indisponível: {exc.__class__.__name__}",
        }

