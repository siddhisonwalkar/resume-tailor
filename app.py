import io, os
from copy import deepcopy
import streamlit as st
from docx import Document
from docx.oxml.text.paragraph import CT_P
from docx.oxml.table import CT_Tbl
from docx.text.paragraph import Paragraph
from docx.table import Table
import openai

st.set_page_config(page_title="One-Minute Resume Tailor", page_icon="📝", layout="centered")
st.title("📝 One-Minute Resume Tailor")
st.caption("Upload .docx resume + paste JD → get edited .docx that keeps your template. Export to PDF in Word/Google Docs.")

# --- Secrets ---
api_key = os.environ.get("OPENAI_API_KEY", "")
if not api_key:
    st.warning("Add OPENAI_API_KEY in Streamlit Secrets (TOML: OPENAI_API_KEY = \"sk-...\" ).")
openai.api_key = api_key

# --- Helpers to walk the doc without breaking styles ---
def _iter_block_items(parent):
    if isinstance(parent, Document):
        parent_elm = parent.element.body
    else:
        parent_elm = parent._element
    for child in parent_elm.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            yield Table(child, parent)

def extract_text_snapshot(doc):
    lines = []
    for block in _iter_block_items(doc):
        if isinstance(block, Paragraph):
            txt = block.text.strip()
            if txt:
                lines.append(txt)
        else:
            for row in block.rows:
                row_txt = " | ".join([cell.text.strip() for cell in row.cells])
                if row_txt.strip():
                    lines.append(row_txt)
    return "\n".join(lines)

SYSTEM_PROMPT = """You tailor resumes to a specific job description while preserving structure and tone.
Rules:
- Keep the resume ONE PAGE in content length.
- Preserve section order and headings from the original (Summary, Experience, Projects, Education, Skills).
- Rewrite bullets to mirror JD responsibilities and keywords naturally (no keyword stuffing).
- Prefer concise, metric-led bullets: Action Verb + What + Impact (+ Tools).
- Do NOT invent employers, titles, or dates; tighten and rephrase only.
"""

def call_llm(resume_text, jd_text):
    user_prompt = f"""
ORIGINAL RESUME (text-only snapshot):
---
{resume_text}
---

JOB DESCRIPTION:
---
{jd_text}
---

Task: Return ONLY the revised resume TEXT (no extra commentary), keeping the SAME SECTION ORDER and roughly the same number of bullets per experience. Keep it to ONE PAGE worth of concise content.
"""
    resp = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role":"system","content": SYSTEM_PROMPT},
            {"role":"user","content": user_prompt}
        ],
        temperature=0.2
    )
    return resp.choices[0].message.content.strip()

def rewrite_doc_in_place(src_doc, revised_text):
    new_lines = [ln.rstrip() for ln in revised_text.splitlines()]
    it = iter(new_lines)
    def next_line():
        try:
            return next(it)
        except StopIteration:
            return ""

    for block in _iter_block_items(src_doc):
        if isinstance(block, Paragraph):
            line = next_line()
            if block.runs:
                block.runs[0].text = line
                for r in block.runs[1:]:
                    r.text = ""
            else:
                block.text = line
        else:  # table
            for row in block.rows:
                for cell in row.cells:
                    line = next_line()
                    if cell.paragraphs:
                        p = cell.paragraphs[0]
                        if p.runs:
                            p.runs[0].text = line
                            for r in p.runs[1:]:
                                r.text = ""
                        else:
                            p.text = line
    return src_doc

# --- UI ---
resume_file = st.file_uploader("Upload your **.docx** resume", type=["docx"])
jd = st.text_area("Paste the Job Description", height=220, placeholder="Paste JD here...")

if st.button("✨ Tailor my resume", type="primary", use_container_width=True):
    if not (resume_file and jd and api_key):
        st.error("Please upload a .docx, paste a JD, and ensure the API key is set.")
        st.stop()

    try:
        src = Document(resume_file)
    except Exception as e:
        st.error(f"Could not read .docx. Ensure it is a valid Word file. Error: {e}")
        st.stop()

    snapshot = extract_text_snapshot(src)
    with st.spinner("Rewriting bullets and aligning to JD..."):
        revised_text = call_llm(snapshot, jd)

    revised_doc = rewrite_doc_in_place(deepcopy(src), revised_text)

    buf = io.BytesIO()
    revised_doc.save(buf)
    st.success("Done! Download your tailored resume:")
    st.download_button(
        "⬇️ Download .docx",
        data=buf.getvalue(),
        file_name="Tailored_Resume.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        use_container_width=True
    )
    st.info("Open the .docx in Google Docs or Word → File → Download → PDF for perfect export.")
