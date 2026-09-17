from decimal import Decimal
import pytest

from app.core.money import format_brl_money, parse_brl_money


def test_parse_zero() -> None:
    assert parse_brl_money("0,00") == Decimal("0.00")
    assert parse_brl_money("0.00") == Decimal("0.00")
    assert parse_brl_money(0) == Decimal("0.00")


def test_parse_thousands_brazilian_format() -> None:
    assert parse_brl_money("2.000,00") == Decimal("2000.00")
    assert parse_brl_money("+ 2.000,00") == Decimal("2000.00")
    assert parse_brl_money("20.000,00") == Decimal("20000.00")
    assert parse_brl_money("12.000,00") == Decimal("12000.00")
    assert parse_brl_money("1.234.567,89") == Decimal("1234567.89")
    assert parse_brl_money("R$ 1.234.567,89") == Decimal("1234567.89")


def test_parse_none_and_empty() -> None:
    assert parse_brl_money("") is None
    assert parse_brl_money(None) is None
    assert parse_brl_money("   ") is None


def test_parse_whitespace_tabs_newlines() -> None:
    assert parse_brl_money("   \t\n 20.000,00 \n") == Decimal("20000.00")
    assert parse_brl_money("\n\t + 2.000,00 \r\n") == Decimal("20000.00") or parse_brl_money("\n\t + 2.000,00 \r\n") == Decimal("2000.00")
    assert parse_brl_money("\n\t + 2.000,00 \r\n") == Decimal("2000.00")


def test_parse_negative_numbers() -> None:
    assert parse_brl_money("- 2.000,00") == Decimal("-2000.00")
    assert parse_brl_money("-R$ 1.500,50") == Decimal("-1500.50")
    assert parse_brl_money("-20000.00") == Decimal("-20000.00")


def test_parse_standard_decimal_strings() -> None:
    assert parse_brl_money("20000.00") == Decimal("20000.00")
    assert parse_brl_money("2000.00") == Decimal("2000.00")
    assert parse_brl_money("10000.00") == Decimal("10000.00")
    assert parse_brl_money("1234.56") == Decimal("1234.56")


def test_parse_numeric_types() -> None:
    assert parse_brl_money(1234) == Decimal("1234.00")
    assert parse_brl_money(Decimal("50.25")) == Decimal("50.25")
    assert parse_brl_money(20000) == Decimal("20000.00")


def test_format_brl_money() -> None:
    assert format_brl_money("20.000,00") == "R$ 20.000,00"
    assert format_brl_money("20000.00") == "R$ 20.000,00"
    assert format_brl_money(Decimal("20000.00")) == "R$ 20.000,00"
    assert format_brl_money(Decimal("1234567.89")) == "R$ 1.234.567,89"
    assert format_brl_money("0,00") == "R$ 0,00"
    assert format_brl_money(None) == "R$ 0,00"
    assert format_brl_money("") == "R$ 0,00"
    assert format_brl_money("- 2.000,00") == "-R$ 2.000,00"
    assert format_brl_money(Decimal("-2000.00")) == "-R$ 2.000,00"

