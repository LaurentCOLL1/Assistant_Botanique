import tkinter as tk
from tkinter import ttk, messagebox
from data import DATABASE_PLANTES

class TabCatalogue(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.plante_selectionnee = None

        self.creer_interface()
        self.charger_liste_plantes()

    def creer_interface(self):
        # Panneau séparateur horizontal (PanedWindow)
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=10, pady=10)

        # --- PARTIE GAUCHE : RECHERCHE ET LISTE DES PLANTES ---
        frame_gauche = ttk.LabelFrame(paned, text=" 📚 Catalogue Général ")
        paned.add(frame_gauche, weight=1)

        # Barre de recherche
        ttk.Label(frame_gauche, text="🔍 Rechercher (nom, famille, origine) :", font=("Arial", 9, "bold")).pack(anchor="w", padx=5, pady=(5, 2))
        self.entry_search = ttk.Entry(frame_gauche)
        self.entry_search.pack(fill="x", padx=5, pady=2)
        self.entry_search.bind("<KeyRelease>", self.filtrer_catalogue)

        # Listbox + Scrollbar pour la liste des plantes
        frame_list = ttk.Frame(frame_gauche)
        frame_list.pack(fill="both", expand=True, padx=5, pady=5)

        scrollbar_list = ttk.Scrollbar(frame_list, orient="vertical")
        self.listbox_plantes = tk.Listbox(
            frame_list, 
            yscrollcommand=scrollbar_list.set, 
            font=("Arial", 9),
            selectmode="single",
            bd=1,
            relief="solid"
        )
        scrollbar_list.config(command=self.listbox_plantes.yview)
        
        scrollbar_list.pack(side="right", fill="y")
        self.listbox_plantes.pack(side="left", fill="both", expand=True)

        self.listbox_plantes.bind("<<ListboxSelect>>", self.sur_selection_plante)

        # Compteur de résultats
        self.lbl_compteur = ttk.Label(frame_gauche, text="0 espèce(s) répertoriée(s)", font=("Arial", 8, "italic"))
        self.lbl_compteur.pack(anchor="e", padx=5, pady=2)

        # --- PARTIE DROITE : FICHE BOTANIQUE DÉTAILLÉE ---
        frame_droite = ttk.LabelFrame(paned, text=" 🔬 Fiche Botanique Complète ")
        paned.add(frame_droite, weight=3)

        # Zone de texte défilante pour afficher la fiche
        frame_text = ttk.Frame(frame_droite)
        frame_text.pack(fill="both", expand=True, padx=5, pady=5)

        scrollbar_text = ttk.Scrollbar(frame_text, orient="vertical")
        self.txt_fiche = tk.Text(
            frame_text,
            yscrollcommand=scrollbar_text.set,
            wrap="word",
            font=("Arial", 10),
            bd=1,
            relief="solid",
            padx=10,
            pady=10
        )
        scrollbar_text.config(command=self.txt_fiche.yview)

        scrollbar_text.pack(side="right", fill="y")
        self.txt_fiche.pack(side="left", fill="both", expand=True)

        # Style des balises (Tags) pour le rendu textuel
        self.txt_fiche.tag_configure("titre_principal", font=("Arial", 14, "bold"), foreground="#1e8449")
        self.txt_fiche.tag_configure("section_header", font=("Arial", 11, "bold"), foreground="#2c3e50", background="#e8f8f5")
        self.txt_fiche.tag_configure("label", font=("Arial", 9, "bold"), foreground="#34495e")
        self.txt_fiche.tag_configure("valeur", font=("Arial", 9), foreground="#000000")
        self.txt_fiche.tag_configure("alerte", font=("Arial", 9, "bold"), foreground="#c0392b")
        self.txt_fiche.tag_configure("conseil", font=("Arial", 9, "italic"), foreground="#27ae60", background="#f0f9f8")

    def charger_liste_plantes(self, liste=None):
        """Remplit la Listbox avec les plantes disponibles."""
        self.listbox_plantes.delete(0, tk.END)
        plantes_a_afficher = liste if liste is not None else DATABASE_PLANTES

        for p in plantes_a_afficher:
            nom_sci = self.extraire_valeur(p, [("taxonomie", "nom_scientifique"), "nom_sci"], "Espèce inconnue")
            nom_vern = self.extraire_valeur(p, [("taxonomie", "noms_vernaculaires"), "nom_vern"], "")
            
            if isinstance(nom_vern, list):
                nom_vern = ", ".join(nom_vern)

            label = f"{nom_sci}"
            if nom_vern:
                label += f" ({nom_vern})"
            
            self.listbox_plantes.insert(tk.END, label)

        self.lbl_compteur.config(text=f"{len(plantes_a_afficher)} espèce(s) répertoriée(s)")

        if len(plantes_a_afficher) > 0 and self.listbox_plantes.curselection() == ():
            self.listbox_plantes.select_set(0)
            self.sur_selection_plante()

    def filtrer_catalogue(self, event=None):
        """Filtre les plantes de la Listbox selon la recherche."""
        query = self.entry_search.get().lower().strip()
        if not query:
            self.charger_liste_plantes(DATABASE_PLANTES)
            return

        resultats = []
        for p in DATABASE_PLANTES:
            nom_sci = str(self.extraire_valeur(p, [("taxonomie", "nom_scientifique"), "nom_sci"], "")).lower()
            nom_vern = str(self.extraire_valeur(p, [("taxonomie", "noms_vernaculaires"), "nom_vern"], "")).lower()
            famille = str(self.extraire_valeur(p, [("taxonomie", "famille"), "famille"], "")).lower()
            origine = str(self.extraire_valeur(p, [("taxonomie", "origine_geographique"), ("taxonomie", "origine"), "origine_geographique", "origine"], "")).lower()

            if any(query in champ for champ in [nom_sci, nom_vern, famille, origine]):
                resultats.append(p)

        self.charger_liste_plantes(resultats)

    def extraire_valeur(self, profil, cles, valeur_defaut="Non spécifié(e)"):
        """Extrait une valeur de façon sécurisée (à plat ou imbriquée)."""
        for cle in cles:
            if isinstance(cle, tuple):
                dico = profil
                trouve = True
                for sous_cle in cle:
                    if isinstance(dico, dict) and sous_cle in dico:
                        dico = dico[sous_cle]
                    else:
                        trouve = False
                        break
                if trouve and dico is not None and dico != "" and not isinstance(dico, dict):
                    return dico
            else:
                if cle in profil and profil[cle] is not None and profil[cle] != "":
                    val = profil[cle]
                    if not isinstance(val, dict):
                        return val

        return valeur_defaut

    def sur_selection_plante(self, event=None):
        """Déclenché au clic sur une plante dans la Listbox."""
        sel = self.listbox_plantes.curselection()
        if not sel:
            return

        texte_ligne = self.listbox_plantes.get(sel[0])
        nom_sci_extrait = texte_ligne.split(" (")[0].strip()

        profil = next((p for p in DATABASE_PLANTES if 
                      self.extraire_valeur(p, [("taxonomie", "nom_scientifique"), "nom_sci"], "") == nom_sci_extrait), None)

        if profil:
            self.afficher_fiche_botanique(profil)

    def selectionner_plante(self, nom_sci_cible):
        """Permet à un onglet externe d'ouvrir directement la fiche d'une plante."""
        for idx in range(self.listbox_plantes.size()):
            texte_ligne = self.listbox_plantes.get(idx)
            if nom_sci_cible.lower() in texte_ligne.lower():
                self.listbox_plantes.selection_clear(0, tk.END)
                self.listbox_plantes.selection_set(idx)
                self.listbox_plantes.see(idx)
                self.sur_selection_plante()
                break

    # Alias pour assurer la rétrocompatibilité
    selectionner_plante_par_nom_sci = selectionner_plante

    def ajouter_champ(self, libelle, valeur, est_alerte=False, masquer_si_vide=False):
        """Formatage d'une ligne d'information dans le Text widget."""
        if valeur is None or valeur == "Non spécifié(e)":
            if masquer_si_vide:
                return
            valeur = "Non spécifié(e)"

        if isinstance(valeur, list):
            valeur = ", ".join(map(str, valeur))

        self.txt_fiche.insert(tk.END, f"  • {libelle} : ", "label")
        tag_valeur = "alerte" if est_alerte else "valeur"
        self.txt_fiche.insert(tk.END, f"{valeur}\n", tag_valeur)

    def ajouter_section(self, titre_section):
        """Formatage d'une en-tête de section."""
        self.txt_fiche.insert(tk.END, f"\n{titre_section.upper()}\n", "section_header")

    def afficher_fiche_botanique(self, profil):
        """Construit et affiche l'intégralité des 9 sections botaniques."""
        self.txt_fiche.config(state="normal")
        self.txt_fiche.delete("1.0", tk.END)

        # --- EN-TÊTE PRINCIPAL ---
        nom_sci = self.extraire_valeur(profil, [("taxonomie", "nom_scientifique"), "nom_sci"], "Espèce Inconnue")
        nom_vern = self.extraire_valeur(profil, [("taxonomie", "noms_vernaculaires"), "nom_vern"], "")
        if isinstance(nom_vern, list):
            nom_vern = ", ".join(nom_vern)

        titre = f"🌿 {nom_sci}"
        if nom_vern:
            titre += f"\n   [{nom_vern}]"
        
        self.txt_fiche.insert(tk.END, f"{titre}\n", "titre_principal")
        self.txt_fiche.insert(tk.END, "="*65 + "\n")

        # --- 1. TAXONOMIE & ORIGINE ---
        self.ajouter_section("🧬 1. Taxonomie & Origine")
        self.ajouter_champ("Nom Scientifique", nom_sci)
        self.ajouter_champ("Nom(s) Vernaculaire(s)", nom_vern or "N/A")
        self.ajouter_champ("Famille Botanique", self.extraire_valeur(profil, [("taxonomie", "famille"), "famille"]))
        self.ajouter_champ("Origine Géographique", self.extraire_valeur(profil, [("taxonomie", "origine_geographique"), ("taxonomie", "origine"), "origine_geographique", "origine"]))

        # --- 2. MORPHOLOGIE ET CARACTÉRISTIQUES PHYSIQUES ---
        self.ajouter_section("🌱 2. Morphologie et Caractéristiques Physiques")
        self.ajouter_champ("Port / Habitus", self.extraire_valeur(profil, [("morphologie", "port"), "port"]))
        self.ajouter_champ("Système Racinaire", self.extraire_valeur(profil, [("morphologie", "systeme_racinaire"), "systeme_racinaire"]))
        self.ajouter_champ("Persistance du Feuillage", self.extraire_valeur(profil, [("morphologie", "feuillage", "persistance"), "persistance"]))
        self.ajouter_champ("Morphologie du Feuillage", self.extraire_valeur(profil, [("morphologie", "feuillage", "morphologie"), "morphologie_feuillage"]))
        self.ajouter_champ("Coloris et Motifs du Feuillage", self.extraire_valeur(profil, [("morphologie", "feuillage", "coloris_motifs"), "coloris_motifs"]))

        # --- 3. FLEURS, GRAINES ET FRUITS ---
        self.ajouter_section("🌺 3. Fleurs, Graines et Fruits")
        self.ajouter_champ("Description des Fleurs", self.extraire_valeur(profil, [("morphologie", "fleurs", "description"), "description_fleurs"]))
        self.ajouter_champ("Parfum des Fleurs", self.extraire_valeur(profil, [("morphologie", "fleurs", "parfum"), "parfum"]))
        self.ajouter_champ("Floraison", self.extraire_valeur(profil, [("morphologie", "floraison"), "floraison"]))
        self.ajouter_champ("Fruits et Graines", self.extraire_valeur(profil, [("morphologie", "fruits_graines"), "fruits_graines"]))

        # --- 4. CONDITIONS DE CULTURE & EXPOSITION ---
        self.ajouter_section("☀️ 4. Conditions de Culture & Exposition")
        self.ajouter_champ("Lumière / Exposition", self.extraire_valeur(profil, [("exigences_climatiques", "exposition"), ("exigences_climatiques", "lumiere"), ("conditions_culture", "exposition"), "exposition"]))
        self.ajouter_champ("Rusticité", self.extraire_valeur(profil, [("exigences_climatiques", "rusticite"), "rusticite"]))
        self.ajouter_champ("Température Idéale", self.extraire_valeur(profil, [("exigences_climatiques", "temperature_ideale"), ("conditions_culture", "temperature"), "temperature_ideale", "temperature"]))
        self.ajouter_champ("Humidité de l'Air (Hygrométrie)", self.extraire_valeur(profil, [("exigences_climatiques", "hygrometrie"), ("conditions_culture", "humidite"), "hygrometrie", "humidite"]))

        # --- 5. ARROSAGE & BESOINS EN EAU ---
        self.ajouter_section("💧 5. Arrosage & Besoins en Eau")
        self.ajouter_champ("Consigne Générale", self.extraire_valeur(profil, [("gestion_eau", "frequence_mode")]))
        
        # Extraction du dictionnaire d'arrosage mensuel
        freq_data = None
        if isinstance(profil.get("gestion_eau"), dict):
            freq_data = profil["gestion_eau"].get("frequence_arrosage")
        if freq_data is None:
            freq_data = profil.get("frequence_arrosage")

        # Affichage sous forme de tableau Treeview encastré si la structure mensuelle existe
        if isinstance(freq_data, dict):
            self.txt_fiche.insert(tk.END, "  • Calendrier des fréquences mensuelles :\n", "label")
            
            frame_table = ttk.Frame(self.txt_fiche)
            
            tree = ttk.Treeview(
                frame_table,
                columns=("Mois", "Intervalle"),
                show="headings",
                height=12
            )
            tree.heading("Mois", text="Mois")
            tree.heading("Intervalle", text="Intervalle entre 2 arrosages")
            
            tree.column("Mois", width=140, anchor="center")
            tree.column("Intervalle", width=260, anchor="center")

            mois_map = [
                ("janvier", "Janvier"), ("fevrier", "Février"), ("mars", "Mars"),
                ("avril", "Avril"), ("mai", "Mai"), ("juin", "Juin"),
                ("juillet", "Juillet"), ("aout", "Août"), ("septembre", "Septembre"),
                ("octobre", "Octobre"), ("novembre", "Novembre"), ("decembre", "Décembre")
            ]

            for key_m, nom_m in mois_map:
                val = freq_data.get(key_m, None)
                if val is None:
                    txt_val = "Non renseigné"
                elif val == 0:
                    txt_val = "0 jour (Repos au sec)"
                else:
                    txt_val = f"Tous les {val} jours"
                tree.insert("", tk.END, values=(nom_m, txt_val))

            tree.pack(side="left", fill="x", expand=True)
            
            # Intégration du composant Treeview directement dans le widget Text
            self.txt_fiche.window_create(tk.END, window=frame_table)
            self.txt_fiche.insert(tk.END, "\n\n")
        else:
            self.ajouter_champ("Fréquence Arrosage", freq_data)

        self.ajouter_champ("Variations Saisonnières", self.extraire_valeur(profil, [("gestion_eau", "variation_saisonniere"), "variation_saisonniere"]))
        self.ajouter_champ("Qualité d'eau Recommandée", self.extraire_valeur(profil, [("gestion_eau", "qualite_eau"), "type_eau"]))
        self.ajouter_champ("Sensibilité Minérale", self.extraire_valeur(profil, [("gestion_eau", "sensibilite_minerale"), "sensibilite_minerale"]))
        
        consignes_eau = self.extraire_valeur(profil, [("gestion_eau", "consignes_arrosage")], None)
        self.ajouter_champ("Consignes Arrosage", consignes_eau, masquer_si_vide=True)

        # --- 6. SUBSTRATS & POTAGE ---
        self.ajouter_section("🪴 6. Substrats & Potage")
        self.ajouter_champ("Mélange / Substrat Conseillé", self.extraire_valeur(profil, [("substrat", "composition_ideale"), ("substrat", "composition"), "substrat"]))
        self.ajouter_champ("pH du Sol", self.extraire_valeur(profil, [("substrat", "ph"), "ph"]))
        self.ajouter_champ("Ingrédients Recommandés", self.extraire_valeur(profil, [("substrat", "ingredients_recommandes"), "ingredients_recommandes"]))
        self.ajouter_champ("Éléments Interdits", self.extraire_valeur(profil, [("substrat", "elements_interdits"), "elements_interdits"]))
        
        drainage = self.extraire_valeur(profil, [("substrat", "drainage"), "drainage"], None)
        self.ajouter_champ("Besoins en Drainage", drainage, masquer_si_vide=True)

        # --- 7. ENTRETIEN & NUTRITION ---
        self.ajouter_section("🛠️ 7. Entretien & Nutrition")
        self.ajouter_champ("Rempotage", self.extraire_valeur(profil, [("entretien", "rempotage"), "rempotage"]))
        self.ajouter_champ("Fertilisation / Engrais", self.extraire_valeur(profil, [("entretien", "fertilisation"), ("entretien", "engrais"), "engrais"]))
        self.ajouter_champ("Taille & Nettoyage", self.extraire_valeur(profil, [("entretien", "taille"), "taille"]))
        self.ajouter_champ("Multiplication", self.extraire_valeur(profil, [("entretien", "multiplication"), "multiplication"]))

        # --- 8. SANTÉ, RAVAGEURS & SÉCURITÉ ---
        self.ajouter_section("🦠 8. Santé, Ravageurs & Sécurité")
        
        toxicite = self.extraire_valeur(profil, [("sante_securite", "toxicite"), "toxicite"])
        est_toxique = any(mot in str(toxicite).lower() for mot in ["toxique", "danger", "oui", "mortel"])
        self.ajouter_champ("Toxicité (Animaux / Enfants)", toxicite, est_alerte=est_toxique)

        self.ajouter_champ("Sensibilité Maladies / Parasites", self.extraire_valeur(profil, [("sante_securite", "maladies"), "maladies"]))
        self.ajouter_champ("Ravageurs Principalement Concernés", self.extraire_valeur(profil, [("sante_securite", "ravageurs"), "ravageurs"]))

        remarques = self.extraire_valeur(profil, [("sante_securite", "proprietes_particulieres"), "proprietes_particulieres"], None)
        self.ajouter_champ("Propriétés Particulières", remarques, masquer_si_vide=True)

        # --- 9. CONSEIL BOTANIQUE ---
        conseil = self.extraire_valeur(profil, ["conseil", "conseil_general"], None)
        if conseil and conseil != "Non spécifié(e)":
            self.txt_fiche.insert(tk.END, "\n💡 9. CONSEIL BOTANIQUE\n", "section_header")
            self.txt_fiche.insert(tk.END, f"{conseil}\n", "conseil")

        self.txt_fiche.config(state="disabled")