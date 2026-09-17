from app.models import CollectionResult, PublicRecord
from collectors.base.client import TransparencyHttpClient
from collectors.base.html import extract_links


class RialmaCollector:
    municipality = "Rialma-GO"

    sources = (
        ("Site oficial - transparencia", "https://rialma.go.gov.br/transparencia/"),
        ("Portal raiz", "https://acessoainformacao.rialma.go.gov.br/"),
        ("Portal - licitacoes", "https://acessoainformacao.rialma.go.gov.br/cidadao/informacao/licitacoes_mg"),
        ("Portal - contratos", "https://acessoainformacao.rialma.go.gov.br/cidadao/informacao/contratos_mg"),
    )

    browser_sources = (
        ("licitacao", "https://acessoainformacao.rialma.go.gov.br/cidadao/informacao/licitacoes_mg"),
        ("contrato", "https://acessoainformacao.rialma.go.gov.br/cidadao/informacao/contratos_mg"),
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
            result.warnings.append("Nenhuma fonte HTTP de Rialma respondeu com sucesso.")

        blocked = [check.label for check in result.source_checks if check.blocked]
        if blocked:
            result.warnings.append(f"Fontes bloqueadas para automacao simples: {', '.join(blocked)}.")

        return result
