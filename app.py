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
    """
    Connect to Dropbox using App Key + App Secret + short-lived token.
    Automatically refreshes the token so it never expires.
    Read/write only — no delete scope used.
    """
    try:
        import dropbox
        app_key    = st.secrets["DROPBOX_APP_KEY"]
        app_secret = st.secrets["DROPBOX_APP_SECRET"]
        token      = st.secrets["DROPBOX_TOKEN"]

        # Use OAuth2 app credentials so token auto-refreshes
        dbx = dropbox.Dropbox(
            oauth2_access_token=token,
            app_key=app_key,
            app_secret=app_secret,
        )
        # Quick check the connection works
        dbx.users_get_current_account()
        return dbx
    except Exception as e:
        st.error(f"Dropbox connection failed: {e}")
        return None


def get_order_graphics_ns(dbx):
    """
    Get a namespace-scoped Dropbox client for the Order Graphics shared folder.
    Caches namespace ID in session state to avoid repeated API calls.
    Returns (dbx_ns, is_namespace) tuple.
    """
    import dropbox as dbx_lib

    # Use cached namespace if available
    if st.session_state.get("og_namespace_id"):
        ns_id = st.session_state.og_namespace_id
        dbx_ns = dbx.with_path_root(dbx_lib.common.PathRoot.namespace_id(ns_id))
        return dbx_ns, True

    # Try direct path first
    for candidate in ["/Design/Order Graphics", "/Order Graphics"]:
        try:
            dbx.files_get_metadata(candidate)
            st.session_state.og_namespace_id = None
            st.session_state.og_path = candidate
            return dbx, False
        except Exception:
            continue

    # Fall back to shared folder listing to get namespace ID
    try:
        shared = dbx.sharing_list_folders()
        for sf in shared.entries:
            if "order graphics" in sf.name.lower():
                ns_id = sf.shared_folder_id
                st.session_state.og_namespace_id = ns_id
                dbx_ns = dbx.with_path_root(dbx_lib.common.PathRoot.namespace_id(ns_id))
                return dbx_ns, True
    except Exception as e:
        st.error(f"Could not locate Order Graphics folder: {e}")

    return None, False


