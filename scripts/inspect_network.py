import asyncio
import argparse
import json
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs

from playwright.async_api import async_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
INTERESTING_TERMS = (
    "despesas", "empenho", "liquidacao", "pagamento", "transparencia", "datatable", "ajax", "api"
)
PAGINATION_TERMS = ("start", "length", "page", "draw", "ano", "exercicio", "datainicial", "datafinal")


def relevant_headers(headers: dict[str, str]) -> dict[str, str]:
    names = {"accept", "content-type", "origin", "referer", "user-agent", "x-requested-with"}
    return {key: value for key, value in headers.items() if key.lower() in names}


async def select_year(page, year: int) -> str | None:
    year_str = str(year)
    for selector in ("select", "input"):
        elements = page.locator(f"{selector}:visible")
        for index in range(await elements.count()):
            element = elements.nth(index)
            name = ((await element.get_attribute("name")) or "").casefold()
            element_id = ((await element.get_attribute("id")) or "").casefold()
            options = await element.locator("option").all() if selector == "select" else []
            if selector == "select":
                for option in options:
                    text = (await option.inner_text()).strip()
                    value = await option.get_attribute("value")
                    if text == year_str or value == year_str:
                        await element.select_option(value=value or text)
                        return f"{name or element_id}={year_str}"
            elif "ano" in name or "ano" in element_id or "exerc" in name or "exerc" in element_id:
                await element.fill(year_str)
                await element.press("Enter")
                return f"{name or element_id}={year_str}"
    return None



async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--municipality", choices=("ceres", "rialma"), default="ceres")
    parser.add_argument("--module", choices=("expenses",), default="expenses")
    parser.add_argument("--year", type=int, default=2026)
    args = parser.parse_args()
    from collectors.municipalities import MUNICIPALITIES
    config = MUNICIPALITIES[args.municipality]
    url = config.expenses_url
    output_path = PROJECT_ROOT / "data" / "network" / f"{args.municipality}_despesas_{args.year}_requests.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    captured: list[dict] = []
    order = 0

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(user_agent=USER_AGENT)

        async def capture_response(response) -> None:
            nonlocal order
            request = response.request
            resource_type = request.resource_type
            if resource_type not in {"xhr", "fetch"}:
                return
            order += 1
            content_type = response.headers.get("content-type", "")
            preview = None
            if "json" in content_type or "text" in content_type or not content_type:
                try:
                    body = await response.text()
                    if len(body) <= 5000:
                        preview = body
                    else:
                        preview = body[:5000]
                except Exception:
                    preview = None
            lower_url = request.url.casefold()
            post_data = request.post_data
            combined = f"{lower_url} {post_data or ''}".casefold()
            captured.append({
                "order": order,
                "resource_type": resource_type,
                "method": request.method,
                "url": request.url,
                "headers": relevant_headers(request.headers),
                "post_data": post_data,
                "response_status": response.status,
                "response_content_type": content_type,
                "response_preview": preview,
                "interesting": any(term in combined or term in content_type.casefold() for term in INTERESTING_TERMS),
                "pagination_hints": [term for term in PAGINATION_TERMS if term in combined],
            })

        page.on("response", capture_response)
        await page.goto(url, wait_until="networkidle", timeout=60_000)
        await page.locator("table.tb").wait_for(state="visible", timeout=30_000)
        selected = await select_year(page, args.year)
        if selected:
            await page.wait_for_timeout(3000)
        next_button = page.get_by_role("button", name=">", exact=True)
        if await next_button.count() and not await next_button.is_disabled():
            await next_button.click()
            await page.wait_for_timeout(3000)
        await page.wait_for_timeout(1000)
        await browser.close()

    year_str = str(args.year)
    year_detected = any(
        f'"ano":"{year_str}"' in (item.get("post_data") or "")
        or f'"ano": "{year_str}"' in (item.get("post_data") or "")
        or f"/{year_str}" in (item.get("post_data") or "")
        or f"-{year_str}" in (item.get("post_data") or "")
        for item in captured
    )

    result = {
        "municipality": args.municipality,
        "module": args.module,
        "year": args.year,
        "url": url,
        "selected_year": selected,
        "year_detected_in_requests": year_detected,
        "captured_at": time.time(),
        "requests": captured,
        "possible_data_endpoints": [
            item for item in captured
            if item["response_status"] < 400
            and (item["pagination_hints"] or item["interesting"] or "json" in item["response_content_type"])
        ],
    }
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Requests XHR/fetch capturadas: {len(captured)}")
    print(f"Possíveis endpoints de dados: {len(result['possible_data_endpoints'])}")
    print(f"Ano selecionado: {selected or 'não identificado'}; detectado nas requisições: {year_detected}")
    print(f"Resultado salvo em {output_path}")


if __name__ == "__main__":
    asyncio.run(main())