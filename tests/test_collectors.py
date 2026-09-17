from collectors.base.html import extract_links
from collectors.base.browser import classify_kind, normalize_visible_items


def test_generic_transparency_links_are_not_licitacao_records() -> None:
    html = """
    <a href="/transparencia/">Transparência</a>
    <a href="/cidadao/transparencia/despesas">Despesas e Receitas</a>
    <a href="/cidadao/transparencia/folhas">Folha de Pagamento</a>
    """

    links = extract_links(html, "https://rialma.go.gov.br", ("licit", "contrato"))

    assert links == []


def test_browser_normalization_ignores_generic_links() -> None:
    records = normalize_visible_items(
        "Ceres-GO",
        "https://example.test/cidadao/informacao/sglicitacoes",
        [{"text": "Licitações", "url": "https://example.test/cidadao/informacao/sglicitacoes", "fields": {}}],
        "licitacao",
    )

    assert records == []


def test_browser_normalization_ignores_generic_route_labels() -> None:
    records = normalize_visible_items(
        "Ceres-GO",
        "https://example.test/cidadao/informacao/sgcontratos",
        [{"text": "Contratos", "url": "/cidadao/informacao/sgcontratos", "fields": {}}],
        "contrato",
    )

    assert records == []


def test_browser_normalization_requires_process_number_without_table_fields() -> None:
    records = normalize_visible_items(
        "Ceres-GO",
        "https://example.test/cidadao/informacao/sglicitacoes",
        [{"text": "Licitações fracassadas e desertas", "url": "/cidadao/informacao/licitacoes_fd", "fields": {}}],
        "licitacao",
    )

    assert records == []


def test_browser_normalization_resolves_relative_link_and_kind() -> None:
    records = normalize_visible_items(
        "Ceres-GO",
        "https://example.test/cidadao/informacao/sglicitacoes",
        [{"text": "Pregão 000034/2026", "url": "/licitacao/34", "fields": {}}],
    )

    assert records[0].detail_url == "https://example.test/licitacao/34"
    assert records[0].kind == "licitacao"


def test_browser_classifies_contract() -> None:
    assert classify_kind("Contrato administrativo 12/2026") == "contrato"
