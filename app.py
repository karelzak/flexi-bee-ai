import streamlit as st
from google import genai
from PIL import Image
import json
import os
import base64
from datetime import datetime
import xml.etree.ElementTree as ET
from dotenv import load_dotenv
import io
import pandas as pd

# Načtení proměnných prostředí
load_dotenv()

# Konfigurace Gemini API
API_KEY = os.getenv("GOOGLE_API_KEY")
if API_KEY:
    client = genai.Client(api_key=API_KEY)

def extract_invoice_data(image, mode):
    """Použije Gemini k extrakci strukturovaných dat z obrázku faktury."""
    partner_label = "supplier" if mode == "prijata" else "customer"
    
    prompt = f"""
    Extract the following information from this invoice image:
    - invoice_number (string)
    - variable_symbol (string)
    - issue_date (YYYY-MM-DD)
    - due_date (YYYY-MM-DD)
    - partner_name (string - the name of the {partner_label})
    - partner_ico (string - the IČO/Registration number of the {partner_label})
    - partner_vat_id (string - the DIČ/VAT ID of the {partner_label})
    - base_0 (number - tax exempt amount)
    - rounding (number - rounding amount)
    - base_12 (number - tax base for 12% VAT rate)
    - vat_12 (number - VAT amount for 12% VAT rate)
    - base_21 (number - tax base for 21% VAT rate)
    - vat_21 (number - VAT amount for 21% VAT rate)
    - total_base (number - sum of all tax bases)
    - total_vat (number - sum of all VAT amounts)
    - total_amount (number - total including VAT)
    - currency (string, ISO code e.g., CZK, EUR)

    If a value is not found, return 0 for numeric fields and null for strings.
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt, image],
            config={'response_mime_type': 'application/json'}
        )
        return json.loads(response.text)
    except Exception as e:
        st.error(f"Chyba při komunikaci s Gemini: {e}")
        return None

def generate_flexibee_xml(invoices_list, mode):
    """Převede seznam ověřených faktur do formátu Abra FlexiBee XML s hezkým formátováním."""
    from xml.dom import minidom
    
    root = ET.Element("winstrom", version="1.0")
    tag_name = "faktura-prijata" if mode == "prijata" else "faktura-vydana"
    
    for data in invoices_list:
        invoice = ET.SubElement(root, tag_name)
        
        if mode == "prijata":
            # cisDosle je číslo na papíře od dodavatele, fallback na variabilní symbol pokud chybí
            inv_num = data.get("invoice_number") or data.get("variable_symbol", "")
            ET.SubElement(invoice, "cisDosle").text = str(inv_num)
            # U přijatých neposíláme 'kod', aby FlexiBee přidělilo vlastní interní číslo
        else:
            # U vydaných se 'kod' často shoduje s číslem faktury
            ET.SubElement(invoice, "kod").text = str(data.get("invoice_number", ""))
            
        ET.SubElement(invoice, "varSym").text = str(data.get("variable_symbol", ""))
        ET.SubElement(invoice, "datVyst").text = str(data.get("issue_date", ""))
        ET.SubElement(invoice, "duzpPuv").text = str(data.get("issue_date", ""))
        ET.SubElement(invoice, "datSplat").text = str(data.get("due_date", ""))
        
        # Identifikace partnera (FlexiBee dohledá podle IČ/DIČ v adresáři)
        if data.get("partner_name"):
            ET.SubElement(invoice, "nazFirmy").text = str(data['partner_name'])

        if data.get("partner_ico"):
            ET.SubElement(invoice, "ic").text = str(data['partner_ico'])
        
        if data.get("partner_vat_id"):
            ET.SubElement(invoice, "dic").text = str(data['partner_vat_id'])
        
        if not data.get("partner_ico") and not data.get("partner_vat_id"):
            ET.SubElement(invoice, "popis").text = f"Partner: {data.get('partner_name', 'Neznámý')}"
         
        # Tax Exempt + Rounding
        base_0 = float(data.get("base_0", 0.0)) if data.get("base_0") else 0.0
        rounding = float(data.get("rounding", 0.0)) if data.get("rounding") else 0.0
        ET.SubElement(invoice, "sumOsv").text = str(base_0 + rounding)

        # 12% VAT
        celkem = float(data.get("base_12", 0.0)) if data.get("base_12") else 0.0
        celkem += float(data.get("vat_12", 0.0)) if data.get("vat_12") else 0.0
        ET.SubElement(invoice, "sumZklSniz").text = str(data.get("base_12", 0.0)) if data.get("base_12") else "0.0" 
        ET.SubElement(invoice, "sumDphSniz").text = str(data.get("vat_12", 0.0)) if data.get("vat_12") else "0.0" 
        ET.SubElement(invoice, "sumCelkSniz").text = str(celkem)
    
        # 21% VAT
        celkem = float(data.get("base_21", 0.0)) if data.get("base_21") else 0.0
        celkem += float(data.get("vat_21", 0.0)) if data.get("vat_21") else 0.0
        ET.SubElement(invoice, "sumZklZakl").text = str(data.get("base_21", 0.0)) if data.get("base_21") else "0.0" 
        ET.SubElement(invoice, "sumDphZakl").text = str(data.get("vat_21", 0.0)) if data.get("vat_21") else "0.0" 
        ET.SubElement(invoice, "sumCelkZakl").text = str(celkem)
          
        # Totals
        ET.SubElement(invoice, "sumZklCelkem").text = str(data.get("total_base", "0"))
        ET.SubElement(invoice, "sumDphCelkem").text = str(data.get("total_vat", "0"))
        ET.SubElement(invoice, "sumCelkem").text = str(data.get("total_amount", "0"))
        
        ET.SubElement(invoice, "mena").text = f"code:{data.get('currency', 'CZK')}"
        
        # Typ dokladu musí odpovídat kódu v FlexiBee (FAKTURA je nejvhodnější výchozí)
        ET.SubElement(invoice, "typDokl").text = "code:FAKTURA"

        # Přiložení originálního obrazu faktury
        if data.get("image_b64"):
            attachments = ET.SubElement(invoice, "prilohy")
            attachment = ET.SubElement(attachments, "priloha")
            ET.SubElement(attachment, "nazSoub").text = str(data.get("image_filename", "faktura.jpg"))
            ET.SubElement(attachment, "contentType").text = str(data.get("image_mimetype", "image/jpeg"))
            content = ET.SubElement(attachment, "content")
            content.set("encoding", "base64")
            content.text = data.get("image_b64")

        # Povinne polozky
        ET.SubElement(invoice, "bezPolozek").text = "true"
        ET.SubElement(invoice, "szbDphSniz").text = "12.0"
        ET.SubElement(invoice, "szbDphZakl").text = "21.0"
    
    # Převod na řetězec a formátování pomocí minidom
    xml_str = ET.tostring(root, encoding='utf-8')
    pretty_xml_str = minidom.parseString(xml_str).toprettyxml(indent="  ")
    
    # Navrácení jako bytes pro download_button
    return pretty_xml_str.encode('utf-8')

# Streamlit UI
st.set_page_config(page_title="Převod faktur do FlexiBee", layout="wide")

# Sidebar pro nastavení
st.sidebar.title("Nastavení")
invoice_mode = st.sidebar.radio(
    "Typ zpracovávaných faktur:",
    ("Přijaté (od dodavatelů)", "Vydané (odběratelům)"),
    index=0
)
mode_key = "prijata" if "Přijaté" in invoice_mode else "vydana"
partner_ui_label = "Dodavatel" if mode_key == "prijata" else "Odběratel/Zákazník"

st.title(f"📄 Převodník: Faktury {invoice_mode.split(' ')[0].lower()}")

if not API_KEY:
    st.warning("Prosím, nastavte GOOGLE_API_KEY v souboru .env.")
    st.stop()

# Inicializace stavu
if "processed_invoices" not in st.session_state:
    st.session_state.processed_invoices = []
if "current_file_idx" not in st.session_state:
    st.session_state.current_file_idx = 0
if "extraction_cache" not in st.session_state:
    st.session_state.extraction_cache = {}
if "approved_files" not in st.session_state:
    st.session_state.approved_files = set()
if "auto_analyzing" not in st.session_state:
    st.session_state.auto_analyzing = False

# Vymazat seznam při změně režimu
if "last_mode" in st.session_state and st.session_state.last_mode != mode_key:
    st.session_state.processed_invoices = []
    st.session_state.extraction_cache = {}
    st.session_state.approved_files = set()
    st.session_state.auto_analyzing = False
    st.session_state.current_file_idx = 0
st.session_state.last_mode = mode_key

uploaded_files = st.file_uploader(f"Nahrajte {invoice_mode.lower()} (JPG, PNG)", type=["jpg", "jpeg", "png"], accept_multiple_files=True)

if uploaded_files:
    if "last_files_count" not in st.session_state or st.session_state.last_files_count != len(uploaded_files):
        st.session_state.current_file_idx = 0
        st.session_state.last_files_count = len(uploaded_files)

    # Hromadná analýza - ovládání
    unprocessed_files = [f for f in uploaded_files if (f.name + str(f.size) + mode_key) not in st.session_state.extraction_cache]
    
    if unprocessed_files:
        col_auto1, col_auto2 = st.columns([1, 3])
        if not st.session_state.auto_analyzing:
            if col_auto1.button(f"🤖 Hromadná analýza ({len(unprocessed_files)})", use_container_width=True):
                st.session_state.auto_analyzing = True
                st.rerun()
        else:
            if col_auto1.button("🛑 Zastavit", use_container_width=True):
                st.session_state.auto_analyzing = False
                st.rerun()
            
            # Provedení jednoho kroku analýzy
            f = unprocessed_files[0]
            f_id = f.name + str(f.size) + mode_key
            idx_in_all = uploaded_files.index(f)
            
            with st.spinner(f"Analyzuji: {f.name} ({idx_in_all + 1}/{len(uploaded_files)})..."):
                image_to_analyze = Image.open(f)
                data = extract_invoice_data(image_to_analyze, mode_key)
                if data:
                    # Uložíme i metadata a data obrázku pro pozdější export
                    f.seek(0)
                    img_bytes = f.read()
                    data["image_b64"] = base64.b64encode(img_bytes).decode('utf-8')
                    data["image_filename"] = f.name
                    data["image_mimetype"] = f.type
                    st.session_state.extraction_cache[f_id] = data
                st.rerun()
    elif st.session_state.auto_analyzing:
        st.session_state.auto_analyzing = False
        st.success("Všechny soubory byly analyzovány.")

    # Přehled stavu souborů (dvou-sloupcový seznam)
    with st.expander("📊 Přehled zpracování", expanded=True):
        c1, c2 = st.columns(2)
        for idx, f in enumerate(uploaded_files):
            f_id = f.name + str(f.size) + mode_key
            
            # Ikony stavu
            analyzed_icon = "🧪" if f_id in st.session_state.extraction_cache else "⚪"
            approved_icon = "✅" if f_id in st.session_state.approved_files else "⚪"
            current_marker = " 📍" if idx == st.session_state.current_file_idx else ""
            
            status_text = f"{analyzed_icon} {approved_icon} {f.name}{current_marker}"
            
            target_col = c1 if idx % 2 == 0 else c2
            target_col.write(status_text)

    # Navigační lišta pod přehledem
    col_nav1, col_nav2, col_nav3 = st.columns([1, 4, 1])
    with col_nav1:
        if st.button("⬅️ Předchozí", use_container_width=True) and st.session_state.current_file_idx > 0:
            st.session_state.current_file_idx -= 1
            st.rerun()
    with col_nav2:
        st.markdown(f"<p style='text-align: center; font-size: 1.2rem; font-weight: bold; margin-top: 5px;'>Soubor {st.session_state.current_file_idx + 1} z {len(uploaded_files)}</p>", unsafe_allow_html=True)
    with col_nav3:
        if st.button("Další ➡️", use_container_width=True) and st.session_state.current_file_idx < len(uploaded_files) - 1:
            st.session_state.current_file_idx += 1
            st.rerun()

    st.divider()
    current_file = uploaded_files[st.session_state.current_file_idx]
    image = Image.open(current_file)
    
    col_img, col_form = st.columns(2)
    with col_img:
        st.image(image, caption=current_file.name, use_container_width=True)
    
    with col_form:
        file_id = current_file.name + str(current_file.size) + mode_key
        if file_id not in st.session_state.extraction_cache:
            if st.button("Analyzovat soubor"):
                with st.spinner("Gemini analyzuje..."):
                    data = extract_invoice_data(image, mode_key)
                    if data:
                        # Uložíme i metadata a data obrázku
                        current_file.seek(0)
                        img_bytes = current_file.read()
                        data["image_b64"] = base64.b64encode(img_bytes).decode('utf-8')
                        data["image_filename"] = current_file.name
                        data["image_mimetype"] = current_file.type
                        st.session_state.extraction_cache[file_id] = data
                        st.rerun()
        
        if file_id in st.session_state.extraction_cache:
            data = st.session_state.extraction_cache[file_id]
            st.subheader(f"Ověření dat ({invoice_mode.split(' ')[0]})")
            with st.form(key=f"form_{file_id}"):
                # ... (rest of the form stays the same)
                # ...
                # (I will keep the rest of the form logic from the previous turn)
                c1, c2 = st.columns(2)
                inv_num = c1.text_input("Číslo faktury", data.get("invoice_number"))
                iss_date = c2.text_input("Datum vystavení", data.get("issue_date"))
                
                c1, c2 = st.columns(2)
                var_sym = c1.text_input("Variabilní symbol", data.get("variable_symbol"))
                due_date = c2.text_input("Datum splatnosti", data.get("due_date"))
                
                c1, c2 = st.columns(2)
                p_name = c1.text_input(partner_ui_label, data.get("partner_name"))
                p_ico = c2.text_input(f"IČO {partner_ui_label.lower()}", data.get("partner_ico"))
                
                c1, c2 = st.columns(2)
                c1.empty() 
                p_dic = c2.text_input(f"DIČ {partner_ui_label.lower()}", data.get("partner_vat_id"))
                
                st.divider()
                
                c1, c2 = st.columns(2)
                b0 = c1.number_input("Základ 0% (osvobozeno)", value=float(data.get("base_0", 0.0)) if data.get("base_0") else 0.0)
                round_val = c2.number_input("Zaokrouhlení", value=float(data.get("rounding", 0.0)) if data.get("rounding") else 0.0)

                c1, c2 = st.columns(2)
                b12 = c1.number_input("Základ 12%", value=float(data.get("base_12", 0.0)) if data.get("base_12") else 0.0)
                v12 = c2.number_input("DPH 12%", value=float(data.get("vat_12", 0.0)) if data.get("vat_12") else 0.0)
                
                c1, c2 = st.columns(2)
                b21 = c1.number_input("Základ 21%", value=float(data.get("base_21", 0.0)) if data.get("base_21") else 0.0)
                v21 = c2.number_input("DPH 21%", value=float(data.get("vat_21", 0.0)) if data.get("vat_21") else 0.0)
                
                c1, c2 = st.columns(2)
                t_base = c1.number_input("Základ celkem", value=float(data.get("total_base", 0.0)) if data.get("total_base") else 0.0)
                t_vat = c2.number_input("DPH celkem", value=float(data.get("total_vat", 0.0)) if data.get("total_vat") else 0.0)
                
                c1, c2 = st.columns(2)
                t_amt = c1.number_input("Celkem s DPH", value=float(data.get("total_amount", 0.0)) if data.get("total_amount") else 0.0)
                curr = c2.text_input("Měna", data.get("currency"))

                edited_data = {
                    "invoice_number": inv_num,
                    "variable_symbol": var_sym,
                    "issue_date": iss_date,
                    "due_date": due_date,
                    "partner_name": p_name,
                    "partner_ico": p_ico,
                    "partner_vat_id": p_dic,
                    "base_0": b0,
                    "rounding": round_val,
                    "base_12": b12,
                    "vat_12": v12,
                    "base_21": b21,
                    "vat_21": v21,
                    "total_base": t_base,
                    "total_vat": t_vat,
                    "total_amount": t_amt,
                    "currency": curr,
                    "image_b64": data.get("image_b64"),
                    "image_filename": data.get("image_filename"),
                    "image_mimetype": data.get("image_mimetype")
                }
                
                c_btn1, c_btn2 = st.columns(2)
                submit = c_btn1.form_submit_button("✅ Schválit a uložit", use_container_width=True)
                submit_next = c_btn2.form_submit_button("✅ Schválit a další ➡️", use_container_width=True)
                
                if submit or submit_next:
                    st.session_state.approved_files.add(file_id)
                    new_ico = edited_data.get("partner_ico")
                    new_vs = edited_data.get("variable_symbol")
                    
                    existing_idx = -1
                    for idx, inv in enumerate(st.session_state.processed_invoices):
                        if inv.get("partner_ico") == new_ico and inv.get("variable_symbol") == new_vs:
                            existing_idx = idx
                            break
                    
                    if existing_idx != -1:
                        st.session_state.processed_invoices[existing_idx] = edited_data
                        st.success("Záznam byl aktualizován.")
                    else:
                        st.session_state.processed_invoices.append(edited_data)
                        st.success("Přidáno do seznamu.")
                    
                    if submit_next and st.session_state.current_file_idx < len(uploaded_files) - 1:
                        st.session_state.current_file_idx += 1
                    
                    st.rerun()

if st.session_state.processed_invoices:
    st.divider()
    st.subheader(f"📋 Seznam schválených faktur ({invoice_mode.split(' ')[0]})")
    df = pd.DataFrame(st.session_state.processed_invoices)
    st.dataframe(df, use_container_width=True, column_config={
        "invoice_number": "Číslo faktury", "variable_symbol": "Var. symbol",
        "issue_date": "Vystaveno", "due_date": "Splatnost",
        "partner_name": partner_ui_label, "partner_ico": "IČO", "partner_vat_id": "DIČ",
        "base_0": "Základ 0%",
        "rounding": "Zaokrouhlení",
        "base_12": "Základ 12%", "vat_12": "DPH 12%",
        "base_21": "Základ 21%", "vat_21": "DPH 21%",
        "total_base": "Základ celkem", "total_vat": "DPH celkem",
        "total_amount": "Celkem", "currency": "Měna"
    })
    
    col_exp1, col_exp2 = st.columns(2)
    with col_exp1:
        if st.button("🗑️ Vymazat seznam"):
            st.session_state.processed_invoices = []
            st.rerun()
    with col_exp2:
        filename_prefix = st.text_input("Prefix souboru (např. název firmy)", value="flexibee")
        all_xml = generate_flexibee_xml(st.session_state.processed_invoices, mode_key)
        
        # Očištění prefixu pro bezpečné jméno souboru
        safe_prefix = "".join([c for c in filename_prefix if c.isalnum() or c in (' ', '-', '_')]).strip().replace(' ', '_')
        if not safe_prefix:
            safe_prefix = "flexibee"

        st.download_button(
            label=f"⬇️ Stáhnout XML ({invoice_mode.split(' ')[0]})",
            data=all_xml,
            file_name=f"{safe_prefix}_{mode_key}_{datetime.now().strftime('%Y%m%d_%H%M')}.xml",
            mime="application/xml"
        )
