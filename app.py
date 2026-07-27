import customtkinter as ctk
import os
import fitz  # PyMuPDF
import threading
from tkinter import filedialog
import subprocess
import platform
import ctypes
import sys

# --- ZAŁADOWANIE FONTU Z PLIKU ---
def load_font(font_path):
    if os.path.exists(font_path):
        # Flaga FR_PRIVATE (0x10) sprawia, że font jest widoczny tylko dla tej aplikacji
        FR_PRIVATE = 0x10
        FR_NOT_ENUM = 0x20
        ctypes.windll.gdi32.AddFontResourceExW(font_path, FR_PRIVATE | FR_NOT_ENUM, 0)
        return True
    return False

# Upewniamy się, że ścieżki działają też po spakowaniu PyInstallerem
if hasattr(sys, '_MEIPASS'):
    base_path = sys._MEIPASS
else:
    base_path = os.path.dirname(os.path.abspath(__file__))

font_file = os.path.join(base_path, "Doto-Bold.ttf")
icon_file = os.path.join(base_path, "icon_nothing.ico")

load_font(font_file)

# --- KONFIGURACJA WYGLĄDU (NOTHING / BRUTALISM) ---
ctk.set_appearance_mode("dark")
BG_COLOR = "#0a0a0a"
PANEL_BG = "#141414"
ACCENT_RED = "#ff2a2a"
ACCENT_RED_HOVER = "#cc0000"
TEXT_COLOR = "#ffffff"
TEXT_MUTED = "#888888"          # FIX #15: było #666666 (kontrast 4.1:1), teraz ~5.6:1
BORDER_COLOR = "#222222"
FONT_FAMILY = "Doto"            # Nazwa czcionki po załadowaniu
NORMAL_FONT = "Segoe UI"        # Czytelna czcionka dla długich tekstów

