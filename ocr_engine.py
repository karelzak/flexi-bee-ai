import json
import io
import os
from PIL import Image
from google import genai
from typing import Optional, Dict, Any, List
from models import FlexiDoc
from datetime import datetime

class GeminiOCREngine:
    """
    Handles Gemini API interactions for OCR and data extraction.
    """
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY not provided.")
        self.client = genai.Client(api_key=self.api_key)

    def extract_invoice_data(self, doc: FlexiDoc, mode: str) -> Optional[Dict[str, Any]]:
        """Extracts structured data from a FlexiDoc image."""
        partner_label = "supplier" if mode == "prijata" else "customer"
        
        # Open image from bytes
        image = Image.open(io.BytesIO(doc.content))
        
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
        - currency (string, ISO code e.g., CZK, EUR. Never use "Kč", always use "CZK" for Czech Koruna)

        If a value is not found, return 0 for numeric fields and null for strings.
        """
        
        try:
            response = self.client.models.generate_content(
                model='gemini-2.0-flash', # Or whatever model version is preferred
                contents=[prompt, image],
                config={'response_mime_type': 'application/json'}
            )
            data = json.loads(response.text)
            doc.raw_gemini_response = response.text
            doc.set_data(data)
            return data
        except Exception as e:
            # Re-raise or handle as needed
            raise e

    def check_for_anomalies(self, docs: List[FlexiDoc], mode: str) -> List[Dict[str, Any]]:
        """Detects anomalies in a list of FlexiDoc objects."""
        if not docs:
            return []
            
        simplified_data = []
        for doc in docs:
            data = doc.data.copy()
            data["item_id"] = doc.id
            simplified_data.append({
                "item_id": doc.id,
                "invoice_number": data.get("invoice_number"),
                "variable_symbol": data.get("variable_symbol"),
                "issue_date": data.get("issue_date"),
                "vat_date": data.get("vat_date"),
                "due_date": data.get("due_date"),
                "partner_ico": data.get("partner_ico"),
                "total_amount": data.get("total_amount"),
                "currency": data.get("currency")
            })

        if mode == "vydana":
            mode_instruction = """
            Toto jsou VYDANÉ faktury (všechny vystavila jedna firma). 
            Zaměř se na:
            1. Číselné řady (invoice_number, variable_symbol) - hledej mezery v sekvenci, duplicity nebo podezřelé skoky.
            2. Logiku dat (splatnost před vystavením, data v budoucnosti, DUZP vs vystavení).
            """
        else:
            mode_instruction = """
            Toto jsou PŘIJATÉ faktury od různých dodavatelů (partner_ico). 
            Zaměř se na:
            1. Duplicity - stejné partner_ico + stejné číslo faktury/variabilní symbol.
            2. Logiku dat (splatnost před vystavením, data v budoucnosti, extrémně dlouhá splatnost).
            3. Nekonzistence v partner_ico (např. chybějící nebo podezřele krátké).
            U přijatých faktur NEHLEDEJ číselné řady napříč celým seznamem, protože každý dodavatel má vlastní číslování.
            """

        prompt = f"""
        Analyze the following list of invoices for anomalies and errors.
        The current date is {datetime.now().strftime('%Y-%m-%d')}.
        
        {mode_instruction}
        
        Return a JSON list of objects, each containing:
        - item_id: the ID of the suspicious invoice
        - reason: short explanation in Czech (max 60 chars) why it is suspicious.

        If no anomalies are found, return an empty list [].
        Return ONLY valid JSON.
        """
        
        try:
            response = self.client.models.generate_content(
                model='gemini-2.0-flash',
                contents=[prompt, json.dumps(simplified_data, indent=2)],
                config={'response_mime_type': 'application/json'}
            )
            return json.loads(response.text)
        except Exception as e:
            raise e
