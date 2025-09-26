import io
import re
import streamlit as st
from docx import Document
from docx.oxml.text.paragraph import CT_P
from docx.oxml.table import CT_Tbl
from docx.text.paragraph import Paragraph
from docx.table import Table
from copy import deepcopy
import tiktoken
from openai import OpenAI
import os

# ---- UI ----
st.set_page_config(page_title="One-Minute Resume Tailor", page_icon="📝", layout="centered")
st.title("📝 One-Minute Resume Tailor")
st.caption("Upload your .docx resume + paste a JD → get an edited .docx that keeps your template. Export to PDF in Word/Google Docs.")

api_key = os.environ.get("OPENAI_API_KEY", "")
if not api_key:
    st.warning("Add your OPENAI_API_KEY in Streamlit Secrets before deploying.")
client = OpenAI(api_key=api_key) if api_key else None

resume_file = st.file_uploader("Upload your **.docx** resume (required)", type=["docx"])
jd_input = st.text_area("Paste the Job Description (required)", height=220, placeholder="Paste the JD here...")

# Standard system prompt you’ll reuse across roles (edit freely)
SYSTEM_PROMPT = """You tailor resumes to a specific job description while preserving structure and tone.
Rules:
- Keep the resume ONE PAGE in content length.
- Preserve section order and headings from the original (Summary, Experience, Projects, Education, Skills).
- Rewrite bullets to mirror JD responsibilities and keywords naturally (no keyword stuffing).
- Prefer concise, metric-led bullets: Action Verb + What + Impact (+ Tools).
- Keep formatting cues like bullet granularity (don’t turn paragraphs into walls of text).
- Do NOT invent employers, titles, or dates; tighten and rephrase only.
"""

def _iter_block_items(parent):
    """Yield paragraphs and tables in document order (preserves layout)."""
    if isinstance(parent, Document):
        parent_elm = parent.element.body
    else:
        parent_elm = parent._element
    for child in parent_elm.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            yield Table(child, parent)

def extract_text_structure(doc):
    """Lightly map the document into sections and bullets without destroying style."""
    lines = []
    for block in _iter_block_items(doc):
        if isinstance(block, Paragraph):
            txt = block.text.strip()
            if txt:
                lines.append(("p", txt))
        else:
            # Table: capture each cell text joined by " | " (keeps rough structure)
            for row in block.rows:
                row_txt = " | ".join([cell.text.strip() for cell in row.cells])
                if row_txt.strip():
                    lines.append(("t", row_txt))
    return lines

def count_tokens(txt):
    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(txt))

def call_llm(resume_text, jd_text):
    user_prompt = f"""
Here is the ORIGINAL RESUME content (text-only snapshot):
---
{resume_text}
---

Here is the JOB DESCRIPTION:
---
{jd_text}
---

Task: Return ONLY the revised resume TEXT (no extra commentary), keeping the same SECTION ORDER and roughly the same number of bullets per experience. Keep it to ONE PAGE worth of concise content.
"""
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role":"system","content": SYSTEM_PROMPT},
            {"role":"user","content": user_prompt}
        ],
        temperature=0.2
    )
    return resp.choices[0].message.content.strip()

def rewrite_doc_in_place(src_doc, revised_text):
    """
    Very safe strategy: replace paragraph-by-paragraph text while preserving styles.
    We walk through paragraphs/tables again and fill sequentially from revised_text lines.
    """
    # Split revised text into lines; keep empty lines for spacing hints
    new_lines = [ln.rstrip() for ln in revised_text.splitlines()]
    new_iter = iter(new_lines)

    def next_non_none():
        # Return next line; if we exhaust, return empty string so we don't crash
        try:
            return next(new_iter)
        except StopIteration:
            return ""

    # Rewalk and assign text lines to paragraphs and table cells in order
    for block in _iter_block_items(src_doc):
        if isinstance(block, Paragraph):
            # Assign next non-empty chunk to maintain density; allow empty lines to clear
            line = next_non_none()
            # Replace runs' text but keep run styles
            if block.runs:
                # Clear first run text, set; clear remaining
                block.runs[0].text = line
                for r in block.runs[1:]:
                    r.text = ""
            else:
                block.text = line
        else:
            # Table: fill each cell row-by-row using one line per cell if available
            for row in block.rows:
                for cell in row.cells:
                    line = next_non_none()
                    # Replace paragraph content in the first paragraph of each cell
                    if cell.paragraphs:
                        p = cell.paragraphs[0]
                        if p.runs:
                            p.runs[0].text = line
                            for r in p.runs[1:]:
                                r.text = ""
                        else:
                            p.text = line
    return src_doc

st.markdown("---")
btn = st.button("✨ Tailor my resume", type="primary", use_container_width=True)

if btn:
    if not (resume_file and jd_input and client):
        st.error("Please upload a .docx resume, paste a JD, and ensure the API key is set.")
        st.stop()

    # Load original doc
    try:
        src = Document(resume_file)
    except Exception as e:
        st.error(f"Could not read .docx. Make sure it is a valid Word file. Error: {e}")
        st.stop()

    # Extract snapshot text (for the model), preserving order
    snapshot_lines = extract_text_structure(src)
    snapshot_text = "\n".join([txt for kind, txt in snapshot_lines])

    # Guardrail: trim snapshot if extremely long
    max_chars = 12000
    if len(snapshot_text) > max_chars:
        snapshot_text = snapshot_text[:max_chars]

    with st.spinner("Rewriting bullets and aligning to JD..."):
        revised = call_llm(snapshot_text, jd_input)

    # Create a deep copy of the doc and rewrite text in place (keeps styles/templates)
    revised_doc = rewrite_doc_in_place(deepcopy(src), revised)

    # Offer download as .docx
    out_buf = io.BytesIO()
    revised_doc.save(out_buf)
    st.success("Done! Download your tailored resume:")
    st.download_button(
        label="⬇️ Download .docx",
        data=out_buf.getvalue(),
        file_name="Tailored_Resume.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        use_container_width=True
    )

    st.info("Tip: Open the .docx in Google Docs or Word → File → Download → PDF for a perfect PDF export.")
