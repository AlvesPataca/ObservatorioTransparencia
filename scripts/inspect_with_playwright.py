import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import urljoin

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from playwright.async_api import async_playwright


TARGETS = [
    {
        "municipality": "Ceres-GO",
        "label": "Portal licitacoes",
        "url": "https://acessoainformacao.ceres.go.gov.br/cidadao/informacao/licitacoes",
    },
    {
        "municipality": "Rialma-GO",
        "label": "Portal raiz",
        "url": "https://acessoainformacao.rialma.go.gov.br/",
    },
]


async def inspect_target(browser, target: dict[str, str]) -> dict:
    page = await browser.new_page(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    )

    result = {
        **target,
        "status": None,
        "final_url": None,
        "title": None,
        "links": [],
        "forms": [],
        "buttons": [],
        "inputs": [],
        "text_sample": None,
        "screenshot": None,
        "error": None,
    }

    try:
        response = await page.goto(target["url"], wait_until="networkidle", timeout=45_000)
        result["status"] = response.status if response else None
        result["final_url"] = page.url
        result["title"] = await page.title()

        safe_name = (
            f"{target['municipality']}_{target['label']}"
            .lower()
            .replace("-", "_")
            .replace(" ", "_")
        )
        screenshot_path = PROJECT_ROOT / "data" / f"{safe_name}.png"
        await page.screenshot(path=str(screenshot_path), full_page=True)
        result["screenshot"] = str(screenshot_path)

        result["text_sample"] = " ".join((await page.locator("body").inner_text(timeout=5_000)).split())[:3000]

        result["links"] = await page.locator("a").evaluate_all(
            """anchors => anchors.slice(0, 200).map(a => ({
                text: (a.innerText || a.textContent || '').trim().replace(/\\s+/g, ' '),
                href: a.getAttribute('href'),
                url: a.href
            }))"""
        )
        result["forms"] = await page.locator("form").evaluate_all(
            """forms => forms.map(form => ({
                method: form.getAttribute('method'),
                action: form.getAttribute('action'),
                resolved_action: form.action
            }))"""
        )
        result["buttons"] = await page.locator("button, input[type=button], input[type=submit]").evaluate_all(
            """buttons => buttons.slice(0, 100).map(button => ({
                text: (button.innerText || button.value || '').trim().replace(/\\s+/g, ' '),
                type: button.getAttribute('type'),
                name: button.getAttribute('name')
            }))"""
        )
        result["inputs"] = await page.locator("input, select").evaluate_all(
            """inputs => inputs.slice(0, 100).map(input => ({
                tag: input.tagName.toLowerCase(),
                type: input.getAttribute('type'),
                name: input.getAttribute('name'),
                id: input.getAttribute('id'),
                placeholder: input.getAttribute('placeholder')
            }))"""
        )
    except Exception as exc:
        result["error"] = f"{exc.__class__.__name__}: {exc}"
    finally:
        await page.close()

    for link in result["links"]:
        if link.get("href") and not link.get("url"):
            link["url"] = urljoin(result["final_url"] or target["url"], link["href"])

    return result


async def main() -> None:
    output_path = PROJECT_ROOT / "data" / "playwright_portal_inspection.json"
    output_path.parent.mkdir(exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        results = [await inspect_target(browser, target) for target in TARGETS]
        await browser.close()

    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    for result in results:
        print(f"\n{result['municipality']} - {result['label']}")
        print(f"- Status: {result['status']}")
        print(f"- Titulo: {result['title']}")
        print(f"- URL final: {result['final_url']}")
        print(f"- Links encontrados: {len(result['links'])}")
        print(f"- Forms encontrados: {len(result['forms'])}")
        print(f"- Screenshot: {result['screenshot']}")
        if result["error"]:
            print(f"- Erro: {result['error']}")

    print(f"\nResultado salvo em {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
