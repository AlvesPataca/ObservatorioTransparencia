from collectors.base.expenses import (
    ExpensesCollector,
    deduplicate_expenses,
    extract_expense_rows,
    parse_brazilian_decimal,
    serialize_expenses,
)


RIALMA_EXPENSES_URL = "https://acessoainformacao.rialma.go.gov.br/cidadao/transparencia/mgdespesas"


class RialmaExpensesCollector(ExpensesCollector):
    def __init__(self) -> None:
        super().__init__("Rialma-GO", RIALMA_EXPENSES_URL)


__all__ = [
    "RIALMA_EXPENSES_URL",
    "RialmaExpensesCollector",
    "deduplicate_expenses",
    "extract_expense_rows",
    "parse_brazilian_decimal",
    "serialize_expenses",
]
