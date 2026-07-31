# tab_substrat.py
import re
import tkinter as tk
from tkinter import ttk, messagebox
from data import DATABASE_PLANTES, PROFILS_GENERIQUES

class TabSubstrat(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.mes_plantes = []
        self.combo_mapping = {}  # Dictionnaire de liaison : Texte du menu -> Objet Profil
        self.creer_interface()

    def creer_interface(self):
        main_frame = ttk.LabelFrame(self, text=" Générateur de Recette Sur-Mesure ")
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        frame_top = ttk.Frame(main_frame)
        frame_top.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame_top, text="Choisir une plante / profil :", font=("Arial", 9, "bold")).pack(side="left", padx=5)
        
        self.combo_substrat_plante = ttk.Combobox(frame_top, state="readonly", width=60)
        self.combo_substrat_plante.pack(side="left", padx=5)

        ttk.Label(frame_top, text="Pot (L) :", font=("Arial", 9, "bold")).pack(side="left", padx=10)
        self.entry_vol = ttk.Entry(frame_top, width=6)
        self.entry_vol.insert(0, "2.0")
        self.entry_vol.pack(side="left", padx=2)

        ttk.Label(main_frame, text="Cochez UNIQUEMENT les ingrédients présents dans votre réserve :", font=("Arial", 9, "bold")).pack(anchor="w", padx=10, pady=(10, 2))

        # Zone défilante des ingrédients
        canvas_container = ttk.Frame(main_frame)
        canvas_container.pack(fill="x", padx=10, pady=5)

        canvas = tk.Canvas(canvas_container, height=305)
        scrollbar = ttk.Scrollbar(canvas_container, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        self.ing_vars = {}
        
        categories = {
            "Bases Organiques & Terres (10)": [
                ("Tourbe blonde", True), ("Fibre de coco", True), ("Chips de coco", False), 
                ("Sphaigne sèche", True), ("Mousse de sphaigne vivante", False), 
                ("Pépites de tourbe", False), ("Humus de lombric", False),
                ("Terreau de feuilles", False), ("Terreau argileux (Aquatique / Nénuphars)", True),
                ("Terre franche / Terre de jardin", False), ("Terreau de semis", True), ("Terreau horticole", True)
            ],
            "Minéraux & Drainants (14)": [
                ("Sable grossier", True), ("Perlite", True), ("Pumice", False), 
                ("Pouzzolane", True), ("Micro-pouzzolane", False), ("Vermiculite", True), 
                ("Zéolite", True), ("Kanuma", False), ("Akadama", False), 
                ("Kiryu", False), ("Seramis", False), ("Argile calcinée (Moler)", False),
                ("Billes d'argile", True), ("Gravier de Quartz", False), ("Sable de quartz", False)
            ],
            "Additifs & Spécialités (5)": [
                ("Charbon actif", True), ("Charbon de bambou", False), 
                ("Écorces de pin", True), ("Farine de basalte", False),
                ("Poudre de Calcaire / Dolomie", False)
            ]
        }

        row_idx = 0
        for cat_name, items in categories.items():
            ttk.Label(scrollable_frame, text=f"— {cat_name} —", font=("Arial", 8, "italic", "bold"), foreground="#2980b9").grid(row=row_idx, column=0, columnspan=4, sticky="w", padx=5, pady=(8, 2))
            row_idx += 1
            col_idx = 0
            for item_name, default_val in items:
                var = tk.BooleanVar(value=default_val)
                self.ing_vars[item_name] = var
                ttk.Checkbutton(scrollable_frame, text=item_name, variable=var).grid(row=row_idx, column=col_idx, sticky="w", padx=6, pady=2)
                col_idx += 1
                if col_idx >= 4:
                    col_idx = 0
                    row_idx += 1
            if col_idx != 0:
                row_idx += 1

        ttk.Button(main_frame, text="🧪 Calculer la Recette Sur-Mesure", command=self.calculer_recette).pack(pady=8)

        self.txt_recette = tk.Text(main_frame, height=12, width=80, state="disabled", font=("Consolas", 9))
        self.txt_recette.pack(padx=10, pady=5, fill="both", expand=True)

    def actualiser_combo_substrat(self, mes_plantes):
        self.mes_plantes = mes_plantes
        self.combo_mapping = {}
        options = []

        # 1. Profils génériques par grande famille
        options.append("--- 🌐 RECETTES GÉNÉRIQUES PAR FAMILLE ---")
        for g_p in PROFILS_GENERIQUES:
            lbl = f"🌐 {g_p.get('nom_sci', 'Inconnu')} ({g_p.get('nom_vern', 'N/A')})"
            options.append(lbl)
            self.combo_mapping[lbl] = g_p

        # 2. Collection personnelle JSON
        options.append("--- 🪴 MA COLLECTION (Fichier JSON) ---")
        for p in self.mes_plantes:
            profil_obj = p.get('profil', {})
            nom_sci = profil_obj.get('nom_sci') or profil_obj.get('taxonomie', {}).get('nom_scientifique', 'Inconnu')
            lbl = f"🪴 {p.get('surnom', 'Sans nom')} [{nom_sci}]"
            options.append(lbl)
            self.combo_mapping[lbl] = profil_obj

        # 3. Base d'espèces spécifiques
        options.append("--- 📋 ESPÈCES SPÉCIFIQUES ---")
        for db_p in DATABASE_PLANTES:
            nom_sci = db_p.get('nom_sci') or db_p.get('taxonomie', {}).get('nom_scientifique', 'Inconnu')
            nom_vern = db_p.get('nom_vern') or db_p.get('taxonomie', {}).get('noms_vernaculaires', 'N/A')
            if isinstance(nom_vern, list):
                nom_vern = ", ".join(nom_vern)
            lbl = f"📋 {nom_sci} ({nom_vern})"
            options.append(lbl)
            self.combo_mapping[lbl] = db_p

        self.combo_substrat_plante['values'] = options
        if len(options) > 1:
            self.combo_substrat_plante.current(1)

    def normaliser_profil_en_roles(self, profil):
        """
        Convertit n'importe quelle fiche (JSON ou Profil Générique) 
        en une liste de rôles uniformisée avec ratios et ingrédients associés.
        """
        # CAS 1 : Déjà au format profil générique
        if "roles" in profil:
            return profil.get("roles", []), profil.get("conseil", ""), profil.get("interdits", [])

        # CAS 2 : Fiche plante issue d'un fichier JSON
        substrat = profil.get("substrat", {})
        comp_str = substrat.get("composition_ideale", "")
        recommandes = substrat.get("ingredients_recommandes", [])
        interdits = substrat.get("elements_interdits", [])

        # Construction du conseil de culture
        ph = substrat.get("ph", "Non spécifié")
        freq = profil.get("gestion_eau", {}).get("frequence_mode", "")
        conseil = f"pH idéal : {ph}."
        if freq:
            conseil += f" Arrosage : {freq}"

        # Analyse des pourcentages dans "composition_ideale" (ex: "50% Fibre de coco..., 40% Pumice...")
        matches = re.findall(r'(\d+)%\s*([^,\n\.]+)', comp_str)
        roles = []

        if matches:
            for pct_str, label_raw in matches:
                ratio = float(pct_str) / 100.0
                label_clean = label_raw.strip()

                ing_associes = []

                # 1. Correspondance avec la liste d'ingrédients recommandés de la plante
                mots_cles = [w.lower() for w in re.split(r'[/&\s]+', label_clean) if len(w) > 2]
                for rec in recommandes:
                    if any(m in rec.lower() for m in mots_cles):
                        ing_associes.append(rec)

                # 2. Correspondance avec la réserve globale d'ingrédients de l'application
                for stock_ing in self.ing_vars.keys():
                    if any(m in stock_ing.lower() for m in mots_cles):
                        if stock_ing not in ing_associes:
                            ing_associes.append(stock_ing)

                roles.append({
                    "nom": label_clean,
                    "ratio": ratio,
                    "ing": ing_associes if ing_associes else [label_clean]
                })
        else:
            # Fallback si pas de pourcentages explicites
            cat_org = [i for i in recommandes if any(x in i.lower() for x in ["coco", "tourbe", "terreau", "sphaigne", "humus"])]
            cat_min = [i for i in recommandes if any(x in i.lower() for x in ["perlite", "pumice", "sable", "pouzzolane", "argile", "vermiculite", "zeolite"])]
            cat_add = [i for i in recommandes if any(x in i.lower() for x in ["charbon", "écorce", "ecorce", "engrais", "chaux"])]

            roles = [
                {"nom": "Bases Organiques & Terres", "ratio": 0.50, "ing": cat_org if cat_org else ["Fibre de coco", "Tourbe blonde"]},
                {"nom": "Minéraux & Drainants", "ratio": 0.40, "ing": cat_min if cat_min else ["Perlite", "Sable grossier", "Pumice"]},
                {"nom": "Additifs & Spécialités", "ratio": 0.10, "ing": cat_add if cat_add else ["Charbon actif"]}
            ]

        return roles, conseil, interdits

    def calculer_recette(self):
        try:
            vol = float(self.entry_vol.get())
            if vol <= 0: raise ValueError
        except ValueError:
            messagebox.showerror("Erreur", "Veuillez entrer un volume valide.")
            return

        choix = self.combo_substrat_plante.get()
        if not choix or "---" in choix:
            messagebox.showwarning("Attention", "Veuillez choisir un profil ou une plante valide.")
            return

        profil = self.combo_mapping.get(choix)
        if not profil:
            messagebox.showerror("Erreur", "Profil introuvable.")
            return

        has = {k: v.get() for k, v in self.ing_vars.items()}

        nom_sci = profil.get("nom_sci") or profil.get("taxonomie", {}).get("nom_scientifique", "Inconnu")
        nom_vern = profil.get("nom_vern") or profil.get("taxonomie", {}).get("noms_vernaculaires", "N/A")
        if isinstance(nom_vern, list):
            nom_vern = ", ".join(nom_vern)

        # Normalisation unifiée
        roles, conseil, interdits = self.normaliser_profil_en_roles(profil)

        res = f"=================================================================\n"
        res += f" RECETTE POUR {vol:.2f} L — {str(nom_sci).upper()}\n"
        res += f" Catégorie / Cible : {nom_vern}\n"
        res += f"=================================================================\n\n"

        # Boucle unique d'affichage pour TOUTES les entrées
        for role in roles:
            pct = role.get("ratio", 0)
            litres = vol * pct
            ing_possibles = role.get("ing", [])

            # Filtrage des ingrédients présents en réserve
            dispos = [i for i in ing_possibles if has.get(i, False)]

            nom_role = role.get("nom", "Composant")
            if dispos:
                options_str = ", ".join(dispos)
                res += f"• {nom_role} ({pct*100:.0f}% = {litres:.2f} L) :\n  👉 Disponible(s) dans votre stock : [ {options_str} ]\n\n"
            else:
                sug = " / ".join(ing_possibles[:3]) if ing_possibles else "Ingrédient standard"
                res += f"• {nom_role} ({pct*100:.0f}% = {litres:.2f} L) :\n  ❌ AUCUN INGRÉDIENT DISPONIBLE (Suggéré : {sug})\n\n"

        if conseil:
            res += f"💡 CONSEIL DE CULTURE : {conseil}\n\n"

        # Vérification des ingrédients interdits / déconseillés
        interdits_utilises = []
        for bad in interdits:
            for stock_ing, is_checked in has.items():
                if is_checked and (bad.lower() in stock_ing.lower() or stock_ing.lower() in bad.lower()):
                    interdits_utilises.append(stock_ing)

        if interdits_utilises:
            res += "⚠️ INGRÉDIENTS DÉCONSEILLÉS PRÉSENTS DANS VOTRE STOCK SÉLECTIONNÉ :\n"
            for bad in set(interdits_utilises):
                res += f"   - Ne PAS utiliser {bad} pour cette plante.\n"

        self.txt_recette.config(state="normal")
        self.txt_recette.delete("1.0", tk.END)
        self.txt_recette.insert(tk.END, res)
        self.txt_recette.config(state="disabled")