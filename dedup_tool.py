"""
Herramienta GUI para analizar y eliminar archivos duplicados en Descargas.
Usa customtkinter para la interfaz y hashlib (SHA-256) para comparación exacta.
"""

import os
import hashlib
import threading
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple

import customtkinter as ctk
from tkinter import filedialog, messagebox


# --- Lógica de negocio ---

def get_file_hash(filepath: str, chunk_size: int = 8192) -> str:
    """Calcula el hash SHA-256 de un archivo."""
    sha256 = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            while True:
                data = f.read(chunk_size)
                if not data:
                    break
                sha256.update(data)
        return sha256.hexdigest()
    except (PermissionError, OSError):
        return ""


def scan_duplicates(directory: str, progress_callback=None):
    """
    Escanea un directorio y agrupa archivos por tamaño primero (optimización),
    luego por hash SHA-256 para confirmar duplicados reales.
    Retorna: dict {hash: [lista_de_rutas]} solo con grupos > 1 archivo.
    """
    size_map = defaultdict(list)
    total_files = 0
    skipped_empty = 0
    scanned = 0

    # Fase 1: Agrupar por tamaño
    for root, _, files in os.walk(directory):
        for name in files:
            path = os.path.join(root, name)
            try:
                size = os.path.getsize(path)
                if size > 0:
                    size_map[size].append(path)
                    total_files += 1
                else:
                    skipped_empty += 1
            except OSError:
                continue

    # Fase 2: Hash solo para grupos con mismo tamaño
    hash_map = defaultdict(list)
    candidates = {s: paths for s, paths in size_map.items() if len(paths) > 1}
    candidate_count = sum(len(p) for p in candidates.values())

    for paths in candidates.values():
        for path in paths:
            h = get_file_hash(path)
            if h:
                hash_map[h].append(path)
            scanned += 1
            if progress_callback:
                progress_callback(scanned / max(candidate_count, 1))

    # Filtrar solo verdaderos duplicados
    duplicates = {h: paths for h, paths in hash_map.items() if len(paths) > 1}
    return duplicates, total_files, skipped_empty


