from collectors.base.expenses import (
    ExpensesCollector,
    deduplicate_expenses,
    extract_expense_rows,
    parse_brazilian_decimal,
    serialize_expenses,
)


CERES_EXPENSES_URL = "https://acessoainformacao.ceres.go.gov.br/cidadao/transparencia/sgdespesas"


class CeresExpensesCollector(ExpensesCollector):
    def __init__(self) -> None:
        super().__init__("Ceres-GO", CERES_EXPENSES_URL)


__all__ = [
    "CERES_EXPENSES_URL",
    "CeresExpensesCollector",
    "deduplicate_expenses",
    "extract_expense_rows",
    "parse_brazilian_decimal",
    "serialize_expenses",
]
