"""Motor analítico de anomalias e pontos de revisão contextual.

Implementa regras auditáveis, estatísticas e transparentes baseadas em
quartis (IQR), concentração orçamentária, fluxos contábeis e padrões de compras.
Utiliza estritamente linguagem técnica e neutra ('ponto de revisão', 'outlier estatístico').
"""

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
import json
import math
import re
import unicodedata
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from analytics.document_normalizer import extract_document_and_name
from app.core.money import parse_brl_money
from database.models import AnomalyFinding, Municipality, PublicRecord, SupplierProfile


def _fmt_money(val: float | Decimal | None) -> str:
    if val is None:
        return "R$ 0,00"
    num = float(val)
    # Formatação pt-BR simples
    s = f"{num:,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def _normalize_tokens(text: str | None) -> set[str]:
    if not text:
        return set()
    norm = unicodedata.normalize("NFKD", text.lower())
    without_accents = "".join(c for c in norm if not unicodedata.combining(c))
    tokens = re.findall(r"\b[a-z0-9]{3,}\b", without_accents)
    stopwords = {"referente", "aquisicao", "prestacao", "servico", "servicos", "para", "com", "por", "atender", "secretaria", "municipal", "despesa"}
    return {t for t in tokens if t not in stopwords}


def calculate_percentiles(values: list[float]) -> dict[str, float]:
    """Calcula mediana, Q1 (P25), Q3 (P75), P90, P95, P99, P99.9 e IQR."""
    if not values:
        return {
            "median": 0.0,
            "q1": 0.0,
            "q3": 0.0,
            "iqr": 0.0,
            "p90": 0.0,
            "p95": 0.0,
            "p99": 0.0,
            "p999": 0.0,
        }
    sorted_vals = sorted(values)
    n = len(sorted_vals)

    def _p(pct: float) -> float:
        k = (n - 1) * pct
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sorted_vals[int(k)]
        return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)

    q1 = _p(0.25)
    median = _p(0.50)
    q3 = _p(0.75)
    iqr = max(0.0, q3 - q1)
    p90 = _p(0.90)
    p95 = _p(0.95)
    p99 = _p(0.99)
    p999 = _p(0.999)

    return {
        "median": median,
        "q1": q1,
        "q3": q3,
        "iqr": iqr,
        "p90": p90,
        "p95": p95,
        "p99": p99,
        "p999": p999,
    }


def is_internal_or_public_entity(favored: str | None, municipality: str | None = None) -> bool:
    """Verifica se o favorecido é um ente da administração pública ou transferência interna.
    
    Exclui prefeituras, câmaras, fundos municipais, institutos de previdência e órgãos
    estatais de cálculos de concentração de fornecedores privados.
    """
    if not favored:
        return False
    norm = unicodedata.normalize("NFKD", favored.upper())
    clean = "".join(c for c in norm if not unicodedata.combining(c)).strip()

    patterns = [
        r"\bMUNICIPIO\b",
        r"\bPREFEITURA\b",
        r"\bCAMARA\s+MUNICIPAL\b",
        r"\bFUNDO\s+MUNICIPAL\b",
        r"\bFUNDO\s+DE\s+SAUDE\b",
        r"\bFMS\b",
        r"\bFME\b",
        r"\bFMAS\b",
        r"\bINSTITUTO\s+DE\s+PREVIDENCIA\b",
        r"\bPREVIDENCIA\s+MUNICIPAL\b",
        r"\bRPPS\b",
        r"\bIPASGO\b",
        r"\bSECRETARIA\s+MUNICIPAL\b",
        r"\bSECRETARIA\s+DE\s+ESTADO\b",
        r"\bESTADO\s+DE\s+GOIAS\b",
        r"\bGOVERNO\s+DO\s+ESTADO\b",
        r"\bTRIBUNAL\s+DE\s+CONTAS\b",
        r"\bMINISTERIO\s+PUBLICO\b",
        r"\bRECEITA\s+FEDERAL\b",
        r"\bINSS\b",
        r"\bPASEP\b",
        r"\bFGTS\b",
        r"\bCONSORCIO\s+PUBLICO\b",
        r"\bCONSORCIO\s+INTERMUNICIPAL\b",
    ]
    for pat in patterns:
        if re.search(pat, clean):
            return True

    if municipality:
        mun_norm = unicodedata.normalize("NFKD", municipality.upper())
        mun_clean = "".join(c for c in mun_norm if not unicodedata.combining(c)).split("-")[0].strip()
        if mun_clean and mun_clean in clean:
            if any(term in clean for term in ["MUNICIPIO", "PREFEITURA", "CAMARA", "FUNDO", "SAUDE", "EDUCACAO", "ASSISTENCIA"]):
                return True

    return False


