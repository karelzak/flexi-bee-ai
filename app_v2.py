import streamlit as st
import os
import io
import pandas as pd
from datetime import datetime
from PIL import Image
from dotenv import load_dotenv

# Import our new modules
from models import FlexiDoc, FlexiDocManager
from ocr_engine import GeminiOCREngine
import utils

# Load environment variables
load_dotenv()

# Streamlit Configuration
st.set_page_config(page_title="FlexiBee AI OCR v2", layout="wide")

# Custom CSS for compact UI
st.markdown("""
    <style>
    .stMainBlockContainer { padding-top: 1.5rem !important; }
    .stForm { padding: 0.5rem !important; margin-bottom: 0.5rem !important; }
    hr { margin: 0.5rem 0 !important; }
    div[data-testid="stExpander"] { border: 1px solid #ddd; border-radius: 5px; }
    </style>
""", unsafe_allow_html=True)

# Initialize Session State
if "doc_manager" not in st.session_state:
    st.session_state.doc_manager = FlexiDocManager()
if "selected_doc_id" not in st.session_state:
    st.session_state.selected_doc_id = None
if "auto_analyzing" not in st.session_state:
    st.session_state.auto_analyzing = False

# Sidebar for Settings
st.sidebar.title("Nastavení")

# Company History
history = utils.load_company_history()
default_company = history[0] if history else "moje_firma"
if history:
    selected_history = st.sidebar.selectbox("Historie firem:", options=["-- vybrat z historie --"] + history)
    if selected_history != "-- vybrat z historie --":
        default_company = selected_history

company_name = st.sidebar.text_input("Název firmy:", value=default_company)

invoice_mode_label = st.sidebar.radio(
    "Typ faktur:",
    ("Přijaté (od dodavatelů)", "Vydané (odběratelům)"),
    index=0
)
mode_key = "prijata" if "Přijaté" in invoice_mode_label else "vydana"
partner_ui_label = "Dodavatel" if mode_key == "prijata" else "Odběratel"

st.sidebar.subheader("Export")
include_images = st.sidebar.checkbox("Přikládat obrazy do XML", value=True)

# Initialize OCR Engine
try:
    ocr_engine = GeminiOCREngine()
except ValueError as e:
    st.error(str(e))
    st.stop()

st.title(f"📄 Převodník: Faktury {mode_key}")

# 1. Upload & Scan Section
col_up1, col_up2, col_up3 = st.columns([2, 1, 1])
with col_up1:
    uploaded_files = st.file_uploader("Nahrajte JPG, PNG, PDF", type=["jpg", "jpeg", "png", "pdf"], accept_multiple_files=True, label_visibility="collapsed")
    if uploaded_files:
        existing_names = [d.name for d in st.session_state.doc_manager.documents]
        for f in uploaded_files:
            if f.type == "application/pdf":
                pages = utils.pdf_to_images(f.name, f.getvalue())
                for p in pages:
                    if p['name'] not in existing_names:
                        doc = FlexiDoc(p['name'], p['content'], p['type'], mode_key)
                        st.session_state.doc_manager.add_document(doc)
            else:
                if f.name not in existing_names:
                    doc = FlexiDoc(f.name, f.getvalue(), f.type, mode_key)
                    st.session_state.doc_manager.add_document(doc)

with col_up2:
    if st.button("🖨️ Skenovat z podavače", use_container_width=True):
        utils.save_company_to_history(company_name)
        scanned = utils.run_naps2_scan(company_name)
        for s in scanned:
            doc = FlexiDoc(s['name'], s['content'], s['type'], mode_key)
            st.session_state.doc_manager.add_document(doc)
        if scanned:
            st.success(f"Naskenováno {len(scanned)} stran.")
            st.rerun()

with col_up3:
    if st.button("🗑️ Vymazat vše", use_container_width=True):
        st.session_state.doc_manager.clear()
        st.session_state.selected_doc_id = None
        st.rerun()

docs = st.session_state.doc_manager.documents

