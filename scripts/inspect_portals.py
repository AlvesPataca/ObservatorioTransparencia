import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from collectors.base.client import TransparencyHttpClient
from collectors.ceres import CeresCollector
from collectors.rialma import RialmaCollector


def main() -> None:
    output_path = Path("data/source_checks.json")
    collectors = [CeresCollector(), RialmaCollector()]

    with TransparencyHttpClient() as client:
        results = [collector.inspect(client).model_dump(mode="json") for collector in collectors]

    output_path.parent.mkdir(exist_ok=True)
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    for result in results:
        print(f"\n{result['municipality']}")
        for check in result["source_checks"]:
            status = check["status_code"] or "erro"
            marker = "OK" if check["accessible"] else "BLOQUEADO" if check["blocked"] else "VERIFICAR"
            print(f"- {marker} {status} {check['label']}: {check['url']}")

    print(f"\nResultado salvo em {output_path}")


if __name__ == "__main__":
    main()
