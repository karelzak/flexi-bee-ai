import xml.etree.ElementTree as ET
from xml.dom import minidom
from typing import List, Dict, Any
from models import FlexiDoc

def generate_flexibee_xml(docs: List[FlexiDoc], mode: str, include_attachments: bool = True) -> bytes:
    """Převede seznam ověřených faktur do formátu Abra FlexiBee XML."""
    
    root = ET.Element("winstrom", version="1.0")
    tag_name = "faktura-prijata" if mode == "prijata" else "faktura-vydana"
    
    for doc in docs:
        if not doc.approved:
            continue
            
        data = doc.data
        invoice = ET.SubElement(root, tag_name)
        
        # Očištění polí od mezer pro FlexiBee (již se děje v doc.set_data, ale pro jistotu)
        def clean_val(key):
            val = data.get(key, "")
            if val is None: return ""
            return str(val).replace(" ", "").replace("\xa0", "")

        if mode == "prijata":
            inv_num = clean_val("invoice_number") or clean_val("variable_symbol")
            ET.SubElement(invoice, "cisDosle").text = inv_num
        else:
            ET.SubElement(invoice, "kod").text = clean_val("invoice_number")
            
        ET.SubElement(invoice, "varSym").text = clean_val("variable_symbol")
        ET.SubElement(invoice, "datVyst").text = str(data.get("issue_date", ""))
        
        duzp = data.get("vat_date") or data.get("issue_date", "")
        ET.SubElement(invoice, "duzpPuv").text = str(duzp)
        ET.SubElement(invoice, "datSplat").text = str(data.get("due_date", ""))
        
        if data.get("partner_name"):
            ET.SubElement(invoice, "nazFirmy").text = str(data['partner_name'])

        if data.get("partner_ico"):
            ET.SubElement(invoice, "ic").text = clean_val("partner_ico")
        
        if data.get("partner_vat_id"):
            ET.SubElement(invoice, "dic").text = clean_val("partner_vat_id")
        
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
          
        ET.SubElement(invoice, "sumZklCelkem").text = str(data.get("total_base", "0"))
        ET.SubElement(invoice, "sumDphCelkem").text = str(data.get("total_vat", "0"))
        ET.SubElement(invoice, "sumCelkem").text = str(data.get("total_amount", "0"))
        
        curr_val = data.get('currency', 'CZK')
        if curr_val and curr_val.strip().upper() in ["KČ", "KC"]:
            curr_val = "CZK"
        ET.SubElement(invoice, "mena").text = f"code:{curr_val}"
        
        ET.SubElement(invoice, "typDokl").text = "code:FAKTURA"

        if include_attachments:
            attachments = ET.SubElement(invoice, "prilohy")
            attachment = ET.SubElement(attachments, "priloha")
            ET.SubElement(attachment, "nazSoub").text = doc.name
            ET.SubElement(attachment, "contentType").text = doc.mime_type
            content = ET.SubElement(attachment, "content")
            content.set("encoding", "base64")
            content.text = doc.get_image_b64()

        ET.SubElement(invoice, "bezPolozek").text = "true"
        ET.SubElement(invoice, "szbDphSniz").text = "12.0"
        ET.SubElement(invoice, "szbDphZakl").text = "21.0"
    
    xml_str = ET.tostring(root, encoding='utf-8')
    pretty_xml_str = minidom.parseString(xml_str).toprettyxml(indent="  ")
    return pretty_xml_str.encode('utf-8')