if docs:
    # 2. Document Table Section
    st.subheader("📋 Seznam dokumentů")
    
    # Prepare data for the table
    table_data = []
    for d in docs:
        status = "🆕 Nový"
        if d.approved: status = "✅ Schváleno"
        elif d.data: status = "🧪 Analyzováno"
        
        row = {
            "ID": d.id,
            "Stav": status,
            "Soubor": d.name,
            "Číslo": d.data.get("invoice_number", ""),
            "Partner": d.data.get("partner_name", ""),
            "Částka": d.data.get("total_amount", 0.0),
            "Měna": d.data.get("currency", ""),
            "Anomálie": d.anomaly or ""
        }
        table_data.append(row)
    
    df = pd.DataFrame(table_data)
    
    # Selection logic using data_editor with a checkbox
    if st.session_state.selected_doc_id is None:
        st.session_state.selected_doc_id = docs[0].id
    
    df['Vybrat'] = df['ID'] == st.session_state.selected_doc_id
    
    cols_to_show = ["Vybrat", "Stav", "Soubor", "Číslo", "Partner", "Částka", "Měna", "Anomálie"]
    
    edited_df = st.data_editor(
        df[cols_to_show],
        use_container_width=True,
        hide_index=True,
        key="doc_selector",
        column_config={
            "Vybrat": st.column_config.CheckboxColumn(" ", width="small"),
            "Anomálie": st.column_config.TextColumn("⚠️ Anomálie", width="medium"),
        },
        disabled=[c for c in cols_to_show if c != "Vybrat"]
    )
    
    # Handle selection change
    if "doc_selector" in st.session_state:
        edits = st.session_state.doc_selector.get("edited_rows", {})
        if edits:
            row_idx = int(next(iter(edits.keys())))
            st.session_state.selected_doc_id = df.iloc[row_idx]["ID"]
            st.rerun()

    # Bulk actions under the table
    col_bulk1, col_bulk2, col_bulk3 = st.columns([1, 1, 1])
    unprocessed_docs = [d for d in docs if not d.data]
    with col_bulk1:
        if unprocessed_docs:
            if not st.session_state.auto_analyzing:
                if st.button(f"🤖 Hromadná analýza ({len(unprocessed_docs)})", use_container_width=True):
                    st.session_state.auto_analyzing = True
                    st.rerun()
            else:
                if st.button("🛑 Zastavit analýzu", use_container_width=True):
                    st.session_state.auto_analyzing = False
                    st.rerun()
    
    with col_bulk2:
        if st.button("🔍 Kontrola anomálií", use_container_width=True):
            approved_docs = [d for d in docs if d.approved]
            if approved_docs:
                with st.spinner("Hledám anomálie..."):
                    anomalies = ocr_engine.check_for_anomalies(approved_docs, mode_key)
                    for res in anomalies:
                        doc = st.session_state.doc_manager.get_document(res.get("item_id"))
                        if doc: doc.anomaly = res.get("reason")
                    st.rerun()
            else:
                st.info("Nejprve schvalte nějaké faktury.")

    with col_bulk3:
        approved_docs = [d for d in docs if d.approved]
        if approved_docs:
            xml_data = st.session_state.doc_manager.to_xml(mode_key, include_attachments=include_images)
            utils.save_company_to_history(company_name)
            safe_prefix = "".join([c for c in company_name if c.isalnum() or c in (' ', '-', '_')]).strip().replace(' ', '_') or "flexibee"
            st.download_button(
                label=f"⬇️ Exportovat {len(approved_docs)} faktur do XML",
                data=xml_data,
                file_name=f"{safe_prefix}_{mode_key}_{datetime.now().strftime('%Y%m%d_%H%M')}.xml",
                mime="application/xml",
                use_container_width=True
            )

    # 3. Auto-analysis background step
    if st.session_state.auto_analyzing and unprocessed_docs:
        doc = unprocessed_docs[0]
        try:
            doc.run_ocr(ocr_engine, mode_key)
            st.rerun()
        except Exception as e:
            st.error(f"Chyba u {doc.name}: {e}")
            st.session_state.auto_analyzing = False

    st.divider()

    # 4. Editor Section
    current_doc = st.session_state.doc_manager.get_document(st.session_state.selected_doc_id)
    if current_doc:
        col_img, col_form = st.columns([1, 1])
        with col_img:
            image = Image.open(io.BytesIO(current_doc.content))
            st.image(image, caption=current_doc.name, use_container_width=True)
            if st.button("🗑️ Odstranit dokument", type="secondary"):
                st.session_state.doc_manager.remove_document(current_doc.id)
                st.session_state.selected_doc_id = None
                st.rerun()
        
        with col_form:
            if not current_doc.data:
                if st.button("Analyzovat nyní", type="primary", use_container_width=True):
                    with st.spinner("Gemini pracuje..."):
                        current_doc.run_ocr(ocr_engine, mode_key)
                        st.rerun()
            else:
                data = current_doc.data
                st.subheader("Editace dat")
                with st.form(key=f"form_{current_doc.id}"):
                    c1, c2 = st.columns(2)
                    inv_num = c1.text_input("Číslo faktury", data.get("invoice_number"))
                    iss_date = c2.text_input("Datum vystavení", data.get("issue_date"))
                    
                    c1, c2 = st.columns(2)
                    var_sym = c1.text_input("Variabilní symbol", data.get("variable_symbol"))
                    vat_date = c2.text_input("DUZP", data.get("vat_date"))
                    
                    c1, c2 = st.columns(2)
                    due_date = c1.text_input("Splatnost", data.get("due_date"))
                    desc = c2.text_input("Popis", data.get("description", ""), max_chars=50)

                    c1, c2 = st.columns(2)
                    p_name = c1.text_input(partner_ui_label, data.get("partner_name"))
                    p_ico = c2.text_input("IČO", data.get("partner_ico"))
                    
                    c1, c2 = st.columns(2)
                    p_dic = c1.text_input("DIČ", data.get("partner_vat_id"))
                    curr = c2.text_input("Měna", data.get("currency"))
                    
                    st.divider()
                    
                    c1, c2 = st.columns(2)
                    b12 = c1.number_input("Základ 12%", value=float(data.get("base_12", 0.0)))
                    v12 = c2.number_input("DPH 12%", value=float(data.get("vat_12", 0.0)))
                    
                    c1, c2 = st.columns(2)
                    b21 = c1.number_input("Základ 21%", value=float(data.get("base_21", 0.0)))
                    v21 = c2.number_input("DPH 21%", value=float(data.get("vat_21", 0.0)))
                    
                    t_amt = st.number_input("Celkem s DPH", value=float(data.get("total_amount", 0.0)))

                    col_f1, col_f2 = st.columns(2)
                    if col_f1.form_submit_button("✅ Schválit a uložit", use_container_width=True):
                        new_data = data.copy()
                        new_data.update({
                            "invoice_number": inv_num, "variable_symbol": var_sym, "description": desc,
                            "issue_date": iss_date, "vat_date": vat_date, "due_date": due_date,
                            "partner_name": p_name, "partner_ico": p_ico, "partner_vat_id": p_dic,
                            "currency": curr, "base_12": b12, "vat_12": v12, "base_21": b21, "vat_21": v21,
                            "total_amount": t_amt
                        })
                        current_doc.set_data(new_data)
                        current_doc.approved = True
                        st.rerun()
                    
                    if col_f2.form_submit_button("⏩ Schválit a další", use_container_width=True):
                        # Logic to find next unapproved doc
                        idx = -1
                        for i, d in enumerate(docs):
                            if d.id == current_doc.id:
                                idx = i
                                break
                        # Save current
                        new_data = data.copy()
                        new_data.update({
                            "invoice_number": inv_num, "variable_symbol": var_sym, "description": desc,
                            "issue_date": iss_date, "vat_date": vat_date, "due_date": due_date,
                            "partner_name": p_name, "partner_ico": p_ico, "partner_vat_id": p_dic,
                            "currency": curr, "base_12": b12, "vat_12": v12, "base_21": b21, "vat_21": v21,
                            "total_amount": t_amt
                        })
                        current_doc.set_data(new_data)
                        current_doc.approved = True
                        
                        # Find next
                        if idx != -1 and idx < len(docs) - 1:
                            st.session_state.selected_doc_id = docs[idx+1].id
                        st.rerun()
else:
    st.info("Nahrajte nebo naskenujte faktury pro zahájení zpracování.")
