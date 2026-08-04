"""Consent-gated web research capabilities."""

from genesis.app.research.service import (
    DuckDuckGoSearchProvider,
    ResearchResult,
    SafeWebClient,
    WebPage,
    WebResearchTool,
)

__all__ = [
    "DuckDuckGoSearchProvider",
    "ResearchResult",
    "SafeWebClient",
    "WebPage",
    "WebResearchTool",
]
