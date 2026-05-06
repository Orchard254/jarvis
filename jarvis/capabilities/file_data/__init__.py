"""
5. File & Data System (4 tools)
For local productivity.
"""

import os
import json
import csv
from typing import Optional, Any
from dataclasses import dataclass
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class FileReader:
    """
    file_reader: Read files from disk
    
    Reads various file formats with encoding detection.
    """
    
    def execute(self, file_path: str, encoding: str = "utf-8",
                max_size_mb: int = 10, **kwargs) -> dict:
        """
        Read a file.
        
        Args:
            file_path: Path to file
            encoding: File encoding
            max_size_mb: Maximum file size to read
            
        Returns:
            File content
        """
        try:
            path = Path(file_path)
            
            if not path.exists():
                return {"success": False, "error": "File not found", "output": None}
            
            # Check file size
            size_mb = path.stat().st_size / (1024 * 1024)
            if size_mb > max_size_mb:
                return {
                    "success": False, 
                    "error": f"File too large ({size_mb:.1f}MB > {max_size_mb}MB)",
                    "output": None
                }
            
            # Read based on extension
            ext = path.suffix.lower()
            
            if ext in ['.txt', '.md', '.py', '.js', '.json', '.xml', '.yaml', '.yml']:
                with open(path, 'r', encoding=encoding) as f:
                    content = f.read()
            elif ext == '.csv':
                with open(path, 'r', encoding=encoding) as f:
                    content = f.read()
            else:
                # Binary file - return metadata only
                return {
                    "success": True,
                    "output": {
                        "type": "binary",
                        "path": str(path),
                        "size_bytes": path.stat().st_size,
                        "extension": ext
                    }
                }
            
            return {
                "success": True,
                "output": {
                    "content": content,
                    "path": str(path),
                    "size_bytes": len(content.encode('utf-8')),
                    "lines": len(content.splitlines())
                }
            }
            
        except Exception as e:
            return {"success": False, "error": str(e), "output": None}


class FileWriter:
    """
    file_writer: Write files to disk
    
    Writes content to files with backup support.
    """
    
    def __init__(self, create_backup: bool = True):
        self.create_backup = create_backup
    
    def execute(self, file_path: str, content: str,
                mode: str = "write", encoding: str = "utf-8",
                **kwargs) -> dict:
        """
        Write to a file.
        
        Args:
            file_path: Path to file
            content: Content to write
            mode: 'write' (overwrite) or 'append'
            encoding: File encoding
            
        Returns:
            Write result
        """
        try:
            path = Path(file_path)
            
            # Create backup if exists
            if self.create_backup and path.exists():
                backup_path = path.with_suffix(path.suffix + '.bak')
                path.rename(backup_path)
            
            # Ensure parent directory exists
            path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write content
            write_mode = 'a' if mode == 'append' else 'w'
            with open(path, write_mode, encoding=encoding) as f:
                f.write(content)
            
            return {
                "success": True,
                "output": {
                    "path": str(path),
                    "bytes_written": len(content.encode('utf-8')),
                    "mode": mode,
                    "backup_created": self.create_backup and path.exists()
                }
            }
            
        except Exception as e:
            return {"success": False, "error": str(e), "output": None}


class FileSearch:
    """
    file_search: Search for files
    
    Searches filesystem by name, pattern, or content.
    """
    
    def execute(self, search_path: str = ".", pattern: str = "*",
                search_type: str = "name", content_query: Optional[str] = None,
                max_results: int = 100, recursive: bool = True,
                **kwargs) -> dict:
        """
        Search for files.
        
        Args:
            search_path: Directory to search in
            pattern: Glob pattern (e.g., "*.py")
            search_type: One of 'name', 'content'
            content_query: Text to search for in file contents
            max_results: Maximum results to return
            recursive: Search subdirectories
            
        Returns:
            List of matching files
        """
        try:
            path = Path(search_path)
            
            if not path.exists():
                return {"success": False, "error": "Search path not found", "output": None}
            
            results = []
            
            if search_type == "name":
                # Search by filename pattern
                glob_pattern = f"**/{pattern}" if recursive else pattern
                for file in path.glob(glob_pattern):
                    if file.is_file():
                        results.append({
                            "path": str(file),
                            "name": file.name,
                            "size_bytes": file.stat().st_size,
                            "modified": file.stat().st_mtime
                        })
                        if len(results) >= max_results:
                            break
                            
            elif search_type == "content" and content_query:
                # Search by content
                for file in path.rglob(pattern) if recursive else path.glob(pattern):
                    if not file.is_file():
                        continue
                    
                    try:
                        with open(file, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                            if content_query.lower() in content.lower():
                                # Find line numbers
                                lines = content.splitlines()
                                matches = [i+1 for i, line in enumerate(lines) 
                                          if content_query.lower() in line.lower()]
                                
                                results.append({
                                    "path": str(file),
                                    "name": file.name,
                                    "match_lines": matches[:10],
                                    "match_count": len(matches)
                                })
                                if len(results) >= max_results:
                                    break
                    except:
                        continue
            
            return {
                "success": True,
                "output": {
                    "results": results,
                    "total_found": len(results),
                    "search_path": str(path),
                    "pattern": pattern,
                    "search_type": search_type
                }
            }
            
        except Exception as e:
            return {"success": False, "error": str(e), "output": None}


class DataParser:
    """
    data_parser: CSV/JSON/Excel handling
    
    Parses structured data files.
    """
    
    def execute(self, file_path: str, parse_type: Optional[str] = None,
                sheet_name: Optional[str] = None,
                **kwargs) -> dict:
        """
        Parse structured data file.
        
        Args:
            file_path: Path to data file
            parse_type: Force parse type ('csv', 'json', 'excel')
            sheet_name: Excel sheet name (default: first sheet)
            
        Returns:
            Parsed data
        """
        try:
            path = Path(file_path)
            
            if not path.exists():
                return {"success": False, "error": "File not found", "output": None}
            
            ext = path.suffix.lower()
            ptype = parse_type or {
                '.csv': 'csv',
                '.json': 'json',
                '.xlsx': 'excel',
                '.xls': 'excel'
            }.get(ext)
            
            if not ptype:
                return {
                    "success": False, 
                    "error": f"Unsupported file type: {ext}",
                    "output": None
                }
            
            if ptype == 'json':
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                rows = len(json.dumps(data))
                
            elif ptype == 'csv':
                with open(path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    data = list(reader)
                rows = len(data)
                
            elif ptype == 'excel':
                try:
                    import pandas as pd
                    df = pd.read_excel(path, sheet_name=sheet_name or 0)
                    data = df.to_dict('records')
                    rows = len(df)
                except ImportError:
                    return {
                        "success": False,
                        "error": "pandas/openpyxl required for Excel files",
                        "output": None
                    }
            else:
                return {"success": False, "error": "Unknown parse type", "output": None}
            
            return {
                "success": True,
                "output": {
                    "data": data,
                    "row_count": rows,
                    "file_type": ptype,
                    "columns": list(data[0].keys()) if data else []
                }
            }
            
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"Invalid JSON: {e}", "output": None}
        except Exception as e:
            return {"success": False, "error": str(e), "output": None}


# Factory functions
def get_file_reader() -> FileReader:
    return FileReader()


def get_file_writer(create_backup: bool = True) -> FileWriter:
    return FileWriter(create_backup=create_backup)


def get_file_search() -> FileSearch:
    return FileSearch()


def get_data_parser() -> DataParser:
    return DataParser()
