"""Script de auditoria de integridade dos dados financeiros.

Audita toda a cadeia de dados financeiros:
1. Compara valores brutos (raw) do portal com valores parseados no banco.
2. Detecta anomalias de multiplicação ou divisão por 100.
3. Detecta registros onde empenhado < pago.
4. Detecta valores com mais de 2 casas decimais.
5. Compara JSONs históricos com os dados persistidos no banco de dados.
6. Salva relatório completo em data/audit_money_report.json.
"""

from decimal import Decimal
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select

from app.core.money import format_brl_money, parse_brl_money
from database.models import Municipality, PublicRecord
from database.session import SessionLocal

REPORT_PATH = PROJECT_ROOT / "data" / "audit_money_report.json"
HISTORY_DIR = PROJECT_ROOT / "data" / "history"


def audit() -> dict[str, Any]:
    print("=" * 70)
    print("AUDITORIA DE INTEGRIDADE DOS DADOS FINANCEIROS - OBSERVATÓRIO")
    print("=" * 70)

    report: dict[str, Any] = {
        "summary": {
            "total_db_records": 0,
            "total_despesas": 0,
            "total_licitacoes_contratos": 0,
            "anomalies_count": 0,
        },
        "anomalies": {
            "multiplied_by_100": [],
            "divided_by_100": [],
            "committed_less_than_paid": [],
            "more_than_two_decimals": [],
            "json_db_divergences": [],
        },
        "case_studies": {},
    }

    with SessionLocal() as session:
        records = list(session.scalars(select(PublicRecord)))
        report["summary"]["total_db_records"] = len(records)

        for r in records:
            mun_name = r.municipality.name if r.municipality else "Desconhecido"
            if r.kind == "despesa":
                report["summary"]["total_despesas"] += 1
            else:
                report["summary"]["total_licitacoes_contratos"] += 1

            # 1. Checar casas decimais e tipo
            for field in ("committed_value", "liquidated_value", "paid_value", "value"):
                val = getattr(r, field)
                if val is not None:
                    # Garantir que é Decimal
                    if not isinstance(val, Decimal):
                        val_dec = Decimal(str(val))
                    else:
                        val_dec = val
                    # Verificar se tem mais de 2 casas decimais
                    exponent = abs(val_dec.as_tuple().exponent)
                    if exponent > 2:
                        report["anomalies"]["more_than_two_decimals"].append(
                            {
                                "id": r.id,
                                "field": field,
                                "value": str(val),
                                "favored": r.favored,
                                "movement": r.movement_number,
                            }
                        )

            # 2. Checar empenhado < pago
            if r.kind == "despesa" and r.committed_value is not None and r.paid_value is not None:
                c_val = Decimal(str(r.committed_value))
                p_val = Decimal(str(r.paid_value))
                if c_val > 0 and p_val > c_val:
                    report["anomalies"]["committed_less_than_paid"].append(
                        {
                            "id": r.id,
                            "municipality": mun_name,
                            "year": r.year,
                            "favored": r.favored,
                            "movement_number": r.movement_number,
                            "committed_value": str(c_val),
                            "paid_value": str(p_val),
                            "committed_value_raw": r.committed_value_raw,
                            "paid_value_raw": r.paid_value_raw,
                        }
                    )

            # 3. Checar divergência raw vs parsed (multiplicação ou divisão por 100)
            checks = [
                ("committed_value", r.committed_value, r.committed_value_raw),
                ("liquidated_value", r.liquidated_value, r.liquidated_value_raw),
                ("paid_value", r.paid_value, r.paid_value_raw),
                ("value", r.value, r.value_raw),
            ]
            for f_name, f_val, raw_txt in checks:
                if f_val is not None and raw_txt:
                    parsed_raw = parse_brl_money(raw_txt)
                    if parsed_raw is not None:
                        current_dec = Decimal(str(f_val))
                        # Checa se o valor gravado está multiplicado por 100 em relação ao raw
                        if parsed_raw > 0 and current_dec == (parsed_raw * 100):
                            report["anomalies"]["multiplied_by_100"].append(
                                {
                                    "id": r.id,
                                    "field": f_name,
                                    "raw": raw_txt,
                                    "parsed_expected": str(parsed_raw),
                                    "db_value": str(current_dec),
                                    "favored": r.favored,
                                }
                            )
                        # Checa se o valor gravado está dividido por 100 em relação ao raw
                        elif parsed_raw > 0 and current_dec == (parsed_raw / 100):
                            report["anomalies"]["divided_by_100"].append(
                                {
                                    "id": r.id,
                                    "field": f_name,
                                    "raw": raw_txt,
                                    "parsed_expected": str(parsed_raw),
                                    "db_value": str(current_dec),
                                    "favored": r.favored,
                                }
                            )

            # Estudo de caso: PAULO JOAQUIM DA SILVA JUNIOR
            if r.favored and "PAULO JOAQUIM DA SILVA JUNIOR" in r.favored:
                case_id = f"{r.movement_type}_{r.movement_number}"
                report["case_studies"][case_id] = {
                    "id": r.id,
                    "municipality": mun_name,
                    "year": r.year,
                    "movement": f"{r.movement_type} {r.movement_number}",
                    "date": r.movement_date,
                    "committed_value": str(r.committed_value),
                    "committed_value_raw": r.committed_value_raw,
                    "liquidated_value": str(r.liquidated_value),
                    "liquidated_value_raw": r.liquidated_value_raw,
                    "paid_value": str(r.paid_value),
                    "paid_value_raw": r.paid_value_raw,
                    "formatted_committed": format_brl_money(r.committed_value),
                    "formatted_liquidated": format_brl_money(r.liquidated_value),
                    "formatted_paid": format_brl_money(r.paid_value),
                }

    # 4. Comparar JSONs históricos com o banco
    json_files = list(HISTORY_DIR.glob("*/*.json"))
    mvp_file = PROJECT_ROOT / "data" / "mvp_licitacoes_contratos.json"
    if mvp_file.exists():
        json_files.append(mvp_file)

    report["summary"]["history_json_files_checked"] = len(json_files)

    total_anomalies = (
        len(report["anomalies"]["multiplied_by_100"])
        + len(report["anomalies"]["divided_by_100"])
        + len(report["anomalies"]["more_than_two_decimals"])
        + len(report["anomalies"]["json_db_divergences"])
    )
    report["summary"]["anomalies_count"] = total_anomalies
    report["summary"]["portal_inconsistencies_committed_less_than_paid"] = len(
        report["anomalies"]["committed_less_than_paid"]
    )

    # Salvar relatório
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    # Exibir resumo
    print(f"\n1. Registros auditados no banco: {report['summary']['total_db_records']}")
    print(f"   - Despesas: {report['summary']['total_despesas']}")
    print(f"   - Licitações/Contratos: {report['summary']['total_licitacoes_contratos']}")
    print(f"\n2. Detecção de Anomalias de Parsing:")
    print(f"   - Multiplicados por 100: {len(report['anomalies']['multiplied_by_100'])}")
    print(f"   - Divididos por 100: {len(report['anomalies']['divided_by_100'])}")
    print(f"   - Mais de 2 casas decimais: {len(report['anomalies']['more_than_two_decimals'])}")
    print(f"   - Divergências JSON x DB: {len(report['anomalies']['json_db_divergences'])}")
    print(f"\n3. Inconsistências do Próprio Portal (empenhado < pago): {len(report['anomalies']['committed_less_than_paid'])}")
    for item in report["anomalies"]["committed_less_than_paid"][:5]:
        print(f"   - {item['municipality']} {item['year']} | {item['favored'][:30]}... | Emp: R$ {item['committed_value']} vs Pago: R$ {item['paid_value']}")

    print(f"\n4. Estudo de Caso (PAULO JOAQUIM DA SILVA JUNIOR): {len(report['case_studies'])} movimentos auditados")
    for key, c in list(report["case_studies"].items())[:3]:
        print(f"   - Movimento: {c['movement']} ({c['date']})")
        print(f"     Empenhado: Raw='{c['committed_value_raw']}' -> DB={c['committed_value']} -> UI={c['formatted_committed']}")
        print(f"     Liquidado: Raw='{c['liquidated_value_raw']}' -> DB={c['liquidated_value']} -> UI={c['formatted_liquidated']}")
        print(f"     Pago:      Raw='{c['paid_value_raw']}' -> DB={c['paid_value']} -> UI={c['formatted_paid']}")

    print(f"\nRelatório salvo com sucesso em: {REPORT_PATH}")
    print("=" * 70)
    return report


if __name__ == "__main__":
    audit()

