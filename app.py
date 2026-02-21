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
import fitz  # PyMuPDF

# Načtení proměnných prostředí
load_dotenv()

# Konfigurace Gemini API
API_KEY = os.getenv("GOOGLE_API_KEY")
if API_KEY:
    client = genai.Client(api_key=API_KEY)

@st.cache_data(show_spinner="Dekódování PDF...")
def pdf_to_images_cached(pdf_name, pdf_size, pdf_bytes):
    """Převede PDF na seznam obrázků (jeden pro každou stránku) v šedi s využitím cache."""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages = []
        for i in range(len(doc)):
            page = doc.load_page(i)
            # Matrix(2, 2) = cca 144 DPI (dostatečné pro OCR, rozumná velikost)
            # colorspace=fitz.csGRAY = stupně šedi (výrazně zmenší velikost v base64 i v Gemini)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), colorspace=fitz.csGRAY)
            # Uložíme jako JPG s rozumnou kvalitou (oprava parametru na jpg_quality)
            img_bytes = pix.tobytes("jpg", jpg_quality=85)
            pages.append({
                "name": f"{pdf_name}_strana_{i+1}.jpg",
                "content": img_bytes,
                "type": "image/jpeg",
                "id": f"{pdf_name}_p{i+1}_{pdf_size}"
            })
        doc.close()
        return pages
    except Exception as e:
        st.error(f"Chyba při zpracování PDF {pdf_name}: {e}")
        return []