def accounting_group_key(record: PublicRecord) -> tuple[str, bool]:
    """Retorna (chave_agrupamento, vinculo_comprovado).
    
    Identifica com precisão o empenho contábil ao qual o movimento pertence.
    Regras específicas:
    - Ceres (Megasoft):
      1. Se raw_json tiver 'chave_empenho' (ex: '[3510-20250126]'), utiliza essa chave comprovada.
      2. Se raw_json tiver 'empenho', utiliza o número do empenho comprovado.
      3. Se o número do movimento contiver prefixo comprovado com ponto (ex: '3510.8' ou '3510.8.1'),
         o primeiro segmento numérico ('3510') é o empenho comprovado no padrão Megasoft.
      4. Se for movimento com '8', '8.1', '7.1' isolados sem prefixo e sem chave comprovada no raw_json,
         NÃO inventa relação por prefixo (retorna is_secure = False).
    - Rialma:
      Utiliza o código do empenho ('codigo' no raw_json ou movement_number).
    """
    if not record:
        return ("unknown", False)

    # 1. raw_json (fonte mais segura e auditável)
    if record.raw_json:
        try:
            raw = json.loads(record.raw_json)
            # Megasoft / Ceres chave contábil interna
            chave = raw.get("chave_empenho")
            if chave:
                clean_chave = str(chave).strip(" []")
                if clean_chave:
                    return (f"chave:{clean_chave}", True)

            # Megasoft / Ceres campo 'empenho'
            emp = raw.get("empenho")
            if emp and str(emp).strip():
                clean_emp = str(emp).strip()
                ficha = str(raw.get("ficha") or record.year or "").strip()
                return (f"empenho:{clean_emp}_{ficha}", True)

            # Megasoft Rialma campo 'codigo'
            cod = raw.get("codigo")
            if cod and str(cod).strip():
                return (f"codigo:{str(cod).strip()}_{record.year or ''}", True)
        except Exception:
            pass

    # 2. process_number explícito
    proc = (record.process_number or "").strip()
    if proc and "empenho" in proc.lower():
        num_match = re.search(r"\b\d+\b", proc)
        if num_match:
            return (f"empenho:{num_match.group(0)}_{record.year or ''}", True)

    # 3. movement_number e movement_type
    num = (record.movement_number or "").strip()
    m_type = (record.movement_type or "").strip().lower()

    if not num:
        # Se for um registro autônomo com empenho próprio
        is_autonomous = (record.committed_value or Decimal("0.00")) > Decimal("0.00")
        return (f"record:{record.id}", is_autonomous)

    # Se for o próprio registro de Empenho
    if m_type == "empenho" and num.isdigit():
        return (f"empenho:{num}_{record.year or ''}", True)

    # Prefixo comprovado com ponto: ex: "3510.8" ou "3510.8.1"
    parts = num.split(".")
    if len(parts) >= 2 and parts[0].isdigit() and len(parts[0]) >= 2:
        return (f"empenho:{parts[0]}_{record.year or ''}", True)

    # Registro único com número de empenho direto sem tipo de sub-movimento
    if num.isdigit() and len(num) >= 2 and m_type not in ("pagamento", "liquidação", "liquidacao"):
        return (f"empenho:{num}_{record.year or ''}", True)

    # Sub-movimentos isolados como "8", "8.1", "7.1" sem prefixo ou raw_json comprovado
    return (f"unverified_submov:{num}_{record.id}", False)


def extract_movement_accounting_values(record: PublicRecord) -> dict[str, Decimal]:
    """Extrai os valores contábeis estritamente no mesmo nível do movimento.
    
    Evita misturar colunas cumulativas:
    - Movimento de 'Empenho': valor empenhado (não tem liquidação nem pagamento).
    - Movimento de 'Liquidação': valor liquidado deste movimento (ignora colunas de acumulado pago).
    - Movimento de 'Pagamento': valor pago deste movimento (ignora colunas de acumulado liquidado).
    - Movimento consolidado (Rialma ou 'Ordinário'/'Global'/'Estimativa'): preserva valores informados.
    """
    zero = Decimal("0.00")
    m_type = (record.movement_type or "").strip().lower()

    # 1. Tentar ler valor_mov e valor_empenho do raw_json se disponível
    v_mov = None
    v_emp_raw = None
    if record.raw_json:
        try:
            raw = json.loads(record.raw_json)
            if "valor_mov" in raw:
                v_mov = parse_brl_money(raw.get("valor_mov"))
            if "valor_empenho" in raw:
                v_emp_raw = parse_brl_money(raw.get("valor_empenho"))
        except Exception:
            pass

    rec_emp = record.committed_value or zero
    rec_liq = record.liquidated_value or zero
    rec_pag = record.paid_value or zero

    # Empenho
    if m_type == "empenho":
        emp_val = v_mov if (v_mov is not None and v_mov > zero) else (v_emp_raw if (v_emp_raw is not None and v_emp_raw > zero) else rec_emp)
        return {
            "committed": emp_val,
            "liquidated": zero,
            "paid": zero,
            "empenho_total": emp_val,
        }

    # Liquidação
    if m_type in ("liquidação", "liquidacao"):
        liq_val = v_mov if (v_mov is not None and v_mov > zero) else rec_liq
        emp_ref = v_emp_raw if (v_emp_raw is not None and v_emp_raw > zero) else rec_emp
        return {
            "committed": zero,
            "liquidated": liq_val,
            "paid": zero,
            "empenho_total": emp_ref,
        }

    # Pagamento
    if m_type == "pagamento":
        pag_val = v_mov if (v_mov is not None and v_mov > zero) else rec_pag
        emp_ref = v_emp_raw if (v_emp_raw is not None and v_emp_raw > zero) else rec_emp
        return {
            "committed": zero,
            "liquidated": zero,
            "paid": pag_val,
            "empenho_total": emp_ref,
        }

    # Registro consolidado (Rialma ou 'Ordinário'/'Global'/'Estimativa' ou teste sintético)
    return {
        "committed": rec_emp,
        "liquidated": rec_liq,
        "paid": rec_pag,
        "empenho_total": rec_emp,
    }


