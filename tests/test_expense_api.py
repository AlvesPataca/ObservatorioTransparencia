from collectors.base.expense_api import (
    build_expense_body,
    deduplicate_api_records,
    page_starts,
    parse_expense_api_response,
)
from collectors.base.expenses_http import ExpensesHttpCollector
from collectors.municipalities import MUNICIPALITIES


def _payload_ceres() -> dict:
    return {
        "request": {
            "total": "2",
            "dados": [
                {
                    "movimento": "Empenho",
                    "numero": "10",
                    "data": "01/01/2026",
                    "fornecedor": "Fornecedor Ceres",
                    "descricao": "Material escolar",
                    "valor_empenho": "16.406,90",
                    "liquidado": "0,00",
                    "pagamento": "0,00",
                },
                {
                    "movimento": "Pagamento",
                    "numero": "10.1",
                    "data": "02/01/2026",
                    "fornecedor": "Fornecedor Ceres",
                    "descricao": "Material escolar",
                    "valor_empenho": "16.406,90",
                    "liquidado": "16.406,90",
                    "pagamento": "8.000,00",
                },
            ],
        }
    }


def _payload_rialma() -> dict:
    return {
        "0-3pc4hd": {
            "total": 1,
            "registros": [
                {
                    "codigo": 270623,
                    "numeroDoTcm": 270623,
                    "data": "14/09/2025",
                    "nomeDoFornecedor": "RUBENS VIRGILIO DA SILVA ENGENHARIA",
                    "valorDoEmpenho": 1000.0,
                    "valorTotalDaLiquidacao": 1000.0,
                    "valorTotalDoPagamento": 500.0,
                    "historico": "DESPESA de locação de caçambas",
                    "codigoENomeDaModalidade": "10 - DISPENSA DE LICITAÇÃO",
                }
            ],
        }
    }


def test_parse_expense_api_response_and_brazilian_values() -> None:
    total, records = parse_expense_api_response(_payload_ceres(), "Ceres-GO", "https://example.test/api", year=2026)
    assert total == 2
    assert len(records) == 2
    assert records[0].committed_value == "16406.90"
    assert records[0].year == 2026
    assert records[1].paid_value == "8000.00"


def test_parse_expense_api_response_rialma_format() -> None:
    total, records = parse_expense_api_response(_payload_rialma(), "Rialma-GO", "https://example.test/api")
    assert total == 1
    assert len(records) == 1
    record = records[0]
    assert record.favored == "RUBENS VIRGILIO DA SILVA ENGENHARIA"
    assert record.committed_value == "1000.00"
    assert record.paid_value == "500.00"
    assert record.year == 2025
    assert record.movement_number == "270623"


def test_api_pagination_stops_at_expected_total() -> None:
    assert page_starts(20401, 1000)[-1] == 20000
    assert len(page_starts(20401, 1000)) == 21


def test_api_records_do_not_duplicate() -> None:
    _, records = parse_expense_api_response(_payload_ceres(), "Ceres-GO", "https://example.test/api")
    assert len(deduplicate_api_records(records + records)) == 2


def test_ceres_and_rialma_build_correct_urls_and_headers() -> None:
    collector_ceres = ExpensesHttpCollector("ceres", year=2026)
    collector_rialma = ExpensesHttpCollector("rialma", year=2025)

    assert collector_ceres.endpoint_api == "https://acessoainformacao.ceres.go.gov.br/api"
    assert collector_rialma.endpoint_api == "https://acessoainformacao.rialma.go.gov.br/api"


def test_build_expense_body_contains_requested_year() -> None:
    body_ceres = build_expense_body({"acao": "sgdespesas/listar"}, start=0, length=1000, year=2025)
    assert '"ano": "2025"' in body_ceres["params"]
    assert '"limit": "0, 1000"' in body_ceres["params"]

    body_rialma = build_expense_body({"acao": "megasoft/empenhos"}, start=0, length=1000, year=2026)
    assert "2026" in body_rialma["params"]
    assert '"tamanhoDaPagina": 1000' in body_rialma["params"]
