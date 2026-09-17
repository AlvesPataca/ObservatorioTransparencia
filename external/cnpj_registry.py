"""Adaptador para consulta de dados cadastrais de CNPJ (Receita Federal / Bases Abertas).

Obtém data de abertura, situação cadastral, atividade principal (CNAE) e porte.
Utiliza cache em disco para evitar consultas repetidas e rate limit.
"""

import json
import logging
from pathlib import Path
from typing import Any

import httpx

from analytics.document_normalizer import clean_digits

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "cache" / "cnpj"
PUBLIC_CNPJ_API = "https://brasilapi.com.br/api/cnpj/v1"


def _get_cache_path(digits: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{digits}.json"


def query_cnpj_data(cnpj: str | None) -> dict[str, Any]:
    """Consulta dados cadastrais de um CNPJ.
    
    Retorna sempre dicionário com estrutura uniforme:
    {
        "cnpj": "...",
        "razao_social": "...",
        "data_abertura": "...",
        "situacao_cadastral": "...",
        "cnae_fiscal_descricao": "...",
        "porte": "...",
        "checked": bool,
        "source": "api" | "cache" | "error" | "invalid_cnpj"
    }
    """
    digits = clean_digits(cnpj)
    if not digits or len(digits) != 14:
        return {
            "cnpj": cnpj,
            "razao_social": None,
            "data_abertura": None,
            "situacao_cadastral": None,
            "cnae_fiscal_descricao": None,
            "porte": None,
            "checked": False,
            "source": "invalid_cnpj",
        }

    # 1. Verificar cache local
    cache_file = _get_cache_path(digits)
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    # 2. Consultar API pública
    try:
        with httpx.Client(timeout=6.0) as client:
            resp = client.get(f"{PUBLIC_CNPJ_API}/{digits}")
            if resp.status_code == 200:
                d = resp.json()
                result = {
                    "cnpj": digits,
                    "razao_social": d.get("razao_social") or d.get("nome_fantasia"),
                    "data_abertura": d.get("data_inicio_atividade"),
                    "situacao_cadastral": d.get("descricao_situacao_cadastral"),
                    "cnae_fiscal_descricao": d.get("cnae_fiscal_descricao"),
                    "porte": d.get("porte"),
                    "checked": True,
                    "source": "brasilapi",
                }
                try:
                    cache_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
                return result
            else:
                return {
                    "cnpj": digits,
                    "razao_social": None,
                    "data_abertura": None,
                    "situacao_cadastral": None,
                    "cnae_fiscal_descricao": None,
                    "porte": None,
                    "checked": False,
                    "source": f"http_{resp.status_code}",
                }
    except Exception as exc:
        logger.warning("Falha ao consultar CNPJ %s: %s", digits, exc)
        return {
            "cnpj": digits,
            "razao_social": None,
            "data_abertura": None,
            "situacao_cadastral": None,
            "cnae_fiscal_descricao": None,
            "porte": None,
            "checked": False,
            "source": "error",
        }

