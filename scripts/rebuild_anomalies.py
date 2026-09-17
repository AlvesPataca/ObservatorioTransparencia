"""Script de recálculo e persistência dos pontos de revisão (anomalias).

Executa o AnomalyEngine sobre o banco SQLite e persiste em anomaly_findings
e supplier_profiles. Suporta recálculo global (--all) ou filtrado por categoria (--category).
"""

import argparse
from collections import Counter
from pathlib import Path
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import delete, func, select
from analytics.anomaly_engine import AnomalyEngine
from database.models import AnomalyFinding, Base, SupplierProfile
from database.session import SessionLocal, engine


def rebuild_anomalies(
    municipality: str | None = None,
    year: int | None = None,
    category: str | None = None,
) -> None:
    print("=" * 75)
    print("RECÁLCULO DO MOTOR DE ANOMALIAS E PONTOS DE REVISÃO")
    if category:
        print(f"Modo: Reconstrução pontual da categoria '{category}'")
    else:
        print("Modo: Reconstrução COMPLETA de todas as regras")
    print("=" * 75)

    # 1. Garantir criação das tabelas no banco de dados
    Base.metadata.create_all(engine)

    start = time.perf_counter()

    with SessionLocal() as session:
        # 2. Limpar achados antigos (específicos ou gerais)
        print("Limpando achados anteriores...")
        del_stmt = delete(AnomalyFinding)
        if category:
            # Se for payment_flow_inconsistency, limpa também a categoria correlata
            if category == "payment_flow_inconsistency":
                del_stmt = del_stmt.where(
                    AnomalyFinding.category.in_(["payment_flow_inconsistency", "requer verificação manual de agrupamento"])
                )
            else:
                del_stmt = del_stmt.where(AnomalyFinding.category == category)

        if municipality:
            del_stmt = del_stmt.where(AnomalyFinding.municipality == municipality)
        if year is not None:
            del_stmt = del_stmt.where(AnomalyFinding.year == year)

        session.execute(del_stmt)
        session.commit()

        # 3. Executar o motor analítico
        print("Executando regras auditáveis do AnomalyEngine...")
        engine_inst = AnomalyEngine(session)
        categories_arg = [category] if category else None
        findings = engine_inst.run_all(municipality=municipality, year=year, categories=categories_arg)

        # 4. Salvar no banco
        print(f"Persistindo {len(findings)} achados no banco de dados...")
        session.add_all(findings)
        session.commit()

        # 5. Métricas e sumário executivo
        cat_counter = Counter(f.category for f in findings)
        sev_counter = Counter(f.severity for f in findings)
        mun_counter = Counter(f.municipality for f in findings)
        suppliers_count = session.scalar(select(func.count(SupplierProfile.id))) or 0

    elapsed = time.perf_counter() - start

    print("-" * 75)
    print(f"Recálculo finalizado com sucesso em {elapsed:.2f} segundos!")
    print(f"Total de pontos de revisão persistidos nesta execução: {len(findings)}")
    print(f"Total de perfis de credores registrados: {suppliers_count}")
    print("\nDistribuição por Severidade:")
    for sev, count in sev_counter.items():
        print(f"  - {sev.upper():<10}: {count:>5}")

    print("\nDistribuição por Categoria:")
    for cat, count in cat_counter.most_common():
        print(f"  - {cat:<32}: {count:>5}")

    print("\nDistribuição por Município:")
    for mun, count in mun_counter.items():
        print(f"  - {mun:<20}: {count:>5}")
    print("=" * 75)


def main() -> None:
    parser = argparse.ArgumentParser(description="Recalcula anomalias e pontos de revisão.")
    parser.add_argument("--all", action="store_true", help="Recalcula todas as categorias de anomalias (padrão)")
    parser.add_argument("--category", type=str, default=None, help="Recalcula apenas a categoria especificada")
    parser.add_argument("--municipality", type=str, default=None, help="Filtra por município")
    parser.add_argument("--year", type=int, default=None, help="Filtra por exercício financeiro")

    args = parser.parse_args()
    rebuild_anomalies(municipality=args.municipality, year=args.year, category=args.category)


if __name__ == "__main__":
    main()
