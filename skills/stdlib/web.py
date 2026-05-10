"""skills.stdlib.web — web search and URL fetching."""
from tools.search_web import search_web
from tools.fetch_url import fetch_url

__all__ = ["search_web", "fetch_url", "parallel_fetch"]


def parallel_fetch(urls: list, max_workers: int = 5) -> dict:
    """
    Fetch multiple URLs in parallel using ThreadPoolExecutor.
    
    Args:
        urls: List of URLs to fetch
        max_workers: Maximum concurrent workers (default 5)
    
    Returns:
        dict with success status and results for each URL
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    def fetch_single(url: str) -> dict:
        try:
            result = fetch_url(url)
            return {"url": url, "success": result.get("success", False), "content": result.get("content", ""), "error": result.get("error")}
        except Exception as e:
            return {"url": url, "success": False, "error": str(e)}
    
    results = {}
    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {executor.submit(fetch_single, url): url for url in urls}
            for future in as_completed(future_to_url):
                result = future.result()
                results[result["url"]] = result
        
        success_count = sum(1 for r in results.values() if r["success"])
        return {
            "success": True,
            "action": "parallel_fetch",
            "total": len(urls),
            "successful": success_count,
            "failed": len(urls) - success_count,
            "results": results
        }
    except Exception as e:
        return {
            "success": False,
            "action": "parallel_fetch",
            "error": str(e)
        }
