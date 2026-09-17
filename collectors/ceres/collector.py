from app.models import CollectionResult, PublicRecord
from collectors.base.client import TransparencyHttpClient
from collectors.base.html import extract_links


class CeresCollector:
    municipality = "Ceres-GO"

    sources = (
        ("Site oficial - transparencia", "https://ceres.go.gov.br/transparencia/"),
        ("Portal - licitacoes", "https://acessoainformacao.ceres.go.gov.br/cidadao/informacao/sglicitacoes"),
        ("Portal - contratos", "https://acessoainformacao.ceres.go.gov.br/cidadao/informacao/sgcontratos"),
    )

    browser_sources = (
        ("licitacao", "https://acessoainformacao.ceres.go.gov.br/cidadao/informacao/sglicitacoes"),
        ("contrato", "https://acessoainformacao.ceres.go.gov.br/cidadao/informacao/sgcontratos"),
    )

    def inspect(self, client: TransparencyHttpClient) -> CollectionResult:
        return CollectionResult(
            municipality=self.municipality,
            source_checks=client.check_sources(self.municipality, self.sources),
        )

    def collect_mvp(self, client: TransparencyHttpClient) -> CollectionResult:
        result = self.inspect(client)
        for check in result.source_checks:
            if not check.accessible or "Portal" not in check.label:
                continue
            response = client.get(str(check.url))
            links = extract_links(response.text, str(check.url), ("licit", "contrato"))
            for link in links:
                lowered = f"{link['text']} {link['url']}".lower()
                if "licit" not in lowered and "contrato" not in lowered:
                    continue
                kind = "contrato" if "contrato" in lowered else "licitacao"
                result.records.append(
                    PublicRecord(
                        municipality=self.municipality,
                        kind=kind,
                        source_url=str(check.url),
                        title=link["text"],
                        detail_url=link["url"],
                        raw=link,
                    )
                )

        if not result.records and not any(check.accessible for check in result.source_checks):
            result.warnings.append("Nenhuma fonte HTTP de Ceres respondeu com sucesso.")

        blocked = [check.label for check in result.source_checks if check.blocked]
        if blocked:
            result.warnings.append(f"Fontes bloqueadas para automacao simples: {', '.join(blocked)}.")

        return result
