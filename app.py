import streamlit as st

import os
import re
import uuid
import glob
import inspect
import sqlite3
import io
import fitz  # PyMuPDF

try:
    import pytesseract
    from PIL import Image
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False

TEXT_EXTS = {".txt", ".md", ".csv"}
MIN_CHARS_PER_PAGE = 40      # below this, the page is treated as scanned
MAX_CHARS_PER_FILE = 12000   # keeps a 7B context from overflowing
OCR_DPI = 200


def _ocr_tesseract(pix) -> str:
    return pytesseract.image_to_string(Image.open(io.BytesIO(pix.tobytes("png"))))


def _ocr_with_vlm(pix) -> str:
    """Fallback OCR through the local vision model — still zero external calls."""
    import base64, ollama
    b64 = base64.b64encode(pix.tobytes("png")).decode()
    r = ollama.chat(model="qwen2.5vl:7b", messages=[{
        "role": "user",
        "content": "Transcribe all text on this page verbatim. Output only the text.",
        "images": [b64],
    }])
    return r["message"]["content"]


def extract_pdf_text(path: str) -> str:
    doc = fitz.open(path)
    pages = []
    for page in doc:
        text = page.get_text().strip()
        if len(text) < MIN_CHARS_PER_PAGE:          # scanned / image-only page
            pix = page.get_pixmap(dpi=OCR_DPI)
            try:
                text = (_ocr_tesseract(pix) if HAS_TESSERACT else _ocr_with_vlm(pix)).strip()
            except Exception as e:
                text = f"[OCR failed on this page: {e}]"
        pages.append(f"--- page {page.number + 1} ---\n{text}")
    doc.close()
    return "\n\n".join(pages)[:MAX_CHARS_PER_FILE]


