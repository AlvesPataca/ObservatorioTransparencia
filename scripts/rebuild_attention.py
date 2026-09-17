"""Script de materialização das pontuações de atenção em lote.

Calcula e persiste attention_score, attention_reasons e attention_keywords
para todos os registros em public_records no banco de dados SQLite.
Isso transforma consultas de atenção em buscas indexadas ultra-rápidas.
"""

from pathlib import Path
import sys
import json
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select, text
from database.session import SessionLocal, engine
from database.models import PublicRecord
from analytics.anomalies import score_record_text
from scripts.import_json_to_db import ensure_public_record_columns


def rebuild_attention(batch_size: int = 5000) -> None:
    print("=" * 70)
    print("MATERIALIZANDO PONTUAÇÕES DE ATENÇÃO NO BANCO DE DADOS")
    print("=" * 70)

    # 1. Garantir que as colunas e índices existem
    ensure_public_record_columns(engine)

    start_time = time.perf_counter()
    total_processed = 0
    with_score = 0
    score_dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

    with SessionLocal() as session:
        # Carregar registros com paginação por ID
        max_id = session.scalar(select(PublicRecord.id).order_by(PublicRecord.id.desc()).limit(1)) or 0
        print(f"Total estimado de registros: até ID {max_id}")

        current_min_id = 0
        while current_min_id <= max_id:
            batch = list(
                session.scalars(
                    select(PublicRecord)
                    .where(PublicRecord.id > current_min_id)
                    .order_by(PublicRecord.id)
                    .limit(batch_size)
                )
            )
            if not batch:
                break

            for r in batch:
                content = " ".join(filter(None, [r.title, r.object, r.description, r.favored]))
                score, keywords, reasons = score_record_text(content)
                r.attention_score = score
                r.attention_keywords = json.dumps(keywords, ensure_ascii=False) if keywords else None
                r.attention_reasons = json.dumps(reasons, ensure_ascii=False) if reasons else None

                if score > 0:
                    with_score += 1
                    capped_score = min(score, 5)
                    score_dist[capped_score] = score_dist.get(capped_score, 0) + 1

                current_min_id = r.id

            session.commit()
            total_processed += len(batch)
            print(f"  - Processados {total_processed} registros... (último ID: {current_min_id})")

    elapsed = time.perf_counter() - start_time
    print("-" * 70)
    print(f"Concluído com sucesso em {elapsed:.2f} segundos!")
    print(f"Total de registros processados: {total_processed}")
    print(f"Registros com pontuação de atenção (score >= 1): {with_score}")
    print(f"Distribuição de scores: {score_dist}")
    print("=" * 70)


if __name__ == "__main__":
    rebuild_attention()

