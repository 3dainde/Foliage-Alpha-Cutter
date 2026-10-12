# 🌿 Foliage Alpha Silhouette Cutter & Dynamic PBR Baker

[![Blender Version](https://img.shields.io/badge/Blender-4.2%20%7C%205.0-orange.svg?logo=blender&logoColor=white)](https://www.blender.org/)
[![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Target Engine](https://img.shields.io/badge/Unreal%20Engine-5.x%20Ready-black.svg?logo=unrealengine&logoColor=white)](https://www.unrealengine.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Un add-on professionnel pour **Blender (4.2+ / 5.0)** conçu pour transformer des images de feuillage détourées (textures alpha) en maillages 3D ultra-optimisés, avec adaptation de la topologie aux pixels, shaders de sénescence interactifs, poids de vent intégrés et export de textures PBR pour **Unreal Engine 5** et **Unity**.

---

## 📸 Aperçu & Galerie

| Phénotypes Botaniques (Sativa, Indica, Ruderalis) | Courbure 3D & Triangles Équilibrés |
| :---: | :---: |
| ![Phénotypes](docs/images/phenotypes_comparison.png) | ![Sativa 3D](docs/images/preview_sativa.png) |

| Variété Purple Sombre (Veines Claires) | Variété Blanche Frost (Résine Givrée) |
| :---: | :---: |
| ![Purple](docs/images/preview_purple.png) | ![White](docs/images/preview_white.png) |

---

## ✨ Fonctionnalités Principales

### 1. 🧬 Sélecteur de Phénotypes Botaniques
- **Sativa (9 folioles)** : Folioles longues, élancées et effilées.
- **Indica (7 folioles)** : Folioles larges, denses et couvrantes.
- **Ruderalis (5 folioles)** : Silhouette compacte et rustique.
- Chargement automatique des textures transparentes et adaptation instantanée du ratio d'aspect.

### 2. ✂️ Découpe Silhouette & Topologie Adaptative aux Pixels
- **Algorithme Moore-Neighbor Tracing** pour une extraction de bordure sub-pixel sans artefact.
- **Simplification Ramer-Douglas-Peucker (RDP) Adaptative** : la tolérance $\varepsilon$ est calibrée en fonction de la surface réelle en pixels, évitant la surcharge géométrique sur les petites variétés (Ruderalis) tout en préservant chaque dentelure sur les grandes feuilles.
- **Triangulation Delaunay & Beautify Fill** : maillage sans faces étirées, prêt pour le low-poly de production.
- **Vertex Reducer (Décimation)** : contrôle précis du budget de sommets pour les LODs de jeux vidéo.

### 3. 🍃 Courbure 3D & Gradient de Vent pour Unreal Engine
- Pli en V le long de la nervure principale ($V_{\text{fold}}$) et courbure apicale gravitaire ($D_{\text{roop}}$).
- **Vertex Colors `WindWeight`** : gradient de flexion peint automatiquement sur les sommets pour les shaders de vent UE5 (`SimpleGrassWind` / `Pivot Painter`).

### 4. 🍂 Shading Procédural & Cycle de Vie Dynamique
- **Curseur de Sénescence / Âge (0.0 à 1.0)** :
  - `0.00` : Feuille jeune veloutée (fini mat soyeux).
  - `0.50` : Chlorose progressive (jaunissement marginal).
  - `0.90` : Récolte avec nécrose apicale (pointes noires/brûlées, taches de rouille et rugosité accrue).
- **Variétés Spécifiques** :
  - **🍇 Purple / Anthocyanines** : Teintes sombres violacées avec conservation des nervures vert clair.
  - **❄️ Blanche / Frost** : Cristallisation de résine blanche dégradée vers la base du limbe.
  - **🎨 Personnalisée** : Sélecteur de teinte libre.

### 5. 🎨 Moteur de Bake PBR & Packing ORM (UE5)
- Bake en un clic sans configuration fastidieuse :
  - **Colour (Col)** : Albedo haute fidélité avec état de maturité figé.
  - **Normal Map (Nm)** : Carte d'espace tangent dérivée du relief des nervures.
  - **Metallic / Roughness (Me)** : Rugosité étalonnée selon l'humidité foliaire.
  - **Occlusion Ambiante (AO)** : Ombrage des replis et nervures.
  - **Subsurface Scattering (SSS)** : Profil de translucidité végétale.
  - **Packed ORM (UE5)** : Canal Rouge = AO, Vert = Roughness, Bleu = Metallic.

---

## 🚀 Installation Rapide

1. Téléchargez le fichier [`foliage_alpha_cutter.py`](foliage_alpha_cutter.py) ou clonez ce dépôt :
   ```bash
   git clone https://github.com/3dainde/Foliage-Alpha-Cutter.git
   ```
2. Dans **Blender (4.2+ / 5.0)** :
   - Allez dans `Édition` > `Préférences` > `Add-ons`.
   - Cliquez sur `Installer depuis un disque...` et sélectionnez `foliage_alpha_cutter.py`.
   - Cochez la case pour activer l'add-on.
3. Dans la vue 3D, appuyez sur <kbd>N</kbd> et sélectionnez l'onglet **"Foliage Cut"**.

---

## 📚 Documentation Complète

Pour des explications approfondies, consultez les guides dédiés dans le dossier [`docs/`](docs/) :

- 📖 **[Manuel d'Utilisation Détaillé](docs/MANUEL_UTILISATION.md)** : Guide pas-à-pas illustré de toutes les fonctionnalités, panneaux et paramètres.
- 🔬 **[Documentation Technique](docs/DOCUMENTATION_TECHNIQUE.md)** : Algorithmes mathématiques (Moore-Neighbor, RDP adaptatif, Delaunay, courbures 3D, shader graph, bake PBR).
- 🚀 **[Feuille de Route & Spécifications des TODOs](docs/ROADMAP_TODO.md)** : Conception détaillée des prochaines étapes :
  1. **Ajout de la queue de la feuille (Pétiole 3D procédural)**.
  2. **Création volumétrique de la fleur de cannabis (Bud / Tête florale)**.

---

## 📂 Structure du Dépôt

```
Foliage-Alpha-Cutter/
├── foliage_alpha_cutter.py     # Add-on Blender principal (code source unique)
├── LICENSE                     # Licence open-source MIT
├── README.md                   # Ce fichier de présentation
├── .gitignore                  # Fichiers ignorés par Git
├── textures/                   # Textures transparentes de référence incluses
│   ├── Sativa.png              # Texture Sativa détourée
│   ├── Indica.png              # Texture Indica détourée
│   └── Ruderalis.png           # Texture Ruderalis détourée
└── docs/                       # Documentation exhaustive
    ├── MANUEL_UTILISATION.md   # Guide d'utilisation complet
    ├── DOCUMENTATION_TECHNIQUE.md # Architecture et algorithmes mathématiques
    ├── ROADMAP_TODO.md         # Spécifications du Pétiole et de la Fleur 3D
    └── images/                 # Rendu et captures d'écran de démonstration
```

---

## 🛠️ Feuille de Route (TODOs)

- [x] Découpe automatique du contour alpha (Moore-Neighbor).
- [x] Adaptation dynamique de la densité de maillage aux pixels réels.
- [x] Triangulation Delaunay équilibrée et vertex reducer.
- [x] Courbure spatiale 3D (pli en V et courbure longitudinale).
- [x] Poids de vent Unreal Engine 5 (`WindWeight` dans les Vertex Colors).
- [x] Shader dynamique avec trigger d'âge (vert -> jaune -> nécrose apicale).
- [x] Variétés botaniques (Purple anthocyanines, White résine givrée).
- [x] Moteur de bake PBR avec texture packée ORM (UE5).
- [ ] **TODO 1** : **Pétiole 3D procédural** (Queue de la feuille paramétrique avec section en sillon adaxial, déformation élastique au vent).
- [ ] **TODO 2** : **Modélisation volumétrique de la fleur (Bud)** (Inflorescence multi-échelle, distribution phyllotaxique de calices, stigmates dynamiques et résine de trichomes).

Consultez le document [`docs/ROADMAP_TODO.md`](docs/ROADMAP_TODO.md) pour les détails d'implémentation.

---

## 📄 Licence & Crédits

Ce projet est sous licence **MIT** - voir le fichier [LICENSE](LICENSE) pour plus de détails.  
Créé et maintenu par **[3dainde](https://github.com/3dainde)**.
