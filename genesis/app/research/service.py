"""Safe, provider-neutral web search and source reading.

External pages are deliberately returned as untrusted data. They are never interpreted as
instructions by this layer and no downloaded content is executed.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
import ipaddress
import json
import re
import socket
from typing import Callable, Protocol
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from genesis.app.security import ApprovalRequest, PermissionEngine


@dataclass(frozen=True, slots=True)
class ResearchResult:
    """One source discovered by a search provider."""

    title: str
    url: str
    snippet: str = ""
    trust_level: str = "untrusted_external"


@dataclass(frozen=True, slots=True)
class WebPage:
    """Text extracted from an explicitly approved external page."""

    title: str
    url: str
    text: str
    retrieved_at: str
    trust_level: str = "untrusted_external"


class SearchProvider(Protocol):
    async def search(self, query: str, *, max_results: int) -> tuple[ResearchResult, ...]: ...


class _ValidatedRedirectHandler(HTTPRedirectHandler):
    def __init__(self, validator: Callable[[str], str]) -> None:
        super().__init__()
        self._validator = validator

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        newurl = urljoin(req.full_url, newurl)
        self._validator(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class SafeWebClient:
    """Bounded HTTPS reader with local-network and redirect protection."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 12,
        max_response_bytes: int = 1_000_000,
        resolver: Callable[..., list[tuple]] = socket.getaddrinfo,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self._resolver = resolver
        self._opener = build_opener(_ValidatedRedirectHandler(self.validate_url))

    def validate_url(self, url: str) -> str:
        parsed = urlparse(self.validate_url_syntax(url))
        hostname = parsed.hostname.rstrip(".").lower()
        try:
            addresses = self._resolver(hostname, 443, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise ConnectionError(f"Could not resolve web source: {hostname}") from exc
        if not addresses:
            raise ConnectionError(f"Could not resolve web source: {hostname}")
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0].split("%", 1)[0])
            if not ip.is_global:
                raise PermissionError("Local, private, reserved, and link-local web sources are blocked.")
        return url

    @staticmethod
    def validate_url_syntax(url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme.lower() != "https":
            raise PermissionError("Only HTTPS web sources are allowed.")
        if not parsed.hostname or parsed.username or parsed.password:
            raise PermissionError("The web source must have a public hostname and no embedded credentials.")
        if parsed.port not in {None, 443}:
            raise PermissionError("Only the standard HTTPS port is allowed.")
        hostname = parsed.hostname.rstrip(".").lower()
        if hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal")):
            raise PermissionError("Local and internal network sources are blocked.")
        return url

    async def get_text(self, url: str) -> tuple[str, str]:
        return await asyncio.to_thread(self._get_text, url)

    def _get_text(self, url: str) -> tuple[str, str]:
        self.validate_url(url)
        request = Request(
            url,
            headers={
                "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9",
                "User-Agent": "NeoGen-Research/0.1 (+local-consent-gated-agent)",
            },
        )
        with self._opener.open(request, timeout=self.timeout_seconds) as response:
            final_url = self.validate_url(response.geturl())
            media_type = response.headers.get_content_type()
            if media_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
                raise ValueError(f"Unsupported web content type: {media_type}")
            payload = response.read(self.max_response_bytes + 1)
            if len(payload) > self.max_response_bytes:
                raise ValueError("Web response exceeded the configured size limit.")
            charset = response.headers.get_content_charset() or "utf-8"
            return final_url, payload.decode(charset, errors="replace")


class _DuckDuckGoParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[ResearchResult] = []
        self._href: str | None = None
        self._title_parts: list[str] = []
        self._snippet_parts: list[str] = []
        self._reading_title = False
        self._reading_snippet = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if tag == "a" and "result__a" in classes:
            self._href = attributes.get("href")
            self._title_parts = []
            self._reading_title = True
        elif "result__snippet" in classes:
            self._snippet_parts = []
            self._reading_snippet = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._reading_title:
            self._reading_title = False
            title = _clean_text(" ".join(self._title_parts))
            if title and self._href:
                self.results.append(ResearchResult(title, _unwrap_duckduckgo_url(self._href)))
        elif self._reading_snippet and tag in {"a", "div", "span"}:
            self._reading_snippet = False
            if self.results:
                previous = self.results[-1]
                self.results[-1] = ResearchResult(
                    previous.title,
                    previous.url,
                    _clean_text(" ".join(self._snippet_parts)),
                )

    def handle_data(self, data: str) -> None:
        if self._reading_title:
            self._title_parts.append(data)
        if self._reading_snippet:
            self._snippet_parts.append(data)


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self._in_title = False
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._ignored_depth += 1
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._ignored_depth:
            self._ignored_depth -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        if self._in_title:
            self.title_parts.append(data)
        self.text_parts.append(data)


class DuckDuckGoSearchProvider:
    """No-key search provider; callers may inject another provider with the same protocol."""

    endpoint = "https://html.duckduckgo.com/html/"

    def __init__(self, client: SafeWebClient | None = None) -> None:
        self.client = client or SafeWebClient()

    async def search(self, query: str, *, max_results: int) -> tuple[ResearchResult, ...]:
        _, document = await self.client.get_text(f"{self.endpoint}?q={quote_plus(query)}")
        parser = _DuckDuckGoParser()
        parser.feed(document)
        return tuple(parser.results[:max_results])


class WebResearchTool:
    """Approval-gated web search and page extraction for the coding agent."""

    def __init__(
        self,
        permissions: PermissionEngine,
        *,
        provider: SearchProvider | None = None,
        client: SafeWebClient | None = None,
        max_page_characters: int = 100_000,
    ) -> None:
        self.permissions = permissions
        self.client = client or SafeWebClient()
        self.provider = provider or DuckDuckGoSearchProvider(self.client)
        self.max_page_characters = max_page_characters

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    def request_search(self, project_id: str, query: str, *, max_results: int = 8) -> ApprovalRequest:
        query = self._validate_query(query)
        self._validate_limit(max_results)
        return self.permissions.request(
            project_id,
            "web.search",
            f'Search the public web for "{query}" (up to {max_results} results)',
            action=self._search_action(query, max_results),
        )

    async def search(
        self, project_id: str, query: str, approval_id: str, *, max_results: int = 8
    ) -> tuple[ResearchResult, ...]:
        query = self._validate_query(query)
        self._validate_limit(max_results)
        self.permissions.consume(
            approval_id,
            project_id,
            "web.search",
            action=self._search_action(query, max_results),
        )
        return await self.provider.search(query, max_results=max_results)

    def request_read(self, project_id: str, url: str) -> ApprovalRequest:
        url = self.client.validate_url_syntax(url)
        return self.permissions.request(
            project_id,
            "web.read",
            f"Read public web source {url}",
            action=self._read_action(url),
        )

    async def read(self, project_id: str, url: str, approval_id: str) -> WebPage:
        url = self.client.validate_url_syntax(url)
        self.permissions.consume(approval_id, project_id, "web.read", action=self._read_action(url))
        final_url, document = await self.client.get_text(url)
        parser = _PageParser()
        parser.feed(document)
        title = _clean_text(" ".join(parser.title_parts)) or final_url
        text = _clean_text(" ".join(parser.text_parts))[: self.max_page_characters]
        return WebPage(title, final_url, text, datetime.now(UTC).isoformat())

    @staticmethod
    def _validate_query(query: str) -> str:
        query = _clean_text(query)
        if not query:
            raise ValueError("Search query must not be empty.")
        if len(query) > 500:
            raise ValueError("Search query exceeds 500 characters.")
        return query

    @staticmethod
    def _validate_limit(max_results: int) -> None:
        if not 1 <= max_results <= 20:
            raise ValueError("max_results must be between 1 and 20.")

    @staticmethod
    def _search_action(query: str, max_results: int) -> str:
        return json.dumps({"query": query, "max_results": max_results}, sort_keys=True)

    @staticmethod
    def _read_action(url: str) -> str:
        return json.dumps({"url": url}, sort_keys=True)


def _unwrap_duckduckgo_url(url: str) -> str:
    parsed = urlparse(url)
    target = parse_qs(parsed.query).get("uddg")
    return unquote(target[0]) if target else url


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
