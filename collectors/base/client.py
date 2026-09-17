from collections.abc import Iterable

import httpx

from app.core.config import get_settings
from app.models import SourceCheck


class TransparencyHttpClient:
    def __init__(self) -> None:
        settings = get_settings()
        self._client = httpx.Client(
            follow_redirects=True,
            timeout=settings.request_timeout_seconds,
            headers={
                "User-Agent": settings.user_agent,
                "Accept": "text/html,application/json,*/*",
            },
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "TransparencyHttpClient":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def get(self, url: str) -> httpx.Response:
        return self._client.get(url)

    def check_sources(self, municipality: str, sources: Iterable[tuple[str, str]]) -> list[SourceCheck]:
        checks: list[SourceCheck] = []
        for label, url in sources:
            try:
                response = self.get(url)
                status_code = response.status_code
                content_type = response.headers.get("content-type")
                blocked = status_code in {401, 403, 429}
                checks.append(
                    SourceCheck(
                        municipality=municipality,
                        label=label,
                        url=url,
                        status_code=status_code,
                        content_type=content_type,
                        final_url=str(response.url),
                        accessible=response.is_success,
                        blocked=blocked,
                        notes="Acesso bloqueado para automacao simples." if blocked else None,
                    )
                )
            except httpx.HTTPError as exc:
                checks.append(
                    SourceCheck(
                        municipality=municipality,
                        label=label,
                        url=url,
                        notes=f"Falha HTTP: {exc.__class__.__name__}: {exc}",
                    )
                )
        return checks
