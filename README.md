# Flexi-Bee AI (v2)

Moderní nástroj pro automatické vytěžování faktur pomocí Google Gemini AI a jejich následný export do formátu Abra FlexiBee XML. 

## ✨ Hlavní funkce (v2)

- **AI Vytěžování (Gemini):** Automatická extrakce dat z obrázků a PDF (číslo faktury, VS, data, částky, DPH, partner).
- **Multi-skener (NAPS2):** Podpora skenování přímo z aplikace (z podavače i ze skla) na Windows.
- **Interaktivní tabulka:** Přehledné schvalování a editace vytěžených dat před exportem.
- **Detekce anomálií:** AI kontrola duplicit, mezer v číselných řadách a logických chyb v datech.
- **Batch Export:** Hromadné generování XML souborů připravených pro import do Abra FlexiBee.
- **Modulární architektura:** Čistý, objektově orientovaný kód pro snadnou údržbu a rozšiřitelnost.

## 🚀 Rychlý start

1. **Instalace závislostí:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Konfigurace API klíče:**
   Vytvořte soubor `.env` a přidejte svůj Google Gemini API klíč:
   ```bash
   GOOGLE_API_KEY=your_key_here
   ```

3. **Spuštění:**
   - **Linux:** `./run_app.sh` nebo `python3 run.py`
   - **Windows:** `run_app.bat` nebo `python run.py`

## 🛠️ Požadavky

- **Python 3.10+**
- **NAPS2 (NAPS2.Console.exe):** Vyžadováno pouze na Windows pro funkci skenování.
- **Google Gemini API Key:** Pro funkci OCR a detekci anomálií.

## 📂 Struktura projektu

- `app_v2.py`: Hlavní Streamlit UI aplikace.
- `run.py`: Entry point zajišťující správné spuštění.
- `models.py`: Datové modely (`FlexiDoc`, `FlexiDocManager`).
- `ocr_engine.py`: Komunikace s Google Gemini API.
- `xml_generator.py`: Generování Abra FlexiBee XML.
- `utils.py`: Pomocné funkce (PDF processing, skenování, historie firem).

---
Pro detailní návod k instalaci na Windows viz [README.win](README.win).
