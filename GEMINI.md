# Flexi-Bee AI: Refactoring & v2 Overview

## Architecture (v2)
The application has been refactored from a legacy procedural script (`app.py`) into a modular, object-oriented system to improve maintainability and performance.

### Key Components
- **`models.py`**:
    - `FlexiDoc`: Represents a single invoice. Stores raw image bytes, extracted metadata, and unique persistent UUIDs. Includes methods for OCR and XML generation.
    - `FlexiDocManager`: Container class for managing document sets (add, remove, reorder, bulk XML export).
- **`ocr_engine.py`**: Handles all interactions with the Google Gemini API (Data extraction & Anomaly detection).
- **`xml_generator.py`**: Logic for generating Abra FlexiBee compatible XML.
- **`utils.py`**: Shared utility functions (NAPS2 scanning, PDF processing, company history).
- **`app_v2.py`**: New Streamlit UI focused on a central document table and batch processing.
- **`run.py`**: Direct entry point for the application.

### Startup
- **Windows**: `run_app.bat` (runs `python run.py`)
- **Linux**: `run_app.sh` (runs `python3 run.py`)

## Performance Improvements
- In-memory processing of PDF pages and images.
- Lazy evaluation of Base64 encoding for UI and XML.
- Stable UUID-based state management in Streamlit, leading to faster UI responsiveness.

## Future Plans
- [x] Add support for multiple scanner profiles (NAPS2) - **Done**
- [x] Restore missing tax and rounding fields in UI - **Done**
- [x] Optimize document table with fixed date widths and auto-hide empty columns - **Done**
- [ ] Implement document reordering in the UI.
- [ ] Direct scanner-to-table automation.
- [ ] Enhanced document deletion and management.
