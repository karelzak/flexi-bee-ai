# Invoice to FlexiBee XML Converter

This application uses Google's Gemini 1.5 Flash to extract data from invoice images and generate XML files compatible with Abra FlexiBee.

## Prerequisites

- Python 3.9+
- A Google Gemini API Key

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Create a `.env` file and add your Gemini API Key:
   ```bash
   echo "GOOGLE_API_KEY=your_key_here" > .env
   ```

## Usage

Run the Streamlit application:
   ```bash
   streamlit run app.py
   ```

1. Upload an invoice image (JPG/PNG).
2. Click **Extract Data** to let Gemini analyze the document.
3. Review and edit the recognized fields in the form.
4. Click **Generate XML** to create the FlexiBee import file.
5. Download the `.xml` file and import it into Abra FlexiBee.

## Features

- **OCR + Logic:** Gemini extracts not just text, but structured data (invoice number, dates, amounts, etc.).
- **Interactive Review:** Users can manually correct any errors before the final XML is created.
- **FlexiBee Ready:** Outputs a valid `<winstrom>` XML file for "Incoming Invoices" (faktura-prijata).
