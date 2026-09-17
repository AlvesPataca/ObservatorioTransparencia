"""Script de auditoria de achados contábeis (payment_flow_inconsistency e agrupamentos).

Lista e valida detalhadamente todos os achados contábeis persistidos no banco de dados,
verificando se o agrupamento contábil é robusto, se os movimentos somados pertencem ao
mesmo empenho e sinalizando achados suspeitos que necessitam de revisão.
"""

import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from database.models import AnomalyFinding
from database.session import SessionLocal


def audit_accounting_findings() -> None:
    print("=" * 90)
    print("AUDITORIA DE ACHADOS CONTÁBEIS (DIVERGÊNCIA DE FLUXO ORÇAMENTÁRIO)")
    print("=" * 90)

    with SessionLocal() as session:
        categories = ["payment_flow_inconsistency", "requer verificação manual de agrupamento"]
        findings = (
            session.query(AnomalyFinding)
            .filter(AnomalyFinding.category.in_(categories))
            .order_by(AnomalyFinding.municipality, AnomalyFinding.year, AnomalyFinding.score.desc())
            .all()
        )

        if not findings:
            print("Nenhum achado contábil encontrado no banco de dados.")
            print("=" * 90)
            return

        print(f"Total de achados contábeis identificados: {len(findings)}\n")

        suspicious_count = 0
        legitimate_count = 0

        for i, f in enumerate(findings, start=1):
            try:
                ev = json.loads(f.evidence_json) if f.evidence_json else {}
            except Exception:
                ev = {}

            group_key = ev.get("accounting_key") or f"record:{f.record_id}"
            is_secure = ev.get("is_secure", False)
            mov_nums = ev.get("movement_numbers") or [ev.get("movement_number")] or []
            mov_nums = [str(m) for m in mov_nums if m is not None]
            mov_count = ev.get("movements_count", len(mov_nums) or 1)
            emp = ev.get("committed", 0.0)
            liq = ev.get("liquidated", 0.0)
            pag = ev.get("paid", 0.0)
            diff = ev.get("difference", 0.0)
            period = ev.get("period", str(f.year))
            favored = ev.get("favored") or "Não identificado"

            # Critérios de marcação de achado suspeito
            suspicious_reasons = []
            if not is_secure or str(group_key).startswith("unverified"):
                suspicious_reasons.append("Chave contábil frágil / vínculo com empenho pai não comprovado")

            if len(mov_nums) > 1:
                # Verificar se todos os movimentos compartilham o mesmo prefixo de empenho
                prefixes = {m.split(".")[0] for m in mov_nums if "." in m}
                if len(prefixes) > 1:
                    suspicious_reasons.append(f"Múltiplos prefixos de empenho misturados: {prefixes}")

            if diff <= 5.0 and diff > 0:
                suspicious_reasons.append(f"Diferença residual insignificante (R$ {diff:.2f})")

            is_suspicious = len(suspicious_reasons) > 0
            status_tag = "[SUSPEITO]" if is_suspicious else "[CONSISTENTE]"
            if is_suspicious:
                suspicious_count += 1
            else:
                legitimate_count += 1

            print(f"#{i:<3} {status_tag} ID: {f.id} | Categoria: {f.category} | Severidade: {f.severity.upper()} (Score: {f.score})")
            print(f"     Município / Ano: {f.municipality} ({f.year})")
            print(f"     Favorecido      : {favored}")
            print(f"     Chave de Grupo  : {group_key} (Vínculo seguro: {is_secure})")
            print(f"     Movimentos ({mov_count}): {', '.join(mov_nums[:6])}{' ...' if len(mov_nums) > 6 else ''}")
            print(f"     Período         : {period}")
            print(f"     Empenhado       : R$ {emp:>12,.2f}")
            print(f"     Liquidado       : R$ {liq:>12,.2f}")
            print(f"     Pago            : R$ {pag:>12,.2f}")
            print(f"     Divergência     : R$ {diff:>12,.2f}")

            if is_suspicious:
                print(f"     >>> MOTIVO DA SUSPEITA: {'; '.join(suspicious_reasons)}")
            print("-" * 90)

        print("\nRESUMO DA AUDITORIA CONTÁBIL:")
        print(f"  - Total auditado         : {len(findings)}")
        print(f"  - Achados consistentes   : {legitimate_count}")
        print(f"  - Achados suspeitos      : {suspicious_count}")
        print("=" * 90)


if __name__ == "__main__":
    audit_accounting_findings()

