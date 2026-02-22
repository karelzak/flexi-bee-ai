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
    
    /* Schování Drag & Drop textu a zmenšení uploaderu na velikost tlačítka */
    [data-testid="stFileUploadDropzone"] {
        padding: 0px !important;
        border: none !important;
        background-color: transparent !important;
    }
    [data-testid="stFileUploadDropzone"] > div > span {
        display: none;
    }
    [data-testid="stFileUploadDropzone"] section {
        padding: 0px !important;
    }
    /* Stylizace tlačítka uvnitř uploaderu aby vypadalo jako standardní Streamlit button */
    [data-testid="stFileUploadDropzone"] button {
        width: 100%;
        margin: 0px !important;
    }
    /* Skrytí seznamu nahraných souborů pod uploaderem (máme svou tabulku) */
    [data-testid="stFileUploader"] section + div {
        display: none;
    }
    
    /* Červené tlačítko pro smazání všeho */
    .stButton > button.dangerous-button {
        color: white;
        background-color: #ff4b4b;
        border-color: #ff4b4b;
    }
    .stButton > button.dangerous-button:hover {
        background-color: #ff2b2b;
        border-color: #ff2b2b;
    }
    </style>
""", unsafe_allow_html=True)

# Initialize Session State
if "doc_manager" not in st.session_state:
    st.session_state.doc_manager = FlexiDocManager()
if "selected_doc_id" not in st.session_state:
    st.session_state.selected_doc_id = None
if "auto_analyzing" not in st.session_state:
    st.session_state.auto_analyzing = False
if "checking_anomalies" not in st.session_state:
    st.session_state.checking_anomalies = False
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0

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

st.sidebar.subheader("Automatizace")
auto_load = st.sidebar.checkbox("Automaticky načíst AI data", value=False)
auto_approve = st.sidebar.checkbox("Automaticky schválit", value=False)
auto_anomaly = st.sidebar.checkbox("Automaticky kontrolovat anomálie", value=False)

# Initialize OCR Engine
try:
    ocr_engine = GeminiOCREngine()
except ValueError as e:
    st.error(str(e))
    st.stop()

title_suffix = f" - {company_name}" if company_name and company_name != "moje_firma" else ""
st.title(f"📄 Převodník: Faktury {mode_key}{title_suffix}")

# 1. Upload & Scan Section
col_up1, col_up2 = st.columns([3, 1])
with col_up1:
    uploaded_files = st.file_uploader(
        "📂 Vybrat soubory (JPG, PNG, PDF)...", 
        type=["jpg", "jpeg", "png", "pdf"], 
        accept_multiple_files=True, 
        label_visibility="collapsed",
        key=f"uploader_{st.session_state.uploader_key}"
    )
    if uploaded_files:
        existing_names = [d.name for d in st.session_state.doc_manager.documents]
        new_docs_added = False
        for f in uploaded_files:
            if f.type == "application/pdf":
                pages = utils.pdf_to_images(f.name, f.getvalue())
                for p in pages:
                    if p['name'] not in existing_names:
                        doc = FlexiDoc(p['name'], p['content'], p['type'], mode_key)
                        st.session_state.doc_manager.add_document(doc)
                        new_docs_added = True
            else:
                if f.name not in existing_names:
                    doc = FlexiDoc(f.name, f.getvalue(), f.type, mode_key)
                    st.session_state.doc_manager.add_document(doc)
                    new_docs_added = True
        
        if new_docs_added and auto_load:
            st.session_state.auto_analyzing = True
            st.rerun()

with col_up2:
    c_scan1, c_scan2 = st.columns(2)
    if c_scan1.button("🖨️ Podavač", use_container_width=True, help="Skenovat z podavače (profil 'flexibee')"):
        utils.save_company_to_history(company_name)
        scanned = utils.run_naps2_scan(company_name, profile="flexibee")
        for s in scanned:
            doc = FlexiDoc(s['name'], s['content'], s['type'], mode_key)
            st.session_state.doc_manager.add_document(doc)
        if scanned:
            st.success(f"Naskenováno {len(scanned)} stran.")
            if auto_load:
                st.session_state.auto_analyzing = True
            st.rerun()
            
    if c_scan2.button("🖨️ Sklo", use_container_width=True, help="Skenovat ze skla (profil 'flexibee_glass')"):
        utils.save_company_to_history(company_name)
        scanned = utils.run_naps2_scan(company_name, profile="flexibee_glass")
        for s in scanned:
            doc = FlexiDoc(s['name'], s['content'], s['type'], mode_key)
            st.session_state.doc_manager.add_document(doc)
        if scanned:
            st.success(f"Naskenováno {len(scanned)} stran.")
            if auto_load:
                st.session_state.auto_analyzing = True
            st.rerun()

docs = st.session_state.doc_manager.documents

if docs:
    # 2. Document Table Section
    st.subheader("📋 Seznam dokumentů")
    
    # Automatické spuštění analýzy pokud je zapnuto a jsou nové dokumenty
    unprocessed_docs = [d for d in docs if not d.data]
    
    if st.session_state.auto_analyzing and not unprocessed_docs:
        st.session_state.auto_analyzing = False
        st.rerun()

    if auto_load and unprocessed_docs and not st.session_state.auto_analyzing:
        st.session_state.auto_analyzing = True
        st.rerun()

    # Progress bar / Status pro automatizaci
    if st.session_state.auto_analyzing:
        all_count = len(docs)
        processed_count = all_count - len(unprocessed_docs)
        if all_count > 0:
            progress = processed_count / all_count
            st.progress(progress, text=f"🤖 AI Analýza v průběhu: {processed_count} z {all_count} hotovo...")
    elif st.session_state.checking_anomalies:
        st.info("🔍 AI kontrola anomálií v průběhu, prosím čekejte...")
    
    # Background steps for automation
    if st.session_state.checking_anomalies:
        approved_docs = [d for d in docs if d.approved]
        if approved_docs:
            try:
                anomalies = ocr_engine.check_for_anomalies(approved_docs, mode_key)
                for res in anomalies:
                    doc = st.session_state.doc_manager.get_document(res.get("item_id"))
                    if doc: doc.anomaly = res.get("reason")
            except Exception as e:
                st.error(f"Chyba při kontrole anomálií: {e}")
        st.session_state.checking_anomalies = False
        st.rerun()

    # Prepare data for the table
    table_data = []
    for d in docs:
        status = "🆕 Nový"
        if d.approved: status = "✅ Schváleno"
        elif d.data: status = "🧪 Načteno AI"
        
        row = {
            "ID": d.id,
            "Stav": status,
            "Soubor": d.name,
            "Číslo": d.data.get("invoice_number", ""),
            "VS": d.data.get("variable_symbol", ""),
            "Vystaveno": d.data.get("issue_date", ""),
            "DUZP": d.data.get("vat_date", ""),
            "Splatnost": d.data.get("due_date", ""),
            "Partner": d.data.get("partner_name", ""),
            "IČO": d.data.get("partner_ico", ""),
            "Základ 0%": d.data.get("base_0", 0.0),
            "Zaokrouhl.": d.data.get("rounding", 0.0),
            "Základ celkem": d.data.get("total_base", 0.0),
            "DPH celkem": d.data.get("total_vat", 0.0),
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
    
    # Identifikovat sloupce, které obsahují pouze nuly (pro číselné typy)
    zero_cols = []
    numeric_check = ["Základ 0%", "Zaokrouhl.", "Základ celkem", "DPH celkem"]
    for col in numeric_check:
        if col in df.columns:
            vals = pd.to_numeric(df[col], errors='coerce').fillna(0)
            if (vals == 0).all():
                zero_cols.append(col)

    cols_to_show = ["Vybrat", "Stav", "Soubor", "Číslo", "VS", "Vystaveno", "DUZP", "Splatnost", "Partner", "IČO"]
    cols_to_show += [c for c in ["Základ 0%", "Zaokrouhl.", "Základ celkem", "DPH celkem"] if c not in zero_cols]
    cols_to_show += ["Částka", "Měna", "Anomálie"]
    
    edited_df = st.data_editor(
        df[cols_to_show],
        use_container_width=True,
        hide_index=True,
        key="doc_selector",
        column_config={
            "Vybrat": st.column_config.CheckboxColumn(" ", width="small"),
            "Stav": st.column_config.TextColumn("Stav", width="small"),
            "Soubor": st.column_config.TextColumn("Soubor", width="small"),
            "Anomálie": st.column_config.TextColumn("⚠️ Anomálie", width="small"),
            "Číslo": st.column_config.TextColumn("Číslo", width="medium"),
            "VS": st.column_config.TextColumn("VS", width="medium"),
            "Vystaveno": st.column_config.TextColumn("Vystaveno", width="small"),
            "DUZP": st.column_config.TextColumn("DUZP", width="small"),
            "Splatnost": st.column_config.TextColumn("Splatnost", width="small"),
            "Partner": st.column_config.TextColumn("Partner", width="medium"),
            "IČO": st.column_config.TextColumn("IČO", width="small"),
            "Základ 0%": st.column_config.NumberColumn(format="%.2f", width="small"),
            "Zaokrouhl.": st.column_config.NumberColumn(format="%.2f", width="small"),
            "Základ celkem": st.column_config.NumberColumn(format="%.2f", width="small"),
            "DPH celkem": st.column_config.NumberColumn(format="%.2f", width="small"),
            "Částka": st.column_config.NumberColumn("Celkem", format="%.2f", width="small"),
            "Měna": st.column_config.TextColumn("Měna", width="small"),
        },
        disabled=[c for c in cols_to_show if c != "Vybrat"]
    )
    
    # Summary anomálií
    anomalies_count = len([d for d in docs if d.anomaly])
    approved_count = len([d for d in docs if d.approved])
    if anomalies_count > 0:
        st.warning(f"⚠️ Nalezeno {anomalies_count} anomálií v datech! Zkontrolujte sloupec 'Anomálie' v tabulce.")
    elif approved_count > 0 and not st.session_state.checking_anomalies:
        st.success("✅ Žádné anomálie nenalezeny.")
    
    # Handle selection change
    if "doc_selector" in st.session_state:
        edits = st.session_state.doc_selector.get("edited_rows", {})
        if edits:
            row_idx = int(next(iter(edits.keys())))
            st.session_state.selected_doc_id = df.iloc[row_idx]["ID"]
            st.rerun()

    # Bulk actions under the table
    col_bulk1, col_bulk2, col_bulk3, col_bulk4, col_bulk5 = st.columns([1, 1, 1, 1, 1])
    unprocessed_docs = [d for d in docs if not d.data]
    with col_bulk1:
        if unprocessed_docs:
            if not st.session_state.auto_analyzing:
                if st.button(f"🤖 Načíst AI data ({len(unprocessed_docs)})", use_container_width=True):
                    st.session_state.auto_analyzing = True
                    st.rerun()
            else:
                if st.button("🛑 Zastavit načítání", use_container_width=True):
                    st.session_state.auto_analyzing = False
                    st.rerun()
    
    with col_bulk2:
        docs_with_data = [d for d in docs if d.data]
        if st.button(f"🧹 Smazat AI data ({len(docs_with_data)})", use_container_width=True, help="Smaže vytěžená AI data ze všech dokumentů v seznamu, ale dokumenty samotné ponechá."):
            for d in docs_with_data:
                d.clear_data()
            st.rerun()

    with col_bulk3:
        to_approve = [d for d in docs if d.data and not d.approved]
        if st.button(f"✅ Schválit vše ({len(to_approve)})", use_container_width=True, help="Označí všechny dokumenty s načtenými daty jako schválené."):
            for d in to_approve:
                d.approved = True
            if auto_anomaly:
                st.session_state.checking_anomalies = True
            st.rerun()

    with col_bulk4:
        if st.button("🔍 Kontrola anomálií", use_container_width=True):
            if any(d.approved for d in docs):
                st.session_state.checking_anomalies = True
                st.rerun()
            else:
                st.info("Nejprve schvalte nějaké faktury.")

    with col_bulk5:
        approved_docs = [d for d in docs if d.approved]
        if approved_docs:
            xml_data = st.session_state.doc_manager.to_xml(mode_key, include_attachments=include_images)
            utils.save_company_to_history(company_name)
            safe_prefix = "".join([c for c in company_name if c.isalnum() or c in (' ', '-', '_')]).strip().replace(' ', '_') or "flexibee"
            st.download_button(
                label=f"⬇️ XML export ({len(approved_docs)})",
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
            if auto_approve:
                doc.approved = True
                
                # Pokud po auto-schválení už nejsou žádné další dokumenty k analýze
                # a je zapnuta auto-anomálie, naplánujeme ji
                if len(unprocessed_docs) == 1 and auto_anomaly:
                    st.session_state.checking_anomalies = True
            
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
            
            c_del1, c_del2 = st.columns(2)
            if c_del1.button("🗑️ Odstranit dokument", type="secondary", use_container_width=True, help="Úplně odstraní dokument z tohoto seznamu."):
                st.session_state.doc_manager.remove_document(current_doc.id)
                st.session_state.selected_doc_id = None
                st.rerun()
            
            if current_doc.data:
                if c_del2.button("🧹 Smazat AI data", type="secondary", use_container_width=True, help="Smaže pouze vytěžená AI data, ale dokument v seznamu ponechá."):
                    current_doc.clear_data()
                    st.rerun()
        
        with col_form:
            if not current_doc.data:
                if st.button("Načíst AI data nyní", type="primary", use_container_width=True):
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
                    b0 = c1.number_input("Základ 0% (osvobozeno)", value=float(data.get("base_0", 0.0)))
                    round_val = c2.number_input("Zaokrouhlení", value=float(data.get("rounding", 0.0)))

                    c1, c2 = st.columns(2)
                    b12 = c1.number_input("Základ 12%", value=float(data.get("base_12", 0.0)))
                    v12 = c2.number_input("DPH 12%", value=float(data.get("vat_12", 0.0)))
                    
                    c1, c2 = st.columns(2)
                    b21 = c1.number_input("Základ 21%", value=float(data.get("base_21", 0.0)))
                    v21 = c2.number_input("DPH 21%", value=float(data.get("vat_21", 0.0)))
                    
                    c1, c2 = st.columns(2)
                    t_base = c1.number_input("Základ celkem", value=float(data.get("total_base", 0.0)))
                    t_vat = c2.number_input("DPH celkem", value=float(data.get("total_vat", 0.0)))

                    t_amt = st.number_input("Celkem s DPH", value=float(data.get("total_amount", 0.0)))

                    col_f1, col_f2 = st.columns(2)
                    if col_f1.form_submit_button("✅ Schválit a uložit", use_container_width=True):
                        new_data = data.copy()
                        new_data.update({
                            "invoice_number": inv_num, "variable_symbol": var_sym, "description": desc,
                            "issue_date": iss_date, "vat_date": vat_date, "due_date": due_date,
                            "partner_name": p_name, "partner_ico": p_ico, "partner_vat_id": p_dic,
                            "currency": curr, 
                            "base_0": b0, "rounding": round_val,
                            "base_12": b12, "vat_12": v12, "base_21": b21, "vat_21": v21,
                            "total_base": t_base, "total_vat": t_vat,
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
                            "currency": curr, 
                            "base_0": b0, "rounding": round_val,
                            "base_12": b12, "vat_12": v12, "base_21": b21, "vat_21": v21,
                            "total_base": t_base, "total_vat": t_vat,
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

# Globální akce na konci aplikace
if docs:
    st.divider()
    col_footer1, col_footer2, col_footer3 = st.columns([2, 1, 2])
    with col_footer2:
        if st.button(f"🗑️ Vymazat vše ({len(docs)})", use_container_width=True, type="primary", help="Úplně vyčistí seznam dokumentů (pracovní plochu)."):
            st.session_state.doc_manager.clear()
            st.session_state.selected_doc_id = None
            st.session_state.uploader_key += 1
            st.rerun()
