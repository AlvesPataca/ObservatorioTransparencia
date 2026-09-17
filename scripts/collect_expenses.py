import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from collectors.base.expenses_http import ExpensesHttpCollector
from collectors.ceres.expenses import CeresExpensesCollector
from collectors.municipalities import MUNICIPALITIES
from collectors.rialma.expenses import RialmaExpensesCollector


def main() -> None:
    parser = argparse.ArgumentParser(description="Coleta despesas públicas por município e por ano.")
    parser.add_argument("--municipality", choices=("ceres", "rialma", "all"), required=True)
    parser.add_argument("--year", type=int, help="Ano único para coleta (ex: 2026)")
    parser.add_argument("--years", type=int, nargs="+", help="Lista de anos para coleta (ex: 2025 2026)")
    parser.add_argument("--max-pages", type=int, help="Máximo de páginas no fallback Playwright")
    parser.add_argument("--length", type=int, default=1000, help="Tamanho do lote por requisição HTTP (padrão: 1000)")
    parser.add_argument("--all", action="store_true", help="Coleta todas as despesas via HTTP direto")
    args = parser.parse_args()

    if not args.year and not args.years:
        parser.error("É obrigatório informar --year (ex: --year 2026) ou --years (ex: --years 2025 2026)")

    years = [args.year] if args.year else list(args.years)
    target_municipalities = ["ceres", "rialma"] if args.municipality == "all" else [args.municipality]

    playwright_collectors = {
        "ceres": CeresExpensesCollector,
        "rialma": RialmaExpensesCollector,
    }

    for mun_key in target_municipalities:
        mun_config = MUNICIPALITIES[mun_key]
        for year in years:
            print(f"\nIniciando coleta de despesas: {mun_config.name} | Ano {year}")
            if args.all:
                http_collector = ExpensesHttpCollector(municipality_key=mun_key, year=year)
                records, expected_total = http_collector.collect(length=args.length)
                pages = (len(records) + args.length - 1) // args.length if len(records) > 0 else 0
            else:
                pw_collector = playwright_collectors[mun_key]()
                records, expected_total, pages = asyncio.run(pw_collector.collect(max_pages=args.max_pages))

            payload = {
                "municipality": mun_config.name,
                "kind": "despesa",
                "year": year,
                "source_url": mun_config.expenses_url,
                "collected_at": datetime.now(UTC).isoformat(),
                "total_expected": expected_total,
                "pages_collected": pages,
                "records": [record.model_dump(mode="json") for record in records],
            }

            output_dir = PROJECT_ROOT / "data" / "history" / mun_key
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"despesas_{year}.json"
            output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

            print(f"Salvo em {output_path}")
            print(f"Total coletado: {len(records)} | Esperado: {expected_total} | Páginas/lotes: {pages}")


if __name__ == "__main__":
    main()
