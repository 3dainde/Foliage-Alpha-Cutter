# Workspace: Foliage-Alpha-Cutter

Ce projet est l'espace de travail dédié au développement de l'add-on Blender **Foliage Alpha Silhouette Cutter & Dynamic PBR Baker**.

## Règles & Conventions du Projet
- **Langage & Environnement** : Python 3.10+ pour Blender 4.2+ / 5.0 (`bpy`, `bmesh`, `mathutils`, `numpy`).
- **Structure des Fichiers** :
  - `foliage_alpha_cutter.py` : Code source de l'add-on Blender.
  - `docs/` : Documentation complète (`MANUEL_UTILISATION.md`, `DOCUMENTATION_TECHNIQUE.md`, `ROADMAP_TODO.md`).
  - `textures/` : Textures PNG transparentes de référence.
- **Standards de Code** :
  - Respect des conventions de nommage Blender (`bl_idname`, `MESH_OT_*`, `VIEW3D_PT_*`).
  - Optimisation des maillages pour les moteurs de jeu en temps réel (Unreal Engine 5).
  - Préservation du typage et des docstrings pour la documentation automatique.
