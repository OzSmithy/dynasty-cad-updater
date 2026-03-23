import io
import os
import re
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
    page_title="DROG — Dynasty Repeat Order Graphics",
    page_icon="⚡",
    layout="centered",
)

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Libre+Franklin:wght@300;400;500;600;700;800&display=swap');

  /* ── Reset & base ─────────────────────────────────────────── */
  html, body, [class*="css"] {
    font-family: 'Libre Franklin', sans-serif;
    background-color: #F5F5F3;
    color: #1A1B18;
  }
  #MainMenu, footer, header { visibility: hidden; }
  .block-container {
    padding-top: 2rem;
    max-width: 720px;
  }

  /* ── Header ───────────────────────────────────────────────── */
  .ds-header {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 20px 0 18px 0;
    border-bottom: 1px solid #DDDDD9;
    margin-bottom: 2rem;
  }
  .ds-logo-img { flex-shrink: 0; display: flex; align-items: center; }
  .ds-title {
    font-size: 15px;
    font-weight: 700;
    letter-spacing: .01em;
    color: #1A1B18;
    line-height: 1.2;
    text-transform: none;
    font-family: 'Libre Franklin', sans-serif;
  }
  .ds-sub {
    font-size: 12px;
    color: #6B6B67;
    letter-spacing: 0;
    text-transform: none;
    margin-top: 2px;
    font-weight: 400;
  }

  /* ── Step labels ──────────────────────────────────────────── */
  .step-label {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: .1em;
    text-transform: uppercase;
    color: #E8441A;
    margin: 1.5rem 0 .5rem;
  }

  /* ── Helper notes ─────────────────────────────────────────── */
  .auto-note    { font-size: 11px; color: #E8441A; letter-spacing: .02em; margin-top: -8px; margin-bottom: 6px; }
  .comment-hint { font-size: 11px; color: #6B6B67; margin-top: -8px; margin-bottom: 6px; }

  /* ── Found file banner ────────────────────────────────────── */
  .file-found {
    background: #fff;
    border: 1px solid #DDDDD9;
    border-left: 3px solid #E8441A;
    border-radius: 4px;
    padding: 10px 14px;
    margin: 8px 0;
    font-size: 13px;
    color: #1A1B18;
    font-weight: 500;
  }

  /* ── Folder path chip ─────────────────────────────────────── */
  .file-path {
    background: #fff;
    border: 1px solid #DDDDD9;
    border-radius: 4px;
    padding: 8px 12px;
    margin: 4px 0;
    font-size: 11px;
    color: #6B6B67;
    font-family: monospace;
    word-break: break-all;
  }

  /* ── Save preview box ─────────────────────────────────────── */
  .save-preview {
    background: #fff;
    border: 1px solid #DDDDD9;
    border-left: 3px solid #1A1B18;
    border-radius: 4px;
    padding: 12px 16px;
    margin: 8px 0;
    font-size: 12px;
    color: #3F3C39;
    line-height: 1.8;
  }

  /* ── Safety badge ─────────────────────────────────────────── */
  .safety-badge {
    display: inline-block;
    background: #F5F5F3;
    border: 1px solid #DDDDD9;
    border-radius: 3px;
    padding: 2px 8px;
    font-size: 10px;
    color: #3F3C39;
    letter-spacing: .06em;
    text-transform: uppercase;
    margin-right: 4px;
    font-weight: 600;
  }

  /* ── Streamlit element overrides ──────────────────────────── */
  div[data-testid="stTextInput"] input,
  div[data-testid="stDateInput"] input {
    background: #fff !important;
    border: 1px solid #DDDDD9 !important;
    border-radius: 4px !important;
    color: #1A1B18 !important;
    font-family: 'Libre Franklin', sans-serif !important;
  }
  div[data-testid="stTextInput"] input:focus,
  div[data-testid="stDateInput"] input:focus {
    border-color: #1A1B18 !important;
    box-shadow: none !important;
  }
  div[data-testid="stCheckbox"] label {
    font-size: 13px;
    color: #1A1B18;
    font-weight: 500;
  }
  .stButton > button {
    background: #1A1B18 !important;
    color: #fff !important;
    border: none !important;
    border-radius: 4px !important;
    font-family: 'Libre Franklin', sans-serif !important;
    font-weight: 600 !important;
    font-size: 13px !important;
    padding: 10px 20px !important;
    letter-spacing: .02em !important;
    transition: background .15s ease !important;
  }
  .stButton > button:hover {
    background: #E8441A !important;
  }
  .stButton > button:disabled {
    background: #DDDDD9 !important;
    color: #9E9E9A !important;
  }
  div[data-testid="stExpander"] {
    border: 1px solid #DDDDD9 !important;
    border-radius: 4px !important;
    background: #fff !important;
  }
  div.stAlert {
    border-radius: 4px !important;
  }
  hr { border-color: #DDDDD9 !important; }
</style>

<div class="ds-header">
  <div class="ds-logo-img">
    <img src="data:image/png;base64,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" alt="Dynasty Sport" style="height:40px; width:auto; display:block;" />
  </div>
  <div>
    <div class="ds-title">Dynasty Repeat Order Graphics</div>
    <div class="ds-sub">DROG &nbsp;·&nbsp; Order Graphic Repeat Tool</div>
  </div>
</div>
""", unsafe_allow_html=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DROPBOX — safe, minimal-permission helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_dropbox_client():
    """
    Connect to Dropbox using App Key + App Secret + refresh token (never expires).
    The refresh token (starts with 'ad') is passed as oauth2_refresh_token so
    the SDK automatically exchanges it for short-lived access tokens as needed.
    """
    try:
        import dropbox
        app_key    = st.secrets["DROPBOX_APP_KEY"]
        app_secret = st.secrets["DROPBOX_APP_SECRET"]
        token      = st.secrets["DROPBOX_TOKEN"]
        dbx = dropbox.Dropbox(
            oauth2_refresh_token=token,
            app_key=app_key,
            app_secret=app_secret,
        )
        dbx.users_get_current_account()
        return dbx
    except Exception as e:
        st.error(f"Dropbox connection failed: {e}")
        return None


DROG_ARCHIVE_PATH = "/drog"   # path inside the DESIGN shared folder

def get_design_ns(dbx):
    """
    Get a namespace-scoped Dropbox client for the DESIGN shared folder.
    The DROG archive folder lives at /DROG inside this namespace.
    Caches namespace ID in session state to avoid repeated API calls.
    Returns dbx_ns or None on failure.
    """
    import dropbox as dbx_lib
    cache_key = "design_namespace_id"
    if st.session_state.get(cache_key):
        ns_id  = st.session_state[cache_key]
        dbx_ns = dbx.with_path_root(dbx_lib.common.PathRoot.namespace_id(ns_id))
        try:
            dbx_ns.files_list_folder(DROG_ARCHIVE_PATH)
            return dbx_ns
        except Exception:
            st.session_state[cache_key] = None

    try:
        shared = dbx.sharing_list_folders()
        for entry in shared.entries:
            if entry.name.lower() == "design":
                ns_id = entry.shared_folder_id
                st.session_state[cache_key] = ns_id
                return dbx.with_path_root(dbx_lib.common.PathRoot.namespace_id(ns_id))
    except Exception as e:
        st.warning(f"Could not locate DESIGN shared folder: {e}")
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
                # Use recursive=True to find files in any subfolder depth
                sub = dbx_ns.files_list_folder(folder.path_lower, recursive=True)
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
    Replace the P/O prefix in the source filename with the new P/O number.
    Handles both underscore and space separated filenames:
      DSAU-CS0193_Five Star Removals.PDF  → DSAU-CS0194_Five Star Removals.PDF
      DSAU-CM3691C BEAUDESERT JRL.pdf     → DSAU-CM3905A BEAUDESERT JRL.pdf
    """
    new_po = new_po.strip().upper()
    new_po = re.sub(r'\s*-\s*', '-', new_po)  # remove spaces around dash: DSAU - CM3905A → DSAU-CM3905A
    # Match the full PO prefix: e.g. DSAU-CM3691C or DSNZ-TW0622 then space or underscore
    match = re.match(r'^([A-Z]{2,4}-[A-Z]{2,3}\d+[A-Z]*)([\s_])(.*)', source_filename, re.IGNORECASE)
    if match:
        separator = match.group(2)  # preserve original separator (_ or space)
        remainder = match.group(3)  # everything after the PO prefix
        return f"{new_po}{separator}{remainder}"
    # Fallback: just prepend new PO to the whole filename
    return f"{new_po} {source_filename}"


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
            # Custom has table rows between top=190 and top=330 (ARTIST/DATE/PREV REF/COMMENTS)
            # Stock table ends at top~190 (DATE is last row)
            # Ignore footer rects (top > 400)
            deep_rects = [
                r for r in rects
                if 195 < r['top'] < 400
                and r['x0'] < 220
                and r['x1'] > 100
            ]
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
        import pdfplumber, re
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            chars = pdf.pages[0].chars
            # Tight x bounds: value column only (DIVIDER_X to RIGHT_X)
            # Tight y bounds: P/O row only
            row = sorted(
                [c for c in chars if DIVIDER_X < c["x0"] < RIGHT_X + 20 and 55 < c["top"] < 85],
                key=lambda c: c["x0"],
            )
            # Join chars, strip spaces (font kerning can produce phantom spaces)
            text = "".join(c["text"] for c in row if c["text"] != " ").strip()
            # Extract only the P/O number pattern: e.g. DSAU-DM2272, DSNZ-TW0622
            match = re.search(r'DS[A-Z]{2}-[A-Z]{2}\d+', text)
            return match.group(0) if match else (text.split()[0] if text else None)
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

        # Only overlay if there is something to write
        if not text:
            continue

        c.setFillColorRGB(1, 1, 1)
        c.rect(DIVIDER_X + lw2, y0 + lw2,
               RIGHT_X - DIVIDER_X - BORDER_LW, ch - BORDER_LW, fill=1, stroke=0)

        if field == "comments":
            # Use Helvetica for comments — user-typed text may contain characters
            # not in the Grover font subset (e.g. X is never in Dynasty Sport PDFs)
            c.setFont("Helvetica", FONT_SIZE)
            c.setFillColorRGB(0.85, 0, 0)
            lines   = wrap_text(text, "Helvetica", FONT_SIZE, maxw, c)
            start_y = y1 - 4 - FONT_SIZE
            for i, line in enumerate(lines):
                ly = start_y - i * LINE_HEIGHT
                if ly >= y0 + 2:
                    c.drawString(TEXT_X, ly, line)
        else:
            c.setFillColorRGB(0, 0, 0)
            if field in ("po_number", "previous_ref", "date", "artist"):
                # Use Helvetica — Grover font subset may not contain all characters
                # needed for new P/O numbers (e.g. digits not in the source PDF)
                c.setFont("Helvetica", FONT_SIZE)
            else:
                c.setFont("Grover-Regular", FONT_SIZE)
            c.drawString(TEXT_X, y0 + (ch - FONT_SIZE) / 2 + 2, text)

        # Redraw only the VALUE cell border (right of divider) — never touch label column
        c.setStrokeColorRGB(0, 0, 0)
        c.setLineWidth(BORDER_LW)
        c.rect(DIVIDER_X, y0, RIGHT_X - DIVIDER_X, ch, fill=0, stroke=1)

    # Redraw the vertical divider line between label and value columns
    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(BORDER_LW)
    c.line(DIVIDER_X, divider_y0, DIVIDER_X, divider_y1)

    # Stock-only: free-floating comment below DATE row, centred, red, Helvetica
    stock_comment = vals.get("stock_comment", "").strip()
    if stock_comment:
        centre_x  = (DIVIDER_X + RIGHT_X) / 2          # 141.52
        text_y    = divider_y0 - 14                     # just below DATE cell bottom
        max_w     = RIGHT_X - DIVIDER_X - 4
        c.setFont("Helvetica", FONT_SIZE)
        c.setFillColorRGB(0.85, 0, 0)
        lines = wrap_text(stock_comment, "Helvetica", FONT_SIZE, max_w, c)
        for i, line in enumerate(lines):
            line_y = text_y - i * LINE_HEIGHT
            c.drawCentredString(centre_x, line_y, line)

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
            "dbx_ns", "og_namespace_id", "design_namespace_id", "graphic_type", "dropbox_saved"]:
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
        key="input_search_po",
    )
with s_col2:
    customer_letter = st.text_input(
        "Customer Letter",
        placeholder="e.g. F",
        max_chars=1,
        label_visibility="collapsed",
        help="First letter of the customer name (e.g. F for Five Star Removals)",
        key="input_customer_letter",
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
            st.session_state.source_po        = search_po.strip().upper()
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
            "P/O Number",
            placeholder="e.g. DSNZ-PL5475",
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

    # Defaults — overwritten below by the appropriate input widgets
    comments     = ""
    previous_ref = ""

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
    # Stock gets a free-text comment (written below DATE, no cell box, centred, red)
    if is_stock:
        col1, col2 = st.columns([1, 2])
        with col1:
            st.markdown("**Comments**")
            st.markdown(
                '<div class="comment-hint">Appears in red below DATE on PDF</div>',
                unsafe_allow_html=True,
            )
        with col2:
            default_comment = f"*REPEAT OF {st.session_state.source_po}" if st.session_state.source_po else ""
            comments = st.text_input(
                "Stock Comments",
                value=default_comment,
                label_visibility="collapsed",
            )
        previous_ref = ""


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
                        "po_number":    re.sub(r'\s*-\s*', '-', po_number.strip().upper()),
                        "artist":       artist.strip().upper(),
                        "date":         date_val,
                        # Custom: include previous_ref + comments in cells
                        # Stock: comments passed separately for free-float rendering
                        **({"previous_ref": previous_ref.strip().upper(),
                            "comments":     comments.strip().upper()}
                           if (st.session_state.graphic_type or "custom") == "custom"
                           else {"stock_comment": comments.strip().upper()}),
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
                        # Primary: save to the same folder as the source file
                        with st.spinner(f"Uploading **{fname}** to customer folder…"):
                            save_path = upload_new_file_to_dropbox(
                                dbx_upload,
                                st.session_state.source_folder,
                                fname,
                                result_bytes,
                                st.session_state.source_filename,
                            )

                        # Secondary: save archive copy to DESIGN/DROG/
                        drog_path  = None
                        drog_error = None
                        try:
                            dbx_design = get_design_ns(get_dropbox_client())
                            if dbx_design:
                                with st.spinner("Saving archive copy to Design/DROG/…"):
                                    drog_path = upload_new_file_to_dropbox(
                                        dbx_design,
                                        DROG_ARCHIVE_PATH,
                                        fname,
                                        result_bytes,
                                        st.session_state.source_filename,
                                    )
                            else:
                                drog_error = "DESIGN shared folder not found in Dropbox"
                        except ValueError as dve:
                            drog_error = str(dve)
                        except Exception as de:
                            drog_error = str(de)

                        st.session_state.result_pdf      = result_bytes
                        st.session_state.result_filename = fname
                        st.session_state.dropbox_saved   = True

                        pages = len(PdfReader(io.BytesIO(result_bytes)).pages)
                        drog_line = (
                            f"📁 Archive `Design/DROG/`: `{drog_path}`"
                            if drog_path
                            else f"⚠️ Archive copy skipped — {drog_error}"
                        )
                        st.success(
                            f"✓ **{fname}** saved to Dropbox successfully  \n"
                            f"📁 Customer folder: `{save_path}`  ·  "
                            f"{pages} page{'s' if pages > 1 else ''}  \n"
                            f"{drog_line}  \n"
                            f"🔒 Source file **{st.session_state.source_filename}** "
                            f"was not modified."
                        )

                except ValueError as ve:
                    # Safety guard triggered — clear message, no upload happened
                    st.error(f"🚫 Upload blocked — {ve}")
                except Exception as e:
                    st.error(f"Error: {e}")

    # ── Local download backup (only shown after successful Dropbox save) ───────
    if st.session_state.get("dropbox_saved") and st.session_state.result_pdf:
        st.divider()
        col_dl, col_new = st.columns([2, 1])
        with col_dl:
            st.download_button(
                label="⬇  DOWNLOAD",
                data=st.session_state.result_pdf,
                file_name=st.session_state.result_filename or "output.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        with col_new:
            if st.button("↩  Start Another", use_container_width=True):
                for key in ["source_pdf_bytes", "source_filename", "source_folder",
                            "source_po", "page_count", "result_pdf", "result_filename",
                            "dbx_ns", "og_namespace_id", "design_namespace_id",
                            "graphic_type", "dropbox_saved"]:
                    st.session_state[key] = None
                # Clear search fields by deleting their keys
                for k in ["input_search_po", "input_customer_letter"]:
                    if k in st.session_state:
                        del st.session_state[k]
                st.rerun()
