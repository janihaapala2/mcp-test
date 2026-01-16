import logging
import os
import sys
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

#from mcp.server.fastmcp import FastMCP
from fastmcp import FastMCP

# IMPORTANT for STDIO MCP: never write to stdout. Log to stderr only.
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
log = logging.getLogger("demo-mcp-movie-library")

TRANSPORT = os.getenv("MCP_TRANSPORT", "stdio").strip().lower()
if TRANSPORT == "http":
    TRANSPORT = "streamable-http"

#OMA TESTI
#TRANSPORT = "streamable-http"


mcp = FastMCP(
    "DemoMovieLibrary",
    stateless_http=(TRANSPORT == "streamable-http"),
    json_response=True,
)

_lock = threading.Lock()
_movies: Dict[str, Dict[str, Any]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_genres(genres: Optional[List[str]]) -> List[str]:
    if not genres:
        return []
    # normalize: trim + lower-case uniqueness while preserving readable casing
    seen = set()
    out = []
    for g in genres:
        g2 = (g or "").strip()
        if not g2:
            continue
        key = g2.lower()
        if key not in seen:
            seen.add(key)
            out.append(g2)
    return out


def _require_movie(movie_id: str) -> Dict[str, Any]:
    m = _movies.get(movie_id)
    if not m:
        raise ValueError(f"Movie not found: {movie_id}")
    return m


def _movie_public(m: Dict[str, Any]) -> Dict[str, Any]:
    # Return a copy safe for JSON serialization
    return dict(m)


@mcp.tool()
def add_movie(
    title: str,
    year: int,
    genres: Optional[List[str]] = None,
    director: Optional[str] = None,
) -> Dict[str, Any]:
    """Add a movie to the library and return the created record."""
    title = (title or "").strip()
    if not title:
        raise ValueError("title is required.")
    if year < 1878 or year > 3000:
        raise ValueError("year looks invalid.")

    movie_id = str(uuid.uuid4())
    record = {
        "id": movie_id,
        "title": title,
        "year": int(year),
        "genres": _normalize_genres(genres),
        "director": (director or "").strip() or None,
        "borrowed": False,
        "borrowed_by": None,
        "borrowed_at": None,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }

    with _lock:
        _movies[movie_id] = record

    return _movie_public(record)


@mcp.tool()
def get_movie(movie_id: str) -> Dict[str, Any]:
    """Get a movie by id."""
    with _lock:
        m = _require_movie(movie_id)
        return _movie_public(m)


@mcp.tool()
def list_movies(only_available: bool = False) -> List[Dict[str, Any]]:
    """List movies. Set only_available=True to exclude borrowed ones."""
    with _lock:
        items = list(_movies.values())
        if only_available:
            items = [m for m in items if not m["borrowed"]]
        # stable ordering
        items.sort(key=lambda x: (x["title"].lower(), x["year"], x["id"]))
        return [_movie_public(m) for m in items]


@mcp.tool()
def search_movies(
    query: Optional[str] = None,
    year: Optional[int] = None,
    genre: Optional[str] = None,
    director: Optional[str] = None,
    only_available: bool = False,
) -> List[Dict[str, Any]]:
    """
    Search movies by:
      - query: substring match in title (case-insensitive)
      - year: exact match
      - genre: exact match against genres (case-insensitive)
      - director: substring match (case-insensitive)
      - only_available: exclude borrowed movies
    """
    q = (query or "").strip().lower()
    g = (genre or "").strip().lower()
    d = (director or "").strip().lower()

    with _lock:
        results = list(_movies.values())

    if only_available:
        results = [m for m in results if not m["borrowed"]]
    if q:
        results = [m for m in results if q in m["title"].lower()]
    if year is not None:
        results = [m for m in results if m["year"] == int(year)]
    if g:
        results = [m for m in results if any(g == gg.lower() for gg in m.get("genres", []))]
    if d:
        results = [m for m in results if (m.get("director") or "").lower().find(d) != -1]

    results.sort(key=lambda x: (x["title"].lower(), x["year"], x["id"]))
    return [_movie_public(m) for m in results]


@mcp.tool()
def update_movie(
    movie_id: str,
    title: Optional[str] = None,
    year: Optional[int] = None,
    genres: Optional[List[str]] = None,
    director: Optional[str] = None,
) -> Dict[str, Any]:
    """Update fields on a movie and return the updated record."""
    with _lock:
        m = _require_movie(movie_id)

        if title is not None:
            t = title.strip()
            if not t:
                raise ValueError("title cannot be empty.")
            m["title"] = t

        if year is not None:
            y = int(year)
            if y < 1878 or y > 3000:
                raise ValueError("year looks invalid.")
            m["year"] = y

        if genres is not None:
            m["genres"] = _normalize_genres(genres)

        if director is not None:
            d = director.strip()
            m["director"] = d or None

        m["updated_at"] = _now_iso()
        return _movie_public(m)


@mcp.tool()
def delete_movie(movie_id: str) -> Dict[str, Any]:
    """Delete a movie. Returns {deleted: True, id: ...}."""
    with _lock:
        _require_movie(movie_id)
        del _movies[movie_id]
    return {"deleted": True, "id": movie_id}


@mcp.tool()
def borrow_movie(movie_id: str, borrower: str) -> Dict[str, Any]:
    """Mark a movie as borrowed by someone."""
    borrower = (borrower or "").strip()
    if not borrower:
        raise ValueError("borrower is required.")

    with _lock:
        m = _require_movie(movie_id)
        if m["borrowed"]:
            raise ValueError(f"Movie is already borrowed by {m['borrowed_by']}.")
        m["borrowed"] = True
        m["borrowed_by"] = borrower
        m["borrowed_at"] = _now_iso()
        m["updated_at"] = _now_iso()
        return _movie_public(m)


@mcp.tool()
def return_movie(movie_id: str) -> Dict[str, Any]:
    """Return a borrowed movie (make it available)."""
    with _lock:
        m = _require_movie(movie_id)
        if not m["borrowed"]:
            raise ValueError("Movie is not borrowed.")
        m["borrowed"] = False
        m["borrowed_by"] = None
        m["borrowed_at"] = None
        m["updated_at"] = _now_iso()
        return _movie_public(m)


def main() -> None:
    log.info("Starting MCP server with transport=%s", TRANSPORT)
    host = os.getenv("MCP_HOST", "0.0.0.0")          # IMPORTANT in Docker
    port = int(os.getenv("MCP_PORT", "8000"))
    if TRANSPORT == "stdio":
        mcp.run()
    else:
        mcp.run(transport=TRANSPORT, host=host, port=port)


if __name__ == "__main__":
    main()