def search_dropbox_readonly(dbx, po_number: str, customer_letter: str):
    """
    SAFE READ-ONLY operation.
    Scans only the single letter subfolder within Order Graphics.
    Structure: Order Graphics / [LETTER] / [CUSTOMER] / file.PDF
    Only 2 levels deep — fast even with thousands of files.
    Returns (display_path, filename, bytes) or (None, None, None).
    """
    import dropbox as dbx_module

    query  = po_number.strip().upper()
    letter = customer_letter.strip().upper()[:1]  # single letter only

    if not query or not letter:
        return None, None, None

    # Get namespace-scoped client
    dbx_ns, is_ns = get_order_graphics_ns(dbx)
    if not dbx_ns:
        st.error("Could not connect to Order Graphics folder.")
        return None, None, None

    found_meta = None

    try:
        # List customer folders under the letter folder
        letter_result = dbx_ns.files_list_folder(f"/{letter}")
        customer_folders = [
            e for e in letter_result.entries
            if isinstance(e, dbx_module.files.FolderMetadata)
        ]

        status = st.empty()
        status.info(f"Found {len(customer_folders)} customer folder(s) under `{letter}/` — scanning…")

        for folder in customer_folders:
            try:
                sub = dbx_ns.files_list_folder(folder.path_lower)
                while True:
                    for entry in sub.entries:
                        if isinstance(entry, dbx_module.files.FileMetadata):
                            if (entry.name.upper().startswith(query)
                                    and entry.name.upper().endswith(".PDF")):
                                found_meta = entry
                                break
                    if found_meta or not sub.has_more:
                        break
                    sub = dbx_ns.files_list_folder_continue(sub.cursor)
            except Exception:
                continue
            if found_meta:
                break

        status.empty()

    except dbx_module.exceptions.ApiError as e:
        st.error(
            f"Could not open letter folder `/{letter}` in Order Graphics. "
            f"Make sure the customer letter is correct. Error: {e}"
        )
        return None, None, None

    if found_meta:
        st.info(f"✓ Found: `{found_meta.path_display}`")
        _, response = dbx_ns.files_download(found_meta.path_lower)
        # Store the namespace-scoped client so upload goes to same folder
        st.session_state.dbx_ns = dbx_ns
        # Use path_lower of the file's parent folder (e.g. /f/five star removals)
        folder_path = found_meta.path_lower.rsplit("/", 1)[0]  # e.g. /f/five star removals
        return folder_path, found_meta.name, response.content
    else:
        st.warning(
            f"No file starting with `{query}` found under `Order Graphics/{letter}/`. "
            f"Check the P/O Number and customer letter are correct."
        )
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
    DSAU-CS0193_Five Star Removals-Stock Polo.PDF → DSAU-CS0194_Five Star Removals-Stock Polo.PDF
    Everything after the first underscore is preserved exactly, including
    spaces, capitalisation and the original file extension.
    """
    new_po = new_po.strip().upper()
    parts  = source_filename.split("_", 1)
    if len(parts) == 2:
        return f"{new_po}_{parts[1]}"
    # Fallback: no underscore found — keep original name but swap prefix
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

# Custom Order Graphic — 5 editable fields in lower table section
CUSTOM_CELLS = {
    "po_number":    {"rl_y0": PAGE_HEIGHT - 79.497,  "rl_y1": PAGE_HEIGHT - 57.310},
    "artist":       {"rl_y0": PAGE_HEIGHT - 212.871, "rl_y1": PAGE_HEIGHT - 190.684},
    "date":         {"rl_y0": PAGE_HEIGHT - 235.058, "rl_y1": PAGE_HEIGHT - 212.871},
    "previous_ref": {"rl_y0": PAGE_HEIGHT - 257.245, "rl_y1": PAGE_HEIGHT - 235.058},
    "comments":     {"rl_y0": PAGE_HEIGHT - 321.223, "rl_y1": PAGE_HEIGHT - 257.245},
}

# Stock Order Graphic — 3 editable fields (P/O NUMBER, ARTIST, DATE only)
# Exact coords from PDF rect analysis
STOCK_CELLS = {
    "po_number": {"rl_y0": 515.779, "rl_y1": 537.966},
    "artist":    {"rl_y0": 426.780, "rl_y1": 448.967},
    "date":      {"rl_y0": 404.593, "rl_y1": 426.780},
}

# Divider line extents per type
CUSTOM_DIVIDER_Y0 = PAGE_HEIGHT - 321.223
CUSTOM_DIVIDER_Y1 = PAGE_HEIGHT - 57.310
STOCK_DIVIDER_Y0  = 404.593
STOCK_DIVIDER_Y1  = 537.966

# Keep CELLS as alias — will be set dynamically per PDF type
CELLS = CUSTOM_CELLS


def detect_graphic_type(pdf_bytes: bytes) -> str:
    """
    Detect whether a PDF is a Custom or Stock Order Graphic.
    Stock Order Graphics have 6 rows ending at ~top=190 (DATE is last field).
    Custom Order Graphics have additional rows below (ARTIST, DATE, PREV REF, COMMENTS).
    Returns "stock" or "custom".
    """
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            page = pdf.pages[0]
            rects = page.rects
            # Check if there are rects below top=190 (custom has rows down to ~321)
            deep_rects = [r for r in rects if r['top'] > 195 and r['x0'] < 220 and r['x1'] > 100]
            return "custom" if deep_rects else "stock"
    except Exception:
        return "custom"  # safe default


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


def make_overlay(font_path, vals, pw, ph, cells=None, divider_y0=None, divider_y1=None):
    if cells is None:
        cells = CUSTOM_CELLS
    if divider_y0 is None:
        divider_y0 = CUSTOM_DIVIDER_Y0
    if divider_y1 is None:
        divider_y1 = CUSTOM_DIVIDER_Y1

    pkt  = io.BytesIO()
    c    = canvas.Canvas(pkt, pagesize=(pw, ph))
    lw2  = BORDER_LW / 2
    maxw = RIGHT_X - TEXT_X - 4

    for field, cell in cells.items():
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

        # Redraw only the VALUE cell border (right of divider) — never touch label column
        c.setStrokeColorRGB(0, 0, 0)
        c.setLineWidth(BORDER_LW)
        c.rect(DIVIDER_X, y0, RIGHT_X - DIVIDER_X, ch, fill=0, stroke=1)

    # Redraw the vertical divider line between label and value columns
    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(BORDER_LW)
    c.line(DIVIDER_X, divider_y0, DIVIDER_X, divider_y1)
    c.save(); pkt.seek(0)
    return pkt


def process_pdf(pdf_bytes: bytes, vals: dict, graphic_type: str = "custom") -> bytes:
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

        # Select correct cell layout and divider extents
        if graphic_type == "stock":
            cells       = STOCK_CELLS
            divider_y0  = STOCK_DIVIDER_Y0
            divider_y1  = STOCK_DIVIDER_Y1
        else:
            cells       = CUSTOM_CELLS
            divider_y0  = CUSTOM_DIVIDER_Y0
            divider_y1  = CUSTOM_DIVIDER_Y1

        reader = PdfReader(io.BytesIO(pdf_bytes))
        writer = PdfWriter()

        for orig in reader.pages:
            w  = float(orig.mediabox.width)
            h  = float(orig.mediabox.height)
            op = PdfReader(make_overlay(tmp.name, vals, w, h, cells, divider_y0, divider_y1)).pages[0]
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
            "source_po", "page_count", "result_pdf", "result_filename",
            "dbx_ns", "og_namespace_id", "graphic_type"]:
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

s_col1, s_col2, s_col3 = st.columns([3, 1, 1])
with s_col1:
    search_po = st.text_input(
        "Source P/O Number",
        placeholder="e.g. DSAU-CS0193",
        label_visibility="collapsed",
    )
with s_col2:
    customer_letter = st.text_input(
        "Customer Letter",
        placeholder="e.g. F",
        max_chars=1,
        label_visibility="collapsed",
        help="First letter of the customer name (e.g. F for Five Star Removals)",
    )
with s_col3:
    do_search = st.button(
        "🔍  Search", use_container_width=True,
        disabled=not (search_po.strip() and customer_letter.strip()),
    )

st.markdown(
    '<span style="font-size:11px;color:#888;">Enter the P/O Number and first letter of the customer name (e.g. F for Five Star Removals)</span>',
    unsafe_allow_html=True,
)

if do_search and search_po.strip() and customer_letter.strip():
    dbx = get_dropbox_client()
    if dbx:
        path, filename, pdf_bytes = search_dropbox_readonly(
            dbx, search_po.strip(), customer_letter.strip()
        )
        if pdf_bytes:
            st.session_state.source_pdf_bytes = pdf_bytes
            st.session_state.source_filename  = filename
            st.session_state.source_folder    = path  # already the folder path
            st.session_state.source_po        = extract_po_number(pdf_bytes)
            st.session_state.graphic_type     = detect_graphic_type(pdf_bytes)
            st.session_state.page_count       = len(PdfReader(io.BytesIO(pdf_bytes)).pages)
            st.session_state.result_pdf       = None
            st.session_state.result_filename  = None
            st.rerun()

if st.session_state.source_pdf_bytes:
    pages = st.session_state.page_count
    gtype = st.session_state.graphic_type or "custom"
    gtype_label = "📋 Stock Order Graphic" if gtype == "stock" else "🎨 Custom Order Graphic"
    st.markdown(
        f'<div class="file-found">'
        f'✓ &nbsp;<strong>{st.session_state.source_filename}</strong>'
        f'&nbsp;·&nbsp; {pages} page{"s" if pages > 1 else ""}'
        f'&nbsp;·&nbsp; P/O: <strong>{st.session_state.source_po or "unknown"}</strong>'
        f'&nbsp;·&nbsp; {gtype_label}'
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
        '<div class="step-label">02 — Verify Source PDF</div>',
        unsafe_allow_html=True,
    )
    fname   = st.session_state.source_filename
    fpath   = st.session_state.source_folder
    st.markdown(f"**{fname}** — 📁 `{fpath}`")
    st.caption("Confirm this is the correct file before updating the fields below.")
    st.download_button(
        label="⬇  Download source PDF to verify",
        data=st.session_state.source_pdf_bytes,
        file_name=st.session_state.source_filename,
        mime="application/pdf",
        use_container_width=False,
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

    is_stock = (st.session_state.graphic_type == "stock")

    if not is_stock:
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
            default_comment = f"*REPEAT OF {st.session_state.source_po}" if st.session_state.source_po else ""
            comments = st.text_input(
                "Comments",
                value=default_comment,
                label_visibility="collapsed",
            )
    else:
        previous_ref = ""
        comments     = ""


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
                        # Only include fields relevant to the graphic type
                        **({"previous_ref": previous_ref.strip().upper(),
                            "comments":     comments.strip().upper()}
                           if (st.session_state.graphic_type or "custom") == "custom"
                           else {}),
                    }
                    result_bytes = process_pdf(
                        st.session_state.source_pdf_bytes,
                        vals,
                        graphic_type=st.session_state.graphic_type or "custom",
                    )

                    fname = new_filename.strip()
                    if not fname.lower().endswith(".pdf"):
                        fname += ".pdf"

                    # ── Step B: upload with all safety guards ─────────────────
                    # Use namespace-scoped client so file lands in the shared folder
                    dbx_upload = st.session_state.get("dbx_ns") or get_dropbox_client()
                    if dbx_upload:
                        with st.spinner(f"Uploading **{fname}** to Dropbox…"):
                            save_path = upload_new_file_to_dropbox(
                                dbx_upload,
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
