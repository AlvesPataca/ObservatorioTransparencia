"""Script de auditoria de fluxo contábil de despesas (auditoria de empenhos e liquidações/pagamentos)."""

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "observatorio.db"


def audit_top_print_3510():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    query = """
        SELECT 
            id,
            municipality_id,
            year,
            kind,
            movement_type,
            movement_number,
            movement_date,
            committed_value,
            liquidated_value,
            paid_value,
            description,
            favored,
            raw_json
        FROM public_records
        WHERE (favored LIKE '%TOP PRINT%' OR movement_number LIKE '%3510%')
        ORDER BY year, id
    """

    rows = c.execute(query).fetchall()
    print(f"Total de registros encontrados: {len(rows)}\n")
    print(f"{'ID':<6} | {'Ano':<4} | {'Tipo':<12} | {'Nº Movimento':<14} | {'Data':<10} | {'Empenhado':<12} | {'Liquidado':<12} | {'Pago':<12} | {'Favorecido'}")
    print("-" * 120)

    for r in rows:
        tipo = r["movement_type"] or "-"
        num = r["movement_number"] or "-"
        data = r["movement_date"] or "-"
        emp = f"{r['committed_value']:,.2f}" if r["committed_value"] is not None else "-"
        liq = f"{r['liquidated_value']:,.2f}" if r["liquidated_value"] is not None else "-"
        pag = f"{r['paid_value']:,.2f}" if r["paid_value"] is not None else "-"
        fav = (r["favored"] or "-")[:35]

        print(f"{r['id']:<6} | {r['year']:<4} | {tipo:<12} | {num:<14} | {data:<10} | {emp:<12} | {liq:<12} | {pag:<12} | {fav}")

    # Detalhar empenho 3510 especificamente
    print("\n" + "=" * 120)
    print("DETALHAMENTO DO EMPENHO 3510 (Ceres-GO):")
    print("=" * 120)
    rows_3510 = [r for r in rows if "3510" in str(r["movement_number"])]
    for r in rows_3510:
        print(f"\n[ID {r['id']}] Ano: {r['year']} | Mov: {r['movement_number']} ({r['movement_type']}) | Data: {r['movement_date']}")
        print(f"  Empenhado: R$ {r['committed_value']} | Liquidado: R$ {r['liquidated_value']} | Pago: R$ {r['paid_value']}")
        print(f"  Descrição: {r['description']}")
        if r["raw_json"]:
            try:
                raw = json.loads(r["raw_json"])
                relevant_raw = {
                    k: raw[k] for k in [
                        "chave_empenho", "empenho", "numero", "movimento",
                        "valor_empenho", "valor_mov", "valor", "liquidado",
                        "pagamento", "acumulado_liquidado", "acumulado_pagamento"
                    ] if k in raw
                }
                print(f"  raw_json relevante: {relevant_raw}")
            except Exception:
                pass


if __name__ == "__main__":
    audit_top_print_3510()

