# 🚀 Feuille de Route & Spécifications des TODOs : Foliage Alpha Cutter

Ce document détaille les spécifications fonctionnelles et techniques des deux fonctionnalités majeures planifiées pour les prochaines versions de l'add-on :
1. **L'ajout de la queue de la feuille (Pétiole 3D procédural)**
2. **La modélisation volumétrique de la fleur de cannabis (Bud / Tête florale)**

---

## 📌 Sommaire

- [TODO 1 : Queue de la Feuille (Pétiole 3D Procédural)](#todo-1--queue-de-la-feuille-pétiole-3d-procédural)
  - [1.1 Analyse Botanique](#11-analyse-botanique)
  - [1.2 Spécification Technique de Modélisation](#12-spécification-technique-de-modélisation)
  - [1.3 Intégration Shaders & Poids de Vent UE](#13-intégration-shaders--poids-de-vent-ue)
  - [1.4 Algorithme Prévisionnel](#14-algorithme-prévisionnel)
- [TODO 2 : Création Volumétrique de la Fleur (Bud / Inflorescence)](#todo-2--création-volumétrique-de-la-fleur-bud--inflorescence)
  - [2.1 Analyse Botanique de l'Inflorescence Femelle](#21-analyse-botanique-de-linflorescence-femelle)
  - [2.2 Architecture 3D Temps Réel (Optimisée Unreal Engine 5)](#22-architecture-3d-temps-réel-optimisée-unreal-engine-5)
  - [2.3 Shader Spécifique "Bud Flower"](#23-shader-spécifique-bud-flower)
  - [2.4 Paramètres de Contrôle Prévus](#24-paramètres-de-contrôle-prévus)
- [Calendrier des Versions](#calendrier-des-versions)

---

## TODO 1 : Queue de la Feuille (Pétiole 3D Procédural)

### 1.1 Analyse Botanique
Le **pétiole** est la pièce foliaire reliant le limbe à la tige principale de la plante. Dans le cas du chanvre (*Cannabis sativa L.*) :
- **Proportions** : Sa longueur varie généralement entre $50\%$ et $120\%$ de la longueur de la foliole centrale, selon l'exposition lumineuse.
- **Section Transversale** : Le pétiole n'est pas un cylindre parfait. Il présente une gouttière longitudinale sur sa face adaxiale (supérieure) et une forme convexe en demi-cercle sur sa face abaxiale (inférieure).
- **Effilement (Tapering)** : Le diamètre est maximal au niveau de l'insertion nodale sur la tige et s'amincit progressivement jusqu'au point de divergence des folioles palmées.
- **Pigmentation** : Souvent teinté d'anthocyanines (rouge violacé ou pourpre), en particulier sur les tiges matures ou exposées à une forte intensité lumineuse.

### 1.2 Spécification Technique de Modélisation
Pour préserver un coût de rendu minimal dans les moteurs temps réel tout en éliminant l'aspect "feuille flottante" :

1. **Génération d'une Spline 3D Paramétrique** :
   - Définition d'une courbe de Bézier à 3 points de contrôle :
     - $P_0$ (Base nodale) : ancrage rigide sur la tige ($[0, y_{\text{base}}, 0]$).
     - $P_1$ (Milieu) : fléchissement gravitaire avec courbure vers le bas.
     - $P_2$ (Sommet) : tangente alignée avec le plan de départ du limbe foliaire.
2. **Profil de Section Basse-Polygone (Low-Poly Profile)** :
   - Profil polygonal à **6 ou 8 sommets** (idéal pour le foliage temps réel UE5).
   - Rayon variable : $R(t) = R_{\text{base}} \cdot (1 - 0.45 t)$ pour $t \in [0, 1]$.
3. **Déroulage UV Automatique (Ribbon UVs)** :
   - Déroulage unifié dans une bande UV rectiligne sans distorsion.
   - Permet d'utiliser une texture de tige tuilable ou de mapper la texture existante.
4. **Jonction avec le Limbe** :
   - Possibilité de raccorder le sommet du pétiole avec les sommets de la base du limbe via `bmesh.ops.weld_verts` ou par emboîtement propre avec normale adoucie.

### 1.3 Intégration Shaders & Poids de Vent UE
- **Couleur de Sommet `WindWeight` Révisée** :
  - Base du pétiole ($t = 0.0$) : $W = 0.0$ (point fixe ancré sur le tronc).
  - Corps du pétiole ($t \in [0, 1]$) : $W(t) = 0.35 \cdot t^{1.5}$ (élasticité modérée de la tige).
  - Limbe foliaire : $W = 0.35 + 0.65 \cdot W_{\text{limbe}}$ (flexion maximale des folioles).
- **Pigmentation du Pétiole** :
  - Curseur d'intensité anthocyanine pour teinter le pétiole en pourpre unabhängig du limbe.

### 1.4 Algorithme Prévisionnel

```python
def generate_procedural_petiole(bm, base_coord, leaf_root_coord, length=0.15, radius=0.006, segments=6, resolution=8):
    """
    Génère un cylindre profilé extrudé le long d'une courbe de Bézier
    reliant la tige nodale à la racine des folioles.
    """
    # 1. Calcul des points de contrôle Bézier avec gravité
    p0 = Vector(base_coord)
    p2 = Vector(leaf_root_coord)
    mid_droop = Vector((0.0, -length * 0.1, -length * 0.2))
    p1 = (p0 + p2) * 0.5 + mid_droop

    # 2. Échantillonnage le long de la courbe
    curve_points = [bezier_interp(p0, p1, p2, t) for t in np.linspace(0, 1, resolution)]

    # 3. Extrusion du profil polygonal à rayon décroissant (taper)
    # ... création des quads BMesh et assignation des coordonnées UV ruban ...
```

---

## TODO 2 : Création Volumétrique de la Fleur (Bud / Inflorescence)

![Rendu Conceptuel de la Fleur](images/preview_purple.png)

### 2.1 Analyse Botanique de l'Inflorescence Femelle
La tête de chanvre cultivée (*bud* ou *cola*) n'est pas un pétale unique, mais une **inflorescence composée** compacte :
- **Axe Central (Rachis)** : La tige florale centrale sur laquelle s'insèrent les sous-unités.
- **Calices & Bractées** : Petits organes coniques en forme de goutte d'eau abritant l'ovaire, densément imbriqués selon une spirale de Fibonacci.
- **Pistils (Stigmates)** : Paires de filaments délicats émergeant de chaque calice. Ils sont blancs et droits au début de la floraison, puis s'enroulent et virent à l'orange ambré ou brun rouille à maturité.
- **Trichomes Glandulaires** : Micro-structures capitellées sphériques recouvrant les bractées, responsables de l'aspect givré, brillant et collant de la fleur.

### 2.2 Architecture 3D Temps Réel (Optimisée Unreal Engine 5)
Une modélisation brute des milliers de calices individuels dépasserait rapidement les millions de polygones. La solution retenue est une **approche hybride multi-échelle** hautement optimisée pour Nanite et le système Foliage d'Unreal Engine :

```
             [ Axe Central / Core Low-Poly ]
                           │
       ┌───────────────────┴───────────────────┐
       ▼                                       ▼
[ Cartes de Foliage Croisées ]         [ Bractées Coniques Simplifiées ]
(Clusters de calices + résine)          (Volume extérieur basse résolution)
       │                                       │
       └───────────────────┬───────────────────┘
                           ▼
          [ Filaments des Pistils & Bruits ]
         (Couleur orange/brun dynamique par âge)
```

1. **Noyau Central (Core Spine)** :
   - Cylindre ou cône basse-définition formant la structure de la tête florale.
2. **Distribution par Phyllotaxie de Fibonacci ($137.5^\circ$)** :
   - Émission de petites grappes de calices (*leaflet / calyx clusters*) le long de l'axe vertical selon l'angle d'or :
     $$\theta_n = n \cdot 137.5^\circ, \quad r_n = R_{\max} \cdot \sqrt{1 - \frac{z_n}{H}}$$
3. **Cartes Alpha de Bractées avec Normales Sphérisées (Spherical Normals)** :
   - Comme pour les arbres réalistes, les normales des cartes de la fleur seront projetées depuis le centre volumétrique du bud pour donner un ombrage doux et plein, sans coupures planes.

### 2.3 Shader Spécifique "Bud Flower"
- **Subsurface Scattering Renforcé (SSS)** : Le calice frais est épais et gorgé de sève, transmettant une douce luminescence vert chartreuse à contre-jour.
- **Trigger de Pistils Dynamique** :
  - Âge précoce ($0.0 - 0.4$) : Pistils blancs laiteux, turgescents.
  - Âge intermédiaire ($0.4 - 0.7$) : Pistils orange vifs, début de courbure.
  - Récolte ($0.7 - 1.0$) : Pistils bruns rouille, enroulés et rétractés sur le calice.
- **Givre de Trichomes Scintillant (Sparkle Glitter)** :
  - Texture de micro-points spéculaires avec reflet de Fresnel pour reproduire la résine scintillante sans surcharger la géométrie.

### 2.4 Paramètres de Contrôle Prévus dans l'Add-on
- **Forme du Bud** : Conique (*Sativa Cola*), Trapu/Rond (*Indica Nug*), Épars (*Wild Ruderalis*).
- **Densité Florale** : Curseur d'espacement des calices (du bud aéré au bud compact ultra-dense).
- **Maturité des Pistils** : Pourcentage de pistils ambrés ($0\%$ à $100\%$).
- **Givre de Résine (Trichome Coverage)** : Curseur de saturation en résine brillante.

---

## Calendrier des Versions

| Version | Fonctionnalité Clé | Statut |
| :---: | :--- | :---: |
| **v1.5.0** | Phénotypes Sativa/Indica/Ruderalis, Découpe Alpha adaptative aux pixels, Shader Dynamique (Âge & Variétés), Bake PBR, Vertex Colors Vent UE. | **Terminé (Actuel)** |
| **v1.6.0** | **TODO 1 : Pétiole 3D Procédural** (Queue de feuille paramétrique, raccordement limbe, déformation élastique vent). | **Prochaine étape** |
| **v2.0.0** | **TODO 2 : Générateur Volumétrique de Fleur (Bud)** (Clusters phyllotaxiques, normales sphérisées, pistils dynamiques, SSS inflorescence). | **Planifié** |
