import customtkinter as ctk
import os
import fitz  # PyMuPDF
import threading
from tkinter import filedialog
import subprocess
import platform
import ctypes
import sys
import time

# --- ZAŁADOWANIE FONTU Z PLIKU ---
def load_font(font_path):
    if os.path.exists(font_path):
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

# --- DESIGN TOKENS NOTHING OS (DARK INDUSTRIAL) ---
ctk.set_appearance_mode("dark")
COLOR_BG = "#0a0a0a"             # Głęboka czerń tła
COLOR_PANEL = "#121212"          # Panele boczne i karty
COLOR_SURFACE_INPUT = "#181818"  # Wnętrza pól tekstowych
COLOR_DOT_GRID = "#1e1e1e"       # Dyskretna matryca tła
COLOR_BORDER = "#222222"         # Ramki spoczynkowe
COLOR_BORDER_HOVER = "#444444"   # Ramki aktywne / hover
COLOR_BORDER_BTN = "#2a2a2a"     # Obramowanie przycisków drugorzędnych
COLOR_RED = "#ff2a2a"            # Nothing Red
COLOR_RED_HOVER = "#cc1111"      # Czerwony hover
COLOR_TEXT_PRIMARY = "#ffffff"   # Główny tekst
COLOR_TEXT_MUTED = "#888888"     # Metadane i etykiety drugorzędne (kontrast 5.6:1)

FONT_FAMILY = "Doto"            # Branding, główne przyciski
NORMAL_FONT = "Segoe UI"        # Czytelny font dla nazw plików i etykiet
TECH_FONT = "Consolas"          # Ścieżki, logi statusu, numery stron

MAX_RESULTS = 500               # Twardy limit bezpieczeństwa przed wyczerpaniem uchwytów GDI

# --- FUNKCJE POMOCNICZE (DEFENSIVE PROGRAMMING) ---
def safe_win_path(p):
    """Normalizacja do rozszerzonej składni ścieżek Windows (MAX_PATH > 260 znaków)."""
    p = os.path.abspath(p)
    if platform.system() == "Windows" and len(p) >= 240 and not p.startswith("\\\\?\\"):
        return f"\\\\?\\{p}"
    return p

def truncate_middle(text, max_len=55):
    """Skracanie długich nazw ze środka z zachowaniem początku i rozszerzenia."""
    if len(text) <= max_len:
        return text
    half = (max_len - 3) // 2
    return f"{text[:half]}...{text[-half:]}"

def lerp_color(c1, c2, factor):
    """Interpolacja liniowa pomiędzy dwoma kolorami HEX (#rrggbb)."""
    factor = max(0.0, min(1.0, factor))
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    return f"#{int(r1+(r2-r1)*factor):02x}{int(g1+(g2-g1)*factor):02x}{int(b1+(b2-b1)*factor):02x}"


# --- PŁYWAJĄCY TOAST MANAGER (SONNER-INSPIRED) ---
class ToastNotification:
    def __init__(self, master):
        self.master = master
        self.frame = ctk.CTkFrame(
            master,
            corner_radius=0,
            fg_color="#141414",
            border_width=1,
            border_color=COLOR_BORDER_HOVER
        )
        self.title_label = ctk.CTkLabel(
            self.frame,
            text="",
            font=ctk.CTkFont(family=NORMAL_FONT, weight="bold", size=12),
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w"
        )
        self.title_label.pack(padx=14, pady=(8, 2), anchor="w")

        self.sub_label = ctk.CTkLabel(
            self.frame,
            text="",
            font=ctk.CTkFont(family=TECH_FONT, size=11),
            text_color=COLOR_TEXT_MUTED,
            anchor="w"
        )
        self.sub_label.pack(padx=14, pady=(0, 8), anchor="w")
        self._timer = None

    def show(self, title, subtitle="", kind="info"):
        if self._timer is not None:
            self.master.after_cancel(self._timer)

        border_col = COLOR_RED if kind == "error" else (COLOR_TEXT_PRIMARY if kind == "success" else COLOR_BORDER_HOVER)
        self.frame.configure(border_color=border_col)
        self.title_label.configure(text=title)

        if subtitle:
            self.sub_label.configure(text=truncate_middle(subtitle, 50))
            self.sub_label.pack(padx=14, pady=(0, 8), anchor="w")
        else:
            self.sub_label.pack_forget()

        self.frame.place(relx=0.98, rely=0.96, anchor="se")
        self.frame.lift()
        self._timer = self.master.after(3000, self.hide)

    def hide(self):
        self._timer = None
        self.frame.place_forget()


