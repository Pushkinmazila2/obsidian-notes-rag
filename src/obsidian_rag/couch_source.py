"""CouchDB LiveSync source — reads Obsidian notes from a Self-hosted LiveSync database.

Architecture
------------
Self-hosted LiveSync stores each Obsidian note as TWO kinds of CouchDB documents:

  * **Metadata doc** — ``_id`` = the note path (e.g. ``Работа/note.md``).
    Fields: ``type`` ("plain" | "newnote"), ``path``, ``children`` (list of chunk IDs),
    ``ctime``, ``mtime``, ``size``.

  * **Leaf doc** — ``_id`` = ``h:<hash>``.
    Fields: ``type`` = "leaf", ``data`` = raw text of that chunk.

To reconstruct a note we fetch the metadata doc, then fetch every leaf in
``children`` and concatenate ``data`` fields in order.

Live updates
-----------
CouchDB exposes a ``_changes`` feed.  We consume it as an SSE stream
(``feed=eventsource``) to get real-time push notifications without polling.
Each change event carries the doc ``_id``; we look up whether it is a metadata
doc (contains '/' or ends with '.md') and trigger re-indexing of that note.

Docker / isolation
-----------------
The module is pure-HTTP (httpx) and works whether the CouchDB instance is on
localhost, inside a Docker container, or behind a reverse proxy.  Pass
``couchdb_url="http://admin:password@localhost:5984"`` (credentials in URL) or
use ``username`` / ``password`` kwargs — both are supported.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Callable, Iterator, List, Optional
from urllib.parse import quote, urlparse, urlunparse

import httpx

from .indexer import Chunk, Embedder, IndexerConfig, chunk_markdown
from .store import VectorStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def _build_base_url(couchdb_url: str, username: Optional[str], password: Optional[str]) -> str:
    """Normalise CouchDB URL, injecting credentials if provided separately."""
    parsed = urlparse(couchdb_url)
    if username and password and not parsed.username:
        netloc = f"{quote(username, safe='')}:{quote(password, safe='')}@{parsed.hostname}"
        if parsed.port:
            netloc += f":{parsed.port}"
        parsed = parsed._replace(netloc=netloc)
    return urlunparse(parsed).rstrip("/")


def _doc_url(base: str, db: str, doc_id: str) -> str:
    return f"{base}/{db}/{quote(doc_id, safe='')}"


def _changes_url(base: str, db: str) -> str:
    return f"{base}/{db}/_changes"


# ---------------------------------------------------------------------------
# Low-level CouchDB client
# ---------------------------------------------------------------------------

class CouchDBClient:
    """Thin httpx wrapper around the CouchDB HTTP API."""

    def __init__(
        self,
        couchdb_url: str = "http://localhost:5984",
        db: str = "obsidian",
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.base = _build_base_url(couchdb_url, username, password)
        self.db = db
        self._client = httpx.Client(timeout=timeout, follow_redirects=True)

    # -- document access -------------------------------------------------------

    def get_doc(self, doc_id: str) -> Optional[dict]:
        """Fetch a single document by ID.  Returns None on 404."""
        url = _doc_url(self.base, self.db, doc_id)
        resp = self._client.get(url)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def get_docs_bulk(self, doc_ids: List[str]) -> List[dict]:
        """Fetch multiple documents in one ``_bulk_get`` request."""
        url = f"{self.base}/{self.db}/_bulk_get"
        payload = {"docs": [{"id": did} for did in doc_ids]}
        resp = self._client.post(url, json=payload)
        resp.raise_for_status()
        results = []
        for item in resp.json().get("results", []):
            for doc_envelope in item.get("docs", []):
                ok = doc_envelope.get("ok")
                if ok:
                    results.append(ok)
        return results

    # -- vault iteration -------------------------------------------------------

    def iter_note_metadata(self) -> Iterator[dict]:
        """Yield all metadata docs (type 'plain' or 'newnote') via _all_docs."""
        url = f"{self.base}/{self.db}/_all_docs"
        params = {"include_docs": "true"}
        resp = self._client.get(url, params=params)
        resp.raise_for_status()
        for row in resp.json().get("rows", []):
            doc = row.get("doc", {})
            if doc.get("type") in ("plain", "newnote") and doc.get("children"):
                yield doc

    # -- note reconstruction ---------------------------------------------------

        def reconstruct_note(self, meta: dict) -> str:
        """Fetch all leaf chunks for a metadata doc and concatenate their data."""
        children: List[str] = meta.get("children", [])
        if not children:
            logger.debug("No children found for note: %s", meta.get("_id"))
            return ""

        logger.debug("Reconstructing note with %d chunks: %s", len(children), meta.get("_id"))
        
        leaf_docs = self.get_docs_bulk(children)
        by_id = {d["_id"]: d.get("data", "") for d in leaf_docs if "_id" in d and "data" in d}
        
        # Check for missing chunks
        missing = [cid for cid in children if cid not in by_id]
        if missing:
            logger.warning("Missing %d chunks for note %s: %s", 
                         len(missing), meta.get("_id"), missing[:5])

        # Preserve original order from children list
        parts = [by_id.get(cid, "") for cid in children]
        full_text = "".join(parts)
        
        logger.debug("Reconstructed note length: %d chars", len(full_text))
        return full_text

    # -- changes feed ----------------------------------------------------------

    def iter_changes_sse(
        self,
        since: str = "now",
        heartbeat: int = 30000,
    ) -> Iterator[dict]:
        """Yield change event dicts from the CouchDB ``_changes`` SSE feed.

        Each yielded dict has at least ``id`` and ``seq`` keys.
        Blocks indefinitely — run in a dedicated thread.
        """
        url = _changes_url(self.base, self.db)
        params = {
            "feed": "eventsource",
            "since": since,
            "heartbeat": str(heartbeat),
            "include_docs": "false",
        }
        # Use a streaming client with a long timeout
        with httpx.Client(timeout=httpx.Timeout(None, connect=10.0), follow_redirects=True) as stream_client:
            with stream_client.stream("GET", url, params=params) as resp:
                resp.raise_for_status()
                buf = ""
                for raw_line in resp.iter_lines():
                    line = raw_line.strip()
                    if not line:
                        # blank line = end of SSE event block
                        if buf:
                            try:
                                yield json.loads(buf)
                            except json.JSONDecodeError:
                                pass
                            buf = ""
                        continue
                    if line.startswith("data:"):
                        data_part = line[5:].strip()
                        if data_part:
                            buf = data_part  # CouchDB emits one data: per event
                    # ignore other SSE fields (event:, id:, retry:)

    def close(self):
        self._client.close()


# ---------------------------------------------------------------------------
# High-level indexer: CouchDB → VectorStore
# ---------------------------------------------------------------------------

class CouchDBIndexer:
    """Reads notes from a CouchDB LiveSync database and populates a VectorStore."""

    def __init__(
        self,
        client: CouchDBClient,
        embedder: Embedder,
        store: VectorStore,
        config: Optional[IndexerConfig] = None,
    ):
        self.client = client
        self.embedder = embedder
        self.store = store
        self.config = config or IndexerConfig()

        def _chunks_for_note(self, meta: dict) -> List[Chunk]:
        """Reconstruct a note and split it into chunks."""
        # Use the ``path`` field (canonical case) as file_path; fall back to _id
        file_path: str = meta.get("path") or meta["_id"]
        
        logger.debug("Processing note: %s (type: %s)", file_path, meta.get("type"))

        # Reconstruct full note content from chunks
        content = self.client.reconstruct_note(meta)
        if not content.strip():
            logger.warning("Empty content for note: %s", file_path)
            return []
        
        logger.debug("Content length: %d chars", len(content))

        # Split into chunks for indexing
        chunks = chunk_markdown(content, file_path, config=self.config)
        logger.debug("Created %d chunks for note: %s", len(chunks), file_path)
        
        return chunks

    def index_note(self, meta: dict) -> int:
        """Index a single note.  Returns number of chunks stored."""
        chunks = self._chunks_for_note(meta)
        if not chunks:
            return 0

        embeddings = [self.embedder.embed(c.content) for c in chunks]
        self.store.upsert_batch(chunks, embeddings)
        return len(chunks)

    def index_all(
        self,
        path_filter: Optional[str] = None,
        clear: bool = False,
        progress_cb: Optional[Callable[[str, int, int], None]] = None,
    ) -> dict:
        """Full re-index of the CouchDB vault.

        Args:
            path_filter: Optional prefix filter (e.g. "Работа/")
            clear:       Wipe the store before indexing
            progress_cb: Optional callback(file_path, files_done, total_files)

        Returns:
            Stats dict
        """
        if clear:
            self.store.clear()

        all_meta = list(self.client.iter_note_metadata())

        if path_filter:
            all_meta = [
                m for m in all_meta
                if (m.get("path") or m["_id"]).startswith(path_filter)
            ]

        total = len(all_meta)
        file_count = 0
        chunk_count = 0
        errors = []

        for i, meta in enumerate(all_meta):
            fp = meta.get("path") or meta["_id"]
            try:
                n = self.index_note(meta)
                chunk_count += n
                file_count += 1
                if progress_cb:
                    progress_cb(fp, i + 1, total)
            except Exception as exc:
                logger.error("Error indexing %s: %s", fp, exc)
                errors.append({"file": fp, "error": str(exc)})

        return {
            "source": "couchdb",
            "files_indexed": file_count,
            "chunks_created": chunk_count,
            "total_in_store": self.store.get_stats()["count"],
            "errors": errors or None,
            "path_filter": path_filter,
            "cleared": clear,
        }

    def index_by_id(self, doc_id: str) -> dict:
        """Re-index a single note by its CouchDB _id (the note path).

        Deletes stale chunks for that file first, then re-indexes.
        """
        meta = self.client.get_doc(doc_id)
        if not meta:
            return {"error": f"Document not found: {doc_id}"}
        if meta.get("type") not in ("plain", "newnote"):
            return {"skipped": f"Not a note metadata doc: {doc_id}"}

        file_path: str = meta.get("path") or meta["_id"]

        # Remove old chunks for this file before re-indexing
        self.store.delete_by_file(file_path)

        n = self.index_note(meta)
        return {"file_path": file_path, "chunks": n}


# ---------------------------------------------------------------------------
# Live watcher: SSE → incremental re-index
# ---------------------------------------------------------------------------

class CouchDBWatcher:
    """Watches CouchDB _changes SSE feed and re-indexes modified notes.

    Designed to run in a Docker container or as a background thread.
    The watcher is resilient: it reconnects on network errors with
    exponential back-off.
    """

    # Docs that LiveSync creates internally — skip them
    _INTERNAL_PREFIXES = ("_design/", "h:", "_local/")

    def __init__(
        self,
        client: CouchDBClient,
        indexer: CouchDBIndexer,
        since: str = "now",
        reconnect_delay: float = 5.0,
        max_reconnect_delay: float = 120.0,
    ):
        self.client = client
        self.indexer = indexer
        self.since = since
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_delay = max_reconnect_delay
        self._stop_event = threading.Event()
        self._last_seq: str = since

    def _is_note_change(self, doc_id: str) -> bool:
        """Return True if this change event corresponds to a note metadata doc."""
        if any(doc_id.startswith(p) for p in self._INTERNAL_PREFIXES):
            return False
        # Note paths always end with .md
        return doc_id.endswith(".md")

    def _handle_change(self, event: dict):
        doc_id: str = event.get("id", "")
        self._last_seq = event.get("seq", self._last_seq)

        if not self._is_note_change(doc_id):
            return

        # Check if the doc was deleted
        if event.get("deleted"):
            logger.info("Note deleted, removing from index: %s", doc_id)
            # Try both _id and path variants
            self.indexer.store.delete_by_file(doc_id)
            return

        logger.info("Note changed, re-indexing: %s", doc_id)
        try:
            result = self.indexer.index_by_id(doc_id)
            logger.info("Re-indexed %s → %s", doc_id, result)
        except Exception as exc:
            logger.error("Failed to re-index %s: %s", doc_id, exc)

    def run_forever(self):
        """Block and process SSE events.  Call stop() to terminate."""
        delay = self.reconnect_delay
        while not self._stop_event.is_set():
            try:
                logger.info(
                    "Connecting to CouchDB _changes SSE feed (since=%s)…",
                    self._last_seq,
                )
                for event in self.client.iter_changes_sse(since=self._last_seq):
                    if self._stop_event.is_set():
                        break
                    self._handle_change(event)
                    delay = self.reconnect_delay  # reset on success
            except Exception as exc:
                if self._stop_event.is_set():
                    break
                logger.warning(
                    "SSE feed disconnected (%s). Reconnecting in %.0fs…",
                    exc, delay,
                )
                self._stop_event.wait(delay)
                delay = min(delay * 2, self.max_reconnect_delay)

        logger.info("CouchDBWatcher stopped.")

    def stop(self):
        """Signal the watcher to stop."""
        self._stop_event.set()

    def start_background(self) -> threading.Thread:
        """Start the watcher in a daemon thread and return it."""
        t = threading.Thread(target=self.run_forever, daemon=True, name="couch-watcher")
        t.start()
        return t


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def create_couch_client(config) -> CouchDBClient:
    """Build a CouchDBClient from a Config instance."""
    return CouchDBClient(
        couchdb_url=config.couchdb_url,
        db=config.couchdb_db,
        username=config.couchdb_username or None,
        password=config.couchdb_password or None,
    )


def create_couch_indexer(client: CouchDBClient, embedder: Embedder, store: VectorStore, config) -> CouchDBIndexer:
    """Build a CouchDBIndexer from component instances."""
    return CouchDBIndexer(
        client=client,
        embedder=embedder,
        store=store,
        config=config.indexer,
    )