# main.py
import tkinter as tk
from tkinter import ttk

from tab_gestion import TabGestion
from tab_substrat import TabSubstrat
from tab_diagnostic import TabDiagnostic
from tab_catalogue import TabCatalogue  # <-- Le nouveau module

class PlantCareApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Assistant Botanique — Soins, Substrats & Suivi Arrosages")
        self.root.geometry("1400x1200")

        style = ttk.Style()
        style.theme_use("clam")

        # Conteneur d'onglets
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True)

        # 1. Instanciation du Catalogue (avec callback optionnel si besoin)
        self.tab_catalogue = TabCatalogue(self.notebook)

        # 2. Instanciation des autres sous-programmes (Frames)
        self.tab_substrat = TabSubstrat(self.notebook)
        
        # 3. Instanciation de la gestion avec la passerelle vers le catalogue via "voir_catalogue_callback"
        self.tab_gestion = TabGestion(
            self.notebook, 
            on_collection_changed_callback=self.on_collection_updated,
            voir_catalogue_callback=self.naviguer_vers_catalogue
        )
        
        self.tab_diagnostic = TabDiagnostic(self.notebook)

        # Ajout des onglets au Notebook dans l'ordre de ton choix
        self.notebook.add(self.tab_gestion, text="🪴 Ma Collection & Soins")
        self.notebook.add(self.tab_catalogue, text="📖 Catalogue Général")  # <-- Ajouté ici
        self.notebook.add(self.tab_substrat, text="🧪 Générateur de Substrat")
        self.notebook.add(self.tab_diagnostic, text="🩺 Diagnostic & Soins")

        # Sync initiale entre la collection et le menu déroulant du substrat
        self.tab_substrat.actualiser_combo_substrat(self.tab_gestion.mes_plantes)

    def on_collection_updated(self, nouvelles_plantes):
        """Déclenché automatiquement lorsque la collection est modifiée/sauvegardée."""
        self.tab_substrat.actualiser_combo_substrat(nouvelles_plantes)

    def naviguer_vers_catalogue(self, nom_sci):
        """Bascule automatiquement sur l'onglet Catalogue et sélectionne la plante ciblée."""
        self.notebook.select(self.tab_catalogue)
        self.tab_catalogue.selectionner_plante(nom_sci)


if __name__ == "__main__":
    root = tk.Tk()
    app = PlantCareApp(root)
    root.mainloop()