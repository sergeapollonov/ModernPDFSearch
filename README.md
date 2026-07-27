# ModernPDFSearch (SYS.SEARCH // PDF)

Nowoczesna, błyskawiczna aplikacja biurkowa z interfejsem graficznym (GUI) do przeszukiwania dokumentów PDF. Zaprojektowana w surowym i minimalistycznym stylu inspirowanym designem marki **Nothing** (Brutalist Dot Grid UI, czcionka Doto, wysoki kontrast i animacje oparte na kropkach).

---

## 🌟 Główne funkcjonalności

- **Błyskawiczne skanowanie:** Przeszukiwanie całych katalogów (wraz z podkatalogami) pod kątem plików `.pdf` dzięki ultrawydajnej bibliotece `PyMuPDF` (`fitz`).
- **Precyzyjne wyniki:** Wyświetlanie nazw plików, dokładnego numeru strony z odnalezioną frazą oraz pełnej ścieżki na dysku.
- **Akcje na wynikach:**
  - `[ ŚCIEŻKA ]` – natychmiastowe skopiowanie pełnej ścieżki pliku do schowka.
  - `[ FOLDER ]` – otwarcie Eksploratora Windows z automatycznie zaznaczonym plikiem docelowym.
  - `[ OTWÓRZ ]` – otwarcie pliku PDF bezpośrednio w domyślnym systemowym czytniku.
- **Asynchroniczna praca w tle:** Skanowanie odbywa się w osobnym wątku (`threading.Thread`), nie blokując interfejsu. Możliwość natychmiastowego przerwania skanowania w dowolnym momencie (`[ PRZERWIJ ]`).
- **Dopracowany UX/UI:**
  - Tło z dynamiczną siatką kropek (Dot Grid), skalujące się płynnie przy zmianie rozmiaru okna (dzięki technice *debouncingu*).
  - Animowany pasek postępu ze stylizowanymi czerwonymi kropkami.
  - Licznik wyników na żywo oraz automatyczne raportowanie uszkodzonych/niedostępnych plików PDF w statusie (`BŁĘDY: X`).
  - Podświetlanie kart wyników po najechaniu myszą (hover effect).

---

## 🛠 Wymagania i instalacja ze źródeł

Aby uruchomić aplikację w środowisku programistycznym na dowolnym stanowisku:

### 1. Wymagania systemowe
- System operacyjny: Windows 10 / 11 (zalecany ze względu na integrację z Eksploratorem Windows; aplikacja posiada też obsługę macOS/Linux).
- **Python 3.10+** (zalecany Python 3.14 / 3.12).

### 2. Szybki start

Sklonuj repozytorium na swój dysk:
```bash
git clone <URL_TEGO_REPOZYTORIUM>
cd ModernPDFSearch
```

Utwórz i aktywuj wirtualne środowisko (zalecane):
```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux / macOS:
source venv/bin/activate
```

Zainstaluj wymagane biblioteki:
```bash
pip install -r requirements.txt
```

Uruchom aplikację:
```bash
python app.py
```

---

## 📦 Budowanie pliku wykonywalnego (.exe)

Aplikacja jest w pełni przystosowana do spakowania jako pojedynczy, niezależny plik wykonywalny `.exe` (nie wymaga zainstalowanego Pythona na komputerze docelowym).

W katalogu znajduje się gotowa konfiguracja `ModernPDFSearch.spec` oraz skrypt pomocniczy.

Aby zbudować plik `.exe`, uruchom komendę:
```bash
pyinstaller --noconfirm ModernPDFSearch.spec
```
*Lub użyj dołączonego skryptu automatycznego:*
```cmd
zbuduj_exe.bat
```

Gotowy, samodzielny plik wykonywalny pojawi się w folderze **`dist/ModernPDFSearch.exe`**. Do pliku wykonywalnego automatycznie dołączana jest dedykowana czcionka `Doto-Bold.ttf` oraz ikona `icon_nothing.ico`.

---

## 📂 Struktura repozytorium

```text
ModernPDFSearch/
├── app.py                  # Główny kod źródłowy aplikacji i interfejsu (CustomTkinter)
├── ModernPDFSearch.spec    # Konfiguracja budowania dla PyInstaller (asset bundling)
├── requirements.txt        # Lista zależności (customtkinter, PyMuPDF, pyinstaller)
├── zbuduj_exe.bat          # Skrypt wsadowy Windows do szybkiej kompilacji
├── Doto-Bold.ttf           # Czcionka w stylu Nothing Dot (ładowana dynamicznie)
├── icon_nothing.ico        # Ikona aplikacji dla okna i pliku .exe
├── generate_assets.py      # Skrypt pomocniczy do generowania zasobów graficznych
├── .gitignore              # Ignorowane foldery build/, dist/, venv/
└── README.md               # Dokumentacja projektu
```

---

## 📝 Uwagi techniczne
- W systemie Windows ładowanie czcionki z pliku `.ttf` odbywa się prywatnie dla procesu aplikacji za pomocą wywołania API Win32 (`AddFontResourceExW` z flagą `FR_PRIVATE`), co nie wymaga uprawnień administratora ani instalacji czcionki w systemie.
- Ścieżki w Eksploratorze dla przycisku `[ FOLDER ]` są normalizowane przez `os.path.normpath()`, gwarantując niezawodne podświetlanie pliku w systemie Windows.
