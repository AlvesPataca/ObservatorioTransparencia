import json
import sys
import asyncio
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from collectors.base.client import TransparencyHttpClient
from collectors.base.browser import BrowserTransparencyCollector
from collectors.ceres import CeresCollector
from collectors.rialma import RialmaCollector


def main() -> None:
    output_path = Path("data/mvp_licitacoes_contratos.json")
    collectors = [CeresCollector(), RialmaCollector()]

    with TransparencyHttpClient() as client:
        collected = [collector.collect_mvp(client) for collector in collectors]

    browser = BrowserTransparencyCollector()
    for collector, result in zip(collectors, collected):
        portal_blocked = any(check.blocked for check in result.source_checks if "Portal" in check.label)
        if portal_blocked or not result.records:
            browser_records = asyncio.run(browser.collect(collector.municipality, collector.browser_sources))
            result.records.extend(browser_records)
            if browser_records:
                result.warnings.append("Registros coletados com fallback Playwright.")

    results = [result.model_dump(mode="json") for result in collected]

    output_path.parent.mkdir(exist_ok=True)
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    for result in results:
        print(f"\n{result['municipality']}")
        print(f"- Registros MVP encontrados: {len(result['records'])}")
        for warning in result["warnings"]:
            print(f"- Aviso: {warning}")

    print(f"\nResultado salvo em {output_path}")


if __name__ == "__main__":
    main()
