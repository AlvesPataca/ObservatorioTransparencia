import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import func, select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from database.models import Municipality, PublicRecord
from database.session import SessionLocal


def main() -> None:
    with SessionLocal() as session:
        print("=" * 60)
        print("OBSERVATÓRIO CERES-RIALMA - RELATÓRIO DO BANCO DE DADOS")
        print("=" * 60)

        print("\n1. Registros por município:")
        totals = session.execute(
            select(Municipality.name, func.count(PublicRecord.id))
            .join(PublicRecord, PublicRecord.municipality_id == Municipality.id)
            .group_by(Municipality.name)
            .order_by(Municipality.name)
        )
        for municipality, total in totals:
            print(f"  - {municipality}: {total} registros")

        print("\n2. Registros por município, ano e tipo:")
        by_mun_year_kind = session.execute(
            select(
                Municipality.name,
                PublicRecord.year,
                PublicRecord.kind,
                func.count(PublicRecord.id),
            )
            .join(PublicRecord, PublicRecord.municipality_id == Municipality.id)
            .group_by(Municipality.name, PublicRecord.year, PublicRecord.kind)
            .order_by(Municipality.name, PublicRecord.year.desc().nullslast(), PublicRecord.kind)
        )
        for mun, yr, kind, count in by_mun_year_kind:
            yr_str = str(yr) if yr is not None else "Sem ano"
            print(f"  - {mun} | {yr_str} | {kind}: {count}")

        print("\n3. Total de despesas por ano:")
        expenses_by_year = session.execute(
            select(PublicRecord.year, func.count(PublicRecord.id))
            .where(PublicRecord.kind == "despesa")
            .group_by(PublicRecord.year)
            .order_by(PublicRecord.year.desc().nullslast())
        )
        for yr, count in expenses_by_year:
            yr_str = str(yr) if yr is not None else "Sem ano"
            print(f"  - Ano {yr_str}: {count} despesas")

        print("\n4. Totais financeiros de despesas por município e ano:")
        expenses = list(session.scalars(select(PublicRecord).where(PublicRecord.kind == "despesa")))
        financials: dict[tuple[str, int | str], dict[str, Decimal]] = {}
        for expense in expenses:
            municipality = expense.municipality.name if expense.municipality else "Desconhecido"
            yr_label = expense.year if expense.year is not None else "Sem ano"
            key = (municipality, yr_label)
            summary = financials.setdefault(
                key,
                {"committed": Decimal("0"), "liquidated": Decimal("0"), "paid": Decimal("0")},
            )
            for field, sum_key in (
                ("committed_value", "committed"),
                ("liquidated_value", "liquidated"),
                ("paid_value", "paid"),
            ):
                try:
                    summary[sum_key] += Decimal(getattr(expense, field) or "0")
                except (InvalidOperation, ValueError):
                    pass

        for (mun, yr), data in sorted(financials.items(), key=lambda x: (x[0][0], str(x[0][1]))):
            print(
                f"  - {mun} (Ano {yr}): "
                f"Empenhado = R$ {data['committed']:,.2f} | "
                f"Liquidado = R$ {data['liquidated']:,.2f} | "
                f"Pago = R$ {data['paid']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            )

        print("\n5. Primeiros 5 registros do banco:")
        records = session.scalars(select(PublicRecord).order_by(PublicRecord.id).limit(5))
        for record in records:
            mun_name = record.municipality.name if record.municipality else "-"
            yr_str = f"ano={record.year}" if record.year else "ano=-"
            print(
                f"  - [{record.kind}] {mun_name} ({yr_str}) - {record.title[:60]}... "
                f"| num={record.movement_number or record.process_number or '-'} "
                f"| valor={record.value or record.committed_value or '-'}"
            )
        print("=" * 60)


if __name__ == "__main__":
    main()
