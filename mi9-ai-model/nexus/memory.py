"""Grounded memory: curated corpus on disk + hybrid retrieval.

Whitepaper Ch. 3.9 / 5.4: knowledge lives on disk, not in weights. The
semantic store is any directory of text/markdown/code files; indexing is
lexical BM25 (pure stdlib) + a vector channel added when the embedding model
is available. Everything answers with citations - answers grounded in
documents the user controls (Ch. 4.2).
"""
import argparse
import json
import math
import re
import sqlite3
from pathlib import Path

from . import config

CHUNK_CHARS = 1200
CHUNK_OVERLAP = 150

SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    path TEXT, chunk_id INTEGER, text TEXT,
    n_tokens INTEGER
);
CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(text, content='');
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


def iter_corpus_files(root: Path):
    exts = {".txt", ".md", ".markdown", ".rst", ".py", ".json", ".yaml", ".yml",
            ".toml", ".csv", ".html", ".sh", ".c", ".h", ".cpp", ".hpp", ".js", ".ts",
            ".docx", ".pptx", ".xlsx"}
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() in exts and p.stat().st_size < 4_000_000:
            yield p


def chunk_text(text):
    paras = re.split(r"\n\s*\n", text)
    chunks, cur = [], ""
    for para in paras:
        # hard-split paragraphs longer than a chunk
        pieces = []
        while len(para) > CHUNK_CHARS:
            pieces.append(para[:CHUNK_CHARS])
            para = para[CHUNK_CHARS - CHUNK_OVERLAP:]
        pieces.append(para)
        for piece in pieces:
            if len(cur) + len(piece) + 2 <= CHUNK_CHARS:
                cur = (cur + "\n\n" + piece).strip()
            else:
                if cur:
                    chunks.append(cur)
                cur = piece
    if cur:
        chunks.append(cur)
    return [c for c in chunks if len(c.strip()) > 40]


def index(root: Path = None):
    root = root or config.CORPUS
    if config.INDEX.exists():
        config.INDEX.unlink()
    con = sqlite3.connect(config.INDEX)
    con.executescript(SCHEMA)
    n_files = n_chunks = 0
    for path in iter_corpus_files(root):
        try:
            if path.suffix.lower() in (".docx", ".pptx", ".xlsx"):
                from . import office
                text = office.extract(path)
            else:
                text = path.read_text(errors="replace")
        except Exception:
            continue
        if not text.strip():
            continue
        n_files += 1
        for cid, ch in enumerate(chunk_text(text)):
            rel = str(path.relative_to(root))
            cur = con.execute("INSERT INTO chunks(path, chunk_id, text, n_tokens) VALUES (?,?,?,?)",
                              (rel, cid, ch, len(ch) // 4))
            con.execute("INSERT INTO fts(rowid, text) VALUES (?, ?)",
                        (cur.lastrowid, ch))
            n_chunks += 1
    con.execute("INSERT OR REPLACE INTO meta VALUES ('files', ?)", (str(n_files),))
    con.execute("INSERT OR REPLACE INTO meta VALUES ('chunks', ?)", (str(n_chunks),))
    con.commit()
    con.close()
    print(f"indexed {n_files} files -> {n_chunks} chunks in {config.INDEX.name}")


_TOKEN = re.compile(r"[a-z0-9]+")


def bm25(query, k=6, con=None):
    """BM25 over the FTS5 index with stdlib-only scoring fallback."""
    terms = [t.lower() for t in _TOKEN.findall(query)]
    if not terms:
        return []  # punctuation-only query: nothing to match
    own = con or sqlite3.connect(config.INDEX)
    try:
        # quote each term so FTS5 keywords (AND/OR/NOT) and apostrophes
        # inside a term can't break the MATCH syntax
        match = " OR ".join(f'"{t}"' for t in terms)
        ids = [r[0] for r in own.execute(
            "SELECT rowid FROM fts WHERE fts MATCH ?", (match,))]
        if not ids:
            return []
        n = own.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        avgdl = max(1, own.execute("SELECT AVG(n_tokens) FROM chunks").fetchone()[0])
        rows = {r[0]: (r[1], r[2], r[3]) for r in own.execute(
            "SELECT id, path, text, n_tokens FROM chunks")}
        tf = {}
        for cid in ids:
            toks = _TOKEN.findall(rows[cid][1].lower())
            for t in set(toks):
                if t in terms:
                    tf[(cid, t)] = toks.count(t)
        k1, b = 1.2, 0.75
        scores = {}
        for cid in ids:
            toks = _TOKEN.findall(rows[cid][1].lower())
            dl = rows[cid][2]
            s = 0.0
            for t in set(terms):
                f = toks.count(t)
                if not f:
                    continue
                df = sum(1 for c2 in rows if t in rows[c2][1].lower())
                idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
                s += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * dl / avgdl))
            scores[cid] = s
        top = sorted(scores.items(), key=lambda kv: -kv[1])[:k]
        return [{"path": rows[cid][0], "text": rows[cid][1], "score": round(s, 3)}
                for cid, s in top]
    finally:
        if own is con:
            pass
        else:
            own.close()


def query(q, k=6):
    if not config.INDEX.exists():
        return []
    return bm25(q, k=k)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["index", "query"])
    ap.add_argument("text", nargs="*", default="")
    ap.add_argument("--root", default=None)
    ap.add_argument("-k", type=int, default=6)
    args = ap.parse_args()
    if args.cmd == "index":
        index(Path(args.root) if args.root else None)
    else:
        for hit in query(" ".join(args.text), k=args.k):
            print(f"--- {hit['path']} (score {hit['score']})\n{hit['text'][:400]}\n")


if __name__ == "__main__":
    main()
