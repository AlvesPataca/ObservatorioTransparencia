import json
import re
from collections.abc import Iterable
from typing import Any
from urllib.parse import parse_qs, quote

from app.core.money import parse_brl_money
from app.models import PublicRecord
from collectors.base.expenses import parse_brazilian_decimal


def _extract_year_from_text(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"\b(20\d{2})\b", str(value))
    return int(match.group(1)) if match else None


def parse_expense_api_response(
    payload: dict[str, Any],
    municipality: str,
    source_url: str,
    year: int | None = None,
) -> tuple[int, list[PublicRecord]]:
    container = next(
        (
            value
            for value in payload.values()
            if isinstance(value, dict) and ("dados" in value or "registros" in value)
        ),
        payload,
    )
    expected_total = int(container.get("total") or 0)
    raw_items = container.get("dados") or container.get("registros") or []
    records: list[PublicRecord] = []

    for item in raw_items:
        movement_type = (
            item.get("movimento")
            or item.get("tipo")
            or item.get("tipoDoEmpenho")
            or item.get("faseDoEmpenho")
            or "Empenho"
        )
        movement_number = (
            item.get("numero")
            or item.get("empenho")
            or str(item.get("codigo") or "")
            or str(item.get("numeroDoTcm") or "")
            or None
        )
        description = (item.get("descricao") or item.get("historico") or "").strip()
        favored = (
            item.get("fornecedor")
            or item.get("nomeDoFornecedor")
            or item.get("cnpjENomeDoFornecedor")
        )
        movement_date = item.get("data")
        record_year = (
            year
            or _extract_year_from_text(item.get("ano"))
            or _extract_year_from_text(movement_date)
        )
        committed_raw = (
            item.get("valor_empenho")
            or item.get("valorDoEmpenho")
            or item.get("valorTotalDoEmpenho")
        )
        liquidated_raw = (
            item.get("liquidado")
            or item.get("valor_liquidacao")
            or item.get("valorTotalDaLiquidacao")
            or item.get("valorDaLiquidacao")
        )
        paid_raw = (
            item.get("pagamento")
            or item.get("valor_pagamento")
            or item.get("valorTotalDoPagamento")
            or item.get("valorDoPagamento")
        )
        modality = item.get("modalidade") or item.get("codigoENomeDaModalidade")
        process_number = (
            item.get("processo")
            or str(item.get("codigoDoProcesso") or "")
            or item.get("numeroEAnoDaLicitacao")
            or None
        )

        records.append(
            PublicRecord(
                municipality=municipality,
                kind="despesa",
                year=record_year,
                source_url=source_url,
                detail_url=source_url,
                title=description or f"{movement_type} {movement_number or ''}".strip(),
                object=description,
                movement_type=str(movement_type),
                movement_number=str(movement_number) if movement_number else None,
                favored=favored,
                movement_date=movement_date,
                description=description,
                committed_value=_decimal_text(committed_raw),
                liquidated_value=_decimal_text(liquidated_raw),
                paid_value=_decimal_text(paid_raw),
                committed_value_raw=str(committed_raw) if committed_raw is not None else None,
                liquidated_value_raw=str(liquidated_raw) if liquidated_raw is not None else None,
                paid_value_raw=str(paid_raw) if paid_raw is not None else None,
                modality=str(modality) if modality else None,
                process_number=str(process_number) if process_number else None,
                raw=item,
            )
        )
    return expected_total, records


def _decimal_text(value: Any) -> str | None:
    parsed = parse_brl_money(value)
    return str(parsed) if parsed is not None else None


def find_list_request(network_data: dict[str, Any], action_name: str | None = None) -> dict[str, Any]:
    candidates = (
        [action_name]
        if action_name
        else ["sgdespesas/listar", "megasoft/empenhos"]
    )
    for request in network_data.get("requests", []):
        if request.get("method") != "POST" or not request.get("url", "").rstrip("/").endswith("/api"):
            continue
        post_data = request.get("post_data") or ""
        for cand in candidates:
            if cand in post_data or quote(cand) in post_data:
                return request
    raise ValueError(f"Nenhuma requisição com as ações {candidates} foi encontrada")


def request_params(request: dict[str, Any], action_name: str | None = None) -> dict[str, Any]:
    form = parse_qs(request.get("post_data") or "")
    params_text = form.get("params", ["{}"])[0]
    params = json.loads(params_text)
    targets = (
        [action_name]
        if action_name
        else ["sgdespesas/listar", "megasoft/empenhos"]
    )
    for value in params.values():
        if isinstance(value, dict) and value.get("acao") in targets:
            return value
    raise ValueError(f"Parâmetros para ação {targets} não encontrados")



def build_expense_body(
    params: dict[str, Any],
    start: int,
    length: int,
    year: int | None = None,
) -> dict[str, str]:
    request_params_data = params.copy()
    acao = request_params_data.get("acao", "")
    if "megasoft/empenhos" in acao:
        page = (start // length) + 1
        request_params_data["pagina"] = page
        request_params_data["tamanhoDaPagina"] = length
        if year:
            request_params_data["dataInicial"] = f"01/01/{year}"
            request_params_data["dataFinal"] = f"31/12/{year}"
    else:
        request_params_data["limit"] = f"{start}, {length}"
        if year:
            request_params_data["ano"] = str(year)
            request_params_data["periodo_inicial"] = f"{year}-01-01"
            request_params_data["periodo_final"] = f"{year}-12-31"
            request_params_data.pop("mes", None)

    return {
        "multi_request": "true",
        "params": json.dumps({"expenses": request_params_data}, ensure_ascii=False),
    }



def deduplicate_api_records(records: Iterable[PublicRecord]) -> list[PublicRecord]:
    result: list[PublicRecord] = []
    seen: set[tuple[str | None, str | None, str | None, str | None]] = set()
    for record in records:
        key = (record.movement_type, record.movement_number, record.movement_date, record.favored)
        if key not in seen:
            seen.add(key)
            result.append(record)
    return result


def page_starts(expected_total: int, length: int) -> list[int]:
    if expected_total <= 0 or length <= 0:
        return []
    return list(range(0, expected_total, length))
