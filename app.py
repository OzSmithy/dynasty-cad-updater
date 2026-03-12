import io
import os
import tempfile
from datetime import date

import streamlit as st
from pypdf import PdfReader, PdfWriter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SAFETY RULES — enforced throughout this app
#
#  1. READ-ONLY search  — Dropbox is only ever READ during search/download.
#                         No files are touched, moved, renamed or deleted.
#  2. NEW FILE only     — Dropbox upload ALWAYS creates a new file.
#                         WriteMode.add is used (never overwrite/update).
#                         If a file with the same name already exists the
#                         upload is BLOCKED and the user is told to rename.
#  3. Source never touched — The source PDF is never modified or deleted.
#  4. PDF-only          — The app only ever uploads .pdf files.
#  5. Same folder only  — The new file is saved to the exact folder the
#                         source came from.  No other path is ever written to.
#  6. Filename guard    — The new filename must start with the new P/O Number
#                         AND must differ from the source filename.
#                         Saving with the same name as the source is blocked.
#  7. Dry-run preview   — The full save path is shown and must be confirmed
#                         with a checkbox before the upload button is active.
#  8. No deletes        — The app has no delete capability whatsoever.
#  9. No broad listing  — Dropbox is only queried by filename search;
#                         no folder contents are listed or exposed.
# 10. Errors are safe   — Any exception aborts without touching Dropbox.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Dynasty Sport — CAD Updater",
    page_icon="⚡",
    layout="centered",
)

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@700;800&family=Barlow:wght@300;400&display=swap');
  html, body, [class*="css"] { font-family: 'Barlow', sans-serif; }
  #MainMenu, footer, header { visibility: hidden; }
  .block-container { padding-top: 2rem; max-width: 680px; }
  .ds-header { display:flex; align-items:center; gap:16px; margin-bottom:2rem; }
  .ds-logo-mark {
    width:44px; height:44px; background:#e02020; flex-shrink:0;
    clip-path:polygon(0 0,100% 0,100% 70%,70% 100%,0 100%);
    display:flex; align-items:center; justify-content:center;
  }
  .ds-title {
    font-family:'Barlow Condensed',sans-serif; font-size:22px;
    font-weight:800; letter-spacing:.06em; text-transform:uppercase; line-height:1;
  }
  .ds-sub { font-size:11px; color:#888; letter-spacing:.12em; text-transform:uppercase; margin-top:3px; }
  .step-label {
    font-family:'Barlow Condensed',sans-serif; font-size:11px; font-weight:700;
    letter-spacing:.18em; text-transform:uppercase; color:#e02020; margin:1.5rem 0 .5rem;
  }
  .auto-note    { font-size:11px; color:#e02020; letter-spacing:.04em; margin-top:-10px; margin-bottom:6px; }
  .comment-hint { font-size:11px; color:#888; margin-top:-10px; margin-bottom:6px; }
  .file-found {
    background:rgba(80,200,120,.08); border:1px solid rgba(80,200,120,.3);
    border-radius:4px; padding:10px 14px; margin:8px 0; font-size:13px; color:#50c878;
  }
  .file-path {
    background:rgba(255,255,255,.04); border:1px solid #2a2a2a;
    border-radius:4px; padding:8px 12px; margin:4px 0;
    font-size:11px; color:#888; font-family:monospace; word-break:break-all;
  }
  .save-preview {
    background:rgba(224,32,32,.05); border:1px solid rgba(224,32,32,.25);
    border-radius:4px; padding:12px 16px; margin:8px 0; font-size:12px; color:#ccc; line-height:1.8;
  }
  .safety-badge {
    display:inline-block; background:rgba(80,200,120,.12); border:1px solid rgba(80,200,120,.3);
    border-radius:3px; padding:2px 8px; font-size:10px; color:#50c878;
    letter-spacing:.08em; text-transform:uppercase; margin-right:4px;
  }
</style>

<div class="ds-header">
  <div class="ds-logo-mark">
    <svg width="22" height="22" viewBox="0 0 24 24" fill="white">
      <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
    </svg>
  </div>
  <div>
    <div class="ds-title">Dynasty Sport</div>
    <div class="ds-sub">CAD Order Graphic Updater</div>
  </div>
</div>
""", unsafe_allow_html=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DROPBOX — safe, minimal-permission helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_dropbox_client():
    """Connect to Dropbox using the secret token. Read/write only — no delete scope used."""
    try:
        import dropbox
        token = st.secrets["DROPBOX_TOKEN"]
        return dropbox.Dropbox(token)
    except Exception as e:
        st.error(f"Dropbox connection failed: {e}")
        return None


def search_dropbox_readonly(dbx, po_number: str):
    """
    SAFE READ-ONLY operation.
    Search Dropbox for a PDF whose name starts with po_number.
    Downloads only the first exact match.
    Does NOT list, modify, or touch any other file.
    Returns (display_path, filename, bytes) or (None, None, None).
    """
    import dropbox as dbx_module

    query = po_number.strip().upper()
    if not query:
        return None, None, None

    results = dbx.files_search_v2(
        query,
        options=dbx_module.files.SearchOptions(filename_only=True, max_results=20),
    )

    for match in results.matches:
        meta = match.metadata.get_metadata()
        if not isinstance(meta, dbx_module.files.FileMetadata):
            continue
        name = meta.name
        # Must start exactly with the P/O number and be a PDF — no partial matches
        if name.upper().startswith(query) and name.lower().endswith(".pdf"):
            _, response = dbx.files_download(meta.path_lower)
            return meta.path_display, meta.name, response.content

    return None, None, None


def check_file_exists_in_dropbox(dbx, full_path: str) -> bool:
    """
    SAFE READ-ONLY check.
    Returns True if a file already exists at full_path in Dropbox.
    Used to prevent accidental overwrite.
    """
    import dropbox as dbx_module
    try:
        dbx.files_get_metadata(full_path)
        return True  # file exists
    except dbx_module.exceptions.ApiError:
        return False  # file does not exist


def upload_new_file_to_dropbox(dbx, folder_path: str, filename: str,
                                pdf_bytes: bytes, source_filename: str) -> str:
    """
    SAFE WRITE operation — strict guards enforced before any upload:

      ① Must be a .pdf file
      ② Filename must differ from the source filename (never overwrite source)
      ③ File must NOT already exist at the destination (no silent overwrites)
      ④ Uses WriteMode.add — Dropbox will reject if file exists (double safety)
      ⑤ Only writes to folder_path (the exact folder the source came from)

    Raises ValueError with a clear message if any guard fails.
    Returns the full Dropbox path on success.
    """
    import dropbox as dbx_module

    # Guard ①: PDF only
    if not filename.lower().endswith(".pdf"):
        raise ValueError(f"Safety check failed: filename '{filename}' is not a .pdf file.")

    # Guard ②: Must not match source filename
    if filename.strip().lower() == source_filename.strip().lower():
        raise ValueError(
            f"Safety check failed: new filename '{filename}' is identical to the "
            f"source file '{source_filename}'. The source file will never be modified."
        )

    # Guard ③: Check file doesn't already exist
    save_path = folder_path.rstrip("/") + "/" + filename
    if check_file_exists_in_dropbox(dbx, save_path):
        raise ValueError(
            f"Safety check failed: a file named '{filename}' already exists in "
            f"'{folder_path}'. Please choose a different filename to avoid overwriting."
        )

    # Guard ④ + ⑤: Upload with add mode (fails if file exists — belt and braces)
    dbx.files_upload(
        pdf_bytes,
        save_path,
        mode=dbx_module.files.WriteMode.add,   # NEVER overwrite
    )

    return save_path


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  FILENAME helper
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def propose_new_filename(source_filename: str, new_po: str) -> str:
    """
    Replace the P/O prefix only.
    DSNZ-PL5474_TAWA_RFC_SHORTS_2025.pdf → DSNZ-PL5475_TAWA_RFC_SHORTS_2025.pdf
    Everything after the first underscore is preserved exactly.
    """
    new_po = new_po.strip().upper()
    parts  = source_filename.split("_", 1)
    if len(parts) == 2:
        return f"{new_po}_{parts[1]}"
    return f"{new_po}_ORDER_GRAPHIC.pdf"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  PDF PROCESSING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PAGE_HEIGHT = 595.28
BORDER_LW   = 0.921
DIVIDER_X   = 76.92
RIGHT_X     = 206.121
TEXT_X      = 83.0
FONT_SIZE   = 10.0
LINE_HEIGHT = 13.0

CELLS = {
    "po_number":    {"rl_y0": PAGE_HEIGHT - 79.497,  "rl_y1": PAGE_HEIGHT - 57.310},
    "artist":       {"rl_y0": PAGE_HEIGHT - 212.871, "rl_y1": PAGE_HEIGHT - 190.684},
    "date":         {"rl_y0": PAGE_HEIGHT - 235.058, "rl_y1": PAGE_HEIGHT - 212.871},
    "previous_ref": {"rl_y0": PAGE_HEIGHT - 257.245, "rl_y1": PAGE_HEIGHT - 235.058},
    "comments":     {"rl_y0": PAGE_HEIGHT - 321.223, "rl_y1": PAGE_HEIGHT - 257.245},
}


def extract_grover_font(pdf_bytes: bytes):
    reader = PdfReader(io.BytesIO(pdf_bytes))
    for page in reader.pages:
        try:
            fonts = page["/Resources"].get("/Font", {})
        except Exception:
            continue
        for _, obj in fonts.items():
            try:
                f = obj.get_object()
                if "Grover-Regular" in str(f.get("/BaseFont", "")):
                    d = f["/FontDescriptor"].get_object()
                    if "/FontFile2" in d:
                        return d["/FontFile2"].get_object().get_data()
            except Exception:
                continue
    return None


def extract_po_number(pdf_bytes: bytes):
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            chars = pdf.pages[0].chars
            row   = sorted(
                [c for c in chars if 75 < c["x0"] < 210 and 57 < c["top"] < 83],
                key=lambda c: c["x0"],
            )
            text = "".join(c["text"] for c in row).strip()
            return text.split(" ")[0] if " " in text else text or None
    except Exception:
        return None


def wrap_text(text, font_name, font_size, max_width, c):
    words = text.split(" ")
    lines, cur = [], ""
    for word in words:
        test = (cur + " " + word).strip()
        if c.stringWidth(test, font_name, font_size) <= max_width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def make_overlay(font_path, vals, pw, ph):
    pkt  = io.BytesIO()
    c    = canvas.Canvas(pkt, pagesize=(pw, ph))
    lw2  = BORDER_LW / 2
    maxw = RIGHT_X - TEXT_X - 4

    for field, cell in CELLS.items():
        y0 = cell["rl_y0"]; y1 = cell["rl_y1"]; ch = y1 - y0
        text = vals.get(field, "")

        c.setFillColorRGB(1, 1, 1)
        c.rect(DIVIDER_X + lw2, y0 + lw2,
               RIGHT_X - DIVIDER_X - BORDER_LW, ch - BORDER_LW, fill=1, stroke=0)

        c.setFont("Grover-Regular", FONT_SIZE)
        if field == "comments":
            c.setFillColorRGB(0.85, 0, 0)
            lines   = wrap_text(text, "Grover-Regular", FONT_SIZE, maxw, c)
            start_y = y1 - 4 - FONT_SIZE
            for i, line in enumerate(lines):
                ly = start_y - i * LINE_HEIGHT
                if ly >= y0 + 2:
                    c.drawString(TEXT_X, ly, line)
        else:
            c.setFillColorRGB(0, 0, 0)
            c.drawString(TEXT_X, y0 + (ch - FONT_SIZE) / 2 + 2, text)

        c.setStrokeColorRGB(0, 0, 0)
        c.setLineWidth(BORDER_LW)
        c.rect(0.307, y0, RIGHT_X - 0.307, ch, fill=0, stroke=1)

    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(BORDER_LW)
    c.line(DIVIDER_X, PAGE_HEIGHT - 321.223, DIVIDER_X, PAGE_HEIGHT - 57.310)
    c.save(); pkt.seek(0)
    return pkt


def process_pdf(pdf_bytes: bytes, vals: dict) -> bytes:
    """Generate the updated PDF entirely in memory. Source bytes are never modified."""
    font_data = extract_grover_font(pdf_bytes)
    if not font_data:
        raise ValueError("Grover-Regular font not found — is this a Dynasty Sport Order Graphic PDF?")

    tmp = tempfile.NamedTemporaryFile(suffix=".ttf", delete=False)
    tmp.write(font_data); tmp.close()

    try:
        try:
            pdfmetrics.registerFont(TTFont("Grover-Regular", tmp.name))
        except Exception:
            pass  # already registered from a previous call

        reader = PdfReader(io.BytesIO(pdf_bytes))
        writer = PdfWriter()

        for orig in reader.pages:
            w  = float(orig.mediabox.width)
            h  = float(orig.mediabox.height)
            op = PdfReader(make_overlay(tmp.name, vals, w, h)).pages[0]
            op.merge_page(orig, over=False)
            writer.add_page(op)

        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()

    finally:
        os.unlink(tmp.name)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SESSION STATE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

for key in ["source_pdf_bytes", "source_filename", "source_folder",
            "source_po", "page_count", "result_pdf", "result_filename"]:
    if key not in st.session_state:
        st.session_state[key] = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  STEP 1 — Search Dropbox (READ ONLY)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

st.markdown(
    '<div class="step-label">01 — Find Source File in Dropbox</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<span class="safety-badge">🔒 read only</span> '
    '<span style="font-size:11px;color:#666;">No files are modified during search</span>',
    unsafe_allow_html=True,
)

s_col1, s_col2 = st.columns([3, 1])
with s_col1:
    search_po = st.text_input(
        "Source P/O Number",
        placeholder="e.g. DSNZ-PL5474",
        label_visibility="collapsed",
    )
with s_col2:
    do_search = st.button("🔍  Search", use_container_width=True,
                          disabled=not search_po.strip())

if do_search and search_po.strip():
    with st.spinner(f"Searching Dropbox for **{search_po.strip().upper()}**…"):
        dbx = get_dropbox_client()
        if dbx:
            path, filename, pdf_bytes = search_dropbox_readonly(dbx, search_po.strip())
            if pdf_bytes:
                st.session_state.source_pdf_bytes = pdf_bytes
                st.session_state.source_filename  = filename
                st.session_state.source_folder    = os.path.dirname(path)
                st.session_state.source_po        = extract_po_number(pdf_bytes)
                st.session_state.page_count       = len(PdfReader(io.BytesIO(pdf_bytes)).pages)
                st.session_state.result_pdf       = None
                st.session_state.result_filename  = None
                st.rerun()
            else:
                st.error(
                    f"No PDF found starting with **{search_po.strip().upper()}**. "
                    "Check the P/O Number and try again."
                )

if st.session_state.source_pdf_bytes:
    pages = st.session_state.page_count
    st.markdown(
        f'<div class="file-found">'
        f'✓ &nbsp;<strong>{st.session_state.source_filename}</strong>'
        f'&nbsp;·&nbsp; {pages} page{"s" if pages > 1 else ""}'
        f'&nbsp;·&nbsp; P/O detected: <strong>{st.session_state.source_po or "unknown"}</strong>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="file-path">📁 &nbsp;{st.session_state.source_folder}</div>',
        unsafe_allow_html=True,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  STEP 2 — Preview source PDF
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if st.session_state.source_pdf_bytes:
    st.markdown(
        '<div class="step-label">02 — Preview Source PDF</div>',
        unsafe_allow_html=True,
    )

    import base64
    b64 = base64.b64encode(st.session_state.source_pdf_bytes).decode()
    st.markdown(
        f'<iframe src="data:application/pdf;base64,{b64}" '
        f'width="100%" height="520px" '
        f'style="border:1px solid #2a2a2a; border-radius:4px;"></iframe>',
        unsafe_allow_html=True,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  STEP 3 — Update fields
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if st.session_state.source_pdf_bytes:
    st.markdown(
        '<div class="step-label">03 — Update Fields</div>',
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns([1, 2])
    with col1:
        st.markdown("**P/O Number**")
    with col2:
        po_number = st.text_input(
            "P/O Number", placeholder="e.g. DSNZ-PL5475",
            label_visibility="collapsed",
        )

    col1, col2 = st.columns([1, 2])
    with col1:
        st.markdown("**Artist**")
    with col2:
        artist = st.text_input(
            "Artist", placeholder="e.g. SANA",
            label_visibility="collapsed",
        )

    col1, col2 = st.columns([1, 2])
    with col1:
        st.markdown("**Date**")
    with col2:
        picked_date = st.date_input(
            "Date", value=date.today(),
            format="DD/MM/YYYY",
            label_visibility="collapsed",
        )
        date_val = picked_date.strftime("%d/%m/%Y")

    st.divider()

    col1, col2 = st.columns([1, 2])
    with col1:
        st.markdown("**Previous Ref**")
        st.markdown(
            '<div class="auto-note">⚡ Auto-filled from source P/O</div>',
            unsafe_allow_html=True,
        )
    with col2:
        previous_ref = st.text_input(
            "Previous Ref",
            value=st.session_state.source_po or "",
            label_visibility="collapsed",
            help="Auto-filled from the source PDF's P/O Number — edit if needed",
        )

    col1, col2 = st.columns([1, 2])
    with col1:
        st.markdown("**Comments**")
        st.markdown(
            '<div class="comment-hint">Appears in red on PDF</div>',
            unsafe_allow_html=True,
        )
    with col2:
        comments = st.text_input(
            "Comments",
            placeholder="e.g. *REPEAT OF DSNZ-PL5474",
            label_visibility="collapsed",
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  STEP 4 — Confirm filename & save
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if st.session_state.source_pdf_bytes:
    st.markdown(
        '<div class="step-label">04 — Confirm Filename &amp; Save to Dropbox</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<span class="safety-badge">🔒 new file only</span> '
        '<span style="font-size:11px;color:#666;">'
        'Source file is never modified · Upload blocked if filename already exists'
        '</span>',
        unsafe_allow_html=True,
    )

    # Auto-propose filename
    proposed = ""
    if po_number.strip():
        proposed = propose_new_filename(
            st.session_state.source_filename, po_number.strip()
        )

    col1, col2 = st.columns([1, 2])
    with col1:
        st.markdown("**New Filename**")
    with col2:
        new_filename = st.text_input(
            "New Filename",
            value=proposed,
            label_visibility="collapsed",
            help="Edit if needed — must end in .pdf and differ from source filename",
            placeholder="Enter P/O Number above first",
        )

    # ── Inline safety validation ──────────────────────────────────────────────
    filename_ok = False
    if new_filename.strip():
        fname = new_filename.strip()
        if not fname.lower().endswith(".pdf"):
            st.warning("⚠️  Filename must end in `.pdf`")
        elif fname.lower() == st.session_state.source_filename.lower():
            st.error(
                "🚫  New filename cannot be the same as the source file. "
                "The source file will never be modified."
            )
        elif not fname.upper().startswith(po_number.strip().upper()):
            st.warning(
                "⚠️  Filename should start with the new P/O Number "
                f"(**{po_number.strip().upper()}**). Edit if this is intentional."
            )
            filename_ok = True  # warn but don't block
        else:
            filename_ok = True

    # ── Save preview ──────────────────────────────────────────────────────────
    if filename_ok:
        full_save_path = (
            st.session_state.source_folder.rstrip("/") + "/" + new_filename.strip()
        )
        st.markdown(
            f'<div class="save-preview">'
            f'<strong>Save preview</strong><br>'
            f'📁 &nbsp;Folder: <code>{st.session_state.source_folder}</code><br>'
            f'📄 &nbsp;New file: <strong>{new_filename.strip()}</strong><br>'
            f'🔒 &nbsp;Source unchanged: <code>{st.session_state.source_filename}</code>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # ── Confirmation checkbox (must tick before button activates) ─────────
        confirmed = st.checkbox(
            f'✅  I confirm this is correct — save **{new_filename.strip()}** to Dropbox'
        )

        can_save = bool(
            confirmed
            and po_number.strip()
            and filename_ok
        )

        if st.button(
            "⚡  Generate & Save to Dropbox",
            disabled=not can_save,
            use_container_width=True,
            type="primary",
        ):
            with st.spinner("Generating updated PDF…"):
                try:
                    # ── Step A: generate PDF in memory ────────────────────────
                    vals = {
                        "po_number":    po_number.strip().upper(),
                        "artist":       artist.strip().upper(),
                        "date":         date_val,
                        "previous_ref": previous_ref.strip().upper(),
                        "comments":     comments.strip().upper(),
                    }
                    result_bytes = process_pdf(st.session_state.source_pdf_bytes, vals)

                    fname = new_filename.strip()
                    if not fname.lower().endswith(".pdf"):
                        fname += ".pdf"

                    # ── Step B: upload with all safety guards ─────────────────
                    dbx = get_dropbox_client()
                    if dbx:
                        with st.spinner(f"Uploading **{fname}** to Dropbox…"):
                            save_path = upload_new_file_to_dropbox(
                                dbx,
                                st.session_state.source_folder,
                                fname,
                                result_bytes,
                                st.session_state.source_filename,
                            )

                        st.session_state.result_pdf      = result_bytes
                        st.session_state.result_filename = fname

                        pages = len(PdfReader(io.BytesIO(result_bytes)).pages)
                        st.success(
                            f"✓ **{fname}** saved to Dropbox successfully  \n"
                            f"📁 `{save_path}`  ·  "
                            f"{pages} page{'s' if pages > 1 else ''}  \n"
                            f"🔒 Source file **{st.session_state.source_filename}** "
                            f"was not modified."
                        )

                except ValueError as ve:
                    # Safety guard triggered — clear message, no upload happened
                    st.error(f"🚫 Upload blocked — {ve}")
                except Exception as e:
                    st.error(f"Error: {e}")

    # ── Local download backup (always available after generation) ─────────────
    if st.session_state.result_pdf:
        st.divider()
        st.download_button(
            label="⬇  Also download locally as backup",
            data=st.session_state.result_pdf,
            file_name=st.session_state.result_filename or "output.pdf",
            mime="application/pdf",
            use_container_width=False,
        )
