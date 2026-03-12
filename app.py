import io
import os
import tempfile
from datetime import date

import streamlit as st
from pypdf import PdfReader, PdfWriter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Dynasty Sport — CAD Updater",
    page_icon="⚡",
    layout="centered",
)

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  /* Import font */
  @import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@700;800&family=Barlow:wght@300;400&display=swap');

  html, body, [class*="css"] { font-family: 'Barlow', sans-serif; }

  /* Hide Streamlit default chrome */
  #MainMenu, footer, header { visibility: hidden; }

  /* Main container */
  .block-container { padding-top: 2rem; max-width: 640px; }

  /* Logo header */
  .ds-header {
    display: flex; align-items: center; gap: 16px; margin-bottom: 2rem;
  }
  .ds-logo-mark {
    width: 44px; height: 44px; background: #e02020; flex-shrink: 0;
    clip-path: polygon(0 0,100% 0,100% 70%,70% 100%,0 100%);
    display: flex; align-items: center; justify-content: center;
  }
  .ds-title {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 22px; font-weight: 800;
    letter-spacing: .06em; text-transform: uppercase; line-height: 1;
  }
  .ds-sub {
    font-size: 11px; color: #888;
    letter-spacing: .12em; text-transform: uppercase; margin-top: 3px;
  }

  /* Step labels */
  .step-label {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 11px; font-weight: 700;
    letter-spacing: .18em; text-transform: uppercase;
    color: #e02020; margin: 1.5rem 0 .5rem;
  }

  /* Auto tag on Previous Ref */
  .auto-note {
    font-size: 11px; color: #e02020;
    letter-spacing: .06em; margin-top: -12px; margin-bottom: 8px;
  }

  /* Comment hint */
  .comment-hint {
    font-size: 11px; color: #888; margin-top: -12px; margin-bottom: 8px;
  }

  /* Success box */
  .success-box {
    background: rgba(80,200,120,.08); border: 1px solid rgba(80,200,120,.3);
    border-radius: 4px; padding: 12px 16px; margin-top: 12px;
    font-size: 13px; color: #50c878;
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


# ── PDF constants ─────────────────────────────────────────────────────────────
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


# ── Helpers ───────────────────────────────────────────────────────────────────
def extract_grover_font(pdf_bytes: bytes) -> bytes | None:
    """Pull the Grover-Regular TrueType font out of any Dynasty Sport PDF."""
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


def extract_po_number(pdf_bytes: bytes) -> str | None:
    """Read the P/O NUMBER value from a Dynasty Sport CAD PDF."""
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            chars = pdf.pages[0].chars
            row = sorted(
                [c for c in chars if 75 < c["x0"] < 210 and 57 < c["top"] < 83],
                key=lambda c: c["x0"],
            )
            text = "".join(c["text"] for c in row).strip()
            return text.split(" ")[0] if " " in text else text or None
    except Exception:
        return None


def wrap_text(text: str, font_name: str, font_size: float,
              max_width: float, c) -> list[str]:
    """Word-wrap text to fit within max_width points."""
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


def make_overlay(font_path: str, vals: dict, pw: float, ph: float) -> io.BytesIO:
    """Build one overlay page with updated field values."""
    pkt = io.BytesIO()
    c = canvas.Canvas(pkt, pagesize=(pw, ph))
    lw2  = BORDER_LW / 2
    maxw = RIGHT_X - TEXT_X - 4

    for field, cell in CELLS.items():
        y0 = cell["rl_y0"]
        y1 = cell["rl_y1"]
        ch = y1 - y0
        text = vals.get(field, "")

        # White background over value column
        c.setFillColorRGB(1, 1, 1)
        c.rect(
            DIVIDER_X + lw2,
            y0 + lw2,
            RIGHT_X - DIVIDER_X - BORDER_LW,
            ch - BORDER_LW,
            fill=1, stroke=0,
        )

        # Text
        c.setFont("Grover-Regular", FONT_SIZE)
        if field == "comments":
            # Red, word-wrapped, top-aligned
            c.setFillColorRGB(0.85, 0, 0)
            lines  = wrap_text(text, "Grover-Regular", FONT_SIZE, maxw, c)
            start_y = y1 - 4 - FONT_SIZE
            for i, line in enumerate(lines):
                ly = start_y - i * LINE_HEIGHT
                if ly >= y0 + 2:
                    c.drawString(TEXT_X, ly, line)
        else:
            # Black, single line, vertically centred
            c.setFillColorRGB(0, 0, 0)
            c.drawString(TEXT_X, y0 + (ch - FONT_SIZE) / 2 + 2, text)

        # Black border
        c.setStrokeColorRGB(0, 0, 0)
        c.setLineWidth(BORDER_LW)
        c.rect(0.307, y0, RIGHT_X - 0.307, ch, fill=0, stroke=1)

    # Vertical divider
    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(BORDER_LW)
    c.line(DIVIDER_X, PAGE_HEIGHT - 321.223, DIVIDER_X, PAGE_HEIGHT - 57.310)

    c.save()
    pkt.seek(0)
    return pkt


def process_pdf(pdf_bytes: bytes, vals: dict) -> bytes:
    """Apply updates to every page and return the finished PDF bytes."""
    font_data = extract_grover_font(pdf_bytes)
    if not font_data:
        raise ValueError(
            "Could not find Grover-Regular font in this PDF. "
            "Please make sure it is a Dynasty Sport Order Graphic."
        )

    tmp = tempfile.NamedTemporaryFile(suffix=".ttf", delete=False)
    tmp.write(font_data)
    tmp.close()

    try:
        try:
            pdfmetrics.registerFont(TTFont("Grover-Regular", tmp.name))
        except Exception:
            pass  # already registered

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


# ── UI ────────────────────────────────────────────────────────────────────────

# Step 1 — Upload
st.markdown('<div class="step-label">01 — Upload Source PDF</div>', unsafe_allow_html=True)

uploaded = st.file_uploader(
    "Drop a Dynasty Sport Order Graphic PDF",
    type="pdf",
    label_visibility="collapsed",
)

# Auto-extract P/O number when file is uploaded
source_po = None
if uploaded:
    pdf_bytes = uploaded.read()
    uploaded.seek(0)
    source_po = extract_po_number(pdf_bytes)
    page_count = len(PdfReader(io.BytesIO(pdf_bytes)).pages)
    if source_po:
        st.success(f"✓  **{uploaded.name}** — {page_count} page{'s' if page_count > 1 else ''}  |  P/O detected: **{source_po}**")
    else:
        st.warning(f"Uploaded **{uploaded.name}** ({page_count} pages) — P/O Number not detected, enter Previous Ref manually.")

# Step 2 — Fields
st.markdown('<div class="step-label">02 — Update Fields</div>', unsafe_allow_html=True)

col1, col2 = st.columns([1, 2])

with col1:
    st.markdown("**P/O Number**")
with col2:
    po_number = st.text_input("P/O Number", placeholder="e.g. DSNZ-PL5475",
                               label_visibility="collapsed")

with col1:
    st.markdown("**Artist**")
with col2:
    artist = st.text_input("Artist", placeholder="e.g. SANA",
                            label_visibility="collapsed")

with col1:
    st.markdown("**Date**")
with col2:
    today = date.today().strftime("%d/%m/%Y")
    date_val = st.text_input("Date", value=today, label_visibility="collapsed")

st.divider()

with col1:
    st.markdown("**Previous Ref**")
with col2:
    previous_ref = st.text_input(
        "Previous Ref",
        value=source_po or "",
        label_visibility="collapsed",
        help="Auto-filled from the uploaded PDF's P/O Number",
    )
st.markdown(
    '<div class="auto-note">⚡ Auto-filled from source P/O Number</div>',
    unsafe_allow_html=True,
)

with col1:
    st.markdown("**Comments**")
with col2:
    comments = st.text_input("Comments", placeholder="e.g. *REPEAT OF DSNZ-PL5474",
                              label_visibility="collapsed")
st.markdown(
    '<div class="comment-hint">Comments will appear in red text on the PDF</div>',
    unsafe_allow_html=True,
)

# Step 3 — Generate
st.markdown('<div class="step-label">03 — Generate</div>', unsafe_allow_html=True)

generate = st.button(
    "⬇  Generate & Download PDF",
    disabled=not uploaded,
    use_container_width=True,
    type="primary",
)

if generate:
    if not po_number.strip():
        st.error("Please enter a P/O Number before generating.")
    else:
        with st.spinner("Processing PDF…"):
            try:
                uploaded.seek(0)
                pdf_bytes = uploaded.read()

                vals = {
                    "po_number":    po_number.strip().upper(),
                    "artist":       artist.strip().upper(),
                    "date":         date_val.strip(),
                    "previous_ref": previous_ref.strip().upper(),
                    "comments":     comments.strip().upper(),
                }

                result = process_pdf(pdf_bytes, vals)

                safe_po  = po_number.strip().replace(" ", "_")
                filename = f"{safe_po}_ORDER_GRAPHIC.pdf"

                st.download_button(
                    label="⬇  Click here to save your PDF",
                    data=result,
                    file_name=filename,
                    mime="application/pdf",
                    use_container_width=True,
                )
                pages = len(PdfReader(io.BytesIO(result)).pages)
                st.markdown(
                    f'<div class="success-box">✓ Ready — <strong>{filename}</strong> &nbsp;·&nbsp; {pages} page{"s" if pages > 1 else ""}</div>',
                    unsafe_allow_html=True,
                )

            except Exception as e:
                st.error(f"Error processing PDF: {e}")