class ModernPDFSearch(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("SYS.SEARCH // PDF")
        self.geometry("1100x700")
        self.minsize(900, 500)
        self.configure(fg_color=BG_COLOR)

        # Ustawienie ikony
        if os.path.exists(icon_file):
            self.iconbitmap(icon_file)

        # Zmienne stanu
        self.folder_path = ""
        self.search_thread = None
        self._cancel_event = threading.Event()  # FIX #4: threading.Event zamiast bool

        # Liczniki wyników (FIX #5, #13)
        self.found_count = 0
        self._skipped_count = 0

        # Tło w kropki (Dot Grid Canvas)
        self.bg_canvas = ctk.CTkCanvas(self, bg=BG_COLOR, highlightthickness=0)
        self.bg_canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.bind("<Configure>", self.draw_dot_grid)
        self._dot_resize_timer = None  # FIX #1/#11: debounce

        # --- GŁÓWNY UKŁAD (Grid) ---
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ==========================================
        # PANEL BOCZNY (Lewa Strona - Kontrolki)
        # ==========================================
        self.left_panel = ctk.CTkFrame(self, width=320, corner_radius=0, fg_color=PANEL_BG, border_width=1, border_color=BORDER_COLOR)
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=(20, 10), pady=20)
        # FIX #18: weight=1 na row=4 (przed przyciskiem) żeby status label był zawsze widoczny
        self.left_panel.grid_rowconfigure(4, weight=1)
        self.left_panel.grid_columnconfigure(0, weight=1)

        # Tytuł aplikacji
        self.logo_label = ctk.CTkLabel(self.left_panel, text="[ PDF_SEARCH ]", font=ctk.CTkFont(family=FONT_FAMILY, size=28, weight="bold"), text_color=ACCENT_RED)
        self.logo_label.grid(row=0, column=0, padx=20, pady=(30, 20), sticky="w")

        # 1. Wybór folderu
        self.folder_btn = ctk.CTkButton(self.left_panel, text="> WYBIERZ FOLDER", command=self.select_folder,
                                        corner_radius=0, fg_color="transparent", border_width=1, border_color=TEXT_MUTED, text_color=TEXT_COLOR, hover_color="#2a2a2a", font=ctk.CTkFont(family=FONT_FAMILY, weight="bold", size=14))
        self.folder_btn.grid(row=1, column=0, padx=20, pady=(10, 5), sticky="ew")

        self.folder_label = ctk.CTkLabel(self.left_panel, text="BRAK_ŚCIEŻKI", text_color=TEXT_MUTED, wraplength=260, justify="left", font=ctk.CTkFont(family=NORMAL_FONT, size=13))
        self.folder_label.grid(row=2, column=0, padx=20, pady=(0, 20), sticky="w")

        # 2. Wyszukiwanie
        self.search_entry = ctk.CTkEntry(self.left_panel, placeholder_text="WPROWADŹ FRAZĘ...", height=45, corner_radius=0, border_color=BORDER_COLOR, fg_color=BG_COLOR, text_color=TEXT_COLOR, font=ctk.CTkFont(family=NORMAL_FONT, size=15))
        self.search_entry.grid(row=3, column=0, padx=20, pady=(0, 15), sticky="ew")
        self.search_entry.bind("<Return>", lambda event: self.toggle_search())

        # 3. Główny przycisk Szukaj/Przerwij
        self.action_btn = ctk.CTkButton(self.left_panel, text="[ ROZPOCZNIJ SKAN ]", height=50,
                                        corner_radius=0, fg_color=TEXT_COLOR, text_color="black", hover_color="#e0e0e0",
                                        font=ctk.CTkFont(family=FONT_FAMILY, weight="bold", size=16), command=self.toggle_search)
        self.action_btn.grid(row=4, column=0, padx=20, pady=(0, 10), sticky="sew")

        # Animacja ładowania (Kropki)
        self.progress_canvas = ctk.CTkCanvas(self.left_panel, bg=PANEL_BG, highlightthickness=0, height=8)
        self.progress_canvas.grid(row=5, column=0, padx=20, pady=(0, 10), sticky="new")
        self.progress_canvas.grid_remove()
        self.animation_step = 0
        self.is_animating = False

        # 4. Status na dole
        self.status_label = ctk.CTkLabel(self.left_panel, text="SYS.READY", text_color=TEXT_MUTED, font=ctk.CTkFont(family=FONT_FAMILY, size=12))
        self.status_label.grid(row=6, column=0, padx=20, pady=20, sticky="sw")

        # ==========================================
        # PANEL GŁÓWNY (Prawa Strona - Wyniki)
        # ==========================================
        self.right_panel = ctk.CTkFrame(self, fg_color="transparent")
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=(10, 20), pady=20)
        self.right_panel.grid_rowconfigure(1, weight=1)
        self.right_panel.grid_columnconfigure(0, weight=1)

        self.results_title = ctk.CTkLabel(self.right_panel, text="// WYNIKI", font=ctk.CTkFont(family=FONT_FAMILY, size=24, weight="bold"), text_color=TEXT_COLOR)
        self.results_title.grid(row=0, column=0, padx=10, pady=(0, 10), sticky="w")

        self.results_frame = ctk.CTkScrollableFrame(self.right_panel, fg_color="transparent")
        self.results_frame.grid(row=1, column=0, sticky="nsew")

    # FIX #1 + #11: draw_dot_grid z debouncingiem — rysuje tylko 150ms po ostatnim zdarzeniu resize
    def draw_dot_grid(self, event=None):
        if self._dot_resize_timer is not None:
            self.after_cancel(self._dot_resize_timer)
        self._dot_resize_timer = self.after(150, self._redraw_dots)

    def _redraw_dots(self):
        self._dot_resize_timer = None
        self.bg_canvas.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        dot_color = "#3a3a3a"
        spacing = 76
        for x in range(0, w, spacing):
            for y in range(0, h, spacing):
                self.bg_canvas.create_rectangle(x, y, x + 2, y + 2, fill=dot_color, outline="")

    # --- FUNKCJE INTERFEJSU ---

    def select_folder(self):
        folder = filedialog.askdirectory(title="WYBIERZ FOLDER")
        if folder:
            self.folder_path = folder
            self.folder_label.configure(text=folder, text_color=TEXT_COLOR)

    def toggle_search(self):
        if self.search_thread and self.search_thread.is_alive():
            # FIX #4: używamy threading.Event zamiast bool
            self._cancel_event.set()
            self.action_btn.configure(text="[ ZATRZYMYWANIE... ]", state="disabled", fg_color=TEXT_MUTED)
            self.status_label.configure(text="SYS.ABORTING...")
        else:
            self.start_search()

    def start_search(self):
        query = self.search_entry.get().strip()

        if not self.folder_path:
            self.status_label.configure(text="ERR: BRAK_FOLDERU", text_color=ACCENT_RED)
            return
        if not query:
            self.status_label.configure(text="ERR: PUSTA_FRAZA", text_color=ACCENT_RED)
            return

        # FIX #4: reset threading.Event
        self._cancel_event.clear()

        # FIX #5 + #13: reset liczników
        self.found_count = 0
        self._skipped_count = 0

        self.clear_results()
        self.status_label.configure(text="SYS.SCANNING...", text_color=TEXT_MUTED)

        self.action_btn.configure(
            text="[ PRZERWIJ ]",
            fg_color=ACCENT_RED,
            text_color="white",
            hover_color=ACCENT_RED_HOVER,
            state="normal"
        )

        self.progress_canvas.grid()
        # FIX #10: reset animacji przy nowym skanie
        self.animation_step = 0
        self.is_animating = True
        self.animate_dots()

        self.search_thread = threading.Thread(target=self.search_logic, args=(query,))
        self.search_thread.daemon = True
        self.search_thread.start()

    def clear_results(self):
        for widget in self.results_frame.winfo_children():
            widget.destroy()

    def add_result(self, filepath, page_num):
        filename = os.path.basename(filepath)

        card = ctk.CTkFrame(self.results_frame, corner_radius=0, fg_color=PANEL_BG, border_width=1, border_color=BORDER_COLOR)
        card.pack(fill="x", pady=6, padx=5)

        card.grid_columnconfigure(0, weight=1)
        card.grid_columnconfigure(1, weight=0)
        card.grid_columnconfigure(2, weight=0)
        card.grid_columnconfigure(3, weight=0)  # FIX #8: kolumna dla przycisku FOLDER

        # FIX #17: efekt hover na karcie — subtelna zmiana koloru ramki
        def on_enter(e, c=card): c.configure(border_color="#444444")
        def on_leave(e, c=card): c.configure(border_color=BORDER_COLOR)
        card.bind("<Enter>", on_enter)
        card.bind("<Leave>", on_leave)

        info_frame = ctk.CTkFrame(card, fg_color="transparent")
        info_frame.grid(row=0, column=0, padx=15, pady=15, sticky="ew")

        title_label = ctk.CTkLabel(info_frame, text=filename, font=ctk.CTkFont(family=NORMAL_FONT, weight="bold", size=15), anchor="w", justify="left", text_color=TEXT_COLOR)
        title_label.configure(wraplength=350)
        title_label.pack(fill="x")

        # FIX #16: path_entry z subtelnym tłem sygnalizującym "tylko do odczytu"
        path_entry = ctk.CTkEntry(info_frame, font=ctk.CTkFont(family=NORMAL_FONT, size=11),
                                  text_color=TEXT_MUTED, fg_color="#1a1a1a",
                                  border_width=1, border_color=BORDER_COLOR, height=22)
        path_entry.insert(0, filepath)
        path_entry.configure(state="readonly")
        path_entry.pack(fill="x", pady=(4, 0))

        page_label = ctk.CTkLabel(info_frame, text=f"STRONA: {page_num}", font=ctk.CTkFont(family=NORMAL_FONT, size=13), text_color=TEXT_MUTED, anchor="w")
        page_label.pack(fill="x", pady=(2, 0))

        # FIX #7: zmiana etykiety na "[ ŚCIEŻKA ]" — jasno wskazuje co jest kopiowane
        # FIX #2/3: lambda f=filepath zamiast f=filename
        copy_btn = ctk.CTkButton(card, text="[ ŚCIEŻKA ]", width=90, corner_radius=0,
                                 fg_color="transparent", border_width=1, border_color=TEXT_MUTED,
                                 text_color=TEXT_COLOR, hover_color="#333333",
                                 font=ctk.CTkFont(family=FONT_FAMILY, weight="bold", size=13),
                                 command=lambda f=filepath: self.copy_to_clipboard(f))
        copy_btn.grid(row=0, column=1, padx=(10, 5), pady=15, sticky="e")

        # FIX #8: nowy przycisk otwierający folder w Eksploratorze
        folder_btn = ctk.CTkButton(card, text="[ FOLDER ]", width=90, corner_radius=0,
                                   fg_color="transparent", border_width=1, border_color=TEXT_MUTED,
                                   text_color=TEXT_COLOR, hover_color="#333333",
                                   font=ctk.CTkFont(family=FONT_FAMILY, weight="bold", size=13),
                                   command=lambda f=filepath: self.open_folder(f))
        folder_btn.grid(row=0, column=2, padx=(0, 5), pady=15, sticky="e")

        open_btn = ctk.CTkButton(card, text="[ OTWÓRZ ]", width=90, corner_radius=0,
                                 fg_color=TEXT_COLOR, text_color="black", hover_color="#e0e0e0",
                                 font=ctk.CTkFont(family=FONT_FAMILY, weight="bold", size=13),
                                 command=lambda f=filepath: self.open_file(f))
        open_btn.grid(row=0, column=3, padx=(0, 15), pady=15, sticky="e")

        # FIX #5: aktualizacja licznika na żywo
        self.found_count += 1
        suffix = f" // POMINIĘTO: {self._skipped_count}" if self._skipped_count > 0 else ""
        self.status_label.configure(
            text=f"SYS.SCANNING... // ZNALEZIONO: {self.found_count}{suffix}",
            text_color=TEXT_MUTED
        )

    def copy_to_clipboard(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)
        short = text if len(text) <= 30 else f"...{text[-27:]}"
        self.status_label.configure(text=f"SYS.COPIED: {short}", text_color=TEXT_COLOR)

    def open_file(self, filepath):
        try:
            if platform.system() == "Windows":
                os.startfile(filepath)
            elif platform.system() == "Darwin":
                subprocess.call(["open", filepath])
            else:
                subprocess.call(["xdg-open", filepath])
        except Exception as e:
            self.status_label.configure(text="ERR: FILE_OPEN_FAILED", text_color=ACCENT_RED)
            print(f"Error opening file: {e}")

    # FIX #8: nowa metoda otwierająca folder z zaznaczonym plikiem
    def open_folder(self, filepath):
        try:
            if platform.system() == "Windows":
                norm_path = os.path.normpath(filepath)
                subprocess.Popen(f'explorer /select,"{norm_path}"')
            elif platform.system() == "Darwin":
                subprocess.call(["open", os.path.dirname(filepath)])
            else:
                subprocess.call(["xdg-open", os.path.dirname(filepath)])
        except Exception as e:
            self.status_label.configure(text="ERR: FOLDER_OPEN_FAILED", text_color=ACCENT_RED)
            print(f"Error opening folder: {e}")

    # FIX #13: informowanie o pominiętych plikach PDF (wywołane z wątku przez self.after)
    def _report_skipped(self, filepath):
        self._skipped_count += 1
        suffix = f" // POMINIĘTO: {self._skipped_count}"
        found_part = f"ZNALEZIONO: {self.found_count} //" if self.found_count > 0 else ""
        self.status_label.configure(
            text=f"SYS.SCANNING... // {found_part}{suffix}",
            text_color=TEXT_MUTED
        )

    # --- LOGIKA WYSZUKIWANIA ---

    def animate_dots(self):
        if not self.is_animating:
            return

        self.progress_canvas.delete("all")
        width = self.progress_canvas.winfo_width()
        if width <= 1:
            width = 280

        dot_size = 4
        spacing = 8
        num_dots = max(1, width // (dot_size + spacing))

        start_x = (width - (num_dots * (dot_size + spacing) - spacing)) / 2

        active_count = self.animation_step % (num_dots + 1)

        for i in range(num_dots):
            x = start_x + i * (dot_size + spacing)
            color = ACCENT_RED if i < active_count else "#333333"
            self.progress_canvas.create_rectangle(x, 2, x + dot_size, 2 + dot_size, fill=color, outline="")

        self.animation_step += 1
        self.after(50, self.animate_dots)

    def search_logic(self, query):
        scanned_count = 0
        found_count = 0
        query_lower = query.lower()

        for root, dirs, files in os.walk(self.folder_path):
            # FIX #4: używamy threading.Event.is_set()
            if self._cancel_event.is_set():
                break

            for file in files:
                if self._cancel_event.is_set():
                    break

                if file.lower().endswith(".pdf"):
                    scanned_count += 1
                    filepath = os.path.join(root, file)

                    try:
                        doc = fitz.open(filepath)
                        for page in doc:
                            if self._cancel_event.is_set():
                                break

                            text = page.get_text()
                            if query_lower in text.lower():
                                self.after(0, self.add_result, filepath, page.number + 1)
                                found_count += 1
                                break
                        doc.close()
                    except Exception as e:
                        # FIX #13: raportowanie uszkodzonych/niedostępnych plików
                        print(f"Skipped '{filepath}': {e}")
                        self.after(0, self._report_skipped, filepath)

        self.after(0, self.finish_search, scanned_count, found_count)

    def finish_search(self, scanned_count, found_count):
        self.is_animating = False
        self.progress_canvas.grid_remove()

        self.action_btn.configure(
            text="[ ROZPOCZNIJ SKAN ]",
            fg_color=TEXT_COLOR,
            text_color="black",
            hover_color="#e0e0e0",
            state="normal"
        )

        # FIX #4: is_set() zamiast bool
        cancelled = self._cancel_event.is_set()
        prefix = "SYS.ABORTED" if cancelled else "SYS.DONE"
        skipped_part = f" // BŁĘDY: {self._skipped_count}" if self._skipped_count > 0 else ""
        status_text = f"{prefix} // SKAN: {scanned_count} // ZNALEZIONO: {found_count}{skipped_part}"

        if found_count == 0 and not cancelled:
            self.status_label.configure(text=status_text, text_color=TEXT_MUTED)
            empty_lbl = ctk.CTkLabel(self.results_frame, text="< BRAK_WYNIKÓW >", text_color=TEXT_MUTED, font=ctk.CTkFont(family=FONT_FAMILY, size=16))
            empty_lbl.pack(pady=40)
        else:
            self.status_label.configure(text=status_text, text_color=TEXT_COLOR)

if __name__ == "__main__":
    app = ModernPDFSearch()
    app.mainloop()
