import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, timedelta
import json
import os
import re
import copy
from data import DATABASE_PLANTES, COLLECTION_INITIALE_DEFAUT, FILE_JSON

def parse_date(date_str):
    """Convertit n'importe quelle date (FR ou ISO) en objet date."""
    if not date_str:
        return datetime.now().date()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            pass
    return datetime.now().date()

def format_date_fr(date_obj):
    """Formate un objet date au format français JJ/MM/AAAA."""
    return date_obj.strftime("%d/%m/%Y")

class TabGestion(ttk.Frame):
    MOIS_KEYS = {
        1: "janvier", 2: "fevrier", 3: "mars", 4: "avril",
        5: "mai", 6: "juin", 7: "juillet", 8: "aout",
        9: "septembre", 10: "octobre", 11: "novembre", 12: "decembre"
    }

    def __init__(self, parent, on_collection_changed_callback=None, voir_catalogue_callback=None):
        super().__init__(parent)
        self.on_collection_changed_callback = on_collection_changed_callback
        self.voir_catalogue_callback = voir_catalogue_callback
        self.mes_plantes = []
        self.historique = []  # Pile d'historique pour le Ctrl+Z

        self.creer_interface()
        self.charger_depuis_json()

        # Bind du raccourci Ctrl+Z sur la fenêtre globale
        self.winfo_toplevel().bind("<Control-z>", self.annuler_action)
        self.winfo_toplevel().bind("<Control-Z>", self.annuler_action)

    def enregistrer_historique(self):
        """Conserve un instantané de la collection avant une modification."""
        self.historique.append(copy.deepcopy(self.mes_plantes))
        if len(self.historique) > 20:
            self.historique.pop(0)

    def annuler_action(self, event=None):
        """Annule la dernière action (Ctrl+Z)."""
        widget_actif = self.focus_get()
        if isinstance(widget_actif, (tk.Entry, ttk.Entry, tk.Text)):
            try:
                if widget_actif.cget("state") != "readonly" and widget_actif.cget("state") != "disabled":
                    return
            except tk.TclError:
                pass

        if not self.historique:
            messagebox.showinfo("Annulation", "Aucune action à annuler.")
            return

        self.mes_plantes = self.historique.pop()
        self.sauvegarder_dans_json()
        self.rafraichir_tableau_collection()
        self.afficher_details_plante()
        messagebox.showinfo("Annulation réussie", "↩️ Action annulée avec succès (Ctrl+Z) !")

    def creer_interface(self):
        # --- STYLES PERSONNALISÉS DE BOUTONS ---
        style = ttk.Style()
        
        style.configure("Danger.TButton", background="#e74c3c", foreground="white", font=("Arial", 9, "bold"))
        style.map("Danger.TButton",
                  background=[("active", "#c0392b"), ("disabled", "#f2f3f4")],
                  foreground=[("active", "white")])

        style.configure("Water.TButton", background="#85c1e9", foreground="#1b4f72", font=("Arial", 9, "bold"))
        style.map("Water.TButton",
                  background=[("active", "#3498db"), ("disabled", "#f2f3f4")],
                  foreground=[("active", "white")])

        # 1. Zone d'ajout et recherche
        frame_add = ttk.LabelFrame(self, text=" Ajouter / Rechercher une plante ")
        frame_add.pack(fill="x", padx=10, pady=5)

        frame_top_add = ttk.Frame(frame_add)
        frame_top_add.pack(fill="x", padx=5, pady=2)

        ttk.Label(frame_top_add, text="Surnom :").grid(row=0, column=0, padx=5, pady=2, sticky="w")
        self.entry_surnom = ttk.Entry(frame_top_add, width=50)
        self.entry_surnom.insert(0, "Ma Nouvelle Plante")
        self.entry_surnom.grid(row=0, column=1, padx=5, pady=2)

        ttk.Label(frame_top_add, text="Volume Pot (L) :").grid(row=0, column=2, padx=5, pady=2, sticky="w")
        self.entry_pot = ttk.Entry(frame_top_add, width=10)
        self.entry_pot.insert(0, "1.5")
        self.entry_pot.grid(row=0, column=3, padx=5, pady=2)

        frame_search = ttk.Frame(frame_add)
        frame_search.pack(fill="x", padx=5, pady=2)

        ttk.Label(frame_search, text="🔍 Recherche orthographique (Sci / Vernaculaire) :", font=("Arial", 9, "bold")).pack(anchor="w", padx=5)
        
        self.entry_search = ttk.Entry(frame_search)
        self.entry_search.pack(fill="x", padx=5, pady=2)
        self.entry_search.bind("<KeyRelease>", self.filtrer_recherche)

        self.listbox_plantes = tk.Listbox(frame_search, height=5, font=("Arial", 9))
        self.listbox_plantes.pack(fill="x", padx=5, pady=2)

        btn_add = ttk.Button(frame_add, text="➕ Enregistrer dans ma collection JSON", command=self.ajouter_plante)
        btn_add.pack(pady=4, anchor="e", padx=10)

        # 2. Tableau de la collection
        frame_list = ttk.LabelFrame(self, text=" Ma Collection (Sauvegardée dans 'mes_plantes.json') ")
        frame_list.pack(fill="both", expand=True, padx=10, pady=5)

        columns = ("Surnom", "Nom Scientifique", "Nom Vernaculaire", "Pot (L)", "Dernier Arrosage", "Prochain Arrosage", "Statut")
        self.tree = ttk.Treeview(frame_list, columns=columns, show="headings", height=6)

        self.tree.heading("Surnom", text="Surnom")
        self.tree.heading("Nom Scientifique", text="Nom Scientifique")
        self.tree.heading("Nom Vernaculaire", text="Nom Vernaculaire")
        self.tree.heading("Pot (L)", text="Pot (L)")
        self.tree.heading("Dernier Arrosage", text="Dernier Arrosage")
        self.tree.heading("Prochain Arrosage", text="Prochain Arrosage")
        self.tree.heading("Statut", text="Statut Arrosage")

        self.tree.column("Surnom", width=110, anchor="center")
        self.tree.column("Nom Scientifique", width=150, anchor="w")
        self.tree.column("Nom Vernaculaire", width=140, anchor="w")
        self.tree.column("Pot (L)", width=55, anchor="center")
        self.tree.column("Dernier Arrosage", width=100, anchor="center")
        self.tree.column("Prochain Arrosage", width=100, anchor="center")
        self.tree.column("Statut", width=120, anchor="center")

        self.tree.tag_configure("OK", foreground="#1e8449", font=("Arial", 9, "bold"))
        self.tree.tag_configure("TODAY", foreground="#d35400", font=("Arial", 9, "bold"))
        self.tree.tag_configure("LATE", foreground="#c0392b", font=("Arial", 9, "bold"))
        self.tree.tag_configure("REST", foreground="#2980b9", font=("Arial", 9, "bold"))

        self.tree.pack(fill="both", expand=True, padx=5, pady=5)
        self.tree.bind("<<TreeviewSelect>>", self.afficher_details_plante)

        frame_btns_list = ttk.Frame(frame_list)
        frame_btns_list.pack(fill="x", padx=5, pady=3)

        btn_cal = ttk.Button(frame_btns_list, text="📅 Générer le calendrier d'arrosage", command=self.ouvrir_fenetre_calendrier)
        btn_cal.pack(side="left", padx=5)

        btn_del = ttk.Button(
            frame_btns_list, 
            text="🗑️ Supprimer la plante sélectionnée", 
            command=self.supprimer_plante,
            style="Danger.TButton"
        )
        btn_del.pack(side="right", padx=5)

        # 3. Panneau de détails
        self.frame_detail = ttk.LabelFrame(self, text=" 📋 Fiche de détails & Consignes de soins ")
        self.frame_detail.pack(fill="x", padx=10, pady=5)

        grid_detail = ttk.Frame(self.frame_detail)
        grid_detail.pack(fill="x", padx=10, pady=5)

        ttk.Label(grid_detail, text="🔬 Nom Scientifique :", font=("Arial", 9, "bold")).grid(row=0, column=0, sticky="w", pady=2)
        self.entry_nom_sci = tk.Entry(grid_detail, width=155, state="readonly", font=("Arial", 9, "italic"), bd=1, relief="solid")
        self.entry_nom_sci.grid(row=0, column=1, sticky="w", padx=10, pady=2)

        ttk.Label(grid_detail, text="🌿 Nom Vernaculaire :", font=("Arial", 9, "bold")).grid(row=1, column=0, sticky="w", pady=2)
        self.entry_nom_vern = tk.Entry(grid_detail, width=155, state="readonly", font=("Arial", 9), bd=1, relief="solid")
        self.entry_nom_vern.grid(row=1, column=1, sticky="w", padx=10, pady=2)

        ttk.Label(grid_detail, text="🔔 Statut Arrosage :", font=("Arial", 9, "bold")).grid(row=2, column=0, sticky="w", pady=2)
        self.entry_statut = tk.Entry(grid_detail, width=155, state="readonly", font=("Arial", 9, "bold"), bd=1, relief="solid")
        self.entry_statut.grid(row=2, column=1, sticky="w", padx=10, pady=2)

        ttk.Label(grid_detail, text="💧 Fréquence & Saison :", font=("Arial", 9, "bold")).grid(row=3, column=0, sticky="w", pady=2)
        self.entry_freq = tk.Entry(grid_detail, width=155, state="readonly", font=("Arial", 9), bd=1, relief="solid")
        self.entry_freq.grid(row=3, column=1, sticky="w", padx=10, pady=2)

        ttk.Label(grid_detail, text="🚰 Type d'eau conseillé :", font=("Arial", 9, "bold")).grid(row=4, column=0, sticky="w", pady=2)
        
        self.entry_eau = tk.Text(grid_detail, width=99, height=1, font=("Arial", 14), bd=1, relief="solid", pady=4)
        self.entry_eau.grid(row=4, column=1, sticky="w", padx=10, pady=4)

        self.entry_eau.tag_configure("best_green", foreground="#27ae60", font=("Arial", 13, "bold"))
        self.entry_eau.tag_configure("best_blue", foreground="#2980b9", font=("Arial", 13, "bold"))
        self.entry_eau.tag_configure("best_darkblue", foreground="#1f618d", font=("Arial", 13, "bold"))
        self.entry_eau.tag_configure("neutral", foreground="#000000", font=("Arial", 11))

        ttk.Label(grid_detail, text="💡 Notes & Consignes :", font=("Arial", 9, "bold")).grid(row=5, column=0, sticky="nw", pady=2)
        self.txt_notes = tk.Text(grid_detail, height=4, width=155, font=("Arial", 9), wrap="word", bd=1, relief="solid")
        self.txt_notes.grid(row=5, column=1, sticky="w", padx=10, pady=2)

        # BOUTON VERTICAL "+ d'infos"
        self.btn_plus_infos = tk.Button(
            grid_detail, 
            text="+ \n d '\n i \n n \n f \n o \n s", 
            command=self.aller_au_catalogue,
            bg="#f1c40f", 
            fg="#7d6608", 
            font=("Arial", 10, "bold"),
            relief="raised",
            bd=2,
            cursor="hand2"
        )
        self.btn_plus_infos.grid(row=0, column=2, rowspan=6, sticky="ns", padx=(10, 2), pady=2)

        # Ligne bas avec Alerte générale + Bouton Arrosage
        frame_action_bas = ttk.Frame(self.frame_detail)
        frame_action_bas.pack(fill="x", padx=10, pady=5)
        
        lbl_avertissement_eau_pan = ttk.Label(
            frame_action_bas, 
            text="🛑", 
            font=("Arial", 16, "bold"),
            foreground="#c0392b"
        )
        lbl_avertissement_eau_pan.pack(side="left", padx=5)
        
        lbl_avertissement_eau = ttk.Label(
            frame_action_bas, 
            text="Danger : Ne jamais utiliser d'eau provenant d'un adoucisseur à sel (trop riche en sodium).", 
            font=("Arial", 10, "italic bold"),
            foreground="#c0392b"
        )
        lbl_avertissement_eau.pack(side="left", padx=0)

        self.btn_arrosage = ttk.Button(
            frame_action_bas, 
            text="💧 Marquer comme arrosée aujourd'hui", 
            command=self.marquer_arrosee_aujourdhui,
            style="Water.TButton"
        )
        self.btn_arrosage.pack(side="right", padx=5)

        self.filtrer_recherche()

    def aller_au_catalogue(self):
        """Action déclenchée par le bouton '+ d'infos' : bascule sur l'onglet catalogue et cible la plante."""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Attention", "Veuillez d'abord sélectionner une plante dans votre collection.")
            return
        values = self.tree.item(selected[0], "values")
        surnom = values[0]
        plante = next((p for p in self.mes_plantes if p["surnom"] == surnom), None)
        if plante and self.voir_catalogue_callback:
            nom_sci = plante["profil"].get("nom_sci") or plante["profil"].get("taxonomie", {}).get("nom_scientifique", "")
            self.voir_catalogue_callback(nom_sci)

    def get_delai_actuel(self, profil, date_ref):
        mois_num = date_ref.month
        est_saison_chaude = 4 <= mois_num <= 9  # Avril à Septembre

        gestion_eau = profil.get("gestion_eau", {}) if isinstance(profil.get("gestion_eau"), dict) else {}
        freq_data = gestion_eau.get("frequence_arrosage") or profil.get("frequence_arrosage")

        # 1. Priorité à la structure en dictionnaire mensuel
        if isinstance(freq_data, dict):
            mois_key = self.MOIS_KEYS.get(mois_num, "janvier")
            delai_actuel = freq_data.get(mois_key, 7)
            
            # Détermination indicative des délais Été (ex. Juillet) et Hiver (ex. Janvier)
            delai_ete = freq_data.get("juillet", freq_data.get("juin", 7))
            delai_hiver = freq_data.get("janvier", freq_data.get("decembre", 14))

            return delai_actuel, delai_ete, delai_hiver, est_saison_chaude

        # 2. Algorithme de fallback pour chaînes textuelles
        delai_ete = profil.get("delai_ete") or gestion_eau.get("delai_ete")
        delai_hiver = profil.get("delai_hiver") or gestion_eau.get("delai_hiver")

        freq_str = str(freq_data or gestion_eau.get("frequence_mode") or "").lower()
        var_str = str(gestion_eau.get("variation_saisonniere") or "").lower()
        texte_global = f"{freq_str} {var_str}".lower()

        if delai_ete is None:
            nums = re.findall(r'\d+', freq_str)
            if nums:
                delai_ete = int(nums[0])
            elif "semaine" in freq_str:
                delai_ete = 7
            elif "10 jours" in freq_str or "10j" in freq_str:
                delai_ete = 10
            elif "mois" in freq_str:
                delai_ete = 30
            else:
                delai_ete = 7

        if delai_hiver is None:
            if any(kw in texte_global for kw in ["2 mois", "deux mois", "8 semaines", "60 jours"]):
                delai_hiver = 60
            elif any(kw in texte_global for kw in ["1 mois", "un mois", "4 semaines", "mensuel", "30 jours"]):
                delai_hiver = 30
            elif any(kw in texte_global for kw in ["3 semaines", "21 jours"]):
                delai_hiver = 21
            elif any(kw in texte_global for kw in ["15 jours", "2 semaines", "bimensuel"]):
                delai_hiver = 15
            elif any(kw in texte_global for kw in ["stopper", "suspendre", "aucun arrosage", "pas d'arrosage"]):
                delai_hiver = 90
            else:
                est_succulente = any(kw in str(profil).lower() for kw in [
                    "succulente", "cactus", "cactaceae", "crassulaceae", 
                    "sansevieria", "zz plant", "aloe", "agave", "euphorbia"
                ])
                multiplier = 4 if est_succulente else 2
                delai_hiver = delai_ete * multiplier

        delai_actuel = delai_ete if est_saison_chaude else delai_hiver
        return delai_actuel, delai_ete, delai_hiver, est_saison_chaude

    def calculer_statut_arrosage(self, date_dernier_str, profil):
        date_dernier = parse_date(date_dernier_str)
        aujourdhui = datetime.now().date()

        delai_actuel, delai_ete, delai_hiver, est_saison_chaude = self.get_delai_actuel(profil, aujourdhui)
        date_dernier_fr = format_date_fr(date_dernier)

        # Prise en charge du repos hivernal (intervalle == 0)
        if delai_actuel == 0:
            code_statut = "REST"
            statut_court = "❄️ REPOS (0 j)"
            detail_statut = "❄️ Repos hivernal complet : Aucun arrosage ce mois-ci."
            date_prochain_fr = "Au sec (0 j)"
            couleur = "#2980b9"
        else:
            date_prochain = date_dernier + timedelta(days=delai_actuel)
            jours_restants = (date_prochain - aujourdhui).days
            date_prochain_fr = format_date_fr(date_prochain)

            if jours_restants > 0:
                code_statut = "OK"
                statut_court = f"🟢 OK ({jours_restants} j)"
                detail_statut = f"Prochain arrosage prévu le {date_prochain_fr} (dans {jours_restants} jour(s))"
                couleur = "#1e8449"
            elif jours_restants == 0:
                code_statut = "TODAY"
                statut_court = "🟠 AUJOURD'HUI"
                detail_statut = "⚠️ Plante à arroser aujourd'hui !"
                couleur = "#d35400"
            else:
                code_statut = "LATE"
                retard = abs(jours_restants)
                statut_court = f"🔴 RETARD ({retard} j)"
                detail_statut = f"🚨 En retard de {retard} jour(s) ! (Prévu le {date_prochain_fr})"
                couleur = "#c0392b"

        return {
            "code_statut": code_statut,
            "statut_court": statut_court,
            "detail_statut": detail_statut,
            "date_dernier": date_dernier_fr,
            "date_prochain": date_prochain_fr,
            "delai_actuel": delai_actuel,
            "delai_ete": delai_ete,
            "delai_hiver": delai_hiver,
            "est_saison_chaude": est_saison_chaude,
            "couleur": couleur
        }

    def set_entry_text(self, entry_widget, text, color="black"):
        entry_widget.config(state="normal", fg=color)
        entry_widget.delete(0, tk.END)
        entry_widget.insert(0, text)
        entry_widget.config(state="readonly")

    def charger_depuis_json(self):
        date_du_jour_fr = format_date_fr(datetime.now().date())
        if not os.path.exists(FILE_JSON):
            self.mes_plantes = []
            for item in COLLECTION_INITIALE_DEFAUT:
                profil = next((p for p in DATABASE_PLANTES if p.get("nom_sci") == item["nom_sci"] or p.get("taxonomie", {}).get("nom_scientifique") == item["nom_sci"]), None)
                if profil:
                    self.mes_plantes.append({
                        "surnom": item["surnom"],
                        "profil": profil,
                        "pot": item["pot"],
                        "date_arrosage": date_du_jour_fr
                    })
            self.sauvegarder_dans_json()
        else:
            try:
                with open(FILE_JSON, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.mes_plantes = []
                    for item in data:
                        profil = next((p for p in DATABASE_PLANTES if p.get("nom_sci") == item["nom_sci"] or p.get("taxonomie", {}).get("nom_scientifique") == item["nom_sci"]), None)
                        if profil:
                            raw_date = item.get("date_arrosage", date_du_jour_fr)
                            date_obj = parse_date(raw_date)
                            self.mes_plantes.append({
                                "surnom": item["surnom"],
                                "profil": profil,
                                "pot": item["pot"],
                                "date_arrosage": format_date_fr(date_obj)
                            })
            except Exception as e:
                messagebox.showerror("Erreur JSON", f"Impossible de lire le fichier JSON : {e}")

        self.rafraichir_tableau_collection()

    def sauvegarder_dans_json(self):
        data_to_save = []
        for p in self.mes_plantes:
            nom_sci = p["profil"].get("nom_sci") or p["profil"].get("taxonomie", {}).get("nom_scientifique", "")
            data_to_save.append({
                "surnom": p["surnom"],
                "nom_sci": nom_sci,
                "pot": p["pot"],
                "date_arrosage": p["date_arrosage"]
            })

        try:
            with open(FILE_JSON, "w", encoding="utf-8") as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=4)
        except Exception as e:
            messagebox.showerror("Erreur Sauvegarde", f"Erreur lors de la sauvegarde JSON : {e}")

        if self.on_collection_changed_callback:
            self.on_collection_changed_callback(self.mes_plantes)

    def filtrer_recherche(self, event=None):
        query = self.entry_search.get().lower().strip()
        self.listbox_plantes.delete(0, tk.END)

        for p in DATABASE_PLANTES:
            nom_sci = p.get("nom_sci") or p.get("taxonomie", {}).get("nom_scientifique", "Inconnu")
            nom_vern = p.get("nom_vern") or p.get("taxonomie", {}).get("noms_vernaculaires", "N/A")
            if isinstance(nom_vern, list):
                nom_vern = ", ".join(nom_vern)

            label = f"{nom_sci}  —  [{nom_vern}]"
            if query in nom_sci.lower() or query in nom_vern.lower():
                self.listbox_plantes.insert(tk.END, label)

        if self.listbox_plantes.size() > 0:
            self.listbox_plantes.select_set(0)

    def rafraichir_tableau_collection(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        for p in self.mes_plantes:
            calc = self.calculer_statut_arrosage(p["date_arrosage"], p["profil"])
            nom_sci = p["profil"].get("nom_sci") or p["profil"].get("taxonomie", {}).get("nom_scientifique", "Inconnu")
            nom_vern = p["profil"].get("nom_vern") or p["profil"].get("taxonomie", {}).get("noms_vernaculaires", "N/A")
            if isinstance(nom_vern, list):
                nom_vern = ", ".join(nom_vern)

            self.tree.insert("", "end", values=(
                p["surnom"],
                nom_sci,
                nom_vern,
                p["pot"],
                calc["date_dernier"],
                calc["date_prochain"],
                calc["statut_court"]
            ), tags=(calc["code_statut"],))

    def afficher_details_plante(self, event=None):
        selected = self.tree.selection()
        if not selected:
            self.set_entry_text(self.entry_nom_sci, "-")
            self.set_entry_text(self.entry_nom_vern, "-")
            self.set_entry_text(self.entry_statut, "-")
            self.set_entry_text(self.entry_freq, "Sélectionnez une plante ci-dessus")
            
            self.entry_eau.config(state="normal")
            self.entry_eau.delete("1.0", tk.END)
            self.entry_eau.insert(tk.END, "-")
            self.entry_eau.config(state="disabled")

            self.txt_notes.delete("1.0", tk.END)
            return

        values = self.tree.item(selected[0], "values")
        surnom = values[0]
        plante = next((p for p in self.mes_plantes if p["surnom"] == surnom), None)

        if plante:
            profil = plante["profil"]
            calc = self.calculer_statut_arrosage(plante["date_arrosage"], profil)
            
            gestion_eau = profil.get("gestion_eau", {}) if isinstance(profil.get("gestion_eau"), dict) else {}
            entretien = profil.get("entretien", {}) if isinstance(profil.get("entretien"), dict) else {}
            sante = profil.get("sante_securite", {}) if isinstance(profil.get("sante_securite"), dict) else {}

            nom_sci = profil.get("nom_sci") or profil.get("taxonomie", {}).get("nom_scientifique", "Inconnu")
            nom_vern = profil.get("nom_vern") or profil.get("taxonomie", {}).get("noms_vernaculaires", "N/A")
            if isinstance(nom_vern, list):
                nom_vern = ", ".join(nom_vern)

            self.set_entry_text(self.entry_nom_sci, nom_sci)
            self.set_entry_text(self.entry_nom_vern, nom_vern)
            self.set_entry_text(self.entry_statut, calc["detail_statut"], color=calc["couleur"])

            # 1. Affichage propre de la fréquence
            saison_nom = "Été" if calc["est_saison_chaude"] else "Hiver"
            if calc["delai_actuel"] == 0:
                txt_actuel = "Actuel : REPOS AU SEC"
            else:
                txt_actuel = f"Actuel : tous les {calc['delai_actuel']}j"

            txt_freq_court = (
                f"{txt_actuel} ({saison_nom})  |  "
                f"☀️ Été : tous les {calc['delai_ete']}j  |  "
                f"❄️ Hiver : tous les {calc['delai_hiver']}j"
            )
            self.set_entry_text(self.entry_freq, txt_freq_court)

            # 2. Traitement du type d'eau
            eau_brute = str(gestion_eau.get("qualite_eau") or profil.get("type_eau", "Eau claire")).strip()
            nom_complet = (str(nom_vern) + " " + str(nom_sci)).lower()

            est_tres_sensible = any(term in nom_complet or term in eau_brute.lower() 
                                    for term in ["orchidée", "orchid", "calathea", "carnivore", "dionée", 
                                                 "nepenthes", "maranta", "fougère", "anthurium", "tillandsia", 
                                                 "bromelia", "azalée", "camélia", "hydrangea", "alocasia"])

            self.entry_eau.config(state="normal")
            self.entry_eau.delete("1.0", tk.END)

            if est_tres_sensible:
                self.entry_eau.insert(tk.END, "⭐ MEILLEURS CHOIX : 🧪 Eau Osmosée | 🌧 Eau de Pluie | 🧊 Eau Déminéralisée ", "best_green")
                self.entry_eau.insert(tk.END, f"({eau_brute})", "neutral")
            elif any(k in eau_brute.lower() for k in ["osmosée", "pluie", "déminéralisée"]):
                self.entry_eau.insert(tk.END, "⭐ MEILLEURS CHOIX : 🧪 Eau Osmosée | 🌧 Eau de Pluie ", "best_blue")
                self.entry_eau.insert(tk.END, f"({eau_brute})", "neutral")
            else:
                self.entry_eau.insert(tk.END, "⭐ MEILLEURS CHOIX : 🚰 Eau du robinet reposée 24h | 🍾 Eau de source ", "best_darkblue")
                self.entry_eau.insert(tk.END, f"({eau_brute})", "neutral")

            self.entry_eau.config(state="disabled")

            # 3. Formattage du pavé "Notes & Consignes"
            consignes_list = []

            if profil.get("conseil"):
                consignes_list.append(f"💡 Conseil Général : {profil['conseil']}")

            if entretien.get("rempotage"):
                consignes_list.append(f"🪴 Rempotage : {entretien['rempotage']}")
            if entretien.get("fertilisation"):
                consignes_list.append(f"🧪 Engrais : {entretien['fertilisation']}")
            if entretien.get("taille"):
                consignes_list.append(f"✂️ Taille : {entretien['taille']}")

            if sante.get("toxicite"):
                consignes_list.append(f"⚠️ Toxicité : {sante['toxicite']}")
            if sante.get("maladies"):
                mal = sante["maladies"]
                m_str = ", ".join(mal) if isinstance(mal, list) else mal
                consignes_list.append(f"🦠 Sensibilité maladies : {m_str}")
            if sante.get("proprietes_particulieres"):
                consignes_list.append(f"⭐ Remarques : {sante['proprietes_particulieres']}")

            if est_tres_sensible and "osmosée" not in str(consignes_list).lower():
                consignes_list.append("💧 Sensibilité Eau : Espèce calcifuge. Éviter absolument l'eau du robinet dure.")

            self.txt_notes.delete("1.0", tk.END)
            if consignes_list:
                self.txt_notes.insert(tk.END, "\n".join(consignes_list))
            else:
                self.txt_notes.insert(tk.END, "Aucune consigne ou note particulière.")

    def marquer_arrosee_aujourdhui(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Attention", "Veuillez d'abord sélectionner une plante dans le tableau.")
            return

        self.enregistrer_historique()

        values = self.tree.item(selected[0], "values")
        surnom = values[0]
        date_aujourdhui_fr = format_date_fr(datetime.now().date())

        for p in self.mes_plantes:
            if p["surnom"] == surnom:
                p["date_arrosage"] = date_aujourdhui_fr
                break

        self.sauvegarder_dans_json()
        self.rafraichir_tableau_collection()
        self.afficher_details_plante()
        messagebox.showinfo("Arrosage enregistré", f"'{surnom}' a été marquée comme arrosée aujourd'hui ({date_aujourdhui_fr}) !")

    def ajouter_plante(self):
        surnom = self.entry_surnom.get().strip()
        pot = self.entry_pot.get().strip()
        sel = self.listbox_plantes.curselection()

        if not sel:
            messagebox.showwarning("Attention", "Veuillez sélectionner une espèce.")
            return

        texte_selectionne = self.listbox_plantes.get(sel[0])
        nom_sci = texte_selectionne.split("  —  ")[0].strip()

        profil = next((p for p in DATABASE_PLANTES if p.get("nom_sci") == nom_sci or p.get("taxonomie", {}).get("nom_scientifique") == nom_sci), None)
        if not profil: return

        self.enregistrer_historique()

        nouvelle = {
            "surnom": surnom,
            "profil": profil,
            "pot": pot,
            "date_arrosage": format_date_fr(datetime.now().date())
        }

        self.mes_plantes.append(nouvelle)
        self.sauvegarder_dans_json()
        self.rafraichir_tableau_collection()
        messagebox.showinfo("Succès", f"'{surnom}' a bien été enregistré !")

    def supprimer_plante(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Info", "Sélectionnez une plante à supprimer.")
            return

        surnoms_a_supprimer = [self.tree.item(item, "values")[0] for item in selected]
        liste_surnoms_str = ", ".join([f"'{s}'" for s in surnoms_a_supprimer])

        confirmation = messagebox.askyesno(
            "Confirmation de suppression",
            f"Êtes-vous sûr de vouloir supprimer {liste_surnoms_str} de votre collection ?"
        )

        if not confirmation:
            return

        self.enregistrer_historique()

        for item in selected:
            values = self.tree.item(item, "values")
            surnom = values[0]
            self.mes_plantes = [p for p in self.mes_plantes if p["surnom"] != surnom]

        self.sauvegarder_dans_json()
        self.rafraichir_tableau_collection()
        self.afficher_details_plante()
        messagebox.showinfo("Suppression effectuée", f"Plante(s) supprimée(s). Vous pouvez faire Ctrl+Z pour annuler.")

    def ouvrir_fenetre_calendrier(self):
        win_cal = tk.Toplevel(self)
        win_cal.title("📅 Calendrier d'Arrosage Sur-Mesure")
        win_cal.geometry("700x520")

        frame_top = ttk.LabelFrame(win_cal, text=" Options du calendrier ")
        frame_top.pack(fill="x", padx=10, pady=5)

        aujourdhui = datetime.now().date()
        date_fin_defaut = aujourdhui + timedelta(days=7)

        ttk.Label(frame_top, text="Début (JJ/MM/AAAA) :").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        entry_debut = ttk.Entry(frame_top, width=12)
        entry_debut.insert(0, format_date_fr(aujourdhui))
        entry_debut.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(frame_top, text="Fin (JJ/MM/AAAA) :").grid(row=0, column=2, padx=5, pady=5, sticky="w")
        entry_fin = ttk.Entry(frame_top, width=12)
        entry_fin.insert(0, format_date_fr(date_fin_defaut))
        entry_fin.grid(row=0, column=3, padx=5, pady=5)

        txt_result = tk.Text(win_cal, font=("Consolas", 9), wrap="word", bd=1, relief="solid")
        txt_result.pack(fill="both", expand=True, padx=10, pady=5)

        def generer():
            d_debut = parse_date(entry_debut.get())
            d_fin = parse_date(entry_fin.get())

            if d_fin < d_debut + timedelta(days=6):
                messagebox.showwarning("Durée minimale", "Le calendrier doit s'étendre sur 1 semaine minimum (7 jours).")
                return

            planning = {}

            for p in self.mes_plantes:
                date_dernier = parse_date(p["date_arrosage"])
                curr_date = date_dernier
                
                nom_vern = p["profil"].get("nom_vern") or p["profil"].get("taxonomie", {}).get("noms_vernaculaires", "N/A")
                if isinstance(nom_vern, list):
                    nom_vern = nom_vern[0]

                safety_limit = 0
                while curr_date <= d_fin and safety_limit < 1000:
                    safety_limit += 1
                    delai, _, _, _ = self.get_delai_actuel(p["profil"], curr_date)
                    
                    if delai == 0:
                        # En cas de repos (delai = 0), passer directement au 1er du mois suivant
                        if curr_date.month == 12:
                            curr_date = datetime(curr_date.year + 1, 1, 1).date()
                        else:
                            curr_date = datetime(curr_date.year, curr_date.month + 1, 1).date()
                        continue

                    curr_date += timedelta(days=delai)

                    if d_debut <= curr_date <= d_fin:
                        if curr_date not in planning:
                            planning[curr_date] = []
                        planning[curr_date].append(f"• {p['surnom']} ({nom_vern})")

            res = f"=================================================================\n"
            res += f" 📅 CALENDRIER D'ARROSAGE DU {format_date_fr(d_debut)} AU {format_date_fr(d_fin)}\n"
            res += f"=================================================================\n\n"

            if not planning:
                res += "🟢 Aucun arrosage prévu sur cette période !\n"
            else:
                for date_arr in sorted(planning.keys()):
                    res += f"📍 {format_date_fr(date_arr)} :\n"
                    for item in planning[date_arr]:
                        res += f"   {item}\n"
                    res += "\n"

            txt_result.config(state="normal")
            txt_result.delete("1.0", tk.END)
            txt_result.insert(tk.END, res)

        def copier_presse_papier():
            contenu = txt_result.get("1.0", tk.END).strip()
            if contenu:
                win_cal.clipboard_clear()
                win_cal.clipboard_append(contenu)
                win_cal.update()
                messagebox.showinfo("Presse-papier", "📋 Le calendrier a bien été copié dans le presse-papier !")

        btn_gen = ttk.Button(frame_top, text="⚡ Générer", command=generer)
        btn_gen.grid(row=0, column=4, padx=5, pady=5)

        btn_copy = ttk.Button(frame_top, text="📋 Copier le calendrier", command=copier_presse_papier)
        btn_copy.grid(row=0, column=5, padx=5, pady=5)

        generer()