def extract_file_text(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".pdf":
            return extract_pdf_text(path)
        if ext in TEXT_EXTS:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()[:MAX_CHARS_PER_FILE]
    except Exception as e:
        return f"[Could not read this file: {e}]"
    return ""

from agent.agent import process_user_request
from memory.memory import init_db, save_message, load_messages, clear_session
from network.network_monitor import get_network_snapshot
from ledger.ledger import verify_chain

import memory.memory as _mem  # only for optional/defensive feature detection

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
UPLOAD_DIR = "uploads"
ATTACH_PREFIX = "\U0001F4CE "  # "📎 " marker used to embed attachment paths in a message
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
ALLOWED_TYPES = ["png", "jpg", "jpeg", "pdf", "txt", "md", "csv"]

# Streamlit >= 1.43 lets st.chat_input accept files directly in the bar.
SUPPORTS_INLINE_FILES = "accept_file" in inspect.signature(st.chat_input).parameters


# ---------------------------------------------------------------------------
# Helpers (pure app-layer -- no other module is modified)
# ---------------------------------------------------------------------------
def format_latex(text: str) -> str:
    """Converts \\[ ... \\] and \\( ... \\) LaTeX delimiters to Streamlit-compatible $$ $$ and $ $."""
    text = re.sub(r'\\\[(.*?)\\\]', r'$$\1$$', text, flags=re.DOTALL)
    text = re.sub(r'\\\((.*?)\\\)', r'$\1$', text, flags=re.DOTALL)
    return text


def save_upload(uploaded_file) -> str:
    """Persist an uploaded file under uploads/ with a collision-proof name."""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    safe_name = os.path.basename(uploaded_file.name)
    path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4().hex[:8]}_{safe_name}")
    with open(path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return path


def split_attachments(content: str):
    """Separate the visible text from embedded '📎 <path>' attachment lines."""
    body, paths = [], []
    for line in (content or "").splitlines():
        stripped = line.strip()
        if stripped.startswith(ATTACH_PREFIX):
            paths.append(stripped[len(ATTACH_PREFIX):].strip())
        else:
            body.append(line)
    return "\n".join(body).strip(), paths


def render_message(content: str):
    """Render one chat message, previewing any attachments it carries."""
    body, paths = split_attachments(content)
    if body:
        st.markdown(format_latex(body))
    for path in paths:
        ext = os.path.splitext(path)[1].lower()
        if ext in IMAGE_EXTS and os.path.exists(path):
            st.image(path, width=280, caption=os.path.basename(path))
        else:
            st.caption(f"{ATTACH_PREFIX}{os.path.basename(path)}")


def plain_text(content: str) -> str:
    return split_attachments(content)[0]


# ---------------------------------------------------------------------------
# Session discovery: try memory.memory first, fall back to read-only SQLite.
# Nothing in memory/memory.py has to change either way.
# ---------------------------------------------------------------------------
def _normalize_sessions(raw):
    out = []
    for item in raw or []:
        if isinstance(item, dict):
            sid = item.get("session_id") or item.get("id")
            if not sid:
                continue
            out.append({
                "session_id": str(sid),
                "title": item.get("title") or item.get("preview") or "",
                "count": item.get("count") or item.get("messages") or 0,
                "updated": item.get("updated") or item.get("timestamp") or "",
            })
        elif isinstance(item, (list, tuple)) and item:
            out.append({"session_id": str(item[0]), "title": "", "count": 0, "updated": ""})
        elif isinstance(item, str):
            out.append({"session_id": item, "title": "", "count": 0, "updated": ""})
    return out


def _sessions_from_module():
    for name in ("list_sessions", "get_sessions", "all_sessions",
                 "get_all_sessions", "load_sessions"):
        fn = getattr(_mem, name, None)
        if callable(fn):
            try:
                return _normalize_sessions(fn())
            except Exception:
                continue
    return None


def _discover_db_path():
    for attr in ("DB_PATH", "DB_FILE", "DATABASE", "DB", "DB_NAME",
                 "MEMORY_DB", "SQLITE_PATH", "MEMORY_DB_PATH"):
        value = getattr(_mem, attr, None)
        if isinstance(value, str) and value.strip() and os.path.exists(value):
            return value

    mem_dir = os.path.dirname(getattr(_mem, "__file__", "") or "")
    patterns = []
    for base in (mem_dir, os.getcwd(), os.path.join(os.getcwd(), "memory"), "data"):
        if base:
            patterns += [os.path.join(base, "*.db"), os.path.join(base, "*.sqlite"),
                         os.path.join(base, "*.sqlite3")]
    hits = [p for pattern in patterns for p in glob.glob(pattern)]
    if hits:
        return max(hits, key=os.path.getmtime)
    return None


def _open_db():
    path = _discover_db_path()
    if not path:
        return None
    try:
        return sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except Exception:
        return None


def _find_message_table(conn):
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")]
    for table in tables:
        cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
        lower = [c.lower() for c in cols]
        if "session_id" not in lower:
            continue
        role = next((c for c in cols if c.lower() in ("role", "sender", "author")), None)
        content = next((c for c in cols if c.lower() in ("content", "message", "text", "body")), None)
        if role and content:
            ts = next((c for c in cols if c.lower() in
                       ("timestamp", "created_at", "ts", "time", "created")), None)
            return table, cols[lower.index("session_id")], role, content, ts
    return None


def _sessions_from_sqlite():
    conn = _open_db()
    if conn is None:
        return []
    try:
        found = _find_message_table(conn)
        if not found:
            return []
        table, sid_col, role_col, content_col, ts_col = found
        order_expr = f'MAX("{ts_col}")' if ts_col else "MAX(rowid)"
        rows = conn.execute(
            f'SELECT "{sid_col}", COUNT(*), {order_expr} AS last_seen '
            f'FROM "{table}" GROUP BY "{sid_col}" ORDER BY last_seen DESC'
        ).fetchall()

        sessions = []
        for sid, count, last_seen in rows:
            title_row = conn.execute(
                f'SELECT "{content_col}" FROM "{table}" '
                f'WHERE "{sid_col}" = ? AND lower("{role_col}") = \'user\' '
                f'ORDER BY rowid LIMIT 1', (sid,)
            ).fetchone()
            sessions.append({
                "session_id": str(sid),
                "title": plain_text(title_row[0]) if title_row and title_row[0] else "",
                "count": count,
                "updated": str(last_seen) if ts_col else "",
            })
        return sessions
    except Exception:
        return []
    finally:
        conn.close()


def list_sessions(include_current=True):
    """All known chat sessions, newest first."""
    sessions = _sessions_from_module()
    if sessions is None:
        sessions = _sessions_from_sqlite()

    if include_current:
        known = {s["session_id"] for s in sessions}
        current = st.session_state.get("session_id")
        if current and current not in known:
            sessions.insert(0, {"session_id": current, "title": "", "count": 0, "updated": ""})
    return sessions


def search_sessions(query: str):
    """Keyword search across every stored message; falls back to title matching."""
    needle = (query or "").strip()
    if not needle:
        return []

    escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    like_pattern = "%" + escaped + "%"

    conn = _open_db()
    if conn is not None:
        try:
            found = _find_message_table(conn)
            if found:
                table, sid_col, role_col, content_col, ts_col = found
                order_expr = f'MAX("{ts_col}")' if ts_col else "MAX(rowid)"
                rows = conn.execute(
                    f'SELECT "{sid_col}", COUNT(*), {order_expr} AS last_seen '
                    f'FROM "{table}" WHERE "{content_col}" LIKE ? ESCAPE \'\\\' '
                    f'GROUP BY "{sid_col}" ORDER BY last_seen DESC LIMIT 50',
                    (like_pattern,)
                ).fetchall()

                results = []
                for sid, hits, _ in rows:
                    snippet_row = conn.execute(
                        f'SELECT "{content_col}" FROM "{table}" '
                        f'WHERE "{sid_col}" = ? AND "{content_col}" LIKE ? ESCAPE \'\\\' '
                        f'ORDER BY rowid LIMIT 1', (sid, like_pattern)
                    ).fetchone()
                    title_row = conn.execute(
                        f'SELECT "{content_col}" FROM "{table}" '
                        f'WHERE "{sid_col}" = ? AND lower("{role_col}") = \'user\' '
                        f'ORDER BY rowid LIMIT 1', (sid,)
                    ).fetchone()
                    results.append({
                        "session_id": str(sid),
                        "title": plain_text(title_row[0]) if title_row and title_row[0] else "",
                        "count": hits,
                        "snippet": make_snippet(snippet_row[0] if snippet_row else "", needle),
                    })
                return results
        except Exception:
            pass
        finally:
            conn.close()

    # Fallback: match against session titles only.
    low = needle.lower()
    return [dict(s, snippet="") for s in list_sessions()
            if low in (s.get("title") or "").lower()]


def make_snippet(content: str, needle: str, width: int = 90) -> str:
    body = plain_text(content).replace("\n", " ")
    idx = body.lower().find(needle.lower())
    if idx == -1:
        return body[:width] + ("…" if len(body) > width else "")
    start = max(0, idx - width // 3)
    end = min(len(body), start + width)
    return ("…" if start > 0 else "") + body[start:end] + ("…" if end < len(body) else "")


def session_label(session):
    title = (session.get("title") or "").strip().replace("\n", " ")
    if not title:
        return f"New chat · {session['session_id'][:8]}"
    return title[:38] + ("…" if len(title) > 38 else "")


def transcript_markdown(session_id):
    lines = []
    for message in load_messages(session_id) or []:
        who = "You" if message.get("role") == "user" else "Assistant"
        lines.append(f"**{who}:**\n\n{plain_text(message.get('content', ''))}\n")
    return "\n---\n\n".join(lines) or "_Empty session._"


def switch_to(session_id):
    st.session_state.session_id = session_id
    st.session_state.messages = load_messages(session_id) or []
    st.session_state.pending_files = []


def start_new_chat():
    switch_to(str(uuid.uuid4()))


# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Sovereign AI Workbench", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #0d1117; color: #e6edf3; }
    .main-title { font-size: 2.2rem; font-weight: 700; color: #58a6ff; margin-bottom: 0; }
    .subtitle { color: #8b949e; font-size: 1rem; margin-top: 0; }
    .status-clear { color: #3fb950; font-weight: 600; margin: 0; }
    .status-alert { color: #f85149; font-weight: 600; margin: 0; }
    div[data-testid="stChatMessage"] { background-color: #161b22; border-radius: 10px; padding: 8px; }
    section[data-testid="stSidebar"] { background-color: #10151c; border-right: 1px solid #30363d; }
    section[data-testid="stSidebar"] .stButton button { text-align: left; }
    .sidebar-heading { color: #8b949e; font-size: 0.78rem; letter-spacing: .08em;
                       text-transform: uppercase; margin: 4px 0 2px 0; }
    .hint { color: #8b949e; font-size: 0.9rem; }
    .snippet { color: #8b949e; font-size: 0.78rem; margin: -6px 0 8px 4px; }
</style>
""", unsafe_allow_html=True)

init_db()
os.makedirs(UPLOAD_DIR, exist_ok=True)

if "session_id" not in st.session_state:
    existing = _sessions_from_module()
    if existing is None:
        existing = _sessions_from_sqlite()
    if existing:
        st.session_state.session_id = existing[0]["session_id"]
    else:
        st.session_state.session_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = load_messages(st.session_state.session_id) or []
if "pending_files" not in st.session_state:
    st.session_state.pending_files = []

# ---------------------------------------------------------------------------
# Sidebar — new chat, keyword search, history, audit
# ---------------------------------------------------------------------------
with st.sidebar:
    if st.button("➕ New chat", use_container_width=True):
        start_new_chat()
        st.rerun()

    # -- Find by keyword. Nothing is listed until a keyword is typed. ---------
    st.markdown('<p class="sidebar-heading">🔍 Find by keyword</p>', unsafe_allow_html=True)
    keyword = st.text_input("Find by keyword", placeholder="Type a keyword…",
                            label_visibility="collapsed", key="keyword_search")

    if keyword.strip():
        hits = search_sessions(keyword)
        if not hits:
            st.caption(f"No chats matching “{keyword}”.")
        else:
            st.caption(f"{len(hits)} chat(s) matched")
            for hit in hits:
                if st.button(session_label(hit),
                             key=f"hit_{hit['session_id']}",
                             use_container_width=True):
                    switch_to(hit["session_id"])
                    st.rerun()
                if hit.get("snippet"):
                    st.markdown(f'<p class="snippet">{hit["snippet"]}</p>',
                                unsafe_allow_html=True)

    st.markdown("---")

    # -- History -------------------------------------------------------------
    with st.expander("🕘 History", expanded=False):
        all_sessions = list_sessions()
        if not all_sessions:
            st.caption("No conversations saved yet.")
        for session in all_sessions[:50]:
            sid = session["session_id"]
            is_current = sid == st.session_state.session_id
            if st.button(("▸ " if is_current else "") + session_label(session),
                         key=f"hist_{sid}", use_container_width=True,
                         type="primary" if is_current else "secondary"):
                switch_to(sid)
                st.rerun()
            body = transcript_markdown(sid)
            col_export, col_delete = st.columns(2)
            with col_export:
                st.download_button("⬇️", data=body, file_name=f"chat_{sid[:8]}.md",
                                   mime="text/markdown", key=f"dl_{sid}",
                                   use_container_width=True, help="Export as Markdown")
            with col_delete:
                if st.button("🗑️", key=f"del_{sid}", use_container_width=True,
                             help="Delete this chat"):
                    clear_session(sid)
                    if is_current:
                        st.session_state.messages = []
                    st.rerun()

    # -- Audit ---------------------------------------------------------------
    with st.expander("🔒 Audit panel", expanded=False):
        snapshot = get_network_snapshot()
        st.markdown('<p class="sidebar-heading">Network</p>', unsafe_allow_html=True)
        if snapshot["external_count"] == 0:
            st.markdown('<p class="status-clear">✅ No external connections</p>',
                        unsafe_allow_html=True)
        else:
            st.markdown(f'<p class="status-alert">⚠️ {snapshot["external_count"]} external connection(s)</p>',
                        unsafe_allow_html=True)
            for conn_line in snapshot["external_connections"]:
                st.text(conn_line)
        st.caption(f"↑ {snapshot['bytes_sent'] / 1024:.1f} KB sent · "
                   f"↓ {snapshot['bytes_recv'] / 1024:.1f} KB received")

        st.markdown('<p class="sidebar-heading">Action ledger</p>', unsafe_allow_html=True)
        chain_status = verify_chain()
        if chain_status["valid"]:
            st.markdown(f'<p class="status-clear">✅ {chain_status["entries_checked"]} entries verified</p>',
                        unsafe_allow_html=True)
        else:
            st.markdown(f'<p class="status-alert">⚠️ Broken at entry {chain_status["broken_at"]}</p>',
                        unsafe_allow_html=True)

        if st.button("🔄 Refresh audit", key="refresh_audit", use_container_width=True):
            st.rerun()

    st.markdown("---")
    st.caption(f"Session `{st.session_state.session_id[:8]}` · "
               f"{len(st.session_state.messages)} messages")
    if st.button("🗑️ Clear this chat", use_container_width=True):
        clear_session(st.session_state.session_id)
        st.session_state.messages = []
        st.rerun()

# ---------------------------------------------------------------------------
# Main area — chat only
# ---------------------------------------------------------------------------
st.markdown('<p class="main-title">🛡️ Sovereign AI Workbench</p>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">Secure, air-gapped agentic AI for industrial workflows — zero external calls.</p>',
            unsafe_allow_html=True)

if not st.session_state.messages:
    st.markdown('<p class="hint">Ask for code, an image analysis, or a report. '
                'Attach files straight from the message bar below.</p>',
                unsafe_allow_html=True)

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        render_message(message["content"])

if not SUPPORTS_INLINE_FILES:
    with st.expander("📎 Attach image or report", expanded=False):
        staged = st.file_uploader("Attach", type=ALLOWED_TYPES,
                                  accept_multiple_files=True,
                                  label_visibility="collapsed",
                                  key=f"uploader_{st.session_state.session_id}")
        st.session_state.pending_files = staged or []
        if staged:
            st.caption("Attached: " + ", ".join(f.name for f in staged))

# ---------------------------------------------------------------------------
# Unified message bar (text + attachments)
# ---------------------------------------------------------------------------
if SUPPORTS_INLINE_FILES:
    submission = st.chat_input(
        "Ask for code, analysis, or a report — attach files with 📎",
        accept_file="multiple",
        file_type=ALLOWED_TYPES,
    )
else:
    submission = st.chat_input("Ask for code, analysis, or a report — attach files above")

if submission:
    if SUPPORTS_INLINE_FILES:
        prompt_text = (getattr(submission, "text", "") or "").strip()
        attachments = list(getattr(submission, "files", []) or [])
    else:
        prompt_text = (submission or "").strip()
        attachments = list(st.session_state.pending_files or [])

    saved_paths = [save_upload(f) for f in attachments]

    image_paths = [p for p in saved_paths
                   if os.path.splitext(p)[1].lower() in IMAGE_EXTS]
    doc_paths = [p for p in saved_paths if p not in image_paths]

    # Read every non-image attachment here and inline it into the prompt,
    # so the text actually reaches the model.
    context_blocks = []
    for p in doc_paths:
        text = extract_file_text(p).strip()
        context_blocks.append(
            f"### Attached file: {os.path.basename(p)}\n"
            + (text or "[No text could be extracted from this file, even with OCR.]")
        )

    agent_prompt = prompt_text
    if context_blocks:
        agent_prompt = (
            "Use ONLY the attached file contents below to answer.\n\n"
            + "\n\n".join(context_blocks)
            + f"\n\n### User question\n{prompt_text or 'Summarise the attached file.'}"
        )

    # Only real images go to the vision model — and agent.py's branch needs
    # the literal word "image" in the prompt before it will fire.
    image_path = image_paths[0] if image_paths else None
    if image_path and "image" not in agent_prompt.lower():
        agent_prompt = f"Analyse the attached image. {agent_prompt}".strip()   

    user_content = prompt_text
    if saved_paths:
        attach_block = "\n".join(f"{ATTACH_PREFIX}{p}" for p in saved_paths)
        user_content = (user_content + "\n\n" + attach_block).strip()

    if user_content:
        st.session_state.messages.append({"role": "user", "content": user_content})
        save_message(st.session_state.session_id, "user", user_content)

        with st.spinner("Processing local AI task..."):
            response = process_user_request(
                prompt=agent_prompt,
                image_path=image_path,
                history=st.session_state.messages,
            )

        st.session_state.messages.append({"role": "assistant", "content": response})
        save_message(st.session_state.session_id, "assistant", response)
        st.session_state.pending_files = []
        st.rerun()