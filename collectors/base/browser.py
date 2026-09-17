import re
import unicodedata
from collections.abc import Iterable
from urllib.parse import urljoin

from playwright.async_api import async_playwright

from app.models import PublicRecord
from app.models.transparency import RecordKind


GENERIC_LABELS = {
    "menu",
    "início",
    "inicio",
    "voltar",
    "filtrar",
    "exportar",
    "licitações",
    "licitacoes",
    "licitações até 2021",
    "licitacoes ate 2021",
    "contratos",
}


def _without_accents(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(character)
    )


def classify_kind(text: str, expected_kind: RecordKind | None = None) -> RecordKind | None:
    lowered = text.casefold()
    if "contrat" in lowered:
        return "contrato"
    if "licit" in lowered or "pregão" in lowered or "pregao" in lowered:
        return "licitacao"
    return expected_kind if expected_kind and re.search(r"\d", text) else None


def normalize_record(
    municipality: str,
    source_url: str,
    item: dict[str, str],
    expected_kind: RecordKind | None = None,
) -> PublicRecord | None:
    text = " ".join(item.get("text", "").split())
    normalized_text = _without_accents(text)
    normalized_labels = {_without_accents(label) for label in GENERIC_LABELS}
    if not text or normalized_text in normalized_labels or len(text) < 8:
        return None
    kind = expected_kind or classify_kind(text)
    if kind is None:
        return None
    detail_url = item.get("url") or source_url
    fields = {key: value or None for key, value in item.get("fields", {}).items()}
    if not fields and not re.search(r"\d{2,}[/.-]\d{2,}", text):
        return None
    if detail_url == source_url and not re.search(r"\d", text):
        return None
    return PublicRecord(
        municipality=municipality,
        kind=kind,
        source_url=source_url,
        title=fields.get("object") or text[:240],
        detail_url=urljoin(source_url, detail_url),
        process_number=fields.get("process_number"),
        modality=fields.get("modality"),
        object=fields.get("object"),
        opening_date=fields.get("opening_date"),
        value=fields.get("value"),
        status=fields.get("status"),
        published_at=fields.get("opening_date"),
        raw=item,
    )


def normalize_visible_items(
    municipality: str,
    source_url: str,
    items: Iterable[dict[str, str]],
    expected_kind: RecordKind | None = None,
) -> list[PublicRecord]:
    records: list[PublicRecord] = []
    seen: set[tuple[str, str, str | None]] = set()
    for item in items:
        record = normalize_record(municipality, source_url, item, expected_kind)
        if record is None:
            continue
        key = (record.kind, record.title, record.process_number)
        if key not in seen:
            seen.add(key)
            records.append(record)
    return records


class BrowserTransparencyCollector:
    async def collect(
        self,
        municipality: str,
        sources: Iterable[tuple[RecordKind, str]],
    ) -> list[PublicRecord]:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                records: list[PublicRecord] = []
                for expected_kind, url in sources:
                    records.extend(await self._collect_page(browser, municipality, expected_kind, url))
                return records
            finally:
                await browser.close()

    async def _collect_page(self, browser, municipality: str, expected_kind: RecordKind, url: str) -> list[PublicRecord]:
        page = await browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        try:
            await page.goto(url, wait_until="networkidle", timeout=45_000)
            items = await page.locator("a:visible").evaluate_all(
                """anchors => anchors.map(a => ({
                    text: (a.innerText || a.textContent || '').trim().replace(/\\s+/g, ' '),
                    url: a.href,
                    fields: {}
                }))"""
            )
            items.extend(await page.locator("table:visible tr").evaluate_all(
                """rows => rows.slice(1).map(row => {
                    const cells = [...row.querySelectorAll('th, td')].map(cell => (cell.innerText || '').trim().replace(/\\s+/g, ' '));
                    const links = [...row.querySelectorAll('a')];
                    return {text: cells.join(' | '), url: links[0]?.href || '', fields: {
                        modality: cells[0] || '', process_number: cells[1] || '', opening_date: cells[2] || '',
                        object: cells[3] || '', status: cells[cells.length - 1] || ''
                    }};
                })"""
            ))
            items.extend(await page.locator(".card:visible, [class*='card']:visible").evaluate_all(
                """cards => cards.map(card => ({text: (card.innerText || '').trim().replace(/\\s+/g, ' '), url: card.querySelector('a')?.href || '', fields: {}}))"""
            ))
            return normalize_visible_items(municipality, page.url, items, expected_kind)
        finally:
            await page.close()