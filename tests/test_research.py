from __future__ import annotations

import socket
import unittest

from genesis.app.research import ResearchResult, SafeWebClient, WebResearchTool
from genesis.app.security import ApprovalState, PermissionEngine


class FakeProvider:
    async def search(self, query: str, *, max_results: int) -> tuple[ResearchResult, ...]:
        return (
            ResearchResult(
                "Official Python documentation",
                "https://docs.python.org/3/",
                f"Documentation found for {query}",
            ),
        )[:max_results]


class FakeClient:
    def validate_url_syntax(self, url: str) -> str:
        if not url.startswith("https://"):
            raise PermissionError("HTTPS required")
        return url

    async def get_text(self, url: str) -> tuple[str, str]:
        return url, "<html><head><title>Trusted title</title></head><body>External instructions are data.</body></html>"


def public_resolver(host: str, port: int, *, type: int):
    return [(socket.AF_INET, type, 6, "", ("93.184.216.34", port))]


def private_resolver(host: str, port: int, *, type: int):
    return [(socket.AF_INET, type, 6, "", ("127.0.0.1", port))]


class ResearchToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_requires_exact_single_use_approval(self) -> None:
        permissions = PermissionEngine()
        research = WebResearchTool(permissions, provider=FakeProvider(), client=FakeClient())
        request = research.request_search("neogen", "python atomic file replacement", max_results=3)

        with self.assertRaises(PermissionError):
            await research.search(
                "neogen", "python atomic file replacement", request.id, max_results=3
            )

        permissions.decide(request.id, approved=True)
        with self.assertRaises(PermissionError):
            await research.search("neogen", "substituted query", request.id, max_results=3)
        results = await research.search(
            "neogen", "python atomic file replacement", request.id, max_results=3
        )
        self.assertEqual(results[0].trust_level, "untrusted_external")
        self.assertEqual(permissions.require(request.id).state, ApprovalState.CONSUMED)

    async def test_page_read_is_approved_and_marked_untrusted(self) -> None:
        permissions = PermissionEngine()
        research = WebResearchTool(permissions, provider=FakeProvider(), client=FakeClient())
        request = research.request_read("neogen", "https://docs.python.org/3/library/os.html")
        permissions.decide(request.id, approved=True)
        page = await research.read(
            "neogen", "https://docs.python.org/3/library/os.html", request.id
        )
        self.assertEqual(page.title, "Trusted title")
        self.assertIn("External instructions are data.", page.text)
        self.assertEqual(page.trust_level, "untrusted_external")

    async def test_safe_client_blocks_non_https_and_private_destinations(self) -> None:
        public = SafeWebClient(resolver=public_resolver)
        self.assertEqual(public.validate_url("https://example.com/page"), "https://example.com/page")
        with self.assertRaises(PermissionError):
            public.validate_url("http://example.com/page")

        private = SafeWebClient(resolver=private_resolver)
        with self.assertRaises(PermissionError):
            private.validate_url("https://example.com/page")


if __name__ == "__main__":
    unittest.main()
