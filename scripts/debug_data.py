import json
import sys
from collections import Counter
from pathlib import Path

from sqlalchemy import func, select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from database.models import Municipality, PublicRecord
from database.session import SessionLocal


def main() -> None:
    json_paths = [
        PROJECT_ROOT / "data" / "mvp_licitacoes_contratos.json",
        PROJECT_ROOT / "data" / "ceres_despesas.json",
    ]
    print("Records no JSON por município/tipo:")
    for json_path in json_paths:
        if not json_path.exists():
            continue
        raw_payload = json.loads(json_path.read_text(encoding="utf-8"))
        payload = raw_payload if isinstance(raw_payload, list) else [raw_payload]
        for item in payload:
            records = item.get("records", [])
            counts = Counter(record.get("kind", item.get("kind", "desconhecido")) for record in records)
            print(f"- {json_path.name} / {item['municipality']}: total={sum(counts.values())}; " + ", ".join(f"{kind}={total}" for kind, total in sorted(counts.items())))

    with SessionLocal() as session:
        municipality_total = session.scalar(select(func.count(Municipality.id))) or 0
        duplicate_names = session.execute(
            select(Municipality.name, func.count(Municipality.id))
            .group_by(Municipality.name)
            .having(func.count(Municipality.id) > 1)
        ).all()
        database_totals = session.execute(
            select(Municipality.name, PublicRecord.kind, func.count(PublicRecord.id))
            .join(PublicRecord, PublicRecord.municipality_id == Municipality.id)
            .group_by(Municipality.name, PublicRecord.kind)
            .order_by(Municipality.name, PublicRecord.kind)
        ).all()
        records = session.scalars(
            select(PublicRecord).order_by(PublicRecord.id).limit(10)
        )

        print(f"\nMunicipalities no banco: {municipality_total}")
        print("Nomes duplicados em municipalities:")
        if duplicate_names:
            for name, total in duplicate_names:
                print(f"- {name}: {total}")
        else:
            print("- nenhum")
        print("\nPublic records no banco por município/tipo:")
        for municipality, kind, total in database_totals:
            print(f"- {municipality} / {kind}: {total}")
        print("\n10 primeiros public_records:")
        for record in records:
            print(f"- id={record.id} | {record.municipality.name} | {record.kind} | {record.title} | {record.detail_url}")


if __name__ == "__main__":
    main()