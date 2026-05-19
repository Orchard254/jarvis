"""
Research Sub-Agent — web research, fact-finding, page fetching.

Handles tasks like:
  - "Search for the latest news on X"
  - "Find the price of Y on Amazon"
  - "Fetch the content of this URL and summarize it"
  - "Download the PDF at <url> and save it to Downloads"

Reports findings as structured data + a concise summary to Jarvis.
Jarvis then synthesizes the summary for the user.
"""

from __future__ import annotations

import logging
import time

from agents.base_agent import SubAgentBase, SubAgentResult, SubAgentTask
from agents.sub_agent_registry import register

logger = logging.getLogger(__name__)


class ResearchAgent(SubAgentBase):
    name = "research"
    description = (
        "Web research, fact-finding, URL fetching, and file downloading. "
        "Use for any task that requires searching or reading online content."
    )
    capabilities = [
        "web_search",
        "fetch_page",
        "download_file",
        "open_url",
        "data_analysis",
    ]

    def run(self, task: SubAgentTask) -> SubAgentResult:
        start = time.time()
        tool_log: list[dict] = []
        goal = task.goal
        ctx = task.context

        self._log.info(f"[{task.task_id}] Research task: {goal[:100]}")

        # ── Step 1: Determine the search query ──────────────────────────────
        # Use context if a query is pre-provided, otherwise derive from goal
        query = ctx.get("query") or goal
        max_results = int(ctx.get("max_results", 5))

        findings: list[dict] = []
        errors: list[str] = []

        # ── Step 2: Web search ──────────────────────────────────────────────
        ok, search_result = self._tool_ok("web_search", query=query, max_results=max_results)
        tool_log.append({"tool": "web_search", **search_result})

        if ok:
            findings = search_result.get("results", [])
            source = search_result.get("source", "unknown")
            self._log.info(
                f"[{task.task_id}] Got {len(findings)} results from {source}"
            )
        else:
            errors.append(f"web_search failed: {search_result.get('error', '?')}")

        # ── Step 3: Optionally deep-fetch top URLs ──────────────────────────
        fetch_top = int(ctx.get("fetch_top_n", 0))
        fetched_pages: list[dict] = []

        if fetch_top > 0 and findings:
            max_chars = int(ctx.get("page_max_chars", 6000))
            for item in findings[:fetch_top]:
                url = item.get("url", "")
                if not url:
                    continue
                f_ok, f_result = self._tool_ok("fetch_page", url=url, max_chars=max_chars)
                tool_log.append({"tool": "fetch_page", "url": url, **f_result})
                if f_ok:
                    fetched_pages.append({
                        "url": url,
                        "title": f_result.get("title", ""),
                        "content": f_result.get("content", "")[:3000],
                    })
                else:
                    errors.append(f"fetch_page({url}) failed: {f_result.get('error', '?')}")

        # ── Step 4: Optional direct URL fetch ───────────────────────────────
        if "url" in ctx:
            url = ctx["url"]
            max_chars = int(ctx.get("page_max_chars", 8000))
            f_ok, f_result = self._tool_ok("fetch_page", url=url, max_chars=max_chars)
            tool_log.append({"tool": "fetch_page", "url": url, **f_result})
            if f_ok:
                fetched_pages.append({
                    "url": url,
                    "title": f_result.get("title", ""),
                    "content": f_result.get("content", "")[:4000],
                })
            else:
                errors.append(f"fetch_page({url}) failed: {f_result.get('error', '?')}")

        # ── Step 5: Optional file download ──────────────────────────────────
        downloaded: list[dict] = []
        if "download_url" in ctx and "download_path" in ctx:
            d_ok, d_result = self._tool_ok(
                "download_file",
                url=ctx["download_url"],
                path=ctx["download_path"],
            )
            tool_log.append({"tool": "download_file", **d_result})
            if d_ok:
                downloaded.append({"path": ctx["download_path"], "size": d_result.get("size_bytes")})
            else:
                errors.append(f"download_file failed: {d_result.get('error', '?')}")

        # ── Build result ────────────────────────────────────────────────────
        elapsed = round(time.time() - start, 2)
        success = bool(findings or fetched_pages or downloaded)

        # Build human-readable summary for Jarvis
        summary_parts = []
        if findings:
            summary_parts.append(f"Found {len(findings)} web results for '{query}':")
            for i, r in enumerate(findings[:5], 1):
                title = r.get("title", "")[:80]
                url = r.get("url", "")
                snippet = r.get("snippet", "")[:120]
                summary_parts.append(f"  {i}. {title}\n     {url}\n     {snippet}")
        if fetched_pages:
            summary_parts.append(f"\nFetched {len(fetched_pages)} page(s) in full.")
            for p in fetched_pages:
                summary_parts.append(f"  [{p['title'] or p['url']}] {p['content'][:300]}...")
        if downloaded:
            for d in downloaded:
                summary_parts.append(f"\nDownloaded file: {d['path']} ({d.get('size', '?')} bytes)")
        if errors:
            summary_parts.append(f"\nErrors: {'; '.join(errors)}")
        if not summary_parts:
            summary_parts.append("No results found.")

        return SubAgentResult(
            success=success,
            summary="\n".join(summary_parts),
            data={
                "query": query,
                "results": findings,
                "fetched_pages": fetched_pages,
                "downloaded": downloaded,
                "errors": errors,
            },
            error="; ".join(errors) if not success else "",
            tool_calls=tool_log,
            elapsed_s=elapsed,
            agent_name=self.name,
        )


# Auto-register on import
register(ResearchAgent())
