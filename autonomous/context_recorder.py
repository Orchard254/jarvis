"""
Context Recorder — Semantic visual memory daemon.
Takes snapshots of the current UI tree every N seconds and stores the text in ChromaDB.
Provides Jarvis with "Recall" capabilities to search past desktop states.
"""

import logging
import threading
import time
import asyncio
import uuid
import chromadb
from pathlib import Path
from tools.custom.read_ui_tree import read_ui_tree

logger = logging.getLogger(__name__)

_stop_event = threading.Event()
_thread: "threading.Thread | None" = None
_main_event_loop: asyncio.AbstractEventLoop | None = None

# Configuration
RECORD_INTERVAL_SEC = 10
MAX_RETENTION_DAYS = 7  # Auto-prune to save disk space
CHROMA_DB_PATH = Path("data") / "recall_db"

_client = None
_collection = None

def init_db():
    global _client, _collection
    try:
        CHROMA_DB_PATH.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(CHROMA_DB_PATH))
        _collection = _client.get_or_create_collection(
            name="screen_snapshots",
            metadata={"hnsw:space": "cosine"}
        )
        logger.info("context_recorder: ChromaDB initialized successfully.")
    except Exception as e:
        logger.error(f"context_recorder: Failed to init ChromaDB - {e}")

def search_memory(query: str, n_results: int = 5) -> list[dict]:
    if not _collection:
        return []
    try:
        results = _collection.query(
            query_texts=[query],
            n_results=n_results
        )
        
        matches = []
        if results and results.get("documents") and len(results["documents"]) > 0:
            docs = results["documents"][0]
            metas = results["metadatas"][0]
            for doc, meta in zip(docs, metas):
                matches.append({
                    "text": doc,
                    "window_title": meta.get("window_title", ""),
                    "timestamp": meta.get("timestamp", 0)
                })
        return matches
    except Exception as e:
        logger.error(f"context_recorder search failed: {e}")
        return []

def _prune_old_records():
    if not _collection:
        return
    try:
        cutoff = time.time() - (MAX_RETENTION_DAYS * 86400)
        _collection.delete(where={"timestamp": {"$lt": cutoff}})
    except Exception as e:
        logger.warning(f"context_recorder: prune failed: {e}")

def _monitor_loop(main_loop: asyncio.AbstractEventLoop):
    logger.info("context_recorder: loop started")
    init_db()
    
    last_window = ""
    last_text_signature = ""

    while not _stop_event.is_set():
        try:
            # 1. Read the UI Tree
            ui_res = read_ui_tree()
            if ui_res.get("success") and _collection:
                title = ui_res.get("window_title", "")
                elements = ui_res.get("elements", [])
                
                # Combine all text from elements
                texts = [e["text"] for e in elements if e["text"].strip()]
                combined_text = " ".join(texts)
                
                # Simple deduplication: only index if the window or the text changed significantly
                text_signature = hash(combined_text)
                if combined_text and (title != last_window or text_signature != last_text_signature):
                    doc_id = str(uuid.uuid4())
                    timestamp = time.time()
                    
                    _collection.add(
                        documents=[combined_text],
                        metadatas=[{"window_title": title, "timestamp": timestamp}],
                        ids=[doc_id]
                    )
                    
                    last_window = title
                    last_text_signature = text_signature
                    
            # 2. Prune daily
            if int(time.time()) % 86400 < RECORD_INTERVAL_SEC:
                _prune_old_records()

        except Exception as e:
            logger.debug(f"context_recorder tick failed: {e}")

        _stop_event.wait(RECORD_INTERVAL_SEC)
        
    logger.info("context_recorder: loop stopped")

def start(main_loop: asyncio.AbstractEventLoop) -> dict:
    global _thread, _main_event_loop
    _main_event_loop = main_loop
    if _thread and _thread.is_alive():
        return {"success": True, "reason": "already_running"}
    _stop_event.clear()
    _thread = threading.Thread(target=_monitor_loop, daemon=True, name="context-recorder", args=(_main_event_loop,))
    _thread.start()
    return {"success": True}

def stop() -> dict:
    global _thread
    _stop_event.set()
    if _thread and _thread.is_alive():
        _thread.join(timeout=5)
    return {"success": True}
