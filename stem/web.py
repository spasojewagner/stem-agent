"""Web access for the developmental process.

`web_search` runs server-side through a model with built-in browser search
(Groq's gpt-oss models), so no extra API key is needed. `web_fetch` only
reaches domains on an allow-list. Neither is given to genome-authored code.
"""
from __future__ import annotations

import html
import re
from urllib.parse import urlparse

import requests

from .tools import Tool, clip, schema


def _host_allowed(url: str, allow: list[str]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in allow)


def _html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|nav|footer|header).*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(raw)).strip()


def web_tools(client, settings) -> list[Tool]:
    def search(args: dict) -> str:
        query = str(args.get("query", "")).strip()
        if not query:
            return "ERROR: empty query"
        msg = client.chat(settings.model_search,
                          [{"role": "user", "content": f"Search the web and summarise what you find, "
                                                       f"with sources: {query}"}],
                          tools=[{"type": "browser_search"}], temperature=0.2, max_tokens=900,
                          extra={"tool_choice": "required", "reasoning_effort": "low"})
        return clip(msg.get("content") or "(no results)", 3000)

    def fetch(args: dict) -> str:
        url = str(args.get("url", ""))
        if not url.startswith(("http://", "https://")):
            return "ERROR: url must start with http(s)://"
        if not _host_allowed(url, settings.web_allow):
            return f"ERROR: domain not on the allow-list ({', '.join(settings.web_allow)}). Set STEM_WEB_ALLOW to change it."
        r = requests.get(url, timeout=20, headers={"User-Agent": "stem-agent/2 (+https://github.com/spasojewagner/stem-agent)"})
        return clip(_html_to_text(r.text[:400_000]), 4000)

    return [
        Tool("web_search", "Search the web. Returns a summary with sources.",
             schema({"query": {"type": "string"}}, ["query"]), search),
        Tool("web_fetch", "Fetch a page from an allow-listed domain as plain text.",
             schema({"url": {"type": "string"}}, ["url"]), fetch),
    ]
