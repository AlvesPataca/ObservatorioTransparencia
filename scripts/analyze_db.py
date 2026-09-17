import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from analytics.anomalies import (
    detect_duplicate_titles,
    detect_missing_values,
    detect_same_title_across_municipalities,
    detect_suspicious_keywords,
)
from analytics.reports import (
    recent_records,
    records_by_kind,
    records_by_municipality,
    records_by_status,
    records_missing_value,
    top_modalities,
)
from database.session import SessionLocal


def main() -> None:
    with SessionLocal() as session:
        report = {
            "records_by_municipality": records_by_municipality(session),
            "records_by_kind": records_by_kind(session),
            "records_by_status": records_by_status(session),
            "top_modalities": top_modalities(session),
            "records_missing_value": records_missing_value(session),
            "recent_records": recent_records(session),
            "duplicate_titles": detect_duplicate_titles(session),
            "same_title_across_municipalities": detect_same_title_across_municipalities(session),
            "suspicious_keywords": detect_suspicious_keywords(session),
        }

    output_path = PROJECT_ROOT / "data" / "analysis_report.json"
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Relatório de analytics")
    print("\nRegistros por município:")
    for name, total in report["records_by_municipality"].items():
        print(f"- {name}: {total}")
    print("\nRegistros por tipo:")
    for kind, total in report["records_by_kind"].items():
        print(f"- {kind}: {total}")
    print("\nRegistros por status:")
    for status, total in report["records_by_status"].items():
        print(f"- {status}: {total}")
    print("\nModalidades mais comuns:")
    for item in report["top_modalities"]:
        print(f"- {item['modality']}: {item['total']}")
    print(f"\nRegistros sem valor: {len(report['records_missing_value'])}")
    print(f"Títulos repetidos: {len(report['duplicate_titles'])}")
    print(f"Títulos iguais entre municípios: {len(report['same_title_across_municipalities'])}")
    print(f"Pontos de atenção por palavras-chave: {len(report['suspicious_keywords'])}")
    print(f"\nRelatório JSON salvo em {output_path}")


if __name__ == "__main__":
    main()