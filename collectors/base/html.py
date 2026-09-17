from urllib.parse import urljoin

from bs4 import BeautifulSoup


def extract_links(html: str, base_url: str, keywords: tuple[str, ...]) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    found: list[dict[str, str]] = []

    for anchor in soup.find_all("a"):
        text = " ".join(anchor.get_text(" ", strip=True).split())
        href = anchor.get("href")
        if not href:
            continue

        haystack = f"{text} {href}".lower()
        if any(keyword.lower() in haystack for keyword in keywords):
            found.append({"text": text or href, "url": urljoin(base_url, href)})

    return found
