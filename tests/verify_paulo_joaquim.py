import json
from decimal import Decimal
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient
from app.main import app
from database.session import SessionLocal
from database.models import PublicRecord
from sqlalchemy import select

def main():
    print("=" * 80)
    print("VALIDACAO DO CASO REAL: PAULO JOAQUIM DA SILVA JUNIOR")
    print("=" * 80)

    # 1. Banco de Dados
    with SessionLocal() as s:
        rec = s.scalar(select(PublicRecord).where(
            PublicRecord.favored.ilike("%PAULO JOAQUIM DA SILVA JUNIOR%"),
            PublicRecord.movement_number == "2068.6"
        ))
        if not rec:
            rec = s.scalar(select(PublicRecord).where(
                PublicRecord.favored.ilike("%PAULO JOAQUIM DA SILVA JUNIOR%")
            ))
        
        print(f"\n[REGISTRO SELECIONADO: ID {rec.id} | {rec.movement_type} {rec.movement_number} | Data: {rec.movement_date}]")
        
        # 1. Original do Portal (campo raw_json no banco)
        portal_raw = json.loads(rec.raw_json or "{}")
        print("\n1. ORIGINAL DO PORTAL (Raw payload do portal de Ceres):")
        print(f"   - Fornecedor:       {portal_raw.get('fornecedor')}")
        print(f"   - Valor Empenho:    {portal_raw.get('valor_empenho')}")
        print(f"   - Valor Movimento:  {portal_raw.get('valor_mov')}")
        print(f"   - Liquidado:        {portal_raw.get('liquidado')}")
        print(f"   - Pagamento:        {portal_raw.get('pagamento')}")
        
        # 2. Gravado no Banco
        print("\n2. GRAVADO NO BANCO (SQLite observatorio.db):")
        print(f"   - committed_value:     {repr(rec.committed_value)} (tipo: {type(rec.committed_value).__name__})")
        print(f"   - liquidated_value:    {repr(rec.liquidated_value)} (tipo: {type(rec.liquidated_value).__name__})")
        print(f"   - paid_value:          {repr(rec.paid_value)} (tipo: {type(rec.paid_value).__name__})")
        print(f"   - committed_value_raw: {repr(rec.committed_value_raw)}")
        print(f"   - liquidated_value_raw:{repr(rec.liquidated_value_raw)}")
        print(f"   - paid_value_raw:      {repr(rec.paid_value_raw)}")

    # 3. Retornado pela API
    client = TestClient(app)
    api_res = client.get("/api/records", params={"q": "PAULO JOAQUIM DA SILVA JUNIOR", "limit": 10})
    api_items = api_res.json().get("items", [])
    item = next((i for i in api_items if i.get("movement_number") == rec.movement_number), api_items[0])

    print("\n3. RETORNADO PELA API (/api/records):")
    print(f"   - committed_value:     {repr(item.get('committed_value'))}")
    print(f"   - liquidated_value:    {repr(item.get('liquidated_value'))}")
    print(f"   - paid_value:          {repr(item.get('paid_value'))}")
    print(f"   - committed_value_raw: {repr(item.get('committed_value_raw'))}")
    print(f"   - liquidated_value_raw:{repr(item.get('liquidated_value_raw'))}")
    print(f"   - paid_value_raw:      {repr(item.get('paid_value_raw'))}")

    # 4. Renderizado pelo Frontend (JavaScript formatCurrency corrigido)
    def js_format_currency(val):
        if val is None or val == "":
            return "R$ 0,00"
        s = str(val).strip()
        is_neg = "-" in s or s.startswith("(")
        import re
        clean = re.sub(r"[^\d.,]", "", s)
        if not clean:
            return s
        if "," in clean:
            num = float(clean.replace(".", "").replace(",", "."))
        else:
            if clean.count(".") > 1:
                num = float(clean.replace(".", ""))
            else:
                num = float(clean)
        abs_d = abs(num)
        formatted = f"{abs_d:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
        prefix = "-R$ " if is_neg and num > 0 else "R$ "
        return f"{prefix}{formatted}"

    print("\n4. RENDERIZADO PELO FRONTEND (JavaScript formatCurrency corrigido):")
    formatted_emp = js_format_currency(item.get("committed_value"))
    formatted_liq = js_format_currency(item.get("liquidated_value"))
    formatted_pag = js_format_currency(item.get("paid_value"))
    print(f"   - Empenhado exibido no dashboard: {formatted_emp}")
    print(f"   - Liquidado exibido no dashboard: {formatted_liq}")
    print(f"   - Pago exibido no dashboard:      {formatted_pag}")

    # 5. Comparação e Validação
    portal_emp = portal_raw.get("valor_empenho")
    portal_liq = portal_raw.get("liquidado")
    portal_pag = portal_raw.get("pagamento")

    emp_ok = formatted_emp == f"R$ {portal_emp}"
    liq_ok = formatted_liq == f"R$ {portal_liq}"
    pag_ok = formatted_pag == f"R$ {portal_pag}"

    print("\n5. VALIDACAO DE EXATIDAO CONTRA O PORTAL:")
    print(f"   - Empenhado bate com o portal ({portal_emp}): {emp_ok} [Exibido: {formatted_emp}]")
    print(f"   - Liquidado bate com o portal ({portal_liq}): {liq_ok} [Exibido: {formatted_liq}]")
    print(f"   - Pago bate com o portal ({portal_pag}):       {pag_ok} [Exibido: {formatted_pag}]")
    print("=" * 80)

if __name__ == "__main__":
    main()
