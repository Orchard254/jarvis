"""skills.stdlib.filesystem — file & directory operations."""
from tools.read_file import read_file
from tools.write_file import write_file
from tools.file_ops import file_ops

__all__ = ["read_file", "write_file", "file_ops", "parallel_read"]


def parallel_read(file_paths: list, max_workers: int = 5) -> dict:
    """
    Read multiple files in parallel using ThreadPoolExecutor.
    
    Args:
        file_paths: List of file paths to read
        max_workers: Maximum concurrent workers (default 5)
    
    Returns:
        dict with success status and contents for each file
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    def read_single(path: str) -> dict:
        try:
            result = read_file(path)
            return {"path": path, "success": result.get("success", False), "content": result.get("content", ""), "error": result.get("error")}
        except Exception as e:
            return {"path": path, "success": False, "error": str(e)}
    
    results = {}
    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_path = {executor.submit(read_single, path): path for path in file_paths}
            for future in as_completed(future_to_path):
                result = future.result()
                results[result["path"]] = result
        
        success_count = sum(1 for r in results.values() if r["success"])
        return {
            "success": True,
            "action": "parallel_read",
            "total": len(file_paths),
            "successful": success_count,
            "failed": len(file_paths) - success_count,
            "results": results
        }
    except Exception as e:
        return {
            "success": False,
            "action": "parallel_read",
            "error": str(e)
        }