# --- GŁÓWNA APLIKACJA ---
class ModernPDFSearch(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("SYS.SEARCH // PDF")
        self.geometry("1100x700")
        self.minsize(900, 500)
        self.configure(fg_color=COLOR_BG)

        if os.path.exists(icon_file):
            self.iconbitmap(icon_file)

        # Zmienne stanu
        self.folder_path = ""
        self.search_thread = None
        self._cancel_event = threading.Event()

        # Liczniki wyników
        self.found_count = 0
        self._skipped_count = 0
        self._limit_reached = False

        # Kolejka kaskadowa (Staggered Reveal Queue)
        self._result_queue = []
        self._is_draining = False

        # Tło w kropki (Dot Grid Canvas)
        self.bg_canvas = ctk.CTkCanvas(self, bg=COLOR_BG, highlightthickness=0)
        self.bg_canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.bind("<Configure>", self.draw_dot_grid)
        self._dot_resize_timer = None

        # Układ główny
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ==========================================
        # PANEL BOCZNY (Lewa Strona - Kontrolki)
        # ==========================================
        self.left_panel = ctk.CTkFrame(self, width=320, corner_radius=0, fg_color=COLOR_PANEL, border_width=1, border_color=COLOR_BORDER)
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=(20, 10), pady=20)
        self.left_panel.grid_rowconfigure(4, weight=1)
        self.left_panel.grid_columnconfigure(0, weight=1)

        # Tytuł aplikacji
        self.logo_label = ctk.CTkLabel(
            self.left_panel,
            text="[ PDF_SEARCH ]",
            font=ctk.CTkFont(family=FONT_FAMILY, size=28, weight="bold"),
            text_color=COLOR_RED
        )
        self.logo_label.grid(row=0, column=0, padx=20, pady=(30, 20), sticky="w")

        # 1. Wybór folderu
        self.folder_btn = ctk.CTkButton(
            self.left_panel,
            text="> WYBIERZ FOLDER",
            command=self.select_folder,
            corner_radius=0,
            fg_color="transparent",
            border_width=1,
            border_color=COLOR_BORDER_BTN,
            text_color=COLOR_TEXT_PRIMARY,
            hover_color="#222222",
            font=ctk.CTkFont(family=FONT_FAMILY, weight="bold", size=14)
        )
        self.folder_btn.grid(row=1, column=0, padx=20, pady=(10, 5), sticky="ew")

        self.folder_label = ctk.CTkLabel(
            self.left_panel,
            text="BRAK_ŚCIEŻKI",
            text_color=COLOR_TEXT_MUTED,
            wraplength=260,
            justify="left",
            font=ctk.CTkFont(family=NORMAL_FONT, size=13)
        )
        self.folder_label.grid(row=2, column=0, padx=20, pady=(0, 20), sticky="w")

        # 2. Wyszukiwanie
        self.search_entry = ctk.CTkEntry(
            self.left_panel,
            placeholder_text="WPROWADŹ FRAZĘ...",
            height=45,
            corner_radius=0,
            border_color=COLOR_BORDER,
            fg_color=COLOR_BG,
            text_color=COLOR_TEXT_PRIMARY,
            font=ctk.CTkFont(family=NORMAL_FONT, size=15)
        )
        self.search_entry.grid(row=3, column=0, padx=20, pady=(0, 15), sticky="ew")
        self.search_entry.bind("<Return>", lambda event: self.toggle_search())

        # 3. Główny przycisk Szukaj / Przerwij
        self.action_btn = ctk.CTkButton(
            self.left_panel,
            text="[ ROZPOCZNIJ SKAN ]",
            height=50,
            corner_radius=0,
            fg_color=COLOR_TEXT_PRIMARY,
            text_color="black",
            hover_color="#e0e0e0",
            font=ctk.CTkFont(family=FONT_FAMILY, weight="bold", size=16),
            command=self.toggle_search
        )
        self.action_btn.grid(row=4, column=0, padx=20, pady=(0, 10), sticky="sew")

        # Stały wiersz dla paska postępu (Zero Layout Shift)
        self.progress_canvas = ctk.CTkCanvas(self.left_panel, bg=COLOR_PANEL, highlightthickness=0, height=8)
        self.progress_canvas.grid(row=5, column=0, padx=20, pady=(0, 10), sticky="new")
        self.num_dots = 0
        self.dot_ids = []
        self.is_animating = False
        self._anim_start_time = 0

        # 4. Status na dole (Czytelny font Consolas)
        self.status_label = ctk.CTkLabel(
            self.left_panel,
            text="SYS.READY",
            text_color=COLOR_TEXT_MUTED,
            font=ctk.CTkFont(family=TECH_FONT, size=11),
            justify="left",
            wraplength=270
        )
        self.status_label.grid(row=6, column=0, padx=20, pady=20, sticky="sw")

        # ==========================================
        # PANEL GŁÓWNY (Prawa Strona - Wyniki)
        # ==========================================
        self.right_panel = ctk.CTkFrame(self, fg_color="transparent")
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=(10, 20), pady=20)
        self.right_panel.grid_rowconfigure(1, weight=1)
        self.right_panel.grid_columnconfigure(0, weight=1)

        self.results_title = ctk.CTkLabel(
            self.right_panel,
            text="// WYNIKI [ 0 ]",
            font=ctk.CTkFont(family=FONT_FAMILY, size=24, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY
        )
        self.results_title.grid(row=0, column=0, padx=10, pady=(0, 10), sticky="w")

        self.results_frame = ctk.CTkScrollableFrame(self.right_panel, fg_color="transparent")
        self.results_frame.grid(row=1, column=0, sticky="nsew")

        # Toast manager
        self.toast = ToastNotification(self)

        # Skróty klawiszowe (Keyboard-First)
        self.bind("<Control-f>", lambda e: self.focus_search())
        self.bind("<Control-F>", lambda e: self.focus_search())
        self.bind("<Control-o>", lambda e: self.select_folder())
        self.bind("<Control-O>", lambda e: self.select_folder())
        self.bind("<Escape>", lambda e: self.handle_escape())

        # Pusty stan początkowy (Onboarding Standby)
        self.show_standby_state()

    # --- SKRÓTY I INTERAKCJA ---
    def focus_search(self):
        self.search_entry.focus_set()
        self.search_entry.select_range(0, 'end')
        return "break"

    def handle_escape(self):
        if self.search_thread and self.search_thread.is_alive():
            self.toggle_search()
        else:
            self.search_entry.delete(0, 'end')

    # --- ARCHITEKTONICZNY DOT GRID ---
    def draw_dot_grid(self, event=None):
        if self._dot_resize_timer is not None:
            self.after_cancel(self._dot_resize_timer)
        self._dot_resize_timer = self.after(120, self._redraw_dots)

    def _redraw_dots(self):
        self._dot_resize_timer = None
        self.bg_canvas.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        spacing = 36 if max(w, h) > 2000 else 28
        for x in range(0, w, spacing):
            for y in range(0, h, spacing):
                self.bg_canvas.create_rectangle(x, y, x + 2, y + 2, fill=COLOR_DOT_GRID, outline="")

    # --- STAN POCZĄTKOWY I PUSTY ---
    def show_standby_state(self):
        self.clear_results()
        self.results_title.configure(text="// WYNIKI [ 0 ]")
        box = ctk.CTkFrame(self.results_frame, fg_color="transparent")
        box.pack(expand=True, pady=90)
        ctk.CTkLabel(
            box,
            text="// SYS.STANDBY",
            font=ctk.CTkFont(family=FONT_FAMILY, size=20, weight="bold"),
            text_color=COLOR_TEXT_MUTED
        ).pack(pady=(0, 8))
        ctk.CTkLabel(
            box,
            text="WYBIERZ FOLDER (CTRL+O) I WPROWADŹ FRAZĘ KLUCZOWĄ (CTRL+F),\nABY ROZPOCZĄĆ INDEKSOWANIE STRON PDF.",
            font=ctk.CTkFont(family=NORMAL_FONT, size=12),
            text_color="#555555",
            justify="center"
        ).pack()

    def show_empty_results(self):
        self.clear_results()
        self.results_title.configure(text="// WYNIKI [ 0 ]")
        box = ctk.CTkFrame(self.results_frame, fg_color="transparent")
        box.pack(expand=True, pady=90)
        ctk.CTkLabel(
            box,
            text="< BRAK_WYNIKÓW >",
            font=ctk.CTkFont(family=FONT_FAMILY, size=18, weight="bold"),
            text_color=COLOR_TEXT_MUTED
        ).pack(pady=(0, 8))
        ctk.CTkLabel(
            box,
            text="ŻADEN DOKUMENT W WYBRANYM KATALOGU NIE ZAWIERA PODANEJ FRAZY.",
            font=ctk.CTkFont(family=NORMAL_FONT, size=12),
            text_color="#555555"
        ).pack()

    # --- BŁĄD WALIDACJI (KIERUNKOWY BŁYSK) ---
    def trigger_input_error(self, widget):
        orig_border = widget.cget("border_color")
        widget.configure(border_color=COLOR_RED)
        self.after(80, lambda: widget.configure(border_color="#aa1111"))
        self.after(220, lambda: widget.configure(border_color=orig_border))

    # --- WYBÓR FOLDERU ---
    def select_folder(self):
        folder = filedialog.askdirectory(title="WYBIERZ FOLDER DO PRZESZUKANIA")
        if folder:
            self.folder_path = folder
            self.folder_label.configure(
                text=truncate_middle(folder, 36),
                text_color=COLOR_TEXT_PRIMARY
            )
            self.toast.show("WYBRANO FOLDER", folder, kind="info")

    # --- ZARZĄDZANIE WYSZUKIWANIEM ---
    def toggle_search(self):
        if self.search_thread and self.search_thread.is_alive():
            self._cancel_event.set()
            self.action_btn.configure(text="[ ZATRZYMYWANIE... ]", state="disabled", fg_color="#333333")
            self._abort_step = 0
            self._animate_abort()
        else:
            self.start_search()

    def _animate_abort(self):
        if self.search_thread and self.search_thread.is_alive():
            dots = "." * ((self._abort_step % 3) + 1)
            self.status_label.configure(text=f"SYS.ABORTING{dots}")
            btn_col = "#3a3a3a" if (self._abort_step % 2 == 0) else "#222222"
            self.action_btn.configure(fg_color=btn_col)
            self._abort_step += 1
            self.after(200, self._animate_abort)

    def start_search(self):
        raw_query = self.search_entry.get()
        query = " ".join(raw_query.split())

        if not self.folder_path:
            self.status_label.configure(text="ERR: BRAK_FOLDERU", text_color=COLOR_RED)
            self.trigger_input_error(self.folder_btn)
            self.toast.show("BRAK FOLDERU", "Wskaż katalog przed rozpoczęciem", kind="error")
            return
        if not query:
            self.status_label.configure(text="ERR: PUSTA_FRAZA", text_color=COLOR_RED)
            self.trigger_input_error(self.search_entry)
            self.toast.show("PUSTA FRAZA", "Wpisz szukany tekst", kind="error")
            return
        if len(query) < 2:
            self.status_label.configure(text="ERR: MIN_2_ZNAKI", text_color=COLOR_RED)
            self.trigger_input_error(self.search_entry)
            self.toast.show("ZBYT KRÓTKA FRAZA", "Wymagane minimum 2 znaki", kind="error")
            return

        self._cancel_event.clear()
        self.found_count = 0
        self._skipped_count = 0
        self._limit_reached = False
        self._result_queue.clear()
        self._is_draining = False

        self.clear_results()
        self.results_title.configure(text="// WYNIKI [ 0 ]")
        self.status_label.configure(text="SYS.SCANNING...", text_color=COLOR_TEXT_MUTED)

        self.action_btn.configure(
            text="[ PRZERWIJ ]",
            fg_color=COLOR_RED,
            text_color="white",
            hover_color=COLOR_RED_HOVER,
            state="normal"
        )

        # Start animacji LED Wave
        self.init_progress_dots()
        self.is_animating = True
        self.animate_dots()

        self.search_thread = threading.Thread(target=self.search_logic, args=(query,))
        self.search_thread.daemon = True
        self.search_thread.start()

    def clear_results(self):
        for widget in self.results_frame.winfo_children():
            widget.destroy()

    # --- PŁYNNA ANIMACJA FALI LED (NOTHING MARQUEE WAVE) ---
    def init_progress_dots(self):
        self.progress_canvas.delete("all")
        width = self.progress_canvas.winfo_width()
        if width <= 1:
            width = 280

        dot_size = 4
        spacing = 8
        self.num_dots = max(1, width // (dot_size + spacing))
        start_x = (width - (self.num_dots * (dot_size + spacing) - spacing)) / 2

        self.dot_ids = []
        for i in range(self.num_dots):
            x = start_x + i * (dot_size + spacing)
            dot_id = self.progress_canvas.create_rectangle(
                x, 2, x + dot_size, 2 + dot_size,
                fill="#1c1c1c", outline=""
            )
            self.dot_ids.append(dot_id)
        self._anim_start_time = time.perf_counter()

    def animate_dots(self):
        if not self.is_animating:
            return
        if not self.dot_ids or len(self.dot_ids) != self.num_dots:
            self.init_progress_dots()

        now = time.perf_counter()
        elapsed = now - self._anim_start_time
        speed = 1.1  # Cykl fali co 1.1 sekundy
        cycle_pos = (elapsed * speed) % 1.0
        center_index = cycle_pos * (self.num_dots + 4) - 2

        base_color = "#1c1c1c"
        peak_color = COLOR_RED

        for i, dot_id in enumerate(self.dot_ids):
            dist = abs(i - center_index)
            if dist < 3.2:
                intensity = max(0.0, 1.0 - (dist / 3.2) ** 2)
                color = lerp_color(base_color, peak_color, intensity)
            else:
                color = base_color
            self.progress_canvas.itemconfig(dot_id, fill=color)

        self.after(30, self.animate_dots)

    def reset_progress_dots(self):
        self.is_animating = False
        if hasattr(self, 'dot_ids'):
            for dot_id in self.dot_ids:
                self.progress_canvas.itemconfig(dot_id, fill="#1c1c1c")

    # --- KASKADOWY BUFOR WYNIKÓW (STAGGERED REVEAL) ---
    def queue_result(self, filepath, page_numbers):
        self._result_queue.append((filepath, page_numbers))
        if not self._is_draining:
            self._is_draining = True
            self.after(20, self._drain_result_queue)

    def _drain_result_queue(self):
        if self._cancel_event.is_set() or not self._result_queue:
            self._is_draining = False
            return

        # Drenaż adaptacyjny (1-3 karty na tick zależnie od obciążenia)
        batch = 2 if len(self._result_queue) > 10 else 1
        for _ in range(batch):
            if not self._result_queue:
                break
            filepath, page_numbers = self._result_queue.pop(0)
            self.add_result(filepath, page_numbers)

        delay = 15 if len(self._result_queue) > 10 else 28
        self.after(delay, self._drain_result_queue)

    # --- KARTA WYNIKU ---
    def add_result(self, filepath, page_numbers):
        if self._cancel_event.is_set():
            return

        filename = os.path.basename(filepath)
        self.found_count += 1
        self.results_title.configure(text=f"// WYNIKI [ {self.found_count} ]")

        # Karta z wejściowym border-flashem
        card = ctk.CTkFrame(
            self.results_frame,
            corner_radius=0,
            fg_color=COLOR_PANEL,
            border_width=1,
            border_color=COLOR_RED  # Rozbłysk wejściowy
        )
        card.pack(fill="x", pady=5, padx=5)

        card.grid_columnconfigure(0, weight=1)
        card.grid_columnconfigure(1, weight=0)
        card.grid_columnconfigure(2, weight=0)
        card.grid_columnconfigure(3, weight=0)

        # 2-etapowy zanik rozbłysku (180ms ease-out)
        self.after(90, lambda: card.configure(border_color="#444444") if card.winfo_exists() else None)
        self.after(180, lambda: card.configure(border_color=COLOR_BORDER) if card.winfo_exists() else None)

        # Odporny na migotanie hover
        self.setup_card_hover(card)

        info_frame = ctk.CTkFrame(card, fg_color="transparent")
        info_frame.grid(row=0, column=0, padx=15, pady=12, sticky="ew")

        # 1. Wiersz: Tytuł pliku (KLIKNIJ, ABY SKOPIOWAĆ NAZWĘ PLIKU!)
        title_row = ctk.CTkFrame(info_frame, fg_color="transparent")
        title_row.pack(fill="x", anchor="w")

        title_label = ctk.CTkLabel(
            title_row,
            text=truncate_middle(filename, 55),
            font=ctk.CTkFont(family=NORMAL_FONT, weight="bold", size=15),
            anchor="w",
            text_color=COLOR_TEXT_PRIMARY,
            cursor="hand2"
        )
        title_label.pack(side="left")

        # Etykietka podpowiedzi hover
        hint_label = ctk.CTkLabel(
            title_row,
            text="[KLIKNIJ ABY SKOPIOWAĆ NAZWĘ]",
            font=ctk.CTkFont(family=TECH_FONT, size=9),
            text_color="#444444"
        )

        def on_title_enter(e):
            title_label.configure(text_color=COLOR_RED)
            hint_label.pack(side="left", padx=(10, 0))

        def on_title_leave(e):
            title_label.configure(text_color=COLOR_TEXT_PRIMARY)
            hint_label.pack_forget()

        def on_title_click(e, fn=filename, lbl=title_label):
            self.copy_filename_to_clipboard(fn, lbl)

        title_label.bind("<Enter>", on_title_enter)
        title_label.bind("<Leave>", on_title_leave)
        title_label.bind("<Button-1>", on_title_click)

        # 2. Wiersz: Numer strony / stron
        if len(page_numbers) == 1:
            page_text = f"STRONA // {page_numbers[0]}"
        elif len(page_numbers) <= 4:
            pages_str = ", ".join(map(str, page_numbers))
            page_text = f"STRONY // {pages_str}"
        else:
            pages_str = ", ".join(map(str, page_numbers[:3]))
            page_text = f"STRONY // {pages_str} (+{len(page_numbers)-3} INNYCH)"

        page_label = ctk.CTkLabel(
            info_frame,
            text=page_text,
            font=ctk.CTkFont(family=TECH_FONT, size=11, weight="bold"),
            text_color=COLOR_TEXT_MUTED,
            anchor="w"
        )
        page_label.pack(fill="x", pady=(2, 4))

        # 3. Wiersz: Ścieżka (Consolas, readonly, tło #181818)
        path_entry = ctk.CTkEntry(
            info_frame,
            font=ctk.CTkFont(family=TECH_FONT, size=11),
            text_color=COLOR_TEXT_MUTED,
            fg_color=COLOR_SURFACE_INPUT,
            border_width=1,
            border_color=COLOR_BORDER,
            height=24
        )
        path_entry.insert(0, filepath)
        path_entry.configure(state="readonly")
        path_entry.pack(fill="x", pady=(2, 0))

        # Przyciski akcji (Wysokość 32px dla ergonomii)
        copy_btn = ctk.CTkButton(
            card,
            text="[ ŚCIEŻKA ]",
            width=100,
            height=32,
            corner_radius=0,
            fg_color="transparent",
            border_width=1,
            border_color=COLOR_BORDER_BTN,
            text_color=COLOR_TEXT_PRIMARY,
            hover_color="#222222",
            font=ctk.CTkFont(family=FONT_FAMILY, weight="bold", size=13),
            command=lambda f=filepath, b=None: self.copy_path_to_clipboard(f, copy_btn)
        )
        copy_btn.grid(row=0, column=1, padx=(10, 5), pady=12, sticky="e")

        folder_btn = ctk.CTkButton(
            card,
            text="[ FOLDER ]",
            width=90,
            height=32,
            corner_radius=0,
            fg_color="transparent",
            border_width=1,
            border_color=COLOR_BORDER_BTN,
            text_color=COLOR_TEXT_PRIMARY,
            hover_color="#222222",
            font=ctk.CTkFont(family=FONT_FAMILY, weight="bold", size=13),
            command=lambda f=filepath: self.open_folder(f)
        )
        folder_btn.grid(row=0, column=2, padx=(0, 5), pady=12, sticky="e")

        open_btn = ctk.CTkButton(
            card,
            text="[ OTWÓRZ ]",
            width=95,
            height=32,
            corner_radius=0,
            fg_color=COLOR_TEXT_PRIMARY,
            text_color="black",
            hover_color="#e0e0e0",
            font=ctk.CTkFont(family=FONT_FAMILY, weight="bold", size=13),
            command=lambda f=filepath: self.open_file(f)
        )
        open_btn.grid(row=0, column=3, padx=(0, 15), pady=12, sticky="e")

        # Aktualizacja statusu
        suffix = f" // BŁĘDY: {self._skipped_count}" if self._skipped_count > 0 else ""
        self.status_label.configure(
            text=f"SYS.SCANNING... // ZNALEZIONO: {self.found_count}{suffix}"
        )

    # --- FLICKER-FREE HOVER KARTY ---
    def setup_card_hover(self, card):
        def on_enter(e):
            card.configure(border_color=COLOR_BORDER_HOVER)

        def on_leave(e):
            try:
                x, y = card.winfo_pointerxy()
                widget_under = card.winfo_containing(x, y)
                if widget_under is not None and str(widget_under).startswith(str(card)):
                    return
            except Exception:
                pass
            card.configure(border_color=COLOR_BORDER)

        card.bind("<Enter>", on_enter)
        card.bind("<Leave>", on_leave)

    # --- KOPIOWANIE NAZWY PLIKU Z NAZWY PLIKU ---
    def copy_filename_to_clipboard(self, filename, label_widget=None):
        try:
            self.clipboard_clear()
            self.clipboard_append(filename)
            self.update()
            self.toast.show("SKOPIOWANO NAZWĘ PLIKU", filename, kind="success")
        except Exception:
            self.toast.show("BŁĄD SCHOWKA", "Nie udało się skopiować nazwy", kind="error")
            return

        if label_widget and label_widget.winfo_exists():
            orig_text = label_widget.cget("text")
            label_widget.configure(text=f"[ SKOPIOWANO: {truncate_middle(filename, 35)} ]", text_color=COLOR_RED)
            self.after(1200, lambda: label_widget.configure(text=orig_text, text_color=COLOR_TEXT_PRIMARY) if label_widget.winfo_exists() else None)

    # --- KOPIOWANIE ŚCIEŻKI DO SCHOWKA ---
    def copy_path_to_clipboard(self, filepath, btn=None):
        try:
            self.clipboard_clear()
            self.clipboard_append(filepath)
            self.update()
            self.toast.show("SKOPIOWANO ŚCIEŻKĘ", filepath, kind="success")
        except Exception:
            self.toast.show("BŁĄD SCHOWKA", "System Windows zablokował dostęp do schowka", kind="error")
            return

        if btn and btn.winfo_exists():
            orig_text = btn.cget("text")
            btn.configure(
                text="[ SKOPIOWANO ]",
                fg_color=COLOR_TEXT_PRIMARY,
                text_color="black",
                border_color=COLOR_TEXT_PRIMARY
            )
            def restore():
                if btn.winfo_exists():
                    btn.configure(
                        text=orig_text,
                        fg_color="transparent",
                        text_color=COLOR_TEXT_PRIMARY,
                        border_color=COLOR_BORDER_BTN
                    )
            self.after(1200, restore)

    # --- OTWARCIE PLIKU I FOLDERU ---
    def open_file(self, filepath):
        try:
            safe_p = os.path.normpath(filepath)
            if platform.system() == "Windows":
                os.startfile(safe_p)
            elif platform.system() == "Darwin":
                subprocess.call(["open", safe_p])
            else:
                subprocess.call(["xdg-open", safe_p])
        except Exception as e:
            self.toast.show("BŁĄD OTWARCIA PLIKU", str(e), kind="error")

    def open_folder(self, filepath):
        try:
            safe_p = os.path.normpath(filepath)
            if platform.system() == "Windows":
                # Bezpieczne przekazanie argumentów jako lista
                subprocess.Popen(["explorer.exe", f"/select,{safe_p}"])
            elif platform.system() == "Darwin":
                subprocess.call(["open", os.path.dirname(safe_p)])
            else:
                subprocess.call(["xdg-open", os.path.dirname(safe_p)])
        except Exception as e:
            self.toast.show("BŁĄD OTWARCIA FOLDERU", str(e), kind="error")

    def _report_skipped(self, filepath, reason=""):
        self._skipped_count += 1
        suffix = f" // BŁĘDY: {self._skipped_count}"
        found_part = f" // ZNALEZIONO: {self.found_count}" if self.found_count > 0 else ""
        self.status_label.configure(
            text=f"SYS.SCANNING...{found_part}{suffix}"
        )

    def _report_limit_reached(self):
        self._limit_reached = True
        self.toast.show("OSIĄGNIĘTO LIMIT WYNIKÓW", f"Pokazano pierwsze {MAX_RESULTS} trafień", kind="info")
        warn_lbl = ctk.CTkLabel(
            self.results_frame,
            text=f"[ LIMIT {MAX_RESULTS} WYNIKÓW OSIĄGNIĘTY — ZAWĘŹ FRAZĘ WYSZUKIWANIA ]",
            font=ctk.CTkFont(family=TECH_FONT, weight="bold", size=12),
            text_color=COLOR_RED
        )
        warn_lbl.pack(pady=15)

    # --- GŁÓWNA LOGIKA SKANOWANIA (PAN CERNOŚĆ I/O I PAMIĘCI) ---
    def search_logic(self, query):
        scanned_count = 0
        found_count = 0
        query_folded = query.casefold()

        def walk_error_handler(err):
            self.after(0, self._report_skipped, getattr(err, 'filename', 'FOLDER'), str(err))

        try:
            for root, dirs, files in os.walk(self.folder_path, onerror=walk_error_handler):
                if self._cancel_event.is_set() or found_count >= MAX_RESULTS:
                    break

                for file in files:
                    if self._cancel_event.is_set() or found_count >= MAX_RESULTS:
                        break

                    if file.lower().endswith(".pdf"):
                        scanned_count += 1
                        filepath = os.path.join(root, file)
                        doc = None

                        try:
                            safe_path = safe_win_path(filepath)
                            doc = fitz.open(safe_path)

                            # Wczesna weryfikacja hasła PDF
                            if doc.is_encrypted and doc.needs_pass:
                                self.after(0, self._report_skipped, filepath, "HASŁO / ZASZYFROWANY")
                                continue

                            matching_pages = []
                            for page in doc:
                                if self._cancel_event.is_set():
                                    break
                                text = page.get_text()
                                if query_folded in text.casefold():
                                    matching_pages.append(page.number + 1)
                                    if len(matching_pages) >= 15:
                                        break

                            if matching_pages:
                                found_count += 1
                                self.after(0, self.queue_result, filepath, matching_pages)
                                if found_count >= MAX_RESULTS:
                                    self.after(0, self._report_limit_reached)
                                    break

                        except Exception as e:
                            self.after(0, self._report_skipped, filepath, str(e))
                        finally:
                            if doc is not None:
                                try:
                                    doc.close()
                                except Exception:
                                    pass
        except Exception as e:
            self.after(0, self.toast.show, "BŁĄD SKANOWANIA", str(e), "error")

        self.after(0, self.finish_search, scanned_count, found_count)

    def finish_search(self, scanned_count, found_count):
        self.reset_progress_dots()

        self.action_btn.configure(
            text="[ ROZPOCZNIJ SKAN ]",
            fg_color=COLOR_TEXT_PRIMARY,
            text_color="black",
            hover_color="#e0e0e0",
            state="normal"
        )

        cancelled = self._cancel_event.is_set()
        prefix = "SYS.ABORTED" if cancelled else "SYS.DONE"
        skipped_part = f" // BŁĘDY: {self._skipped_count}" if self._skipped_count > 0 else ""
        limit_part = " // [LIMIT]" if self._limit_reached else ""
        status_text = f"{prefix} // SKAN: {scanned_count} // TRAFIENIA: {found_count}{skipped_part}{limit_part}"

        if found_count == 0 and not cancelled:
            self.status_label.configure(text=status_text, text_color=COLOR_TEXT_MUTED)
            self.show_empty_results()
        else:
            self.status_label.configure(text=status_text, text_color=COLOR_TEXT_PRIMARY)
            if not cancelled:
                self.toast.show("SKANOWANIE UKOŃCZONE", f"Przeszukano: {scanned_count} // Trafienia: {found_count}", kind="success")
            else:
                self.toast.show("SKANOWANIE PRZERWANE", f"Przeszukano: {scanned_count}", kind="info")


if __name__ == "__main__":
    app = ModernPDFSearch()
    app.mainloop()
