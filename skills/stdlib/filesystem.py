"""skills.stdlib.filesystem — file read/write.

These are kept because the exec facade uses them. For advanced file
operations (copy, move, delete, mkdir), the LLM should write the code
via exec(run).
"""
from tools.read_file import read_file
from tools.write_file import write_file

__all__ = ["read_file", "write_file"]
