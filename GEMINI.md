# Projekt: FlexiBee AI Invoice Converter

Tento projekt slouží k převodu obrázků faktur (přijatých i vydaných) do formátu XML pro systém Abra FlexiBee pomocí modelu Gemini 2.5 Flash.

## Technický stack
- **Jazyk:** Python 3.9+
- **Framework:** Streamlit (UI)
- **AI:** `google-genai` SDK (Model: `gemini-2.5-flash`)
- **Výstup:** Formátované XML (`winstrom` 1.0)

## Klíčové vlastnosti a rozhodnutí
- **Režimy:** Podporuje "Přijaté" (dodavatel) a "Vydané" (odběratel) faktury.
- **Identifikace partnera:** V XML nepoužíváme tag `<firma>` (interní ID), ale identifikujeme pomocí `<ic>`, `<dic>` a `<nazev>`. FlexiBee si partnera dohledá nebo založí samo.
- **Číslování:** 
  - U **přijatých** faktur se neposílá `<kod>`, aby FlexiBee přidělilo interní číslo automaticky. Číslo z faktury jde do `<cisDosl>`.
  - U **vydaných** faktur se číslo ukládá do `<kod>`.
- **Typ dokladu:** Používá se `code:STANDARD` jako univerzální výchozí kód.
- **Hromadné zpracování:** Uživatel může nahrát více souborů, procházet je, upravovat a exportovat jako jeden XML soubor.
- **Export:** Možnost definovat prefix názvu souboru (např. jméno firmy) pro snadné odlišení exportů.
- **Unikátnost:** V seznamu jsou faktury identifikovány dvojicí **IČO + Variabilní symbol**, při shodě dochází k aktualizaci záznamu místo duplikace.

## Aktuální stav
- Aplikace je plně funkční v češtině.
- XML je formátované (pretty-print).
- Vyřešena chyba s duplicitním číslováním dokladů při importu do FlexiBee.
- Přidána podpora pro položky osvobozené od DPH (`sumOsv`).
- Částka zaokrouhlení je automaticky přičítána k `sumOsv`.
- Implementováno přikládání originálního souboru k faktuře v XML (base64 v tagu `<prilohy>`).

## Jak pokračovat
Při dalším vývoji je možné se zaměřit na:
1. Automatické doplňování jména firmy z registru ARES podle IČO.
2. Rozpoznávání více sazeb DPH na jedné faktuře.
3. Přidání podpory pro PDF dokumenty.
