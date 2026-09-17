import argparse
import json
import sys
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from collectors.base.expense_api import build_expense_body, find_list_request, parse_expense_api_response, request_params
from collectors.municipalities import MUNICIPALITIES


def resolve_network_path(municipality: str, year: int) -> Path:
    year_path = PROJECT_ROOT / "data" / "network" / f"{municipality}_despesas_{year}_requests.json"
    if year_path.exists():
        return year_path
    fallback_path = PROJECT_ROOT / "data" / "network" / f"{municipality}_despesas_2026_requests.json"
    if fallback_path.exists():
        return fallback_path
    return year_path


def load_template_and_params(network_path: Path, config) -> tuple[dict, dict, str]:
    action = config.expenses_action or "sgdespesas/listar"
    if network_path.exists():
        network_data = json.loads(network_path.read_text(encoding="utf-8"))
        try:
            template = find_list_request(network_data, action_name=action)
            params = request_params(template, action_name=action)
            source_url = network_data.get("url", config.expenses_url)
            return template, params, source_url
        except ValueError:
            pass

    template = {
        "url": config.endpoint_api,
        "headers": {
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        },
    }
    if action == "megasoft/empenhos":
        params = {"acao": "megasoft/empenhos", "codigoDoOrgao": "10"}
    else:
        params = {"acao": "sgdespesas/listar", "order": {}}
    return template, params, config.expenses_url



def main() -> None:
    parser = argparse.ArgumentParser(description="Reproduz a chamada HTTP de despesas observada no Playwright.")
    parser.add_argument("--municipality", choices=("ceres", "rialma"), required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--length", type=int, nargs="+", default=[100, 500, 1000])
    args = parser.parse_args()

    config = MUNICIPALITIES[args.municipality]
    network_path = resolve_network_path(args.municipality, args.year)
    template, params, source_url = load_template_and_params(network_path, config)

    headers = {
        "User-Agent": template.get("headers", {}).get("user-agent", "Mozilla/5.0"),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": source_url,
    }

    print(f"\n--- Replay Despesas: {config.name} (Ano {args.year}) ---")
    for length in args.length:
        body = build_expense_body(params, start=0, length=length, year=args.year)
        response = httpx.post(config.endpoint_api, data=body, headers=headers, timeout=60, follow_redirects=True)
        print(f"length={length} status={response.status_code} content_type={response.headers.get('content-type')}")
        try:
            total, records = parse_expense_api_response(response.json(), config.name, config.expenses_url, year=args.year)
            sample = records[0] if records else None
            sample_info = (
                f"num={sample.movement_number} data={sample.movement_date} "
                f"fav={sample.favored[:30] if sample.favored else '-'} "
                f"emp={sample.committed_value}"
                if sample
                else "nenhum"
            )
            print(
                f"  municipality={args.municipality} year={args.year} "
                f"total_esperado={total} total_retornado={len(records)} "
                f"amostra=[{sample_info}]"
            )
        except (ValueError, json.JSONDecodeError) as exc:
            print(f"  resposta não interpretada: {exc}; preview={response.text[:300]}")


if __name__ == "__main__":
    main()
