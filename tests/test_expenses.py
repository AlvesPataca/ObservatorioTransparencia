from decimal import Decimal

from collectors.ceres.expenses import (
    deduplicate_expenses,
    extract_expense_rows,
    parse_brazilian_decimal,
)
from collectors.rialma.expenses import RialmaExpensesCollector


HTML = """
<table class="tb">
  <tr><th>Movimento</th><th>Favorecido</th><th>Data</th><th>Descrição</th><th>Empenhado</th><th>Liquidado</th><th>Pago</th></tr>
  <tr><td>Empenho<br>6183</td><td>Fornecedor A</td><td>15/09/2026</td><td>Compra de materiais</td><td>16.406,90</td><td>0,00</td><td>0,00</td></tr>
</table>
"""


def test_extract_expense_row() -> None:
    records = extract_expense_rows(HTML)
    assert len(records) == 1
    assert records[0].movement_type == "Empenho"
    assert records[0].movement_number == "6183"
    assert records[0].favored == "Fornecedor A"
    assert records[0].committed_value == "16406.90"
    assert records[0].kind == "despesa"


def test_parse_brazilian_decimal() -> None:
    assert parse_brazilian_decimal("R$ 16.406,90") == Decimal("16406.90")
    assert parse_brazilian_decimal("sem valor") is None


def test_expense_pagination_deduplicates_records() -> None:
    first = extract_expense_rows(HTML)
    second = extract_expense_rows(HTML)
    assert len(deduplicate_expenses(first + second)) == 1


def test_rialma_expense_parser_reuses_common_parser() -> None:
    records = extract_expense_rows(
        HTML,
        municipality="Rialma-GO",
        source_url=RialmaExpensesCollector().source_url,
    )
    assert records[0].municipality == "Rialma-GO"
    assert str(records[0].source_url) == RialmaExpensesCollector().source_url