class AnomalyEngine:
    def __init__(self, session: Session):
        self.session = session

    def analyze_all(self, municipalities: list[str] | None = None, years: list[int] | None = None) -> int:
        """Executa regras para a lista de municípios e anos, persiste no banco e retorna a contagem de achados."""
        all_findings: list[AnomalyFinding] = []
        if municipalities:
            for mun in municipalities:
                if years:
                    for y in years:
                        all_findings.extend(self.run_all(municipality=mun, year=y))
                else:
                    all_findings.extend(self.run_all(municipality=mun))
        elif years:
            for y in years:
                all_findings.extend(self.run_all(year=y))
        else:
            all_findings.extend(self.run_all())

        self.session.add_all(all_findings)
        self.session.commit()
        return len(all_findings)

    def run_all(
        self,
        municipality: str | None = None,
        year: int | None = None,
        categories: list[str] | None = None,
    ) -> list[AnomalyFinding]:
        """Executa o pipeline de regras e gera lista de AnomalyFinding.
        
        Permite filtrar por município, ano e categorias específicas (ex: ['value_outlier']).
        """
        findings: list[AnomalyFinding] = []
        cat_filter = set(categories) if categories else None

        def _should_run(cat_name: str) -> bool:
            if not cat_filter:
                return True
            return cat_name in cat_filter

        # 1. Carregar registros filtrados
        stmt = select(PublicRecord)
        if municipality:
            stmt = stmt.join(Municipality, PublicRecord.municipality_id == Municipality.id).where(Municipality.name == municipality)
        if year is not None:
            stmt = stmt.where(PublicRecord.year == year)

        records = list(self.session.scalars(stmt))
        if not records:
            return []

        # Carregar mapa de municípios
        mun_map = {m.id: m.name for m in self.session.scalars(select(Municipality))}

        # Agrupar por (municipality_name, year)
        grouped_records: dict[tuple[str, int], list[PublicRecord]] = defaultdict(list)
        for r in records:
            m_name = mun_map.get(r.municipality_id, "Município")
            y = r.year or 0
            grouped_records[(m_name, y)].append(r)

        # Atualizar perfis de fornecedores primeiro
        supplier_profile_map = self._build_or_update_supplier_profiles(records)

        # Executar regras por grupo municipal/anual
        for (m_name, y), grp in grouped_records.items():
            if _should_run("value_outlier"):
                findings.extend(self._rule_value_outliers(m_name, y, grp))
            if _should_run("supplier_concentration"):
                findings.extend(self._rule_supplier_concentration(m_name, y, grp, supplier_profile_map))
            if _should_run("recurring_payments"):
                findings.extend(self._rule_recurring_payments(m_name, y, grp, supplier_profile_map))
            if _should_run("payment_flow_inconsistency") or _should_run("requer verificação manual de agrupamento"):
                findings.extend(self._rule_payment_flow_inconsistencies(m_name, y, grp))
            if _should_run("possible_fragmentation"):
                findings.extend(self._rule_possible_fragmentation(m_name, y, grp, supplier_profile_map))
            if _should_run("repeated_description"):
                findings.extend(self._rule_repeated_descriptions(m_name, y, grp))

        # Regras entre anos (ex: novos credores em 2026 vs 2025)
        if _should_run("new_supplier_high_value"):
            findings.extend(self._rule_new_supplier_high_value(grouped_records, supplier_profile_map))

        if cat_filter:
            findings = [f for f in findings if f.category in cat_filter]

        return findings

    def _build_or_update_supplier_profiles(self, records: list[PublicRecord]) -> dict[str, SupplierProfile]:
        """Extrai documentos e agrega histórico de credores em supplier_profiles."""
        # Agrupar registros por nome normalizado
        favored_data: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "raw_favored": "",
                "doc_info": {},
                "records_count": 0,
                "committed": Decimal("0.00"),
                "liquidated": Decimal("0.00"),
                "paid": Decimal("0.00"),
                "first_year": None,
                "first_date": None,
            }
        )

        for r in records:
            raw_fav = (r.favored or "").strip()
            if not raw_fav:
                continue
            doc_info = extract_document_and_name(raw_fav)
            norm_name = doc_info["normalized_name"]
            if not norm_name:
                continue

            entry = favored_data[norm_name]
            entry["raw_favored"] = raw_fav
            entry["doc_info"] = doc_info
            entry["records_count"] += 1
            if r.committed_value:
                entry["committed"] += r.committed_value
            if r.liquidated_value:
                entry["liquidated"] += r.liquidated_value
            if r.paid_value:
                entry["paid"] += r.paid_value

            if r.year:
                entry["first_year"] = min(entry["first_year"] or r.year, r.year)
            if r.movement_date:
                entry["first_date"] = min(entry["first_date"] or r.movement_date, r.movement_date)

        # Persistir ou recuperar SupplierProfile
        existing_profiles = {p.normalized_name: p for p in self.session.scalars(select(SupplierProfile))}
        profile_map: dict[str, SupplierProfile] = {}

        for norm_name, d in favored_data.items():
            prof = existing_profiles.get(norm_name)
            if not prof:
                prof = SupplierProfile(
                    normalized_name=norm_name,
                    document=d["doc_info"].get("document"),
                    document_type=d["doc_info"].get("document_type"),
                    first_seen_year=d["first_year"],
                    first_seen_date=d["first_date"],
                    total_records=d["records_count"],
                    total_committed=d["committed"],
                    total_liquidated=d["liquidated"],
                    total_paid=d["paid"],
                )
                self.session.add(prof)
            else:
                prof.total_records = max(prof.total_records, d["records_count"])
                prof.total_committed = d["committed"]
                prof.total_liquidated = d["liquidated"]
                prof.total_paid = d["paid"]
                if d["doc_info"].get("document") and not prof.document:
                    prof.document = d["doc_info"]["document"]
                    prof.document_type = d["doc_info"]["document_type"]

            profile_map[norm_name] = prof

        self.session.flush()
        return profile_map

    def _rule_value_outliers(
        self, municipality: str, year: int, records: list[PublicRecord]
    ) -> list[AnomalyFinding]:
        """Regra 1: Valores fora do padrão histórico (IQR estratificado e P99).
        
        - Estratifica por movement_type quando n >= 100 (ou geral se n >= 100).
        - Exige amostra mínima n >= 100.
        - Exige valor mínimo absoluto de R$ 50.000,00 e superação de Q3 + 3×IQR e P99.
        - Limita aos Top 50 achados priorizados por município/ano para evitar ruído.
        """
        all_vals = []
        by_mtype: dict[str, list[tuple[float, PublicRecord]]] = defaultdict(list)

        for r in records:
            v = float(r.paid_value or r.committed_value or r.value or 0)
            if v > 0:
                all_vals.append((v, r))
                mtype = (r.movement_type or "Geral").strip()
                by_mtype[mtype].append((v, r))

        # Requisito de amostra mínima n >= 100
        if len(all_vals) < 100:
            return []

        # Determinar grupos de análise
        groups_to_analyze: list[tuple[str, list[tuple[float, PublicRecord]], bool]] = []
        leftover: list[tuple[float, PublicRecord]] = []

        for mtype, items in by_mtype.items():
            if len(items) >= 100:
                groups_to_analyze.append((f"{municipality} / {year} ({mtype})", items, False))
            else:
                leftover.extend(items)

        if leftover:
            if groups_to_analyze:
                # Se já temos grupos estratificados grandes, os resíduos são analisados juntos se >= 100
                if len(leftover) >= 100:
                    groups_to_analyze.append((f"{municipality} / {year} (Outros tipos)", leftover, True))
            else:
                # Nenhum grupo específico atingiu 100, analisa o conjunto completo como grupo geral
                groups_to_analyze.append((f"{municipality} / {year} (Geral)", all_vals, True))

        candidates: list[tuple[int, float, AnomalyFinding]] = []

        for group_name, items, is_broad in groups_to_analyze:
            pure_vals = [it[0] for it in items]
            stats = calculate_percentiles(pure_vals)
            q3 = stats["q3"]
            iqr = stats["iqr"]
            p99 = stats["p99"]
            p999 = stats["p999"]
            extreme_threshold = q3 + (3.0 * iqr)

            # Piso de relevância orçamentária: R$ 50.000,00
            min_relevance = 50000.0

            for v, r in items:
                # Critério robusto: acima de Q3 + 3*IQR E acima de P99 E acima de R$ 50.000,00
                if v > extreme_threshold and v >= p99 and v >= min_relevance:
                    if v >= p999 or v >= 250000.0:
                        severity = "alta"
                        score = 9
                        tier = "Crítico (P99.9 ou >= R$ 250k)"
                    else:
                        severity = "alta"
                        score = 8
                        tier = "Alto (P99 e >= R$ 50k)"

                    pct_rank = round((sum(1 for x in pure_vals if x <= v) / len(pure_vals)) * 100, 2)
                    evidence = {
                        "value": v,
                        "comparison_group": group_name,
                        "sample_size": len(pure_vals),
                        "median": stats["median"],
                        "q1": stats["q1"],
                        "q3": q3,
                        "iqr": iqr,
                        "threshold_extreme": extreme_threshold,
                        "p99": p99,
                        "p99_9": p999,
                        "percentile_rank": pct_rank,
                        "is_broad_group": is_broad,
                        "tier": tier,
                        "movement_number": r.movement_number or r.process_number,
                        "movement_type": r.movement_type,
                        "favored": r.favored,
                    }

                    broad_note = " (amostra consolidada geral)" if is_broad else ""
                    finding = AnomalyFinding(
                        record_id=r.id,
                        municipality_id=r.municipality_id,
                        municipality=municipality,
                        year=year,
                        category="value_outlier",
                        severity=severity,
                        score=score,
                        title="Valor financeiro atípico (outlier estatístico P99)",
                        explanation=(
                            f"Valor de {_fmt_money(v)} supera o limiar estatístico (Q3 + 3×IQR = {_fmt_money(extreme_threshold)}) "
                            f"e o percentil 99 (P99 = {_fmt_money(p99)}) no grupo '{group_name}'{broad_note} com {len(pure_vals)} registros. "
                            f"O lançamento situa-se no percentil {pct_rank}%. Requer ateste de proporcionalidade."
                        ),
                        evidence_json=json.dumps(evidence, ensure_ascii=False),
                    )
                    candidates.append((score, v, finding))

        # Ordenar por score e valor decrescentes e reter no máximo Top 50 por município/ano
        candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return [c[2] for c in candidates[:50]]

    def _rule_supplier_concentration(
        self,
        municipality: str,
        year: int,
        records: list[PublicRecord],
        supplier_map: dict[str, SupplierProfile],
    ) -> list[AnomalyFinding]:
        """Regra 2: Concentração orçamentária por favorecido (apenas fornecedores externos)."""
        findings: list[AnomalyFinding] = []
        favored_totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
        favored_rep_record: dict[str, PublicRecord] = {}
        total_mun_paid = Decimal("0.00")
        total_external_paid = Decimal("0.00")

        for r in records:
            v = r.paid_value or r.committed_value or Decimal("0.00")
            if v > 0 and r.favored:
                total_mun_paid += v
                # Excluir entes públicos (Prefeituras, Câmaras, Fundos, RPPS) de fornecedores privados
                if is_internal_or_public_entity(r.favored, municipality):
                    continue

                norm_name = extract_document_and_name(r.favored)["normalized_name"]
                if norm_name:
                    favored_totals[norm_name] += v
                    total_external_paid += v
                    if norm_name not in favored_rep_record:
                        favored_rep_record[norm_name] = r

        if total_external_paid <= Decimal("100000.00"):
            return []

        # Ordenar fornecedores externos por volume
        sorted_favored = sorted(favored_totals.items(), key=lambda x: x[1], reverse=True)
        for rank, (norm_name, amount) in enumerate(sorted_favored, start=1):
            pct = float((amount / total_mun_paid) * 100) if total_mun_paid > 0 else 0.0
            # Marcar se concentrar >= 8% ou se for top 1 concentrando >= 5%
            if pct >= 8.0 or (rank == 1 and pct >= 5.0):
                severity = "alta" if pct >= 15.0 else "media"
                score = 8 if pct >= 15.0 else (7 if pct >= 10.0 else 6)
                rep = favored_rep_record[norm_name]
                prof = supplier_map.get(norm_name)

                evidence = {
                    "favored": norm_name,
                    "amount": float(amount),
                    "total_supplier": float(amount),
                    "total_municipality": float(total_mun_paid),
                    "total_external": float(total_external_paid),
                    "percentage": round(pct, 2),
                    "rank": rank,
                    "is_external": True,
                }
                findings.append(
                    AnomalyFinding(
                        record_id=rep.id,
                        supplier_id=prof.id if prof else None,
                        municipality_id=rep.municipality_id,
                        municipality=municipality,
                        year=year,
                        category="supplier_concentration",
                        severity=severity,
                        score=score,
                        title="Concentração expressiva em fornecedor externo",
                        explanation=(
                            f"Fornecedor externo '{norm_name}' concentra {pct:.1f}% de todo o montante executado "
                            f"({_fmt_money(amount)}) em {municipality} no exercício {year} (posição #{rank} no ranking de credores). "
                            f"Requer verificação de dependência contratual e pluralidade de fornecedores."
                        ),
                        evidence_json=json.dumps(evidence, ensure_ascii=False),
                    )
                )

        return findings

    def _rule_recurring_payments(
        self,
        municipality: str,
        year: int,
        records: list[PublicRecord],
        supplier_map: dict[str, SupplierProfile],
    ) -> list[AnomalyFinding]:
        """Regra 3: Pagamentos recorrentes ou valores redondos/idênticos repetidos."""
        findings: list[AnomalyFinding] = []
        # Agrupar por favorecido -> valor -> registros
        favored_values: dict[str, dict[float, list[PublicRecord]]] = defaultdict(lambda: defaultdict(list))

        for r in records:
            v = float(r.paid_value or r.committed_value or 0)
            if v > 0 and r.favored:
                norm_name = extract_document_and_name(r.favored)["normalized_name"]
                if norm_name:
                    favored_values[norm_name][v].append(r)

        for norm_name, val_dict in favored_values.items():
            for val, rec_list in val_dict.items():
                # Se houver 8 ou mais pagamentos exatamente com o mesmo valor (ou 5+ de valor redondo >= 10k)
                is_round = (val >= 10000.0 and val % 1000.0 == 0)
                thresh = 5 if is_round else 8

                if len(rec_list) >= thresh:
                    total_accum = val * len(rec_list)
                    rep = rec_list[0]
                    prof = supplier_map.get(norm_name)
                    evidence = {
                        "favored": norm_name,
                        "exact_value": val,
                        "count": len(rec_list),
                        "total_accumulated": total_accum,
                        "is_round_value": is_round,
                        "sample_movements": [r.movement_number or r.process_number for r in rec_list[:5]],
                    }
                    findings.append(
                        AnomalyFinding(
                            record_id=rep.id,
                            supplier_id=prof.id if prof else None,
                            municipality_id=rep.municipality_id,
                            municipality=municipality,
                            year=year,
                            category="recurring_payments",
                            severity="media",
                            score=6,
                            title="Pagamentos repetidos de valor idêntico",
                            explanation=(
                                f"Favorecido '{norm_name}' registrou {len(rec_list)} pagamentos com valor idêntico "
                                f"de {_fmt_money(val)} (totalizando {_fmt_money(total_accum)}) em {municipality} ({year}). "
                                f"Ponto de revisão para atestar a continuidade documental dos serviços."
                            ),
                            evidence_json=json.dumps(evidence, ensure_ascii=False),
                        )
                    )

        return findings

    def _rule_payment_flow_inconsistencies(
        self, municipality: str, year: int, records: list[PublicRecord]
    ) -> list[AnomalyFinding]:
        """Regra 4: Divergência de fluxo orçamentário (pago > empenhado ou liquidado > empenhado).
        
        Agrupa por chave contábil comprovada e compara estritamente no mesmo nível (empenho completo
        ou movimento individual). Evita comparar colunas cumulativas entre fases distintas.
        """
        findings: list[AnomalyFinding] = []
        zero = Decimal("0.00")

        # 1. Agrupar registros de despesa por chave contábil
        groups: dict[str, list[PublicRecord]] = defaultdict(list)
        is_secure_map: dict[str, bool] = {}

        for r in records:
            if r.kind != "despesa":
                continue
            key, is_secure = accounting_group_key(r)
            groups[key].append(r)
            # Se qualquer registro do grupo tem vínculo comprovado, o grupo é seguro
            is_secure_map[key] = is_secure_map.get(key, False) or is_secure

        for key, rec_list in groups.items():
            is_secure = is_secure_map.get(key, False)
            rep = rec_list[0]

            # Caso A: Movimento isolado não comprovado (Task 6)
            if not is_secure and len(rec_list) == 1:
                vals = extract_movement_accounting_values(rep)
                # Se for um pagamento isolado sem empenho
                if vals["paid"] > zero and vals["committed"] == zero:
                    evidence = {
                        "movement_number": rep.movement_number,
                        "paid": float(vals["paid"]),
                        "is_secure": False,
                        "records_count": 1,
                    }
                    findings.append(
                        AnomalyFinding(
                            record_id=rep.id,
                            municipality_id=rep.municipality_id,
                            municipality=municipality,
                            year=year,
                            category="requer verificação manual de agrupamento",
                            severity="baixa",
                            score=3,
                            title="Movimento financeiro sem vínculo de empenho confirmado",
                            explanation=(
                                f"O movimento nº {rep.movement_number or rep.id} registra pagamento de "
                                f"{_fmt_money(vals['paid'])}, mas não foi possível ligar com segurança ao empenho pai "
                                f"pelo portal da prefeitura. O vínculo contábil não foi determinado com segurança; "
                                f"requer verificação manual de agrupamento."
                            ),
                            evidence_json=json.dumps(evidence, ensure_ascii=False),
                        )
                    )
                    continue

            # Caso B: Movimento único consolidado (ex: Rialma ou teste sintético em linha única)
            if len(rec_list) == 1:
                vals = extract_movement_accounting_values(rep)
                emp = vals["committed"]
                liq = vals["liquidated"]
                pag = vals["paid"]

                if emp > zero:
                    if pag > emp and (pag - emp) > Decimal("5.00"):
                        diff = pag - emp
                        evidence = {
                            "movement_number": rep.movement_number,
                            "committed": float(emp),
                            "liquidated": float(liq),
                            "paid": float(pag),
                            "difference": float(diff),
                            "movements_count": 1,
                            "period": rep.movement_date or str(year),
                            "record_ids": [rep.id],
                        }
                        findings.append(
                            AnomalyFinding(
                                record_id=rep.id,
                                municipality_id=rep.municipality_id,
                                municipality=municipality,
                                year=year,
                                category="payment_flow_inconsistency" if is_secure else "requer verificação manual de agrupamento",
                                severity="alta" if is_secure else "baixa",
                                score=8 if is_secure else 4,
                                title="Valor pago superior ao valor empenhado",
                                explanation=(
                                    f"No registro nº {rep.movement_number or rep.id}, o valor pago "
                                    f"({_fmt_money(pag)}) é superior ao valor empenhado ({_fmt_money(emp)}), "
                                    f"com diferença de {_fmt_money(diff)}. "
                                    f"Requer conferência contábil de anulações ou termos suplementares."
                                ),
                                evidence_json=json.dumps(evidence, ensure_ascii=False),
                            )
                        )
                    elif liq > emp and (liq - emp) > Decimal("5.00"):
                        diff = liq - emp
                        evidence = {
                            "movement_number": rep.movement_number,
                            "committed": float(emp),
                            "liquidated": float(liq),
                            "paid": float(pag),
                            "difference": float(diff),
                            "movements_count": 1,
                            "period": rep.movement_date or str(year),
                            "record_ids": [rep.id],
                        }
                        findings.append(
                            AnomalyFinding(
                                record_id=rep.id,
                                municipality_id=rep.municipality_id,
                                municipality=municipality,
                                year=year,
                                category="payment_flow_inconsistency" if is_secure else "requer verificação manual de agrupamento",
                                severity="media" if is_secure else "baixa",
                                score=6 if is_secure else 3,
                                title="Valor liquidado superior ao valor empenhado",
                                explanation=(
                                    f"No registro nº {rep.movement_number or rep.id}, a liquidação "
                                    f"({_fmt_money(liq)}) ultrapassa o empenho ({_fmt_money(emp)}) "
                                    f"em {_fmt_money(diff)}. Ponto de revisão para atesto de regularidade fiscal."
                                ),
                                evidence_json=json.dumps(evidence, ensure_ascii=False),
                            )
                        )
                continue

            # Caso C: Agrupamento contábil com múltiplos movimentos (ex: Empenho + Liquidações + Pagamentos)
            all_vals = [extract_movement_accounting_values(r) for r in rec_list]

            # Valor empenhado total do grupo
            emp_movements = [v["committed"] for v, r in zip(all_vals, rec_list) if (r.movement_type or "").lower() == "empenho" and v["committed"] > zero]
            if emp_movements:
                total_emp = sum(emp_movements)
            else:
                total_emp = max((v["empenho_total"] for v in all_vals), default=zero)

            # Liquidação total é a soma dos movimentos de liquidação deste grupo
            total_liq = sum(v["liquidated"] for v in all_vals)
            # Pagamento total é a soma dos movimentos de pagamento deste grupo
            total_pag = sum(v["paid"] for v in all_vals)

            if total_emp <= zero:
                continue

            # Extrair metadados para evidência auditável (Task 7)
            dates = [r.movement_date for r in rec_list if r.movement_date]
            period = f"{dates[-1]} a {dates[0]}" if len(dates) > 1 else (dates[0] if dates else str(year))
            mov_numbers = [r.movement_number for r in rec_list if r.movement_number]
            mov_summary = ", ".join(mov_numbers[:5]) + (f" (+{len(mov_numbers) - 5} outros)" if len(mov_numbers) > 5 else "")
            rec_ids = [r.id for r in rec_list]

            if total_pag > total_emp and (total_pag - total_emp) > Decimal("5.00"):
                diff = total_pag - total_emp
                evidence = {
                    "accounting_key": key,
                    "is_secure": is_secure,
                    "committed": float(total_emp),
                    "liquidated": float(total_liq),
                    "paid": float(total_pag),
                    "difference": float(diff),
                    "movements_count": len(rec_list),
                    "movement_numbers": mov_numbers,
                    "period": period,
                    "record_ids": rec_ids,
                    "favored": rep.favored,
                }
                findings.append(
                    AnomalyFinding(
                        record_id=rep.id,
                        municipality_id=rep.municipality_id,
                        municipality=municipality,
                        year=year,
                        category="payment_flow_inconsistency" if is_secure else "requer verificação manual de agrupamento",
                        severity="alta" if is_secure else "baixa",
                        score=8 if is_secure else 4,
                        title="Valor pago superior ao valor empenhado no grupo contábil",
                        explanation=(
                            f"No empenho agrupado ({key}), a soma dos pagamentos ({_fmt_money(total_pag)} "
                            f"em {len(rec_list)} movimentos somados: {mov_summary} no período {period}) "
                            f"ultrapassa o valor empenhado ({_fmt_money(total_emp)}) em {_fmt_money(diff)}. "
                            f"Requer conferência contábil de anulações ou termos aditivos suplementares."
                        ),
                        evidence_json=json.dumps(evidence, ensure_ascii=False),
                    )
                )
            elif total_liq > total_emp and (total_liq - total_emp) > Decimal("5.00"):
                diff = total_liq - total_emp
                evidence = {
                    "accounting_key": key,
                    "is_secure": is_secure,
                    "committed": float(total_emp),
                    "liquidated": float(total_liq),
                    "paid": float(total_pag),
                    "difference": float(diff),
                    "movements_count": len(rec_list),
                    "movement_numbers": mov_numbers,
                    "period": period,
                    "record_ids": rec_ids,
                    "favored": rep.favored,
                }
                findings.append(
                    AnomalyFinding(
                        record_id=rep.id,
                        municipality_id=rep.municipality_id,
                        municipality=municipality,
                        year=year,
                        category="payment_flow_inconsistency" if is_secure else "requer verificação manual de agrupamento",
                        severity="media" if is_secure else "baixa",
                        score=6 if is_secure else 3,
                        title="Valor liquidado superior ao valor empenhado no grupo contábil",
                        explanation=(
                            f"No empenho agrupado ({key}), a soma das liquidações ({_fmt_money(total_liq)} "
                            f"em {len(rec_list)} movimentos somados: {mov_summary} no período {period}) "
                            f"ultrapassa o valor empenhado ({_fmt_money(total_emp)}) em {_fmt_money(diff)}. "
                            f"Ponto de revisão para atesto de regularidade fiscal."
                        ),
                        evidence_json=json.dumps(evidence, ensure_ascii=False),
                    )
                )

        return findings

    def _rule_possible_fragmentation(
        self,
        municipality: str,
        year: int,
        records: list[PublicRecord],
        supplier_map: dict[str, SupplierProfile],
    ) -> list[AnomalyFinding]:
        """Regra 5: Possível agrupamento de despesas em curto intervalo para o mesmo credor."""
        findings: list[AnomalyFinding] = []
        # Agrupar despesas por favorecido -> mês
        favored_monthly: dict[tuple[str, str], list[PublicRecord]] = defaultdict(list)

        for r in records:
            if r.kind == "despesa" and r.favored and r.movement_date:
                norm_name = extract_document_and_name(r.favored)["normalized_name"]
                # Extrair YYYY-MM ou DD/MM/AAAA -> mês
                date_str = r.movement_date.strip()
                month_key = ""
                if "/" in date_str:
                    parts = date_str.split("/")
                    if len(parts) == 3:
                        month_key = f"{parts[2]}-{parts[1]}"
                elif "-" in date_str:
                    month_key = date_str[:7]

                if norm_name and month_key:
                    favored_monthly[(norm_name, month_key)].append(r)

        for (norm_name, month_key), rec_list in favored_monthly.items():
            # Se houver 4 ou mais pagamentos no mesmo mês somando mais de R$ 30.000
            if len(rec_list) >= 4:
                total_val = sum(float(r.paid_value or r.committed_value or 0) for r in rec_list)
                if total_val >= 30000.0:
                    rep = rec_list[0]
                    prof = supplier_map.get(norm_name)
                    evidence = {
                        "favored": norm_name,
                        "month": month_key,
                        "movements_count": len(rec_list),
                        "total_month": total_val,
                        "movements": [r.movement_number for r in rec_list if r.movement_number][:8],
                    }
                    findings.append(
                        AnomalyFinding(
                            record_id=rep.id,
                            supplier_id=prof.id if prof else None,
                            municipality_id=rep.municipality_id,
                            municipality=municipality,
                            year=year,
                            category="possible_fragmentation",
                            severity="media",
                            score=6,
                            title="Possível agrupamento de despesas para revisão",
                            explanation=(
                                f"Favorecido '{norm_name}' teve {len(rec_list)} pagamentos no mês {month_key} "
                                f"totalizando {_fmt_money(total_val)}. Requer verificação documental para assegurar "
                                f"o adequado enquadramento em contratação única ou processo regular."
                            ),
                            evidence_json=json.dumps(evidence, ensure_ascii=False),
                        )
                    )

        return findings

    def _rule_repeated_descriptions(
        self, municipality: str, year: int, records: list[PublicRecord]
    ) -> list[AnomalyFinding]:
        """Regra 6: Registros com descrições idênticas ou quase idênticas."""
        findings: list[AnomalyFinding] = []
        favored_desc: dict[str, dict[str, list[PublicRecord]]] = defaultdict(lambda: defaultdict(list))

        for r in records:
            raw_desc = (r.description or r.title or "").strip()
            if len(raw_desc) >= 20 and r.favored:
                norm_name = extract_document_and_name(r.favored)["normalized_name"]
                norm_desc = unicodedata.normalize("NFKD", raw_desc.lower())
                clean_desc = re.sub(r"\s+", " ", "".join(c for c in norm_desc if not unicodedata.combining(c))).strip()
                if norm_name and clean_desc:
                    favored_desc[norm_name][clean_desc].append(r)

        for norm_name, desc_dict in favored_desc.items():
            for desc_text, rec_list in desc_dict.items():
                if len(rec_list) >= 6:
                    total_amount = sum(float(r.paid_value or r.committed_value or 0) for r in rec_list)
                    rep = rec_list[0]
                    evidence = {
                        "favored": norm_name,
                        "description_sample": desc_text[:120],
                        "occurrences": len(rec_list),
                        "total_amount": total_amount,
                    }
                    findings.append(
                        AnomalyFinding(
                            record_id=rep.id,
                            municipality_id=rep.municipality_id,
                            municipality=municipality,
                            year=year,
                            category="repeated_description",
                            severity="baixa",
                            score=4,
                            title="Descrições textuais padronizadas e repetitivas",
                            explanation=(
                                f"Favorecido '{norm_name}' apresentou {len(rec_list)} lançamentos com a mesma descrição "
                                f"textual (totalizando {_fmt_money(total_amount)}). Ponto de revisão formal de histórico."
                            ),
                            evidence_json=json.dumps(evidence, ensure_ascii=False),
                        )
                    )

        return findings

    def _rule_new_supplier_high_value(
        self,
        grouped_records: dict[tuple[str, int], list[PublicRecord]],
        supplier_map: dict[str, SupplierProfile],
    ) -> list[AnomalyFinding]:
        """Regra 7: Favorecido que aparece pela primeira vez em 2026 recebendo valor no percentil superior."""
        findings: list[AnomalyFinding] = []

        # Identificar favorecidos presentes em 2025
        suppliers_2025: dict[str, set[str]] = defaultdict(set)
        for (m_name, y), recs in grouped_records.items():
            if y == 2025:
                for r in recs:
                    if r.favored:
                        norm = extract_document_and_name(r.favored)["normalized_name"]
                        if norm:
                            suppliers_2025[m_name].add(norm)

        # Analisar credores de 2026
        for (m_name, y), recs in grouped_records.items():
            if y == 2026:
                seen_in_2025 = suppliers_2025.get(m_name, set())
                # Totais por fornecedor em 2026
                fav_totals_2026: dict[str, tuple[float, PublicRecord]] = {}
                vals_2026 = []
                for r in recs:
                    v = float(r.paid_value or r.committed_value or 0)
                    if v > 0 and r.favored:
                        norm = extract_document_and_name(r.favored)["normalized_name"]
                        if norm:
                            cur_v, _ = fav_totals_2026.get(norm, (0.0, r))
                            fav_totals_2026[norm] = (cur_v + v, r)
                            vals_2026.append(v)

                if len(vals_2026) < 10:
                    continue

                stats = calculate_percentiles([t[0] for t in fav_totals_2026.values()])
                p90 = stats["p90"]

                for norm, (total_2026, rep) in fav_totals_2026.items():
                    if norm not in seen_in_2025 and total_2026 > p90 and total_2026 >= 50000.0:
                        prof = supplier_map.get(norm)
                        evidence = {
                            "favored": norm,
                            "total_2026": total_2026,
                            "p90_threshold": p90,
                            "first_year_in_database": 2026,
                        }
                        findings.append(
                            AnomalyFinding(
                                record_id=rep.id,
                                supplier_id=prof.id if prof else None,
                                municipality_id=rep.municipality_id,
                                municipality=m_name,
                                year=2026,
                                category="new_supplier_high_value",
                                severity="media",
                                score=7,
                                title="Fornecedor novo na base coletada com valor expressivo",
                                explanation=(
                                    f"O favorecido '{norm}' ingressou na base de dados de {m_name} em 2026 "
                                    f"recebendo volume total de {_fmt_money(total_2026)}, valor superior ao percentil 90 "
                                    f"({_fmt_money(p90)}) dos demais credores no exercício."
                                ),
                                evidence_json=json.dumps(evidence, ensure_ascii=False),
                            )
                        )

        return findings
