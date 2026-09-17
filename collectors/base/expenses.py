import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from bs4 import BeautifulSoup
from playwright.async_api import Browser, async_playwright

from app.models import PublicRecord


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


from app.core.money import parse_brl_money


def parse_brazilian_decimal(value: str | None) -> Decimal | None:
    return parse_brl_money(value)


def _decimal_text(value: Decimal | str | None) -> str | None:
    parsed = parse_brl_money(value)
    return str(parsed) if parsed is not None else None


def _cell_text(cell: Any) -> str:
    return " ".join(cell.get_text(" ", strip=True).split())


def extract_expense_rows(
    html: str,
    municipality: str = "Ceres-GO",
    source_url: str = "https://acessoainformacao.ceres.go.gov.br/cidadao/transparencia/sgdespesas",
) -> list[PublicRecord]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.tb") or soup.find("table")
    if table is None:
        return []

    records: list[PublicRecord] = []
    header_cells = table.select_one("tr").find_all(["th", "td"]) if table.select_one("tr") else []
    header_text = [_cell_text(cell) for cell in header_cells]
    for row in table.select("tr")[1:]:
        cells = row.find_all("td")
        if len(cells) < 7:
            continue
        movement_lines = [
            line.strip()
            for line in cells[0].get_text("\n", strip=True).splitlines()
            if line.strip()
        ]
        if len(movement_lines) >= 2:
            movement_type, movement_number = movement_lines[0], movement_lines[-1]
            data_cells = cells[1:]
        elif not _cell_text(cells[0]) and len(cells) >= 7:
            movement_type = header_text[1] if len(header_text) > 1 else "Movimento"
            movement_number = _cell_text(cells[1])
            data_cells = cells[2:]
        else:
            continue
        if len(data_cells) < 5:
            continue
        favored = _cell_text(data_cells[0])
        movement_date = _cell_text(data_cells[1])
        has_description = len(data_cells) >= 6
        description = _cell_text(data_cells[2]) if has_description else ""
        value_cells = data_cells[3:6] if has_description else data_cells[2:5]
        raw_values = [_cell_text(cell) for cell in value_cells]
        values = [_decimal_text(cell_txt) for cell_txt in raw_values]
        records.append(
            PublicRecord(
                municipality=municipality,
                kind="despesa",
                source_url=source_url,
                detail_url=source_url,
                title=description or f"{movement_type} {movement_number}",
                object=description,
                movement_type=movement_type,
                movement_number=movement_number,
                favored=favored,
                movement_date=movement_date,
                description=description,
                committed_value=values[0] if len(values) > 0 else None,
                liquidated_value=values[1] if len(values) > 1 else None,
                paid_value=values[2] if len(values) > 2 else None,
                committed_value_raw=raw_values[0] if len(raw_values) > 0 else None,
                liquidated_value_raw=raw_values[1] if len(raw_values) > 1 else None,
                paid_value_raw=raw_values[2] if len(raw_values) > 2 else None,
                raw={"cells": [_cell_text(cell) for cell in cells]},
            )
        )
    return records


def deduplicate_expenses(records: list[PublicRecord]) -> list[PublicRecord]:
    unique: list[PublicRecord] = []
    seen: set[tuple[str | None, str | None, str | None, str | None, str | None]] = set()
    for record in records:
        key = (
            record.movement_type,
            record.movement_number,
            record.movement_date,
            record.favored,
            record.description,
        )
        if key not in seen:
            seen.add(key)
            unique.append(record)
    return unique


class ExpensesCollector:
    def __init__(self, municipality: str, source_url: str) -> None:
        self.municipality = municipality
        self.source_url = source_url

    async def collect(self, max_pages: int | None = None) -> tuple[list[PublicRecord], int | None, int]:
        if max_pages is not None and max_pages < 1:
            raise ValueError("max_pages deve ser maior que zero")
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                return await self._collect_with_browser(browser, max_pages)
            finally:
                await browser.close()

    async def _collect_with_browser(
        self, browser: Browser, max_pages: int | None
    ) -> tuple[list[PublicRecord], int | None, int]:
        page = await browser.new_page(user_agent=USER_AGENT)
        try:
            await page.goto(self.source_url, wait_until="networkidle", timeout=45_000)
            await page.locator("table.tb").wait_for(state="visible", timeout=30_000)
            records: list[PublicRecord] = []
            expected_total = self._read_expected_total(await page.locator("body").inner_text())
            current_page = 0
            while True:
                current_page += 1
                html = await page.locator("table.tb").evaluate("table => table.outerHTML")
                page_records = extract_expense_rows(html, self.municipality, page.url)
                records = deduplicate_expenses(records + page_records)
                print(
                    f"[despesas] município={self.municipality} página={current_page} "
                    f"coletados={len(records)} na_pagina={len(page_records)} "
                    f"total_esperado={expected_total or 'desconhecido'}"
                )
                if expected_total is not None and len(records) >= expected_total:
                    break
                if max_pages is not None and current_page >= max_pages:
                    break

                next_page = current_page + 1
                page_selector = page.locator("select[name='ir_para']:visible")
                if await page_selector.count():
                    await page_selector.locator(f"option[value='{next_page}']").wait_for(
                        state="attached", timeout=30_000
                    )
                    await page_selector.select_option(str(next_page))
                else:
                    next_button = page.get_by_role("button", name=">", exact=True)
                    if await next_button.count() == 0 or await next_button.is_disabled():
                        break
                    await next_button.click()
                await page.locator("table.tb tr").nth(1).wait_for(state="visible", timeout=30_000)
                if expected_total is not None:
                    expected_start = (next_page - 1) * 15 + 1
                    expected_end = min(next_page * 15, expected_total)
                    formatted_total = f"{expected_total:,}".replace(",", ".")
                    expected_range = f"{expected_start}-{expected_end} de {formatted_total}"
                    await page.wait_for_function(
                        "expected => document.body.innerText.includes(expected)",
                        arg=expected_range,
                        timeout=60_000,
                    )
                else:
                    await page.wait_for_timeout(500)
            return records, expected_total, current_page
        finally:
            await page.close()

    @staticmethod
    def _read_expected_total(text: str) -> int | None:
        match = re.search(r"\d+\s*-\s*\d+\s+de\s+([\d.]+)", text, re.IGNORECASE)
        return int(match.group(1).replace(".", "")) if match else None


def serialize_expenses(
    municipality: str,
    source_url: str,
    records: list[PublicRecord],
    expected_total: int | None,
    pages: int,
) -> dict[str, Any]:
    return {
        "municipality": municipality,
        "kind": "despesa",
        "source_url": source_url,
        "collected_at": datetime.now(UTC).isoformat(),
        "total_expected": expected_total,
        "pages_collected": pages,
        "records": [record.model_dump(mode="json") for record in records],
    }
