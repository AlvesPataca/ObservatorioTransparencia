"""Adaptador para o Portal da Transparência do Governo Federal (CEIS / CNEP).

Consulta sanções de empresas e pessoas físicas cadastradas no CEIS e CNEP.
Inclui cache local resiliente e fallback gracioso (nunca lança exceção impeditiva).
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx

from analytics.document_normalizer import clean_digits

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "cache" / "portal_transparencia"
BASE_URL = "https://api.portaldatransparencia.gov.br/api-de-dados"


def _get_cache_path(document: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    digits = clean_digits(document)
    return CACHE_DIR / f"{digits}.json"


def check_sanctions_ceis_cnep(document: str | None, api_key: str | None = None) -> dict[str, Any]:
    """Consulta sanções no CEIS e CNEP para o CPF ou CNPJ informado.
    
    Retorna sempre um dicionário estruturado:
    {
        "document": "...",
        "has_sanctions": bool,
        "ceis_records": [...],
        "cnep_records": [...],
        "checked": bool,
        "source": "api" | "cache" | "fallback_no_key" | "error",
        "message": "..."
    }
    """
    digits = clean_digits(document)
    if not digits or len(digits) not in (11, 14):
        return {
            "document": document,
            "has_sanctions": False,
            "ceis_records": [],
            "cnep_records": [],
            "checked": False,
            "source": "invalid_document",
            "message": "Documento não informado ou com formato inválido para consulta de sanções.",
        }

    # 1. Verificar cache local
    cache_file = _get_cache_path(digits)
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    # 2. Obter chave de API (variável de ambiente ou parâmetro)
    token = api_key or os.getenv("PORTAL_TRANSPARENCIA_API_KEY")
    if not token:
        # Modo planejado: sem chave configurada, retorna estrutura limpa sem travar
        result = {
            "document": document,
            "has_sanctions": False,
            "ceis_records": [],
            "cnep_records": [],
            "checked": False,
            "source": "fallback_no_key",
            "message": "Chave da API do Portal da Transparência não configurada (PORTAL_TRANSPARENCIA_API_KEY).",
        }
        return result

    # 3. Executar chamada HTTP com timeout e controle de erro
    headers = {"chave-api-dados": token, "Accept": "application/json"}
    ceis_data = []
    cnep_data = []
    try:
        with httpx.Client(timeout=6.0) as client:
            # Consulta CEIS
            r_ceis = client.get(f"{BASE_URL}/ceis", params={"codigoSancionado": digits}, headers=headers)
            if r_ceis.status_code == 200:
                ceis_data = r_ceis.json()

            # Consulta CNEP
            r_cnep = client.get(f"{BASE_URL}/cnep", params={"codigoSancionado": digits}, headers=headers)
            if r_cnep.status_code == 200:
                cnep_data = r_cnep.json()

        has_sanctions = bool(ceis_data or cnep_data)
        result = {
            "document": document,
            "has_sanctions": has_sanctions,
            "ceis_records": ceis_data,
            "cnep_records": cnep_data,
            "checked": True,
            "source": "api",
            "message": "Consulta realizada com sucesso.",
        }

        # Salvar em cache
        try:
            cache_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

        return result

    except Exception as exc:
        logger.warning("Falha na consulta ao Portal da Transparência para %s: %s", digits, exc)
        return {
            "document": document,
            "has_sanctions": False,
            "ceis_records": [],
            "cnep_records": [],
            "checked": False,
            "source": "error",
            "message": f"Serviço temporariamente indisponível: {exc.__class__.__name__}",
        }

