import uuid
import json
import base64
from datetime import datetime
from typing import Optional, Dict, Any, List

class FlexiDoc:
    """
    Represents a single document (invoice) in the system.
    """
    def __init__(self, name: str, content: bytes, mime_type: str, doc_type: str = "prijata"):
        self.id = str(uuid.uuid4())
        self.name = name
        self.content = content  # Raw bytes of the image/page
        self.mime_type = mime_type
        self.doc_type = doc_type # "prijata" or "vydana"
        
        # Extracted data
        self.data: Dict[str, Any] = {}
        self.raw_gemini_response: Optional[str] = None
        self.approved: bool = False
        self.anomaly: Optional[str] = None
        
        # Timestamp of creation
        self.created_at = datetime.now()

    def set_data(self, data: Dict[str, Any]):
        """Sets the extracted data and performs basic normalization."""
        self.data = data
        # Ensure ID consistency for UI mapping if needed
        self.data["item_id"] = self.id
        
        # Normalization logic moved from app.py
        for key in ["invoice_number", "variable_symbol", "partner_ico", "partner_vat_id"]:
            if self.data.get(key):
                self.data[key] = str(self.data[key]).replace(" ", "").replace("\xa0", "")
        
        if self.data.get("currency") and self.data["currency"].strip().upper() in ["KČ", "KC"]:
            self.data["currency"] = "CZK"
            
        # Fallbacks
        if not self.data.get("vat_date"):
            self.data["vat_date"] = self.data.get("issue_date")
        if not self.data.get("due_date"):
            self.data["due_date"] = self.data.get("issue_date")

    def clear_data(self):
        """Clears AI extracted data and resets approval/anomaly status."""
        self.data = {}
        self.approved = False
        self.anomaly = None
        self.raw_gemini_response = None

    def get_image_mimetype(self) -> str:
        return self.mime_type

    def get_image_b64(self) -> str:
        """Returns base64 encoded content for XML or UI display."""
        return base64.b64encode(self.content).decode('utf-8')

    def run_ocr(self, ocr_engine, mode: str):
        """Runs Gemini OCR on this document."""
        return ocr_engine.extract_invoice_data(self, mode)

    def to_xml(self, mode: str, include_attachments: bool = True) -> bytes:
        """Generates FlexiBee XML for this single document."""
        from xml_generator import generate_flexibee_xml
        return generate_flexibee_xml([self], mode, include_attachments)

    def to_dict(self) -> Dict[str, Any]:
        """Returns a flat dictionary for DataFrame/UI usage."""
        res = self.data.copy()
        res["item_id"] = self.id
        res["name"] = self.name
        res["approved"] = self.approved
        res["anomaly"] = self.anomaly
        # Include technical fields for XML generation if needed
        res["image_b64"] = self.get_image_b64()
        res["image_filename"] = self.name
        res["image_mimetype"] = self.mime_type
        return res

class FlexiDocManager:
    """
    Container for FlexiDoc objects. Handles ordering and bulk operations.
    """
    def __init__(self):
        self.documents: List[FlexiDoc] = []

    def add_document(self, doc: FlexiDoc):
        self.documents.append(doc)

    def remove_document(self, doc_id: str):
        self.documents = [d for d in self.documents if d.id != doc_id]

    def get_document(self, doc_id: str) -> Optional[FlexiDoc]:
        for d in self.documents:
            if d.id == doc_id:
                return d
        return None

    def clear(self):
        self.documents = []

    def reorder(self, new_order_ids: List[str]):
        """Reorders documents based on a list of IDs."""
        id_map = {d.id: d for d in self.documents}
        new_list = []
        for doc_id in new_order_ids:
            if doc_id in id_map:
                new_list.append(id_map[doc_id])
        # Add any missing documents at the end
        missing = [d for d in self.documents if d.id not in new_order_ids]
        self.documents = new_list + missing

    def get_all_data(self) -> List[Dict[str, Any]]:
        """Returns data for all documents as a list of dicts."""
        return [d.to_dict() for d in self.documents]

    def get_approved_data(self) -> List[Dict[str, Any]]:
        """Returns data for approved documents only."""
        return [d.to_dict() for d in self.documents if d.approved]

    def to_xml(self, mode: str, include_attachments: bool = True) -> bytes:
        """Generates FlexiBee XML for all approved documents."""
        from xml_generator import generate_flexibee_xml
        approved_docs = [d for d in self.documents if d.approved]
        return generate_flexibee_xml(approved_docs, mode, include_attachments)