def extract_invoice_data(image_source, mode):
    """Použije Gemini k extrakci strukturovaných dat z obrázku faktury.
    Akceptuje PIL Image nebo bajty.
    """
    partner_label = "supplier" if mode == "prijata" else "customer"
    
    # Pokud dostaneme bajty, převedeme je na PIL Image pro Gemini
    if isinstance(image_source, bytes):
        image = Image.open(io.BytesIO(image_source))
    else:
        image = image_source
    
    prompt = f"""
    Extract the following information from this invoice image:
    - invoice_number (string)
    - variable_symbol (string)
    - description (string - short summary of what the invoice is for, e.g., "Kancelářské potřeby", "Oprava dveří", max 50 characters)
    - issue_date (YYYY-MM-DD)
    - vat_date (YYYY-MM-DD - "Datum zdanitelného plnění" or DUZP. If not found, use null)
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

def generate_flexibee_xml(invoices_list, mode, include_attachments=True):
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
        
        # Datum zdanitelného plnění (DUZP) - fallback na datum vystavení
        duzp = data.get("vat_date") or data.get("issue_date", "")
        ET.SubElement(invoice, "duzpPuv").text = str(duzp)
        
        ET.SubElement(invoice, "datSplat").text = str(data.get("due_date", ""))
        
        # Identifikace partnera (FlexiBee dohledá podle IČ/DIČ v adresáři)
        if data.get("partner_name"):
            ET.SubElement(invoice, "nazFirmy").text = str(data['partner_name'])

        if data.get("partner_ico"):
            ET.SubElement(invoice, "ic").text = str(data['partner_ico'])
        
        if data.get("partner_vat_id"):
            ET.SubElement(invoice, "dic").text = str(data['partner_vat_id'])
        
        # Popis dokladu - pouze pokud je vyplněn
        if data.get("description"):
            ET.SubElement(invoice, "popis").text = str(data["description"])
         
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

        # Přiložení originálního obrazu faktury (volitelně)
        if include_attachments and data.get("image_b64"):
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

# Možnosti exportu
st.sidebar.subheader("Export")
include_images = st.sidebar.checkbox("Přikládat obrazy faktur do XML", value=True, help="Pokud je vypnuto, XML bude mnohem menší, ale bez náhledů faktur.")

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

uploaded_files = st.file_uploader(f"Nahrajte {invoice_mode.lower()} (JPG, PNG, PDF)", type=["jpg", "jpeg", "png", "pdf"], accept_multiple_files=True)

# Rozšíření seznamu souborů o stránky PDF
processable_items = []
if uploaded_files:
    for f in uploaded_files:
        if f.type == "application/pdf":
            # Použijeme getvalue() a metadata pro efektivní cachování v RAM
            pages = pdf_to_images_cached(f.name, f.size, f.getvalue())
            processable_items.extend(pages)
        else:
            f.seek(0)
            img_bytes = f.read()
            processable_items.append({
                "name": f.name,
                "content": img_bytes,
                "type": f.type,
                "id": f"{f.name}_{f.size}"
            })

if processable_items:
    if "last_items_count" not in st.session_state or st.session_state.last_items_count != len(processable_items):
        st.session_state.current_file_idx = 0
        st.session_state.last_items_count = len(processable_items)

    # Hromadná analýza - ovládání
    unprocessed_items = [item for item in processable_items if (item['id'] + mode_key) not in st.session_state.extraction_cache]
    
    if unprocessed_items:
        col_auto1, col_auto2 = st.columns([1, 3])
        if not st.session_state.auto_analyzing:
            if col_auto1.button(f"🤖 Hromadná analýza ({len(unprocessed_items)})", use_container_width=True):
                st.session_state.auto_analyzing = True
                st.rerun()
        else:
            if col_auto1.button("🛑 Zastavit", use_container_width=True):
                st.session_state.auto_analyzing = False
                st.rerun()
            
            # Provedení jednoho kroku analýzy
            item = unprocessed_items[0]
            item_id = item['id'] + mode_key
            idx_in_all = processable_items.index(item)
            
            with st.spinner(f"Analyzuji: {item['name']} ({idx_in_all + 1}/{len(processable_items)})..."):
                data = extract_invoice_data(item['content'], mode_key)
                if data:
                    data["image_b64"] = base64.b64encode(item['content']).decode('utf-8')
                    data["image_filename"] = item['name']
                    data["image_mimetype"] = item['type']
                    # Fallback pro DUZP pokud chybí
                    if not data.get("vat_date"):
                        data["vat_date"] = data.get("issue_date")
                    st.session_state.extraction_cache[item_id] = data
                st.rerun()
    elif st.session_state.auto_analyzing:
        st.session_state.auto_analyzing = False
        st.success("Všechny položky byly analyzovány.")

    # Přehled stavu souborů (dvou-sloupcový seznam)
    with st.expander("📊 Přehled zpracování", expanded=True):
        c1, c2 = st.columns(2)
        for idx, item in enumerate(processable_items):
            item_id = item['id'] + mode_key
            
            # Ikony stavu
            analyzed_icon = "🧪" if item_id in st.session_state.extraction_cache else "⚪"
            approved_icon = "✅" if item_id in st.session_state.approved_files else "⚪"
            current_marker = " 📍" if idx == st.session_state.current_file_idx else ""
            
            status_text = f"{analyzed_icon} {approved_icon} {item['name']}{current_marker}"
            
            target_col = c1 if idx % 2 == 0 else c2
            target_col.write(status_text)

    # Navigační lišta pod přehledem
    col_nav1, col_nav2, col_nav3 = st.columns([1, 4, 1])
    with col_nav1:
        if st.button("⬅️ Předchozí", use_container_width=True) and st.session_state.current_file_idx > 0:
            st.session_state.current_file_idx -= 1
            st.rerun()
    with col_nav2:
        st.markdown(f"<p style='text-align: center; font-size: 1.2rem; font-weight: bold; margin-top: 5px;'>Položka {st.session_state.current_file_idx + 1} z {len(processable_items)}</p>", unsafe_allow_html=True)
    with col_nav3:
        if st.button("Další ➡️", use_container_width=True) and st.session_state.current_file_idx < len(processable_items) - 1:
            st.session_state.current_file_idx += 1
            st.rerun()

    st.divider()
    current_item = processable_items[st.session_state.current_file_idx]
    image = Image.open(io.BytesIO(current_item['content']))
    
    col_img, col_form = st.columns(2)
    with col_img:
        st.image(image, caption=current_item['name'], use_container_width=True)
    
    with col_form:
        item_id = current_item['id'] + mode_key
        if item_id not in st.session_state.extraction_cache:
            if st.button("Analyzovat položku"):
                with st.spinner("Gemini analyzuje..."):
                    data = extract_invoice_data(current_item['content'], mode_key)
                    if data:
                        data["image_b64"] = base64.b64encode(current_item['content']).decode('utf-8')
                        data["image_filename"] = current_item['name']
                        data["image_mimetype"] = current_item['type']
                        st.session_state.extraction_cache[item_id] = data
                        st.rerun()
        
        if item_id in st.session_state.extraction_cache:
            data = st.session_state.extraction_cache[item_id]
            st.subheader(f"Ověření dat ({invoice_mode.split(' ')[0]})")
            with st.form(key=f"form_{item_id}"):
                c1, c2 = st.columns(2)
                inv_num = c1.text_input("Číslo faktury", data.get("invoice_number"))
                iss_date = c2.text_input("Datum vystavení", data.get("issue_date"))
                
                c1, c2 = st.columns(2)
                var_sym = c1.text_input("Variabilní symbol", data.get("variable_symbol"))
                vat_date = c2.text_input("Datum zdanit. plnění (DUZP)", data.get("vat_date") or data.get("issue_date"))
                
                c1, c2 = st.columns(2)
                due_date = c1.text_input("Datum splatnosti", data.get("due_date"))
                desc = c2.text_input("Popis (stručný odhad obsahu)", data.get("description", ""), max_chars=50)

                c1, c2 = st.columns(2)
                p_name = c1.text_input(partner_ui_label, data.get("partner_name"))
                p_ico = c2.text_input(f"IČO {partner_ui_label.lower()}", data.get("partner_ico"))
                
                c1, c2 = st.columns(2)
                p_dic = c1.text_input(f"DIČ {partner_ui_label.lower()}", data.get("partner_vat_id"))
                c2.empty()
                
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
                    "item_id": item_id,
                    "invoice_number": inv_num,
                    "variable_symbol": var_sym,
                    "description": desc,
                    "issue_date": iss_date,
                    "vat_date": vat_date,
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
                    st.session_state.approved_files.add(item_id)
                    new_ico = edited_data.get("partner_ico")
                    new_vs = edited_data.get("variable_symbol")
                    
                    existing_idx = -1
                    for idx, inv in enumerate(st.session_state.processed_invoices):
                        if inv.get("item_id") == item_id: # Identifikace podle ID položky
                            existing_idx = idx
                            break
                    
                    if existing_idx != -1:
                        st.session_state.processed_invoices[existing_idx] = edited_data
                        st.success("Záznam byl aktualizován.")
                    else:
                        st.session_state.processed_invoices.append(edited_data)
                        st.success("Přidáno do seznamu.")
                    
                    if submit_next and st.session_state.current_file_idx < len(processable_items) - 1:
                        st.session_state.current_file_idx += 1
                    
                    st.rerun()
            
            # Hromadné schválení pod formulářem
            analyzed_not_approved = [item for item in processable_items if (item['id'] + mode_key) in st.session_state.extraction_cache and (item['id'] + mode_key) not in st.session_state.approved_files]
            if analyzed_not_approved:
                st.divider()
                if st.button(f"✅ Schválit všechny analyzované položky ({len(analyzed_not_approved)})", use_container_width=True):
                    for item in analyzed_not_approved:
                        item_id = item['id'] + mode_key
                        data = st.session_state.extraction_cache[item_id].copy()
                        data["item_id"] = item_id # Přidat ID do dat
                        
                        existing_idx = -1
                        for idx, inv in enumerate(st.session_state.processed_invoices):
                            if inv.get("item_id") == item_id:
                                existing_idx = idx
                                break
                        
                        if existing_idx != -1:
                            st.session_state.processed_invoices[existing_idx] = data
                        else:
                            st.session_state.processed_invoices.append(data)
                        
                        st.session_state.approved_files.add(item_id)
                    st.success(f"Schváleno {len(analyzed_not_approved)} položek.")
                    st.rerun()

if st.session_state.processed_invoices:
    st.divider()
    st.subheader(f"📋 Seznam schválených faktur ({invoice_mode.split(' ')[0]})")
    st.info("💡 Zaškrtnutím políčka 'Vybrat' otevřete fakturu k úpravě. Aktuálně zobrazená faktura je vždy zaškrtnuta.")
    
    df = pd.DataFrame(st.session_state.processed_invoices)
    
    # Identifikovat sloupce, které obsahují pouze nuly (pro číselné typy)
    zero_cols = []
    numeric_check = ["base_0", "rounding", "base_12", "vat_12", "base_21", "vat_21", "total_base", "total_vat"]
    for col in numeric_check:
        if col in df.columns:
            # Převedeme na čísla a zkontrolujeme, zda jsou všechny hodnoty 0
            vals = pd.to_numeric(df[col], errors='coerce').fillna(0)
            if (vals == 0).all():
                zero_cols.append(col)
    
    # Přidat booleovský příznak pro aktuálně vybraný řádek (zobrazí se jako checkbox)
    current_id = processable_items[st.session_state.current_file_idx]['id'] + mode_key
    df['Vybrat'] = df['item_id'] == current_id
    
    # Skrýt interní ID, technické sloupce a sloupce s nulami
    cols_to_show = ["Vybrat"] + [c for c in df.columns if c not in ["image_b64", "image_filename", "image_mimetype", "item_id", "Vybrat"] + zero_cols]
    
    # Použijeme data_editor pro interaktivní checkbox bez duplicitních systémových checkboxů
    edited_df = st.data_editor(
        df[cols_to_show], 
        use_container_width=True, 
        hide_index=True, 
        key="invoice_selector",
        column_config={
            "Vybrat": st.column_config.CheckboxColumn(" ", width="small"),
            "invoice_number": "Číslo faktury", "variable_symbol": "Var. symbol",
            "description": "Popis",
            "issue_date": "Vystaveno", "vat_date": "DUZP", "due_date": "Splatnost",
            "partner_name": partner_ui_label, "partner_ico": "IČO", "partner_vat_id": "DIČ",
            "base_0": "Základ 0%",
            "rounding": "Zaokrouhlení",
            "base_12": "Základ 12%", "vat_12": "DPH 12%",
            "base_21": "Základ 21%", "vat_21": "DPH 21%",
            "total_base": "Základ celkem", "total_vat": "DPH celkem",
            "total_amount": "Celkem", "currency": "Měna"
        },
        disabled=[c for c in cols_to_show if c != "Vybrat"]
    )
    
    # Zpracování kliknutí na checkbox v data_editoru
    if "invoice_selector" in st.session_state:
        edits = st.session_state.invoice_selector.get("edited_rows", {})
        if edits:
            # Zjistíme, který řádek byl změněn
            row_idx = int(next(iter(edits.keys())))
            selected_item_id = df.iloc[row_idx]["item_id"]
            
            # Najít index v processable_items
            for idx, item in enumerate(processable_items):
                if (item['id'] + mode_key) == selected_item_id:
                    if st.session_state.current_file_idx != idx:
                        st.session_state.current_file_idx = idx
                        st.rerun()
    
    col_exp1, col_exp2 = st.columns(2)
    with col_exp1:
        if st.button("🗑️ Vymazat seznam"):
            st.session_state.processed_invoices = []
            st.rerun()
    with col_exp2:
        filename_prefix = st.text_input("Prefix souboru (např. název firmy)", value="flexibee")
        all_xml = generate_flexibee_xml(st.session_state.processed_invoices, mode_key, include_attachments=include_images)
        
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
