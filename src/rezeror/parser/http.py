from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from rezeror.config import USER_AGENT


@dataclass(slots=True)
class HttpResponse:
    status_code: int
    text: str
    url: str
    headers: Mapping[str, str]


class HttpClient:
    def __init__(
        self,
        user_agent: str = USER_AGENT,
        timeout: tuple[float, float] = (8.0, 30.0),
        retries: int = 3,
        backoff_factor: float = 0.7,
    ) -> None:
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": user_agent})
        retry = Retry(
            total=retries,
            backoff_factor=backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=frozenset(["GET", "HEAD"]),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)

    def fetch_text(
        self,
        url: str,
        headers: Optional[dict[str, str]] = None,
        allow_not_modified: bool = False,
    ) -> HttpResponse:
        response = self._session.get(
            url,
            headers=headers,
            timeout=self._timeout,
            allow_redirects=True,
        )
        if allow_not_modified and response.status_code == 304:
            return HttpResponse(
                status_code=304,
                text="",
                url=response.url,
                headers=response.headers,
            )
        response.raise_for_status()
        return HttpResponse(
            status_code=response.status_code,
            text=response.text,
            url=response.url,
            headers=response.headers,
        )
