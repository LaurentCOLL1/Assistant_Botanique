# tab_diagnostic.py
import tkinter as tk
from tkinter import ttk
from data import DIAGNOSTICS_DATA

class TabDiagnostic(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.creer_interface()

    def creer_interface(self):
        frame_diag = ttk.LabelFrame(self, text=" Assistant de Diagnostic Rapide ")
        frame_diag.pack(fill="both", expand=True, padx=10, pady=10)

        frame_select = ttk.Frame(frame_diag)
        frame_select.pack(fill="x", padx=10, pady=10)

        ttk.Label(frame_select, text="Symptôme observé :", font=("Arial", 9, "bold")).pack(side="left", padx=5)
        self.combo_symptome = ttk.Combobox(frame_select, values=list(DIAGNOSTICS_DATA.keys()), state="readonly", width=55)
        self.combo_symptome.current(0)
        self.combo_symptome.pack(side="left", padx=5)

        ttk.Button(frame_select, text="🔍 Analyser", command=self.analyser_symptome).pack(side="left", padx=10)

        self.txt_diag = tk.Text(frame_diag, height=18, width=80, state="disabled", font=("Arial", 10))
        self.txt_diag.pack(padx=10, pady=10, fill="both", expand=True)

        self.analyser_symptome()

    def analyser_symptome(self):
        symp = self.combo_symptome.get()
        data = DIAGNOSTICS_DATA.get(symp)
        if not data: return

        res = f"=== DIAGNOSTIC : {symp.upper()} ===\n\n"
        res += f"⚠️ CAUSE PROBABLE :\n{data['cause']}\n\n"
        res += f"🛠️ ACTIONS CORRECTIVES RECOMMANDEES :\n{data['action']}\n"

        self.txt_diag.config(state="normal")
        self.txt_diag.delete("1.0", tk.END)
        self.txt_diag.insert(tk.END, res)
        self.txt_diag.config(state="disabled")