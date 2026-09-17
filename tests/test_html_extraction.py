from collectors.base.html import extract_links


def test_extract_links_filters_by_keywords() -> None:
    html = """
    <a href="/informacao/licitacoes">Licitações</a>
    <a href="/informacao/contratos">Contratos</a>
    <a href="/noticias">Noticias</a>
    """

    links = extract_links(html, "https://example.test", ("licit", "contrato"))

    assert links == [
        {"text": "Licitações", "url": "https://example.test/informacao/licitacoes"},
        {"text": "Contratos", "url": "https://example.test/informacao/contratos"},
    ]