def format_size(size_bytes: int) -> str:
    """Formatea bytes a unidad legible."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


# --- GUI ---

class DuplicateCleanerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Eliminador de Duplicados - Descargas")
        self.geometry("900x650")
        self.resizable(True, True)

        # Paleta deliberada: teal/slate para herramientas de sistema
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.duplicates: Dict[str, List[str]] = {}
        self.selected_for_deletion: set = set()
        self.target_dir = ""

        self._build_ui()

    def _build_ui(self):
        # Frame superior: selección de carpeta
        top_frame = ctk.CTkFrame(self, fg_color="transparent")
        top_frame.pack(fill="x", padx=20, pady=(20, 10))

        self.dir_label = ctk.CTkLabel(top_frame, text="Carpeta: (ninguna seleccionada)", anchor="w")
        self.dir_label.pack(side="left", fill="x", expand=True)

        btn_select = ctk.CTkButton(top_frame, text="Seleccionar Carpeta", width=160, command=self._select_folder)
        btn_select.pack(side="right", padx=(10, 0))

        btn_scan = ctk.CTkButton(top_frame, text="Analizar", width=120, command=self._start_scan, state="disabled")
        btn_scan.pack(side="right")
        self.btn_scan = btn_scan

        # Barra de progreso
        self.progress = ctk.CTkProgressBar(self)
        self.progress.pack(fill="x", padx=20, pady=5)
        self.progress.set(0)

        self.status_label = ctk.CTkLabel(self, text="Listo para analizar", anchor="w", font=("Arial", 12))
        self.status_label.pack(fill="x", padx=20)

        # Frame central: lista de duplicados con checkboxes
        list_frame = ctk.CTkScrollableFrame(self, label_text="Archivos duplicados encontrados")
        list_frame.pack(fill="both", expand=True, padx=20, pady=10)
        self.list_frame = list_frame

        # Contenedor para los widgets de resultados
        self.results_container = ctk.CTkFrame(list_frame, fg_color="transparent")
        self.results_container.pack(fill="both", expand=True)

        # Frame inferior: acciones
        bottom_frame = ctk.CTkFrame(self, fg_color="transparent")
        bottom_frame.pack(fill="x", padx=20, pady=(10, 20))

        self.summary_label = ctk.CTkLabel(bottom_frame, text="", anchor="w")
        self.summary_label.pack(side="left", fill="x", expand=True)

        btn_delete = ctk.CTkButton(
            bottom_frame, text="Eliminar Seleccionados", width=180,
            fg_color="#d32f2f", hover_color="#b71c1c",
            command=self._delete_selected, state="disabled"
        )
        btn_delete.pack(side="right")
        self.btn_delete = btn_delete

        btn_select_all = ctk.CTkButton(
            bottom_frame, text="Seleccionar Todos (menos 1 por grupo)", width=220,
            command=self._select_redundant, state="disabled"
        )
        btn_select_all.pack(side="right", padx=(0, 10))
        self.btn_select_all = btn_select_all

        btn_legal = ctk.CTkButton(
            bottom_frame, text="⚖️ Aviso Legal", width=120,
            fg_color="#555555", hover_color="#444444",
            command=self._show_legal_notice
        )
        btn_legal.pack(side="left", padx=(10, 0))

        # Almacenar referencias a checkboxes
        self.checkboxes: Dict[str, ctk.CTkCheckBox] = {}
        self.group_widgets: Dict[str, List[ctk.CTkCheckBox]] = {}

    def _select_folder(self):
        folder = filedialog.askdirectory(title="Seleccionar carpeta de Descargas")
        if folder:
            self.target_dir = folder
            self.dir_label.configure(text=f"Carpeta: {folder}")
            self.btn_scan.configure(state="normal")
            self.status_label.configure(text="Carpeta seleccionada. Pulsa 'Analizar'.")
            self._clear_results()

    def _clear_results(self):
        for widget in self.results_container.winfo_children():
            widget.destroy()
        self.checkboxes.clear()
        self.group_widgets.clear()
        self.selected_for_deletion.clear()
        self.duplicates.clear()
        self.summary_label.configure(text="")
        self.btn_delete.configure(state="disabled")
        self.btn_select_all.configure(state="disabled")
        self.progress.set(0)

    def _start_scan(self):
        self.btn_scan.configure(state="disabled")
        self.btn_delete.configure(state="disabled")
        self.btn_select_all.configure(state="disabled")
        self._clear_results()
        self.status_label.configure(text="Analizando... esto puede tardar unos segundos.")
        self.progress.set(0)

        thread = threading.Thread(target=self._scan_worker, daemon=True)
        thread.start()

    def _scan_worker(self):
        try:
            dups, total, skipped_empty = scan_duplicates(
                self.target_dir,
                progress_callback=lambda v: self.after(0, self.progress.set, v)
            )
            self.after(0, self._on_scan_complete, dups, total, skipped_empty)
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", f"Error durante el análisis:\n{e}"))
            self.after(0, lambda: self.btn_scan.configure(state="normal"))

    def _on_scan_complete(self, duplicates: Dict[str, List[str]], total_files: int, skipped_empty: int = 0):
        self.duplicates = duplicates
        self.btn_scan.configure(state="normal")

        skipped_msg = f" ({skipped_empty} archivos vacíos ignorados)" if skipped_empty > 0 else ""

        if not duplicates:
            self.status_label.configure(text=f"Análisis completo. No se encontraron duplicados entre {total_files} archivos.{skipped_msg}")
            self.summary_label.configure(text="0 duplicados | 0 B recuperables")
            return

        # Construir UI de resultados
        total_dup_files = 0
        total_waste = 0

        for i, (file_hash, paths) in enumerate(duplicates.items()):
            # Marco por grupo
            group_frame = ctk.CTkFrame(self.results_container, border_width=1, border_color="#444444")
            group_frame.pack(fill="x", pady=(0, 8))

            # Etiqueta del grupo con hash parcial y tamaño
            try:
                file_size = os.path.getsize(paths[0])
            except OSError:
                file_size = 0
            waste = file_size * (len(paths) - 1)
            total_waste += waste
            total_dup_files += len(paths)

            header = ctk.CTkLabel(
                group_frame,
                text=f"Grupo {i+1} | {len(paths)} archivos | {format_size(file_size)} c/u | Recuperable: {format_size(waste)}",
                font=("Arial", 12, "bold"),
                anchor="w"
            )
            header.pack(fill="x", padx=10, pady=(8, 4))

            group_checks = []
            for j, path in enumerate(sorted(paths)):
                var = ctk.BooleanVar(value=False)
                cb = ctk.CTkCheckBox(
                    group_frame,
                    text=path,
                    variable=var,
                    onvalue=True,
                    offvalue=False,
                    command=lambda p=path, v=var: self._toggle_selection(p, v),
                    font=("Consolas", 11)
                )
                cb.pack(fill="x", padx=20, pady=2)
                self.checkboxes[path] = cb
                group_checks.append((cb, var))

            self.group_widgets[file_hash] = group_checks

        skipped_msg = f" | {skipped_empty} vacíos ignorados" if skipped_empty > 0 else ""
        self.status_label.configure(text=f"Análisis completo. {total_files} archivos escaneados.{skipped_msg}")
        self.summary_label.configure(
            text=f"{len(duplicates)} grupos | {total_dup_files} archivos duplicados | {format_size(total_waste)} recuperables"
        )
        self.btn_delete.configure(state="normal")
        self.btn_select_all.configure(state="normal")

    def _toggle_selection(self, path: str, var: ctk.BooleanVar):
        if var.get():
            self.selected_for_deletion.add(path)
        else:
            self.selected_for_deletion.discard(path)

    def _select_redundant(self):
        """Selecciona todos los archivos duplicados EXCEPTO el primero de cada grupo."""
        self.selected_for_deletion.clear()
        for file_hash, checks in self.group_widgets.items():
            for idx, (cb, var) in enumerate(checks):
                path = cb.cget("text")
                if idx == 0:
                    var.set(False)
                else:
                    var.set(True)
                    self.selected_for_deletion.add(path)

    def _delete_selected(self):
        if not self.selected_for_deletion:
            messagebox.showinfo("Info", "No hay archivos seleccionados para eliminar.")
            return

        count = len(self.selected_for_deletion)
        confirm = messagebox.askyesno(
            "Confirmar eliminación",
            f"¿Eliminar {count} archivo(s) seleccionado(s)?\n\nEsta acción no se puede deshacer."
        )
        if not confirm:
            return

        deleted = 0
        errors = []
        for path in list(self.selected_for_deletion):
            try:
                os.remove(path)
                deleted += 1
                # Remover de la UI
                if path in self.checkboxes:
                    self.checkboxes[path].destroy()
                    del self.checkboxes[path]
                self.selected_for_deletion.discard(path)
            except Exception as e:
                errors.append(f"{path}: {e}")

        msg = f"{deleted} archivo(s) eliminado(s) correctamente."
        if errors:
            msg += "\n\nErrores:\n" + "\n".join(errors[:10])
        messagebox.showinfo("Resultado", msg)

        # Actualizar resumen
        remaining = len(self.selected_for_deletion)
        self.summary_label.configure(text=f"Restantes tras eliminación: {remaining} seleccionados")

    def _show_legal_notice(self):
        """Muestra el aviso legal / licencia en una ventana modal."""
        license_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "LICENSE")
        try:
            with open(license_path, "r", encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            content = "Archivo LICENSE no encontrado.\n\n© 2026 nicol & Claude (Anthropic)"

        win = ctk.CTkToplevel(self)
        win.title("⚖️ Aviso Legal — Duplicated")
        win.geometry("650x500")
        win.resizable(True, True)
        win.transient(self)
        win.grab_set()

        textbox = ctk.CTkTextbox(win, wrap="word", font=("Consolas", 12))
        textbox.pack(fill="both", expand=True, padx=10, pady=(10, 5))
        textbox.insert("1.0", content)
        textbox.configure(state="disabled")

        btn_close = ctk.CTkButton(win, text="Cerrar", width=120, command=win.destroy)
        btn_close.pack(pady=(0, 10))


if __name__ == "__main__":
    app = DuplicateCleanerApp()
    app.mainloop()