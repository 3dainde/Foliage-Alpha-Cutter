bl_info = {
    "name": "Foliage Alpha Silhouette Cutter & Dynamic PBR Baker",
    "author": "Antigravity & 3dainde",
    "version": (1, 6, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Onglet 'Foliage Cut'",
    "description": "Générateur multi-familles végétales (Cannabis, Potager/Tomates, Arbres, Intérieur) avec découpe silhouette alpha adaptative, Unsubdivide/triangles Delaunay, courbure 3D, vertex colors vent UE5, shader dynamique (Trigger Âge Y+ vers Y-, Variétés Violette et Blanche trichomes Y- vers Y+) et Bake PBR.",
    "category": "Mesh",
}

import bpy
import bmesh
import numpy as np
import math
import os
from mathutils import Vector

# ==============================================================================
# 1. OUTILS UTILITAIRES & RÉCUPÉRATION DES TEXTURES
# ==============================================================================

def get_image_alpha_from_object(obj):
    """Récupère l'image et sa carte alpha depuis le matériau de l'objet."""
    if not obj or not obj.data or not obj.data.materials:
        return None, None
    mat = obj.data.materials[0]
    if not mat or not mat.node_tree:
        return None, None
    for node in mat.node_tree.nodes:
        if node.type == 'TEX_IMAGE' and node.image:
            img = node.image
            w, h = img.size[0], img.size[1]
            if w > 0 and h > 0 and img.channels >= 4:
                px = np.array(img.pixels).reshape((h, w, 4))
                return img, px[:, :, 3]
    return None, None

def get_addon_base_dir():
    """
    Détermine de manière robuste le répertoire racine de l'add-on.
    Gère le cas critique où le script est exécuté depuis le bloc-texte interne d'un fichier .blend,
    évitant l'erreur de chemin 'C:\\...\\File.blend\\textures'.
    """
    if "__file__" in globals() and __file__:
        cand = os.path.abspath(__file__)
        while cand and (not os.path.isdir(cand) or cand.lower().endswith(".blend")):
            cand = os.path.dirname(cand)
        if cand and os.path.exists(os.path.join(cand, "textures")):
            return cand

    known_dirs = [
        r"C:\Users\authi\AppData\Roaming\Blender Foundation\Blender\5.0\scripts\addons",
        r"C:\Users\authi\.gemini\antigravity\scratch\Foliage-Alpha-Cutter",
        r"C:\Users\authi\Desktop\Textures_PBR_Chanvre",
        r"C:\Users\authi\Desktop",
    ]
    for kd in known_dirs:
        if os.path.exists(os.path.join(kd, "textures")) or os.path.exists(kd):
            return kd
    return os.path.expanduser("~")

def get_source_diffuse_image(obj=None):
    """Récupère la meilleure image source pour le bake PBR."""
    if obj and obj.data and obj.data.materials:
        mat = obj.data.materials[0]
        if mat and mat.node_tree:
            for node in mat.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image:
                    name_l = node.image.name.lower()
                    if "tipmask" not in name_l and "vein" not in name_l and "rough" not in name_l:
                        return node.image
                        
    for img in bpy.data.images:
        name_l = img.name.lower()
        if any(k in name_l for k in ["sativa", "indica", "ruderalis", "regulier", "pomme", "rugueux", "chene", "erable", "monstera", "leaf"]):
            if "mask" not in name_l and "vein" not in name_l and "rough" not in name_l:
                return img

    addon_dir = get_addon_base_dir()
    for fallback in [
        os.path.join(addon_dir, "textures", "Sativa.png") if addon_dir else "",
        os.path.join(addon_dir, "textures", "Feuillage_Regulier.png") if addon_dir else "",
        os.path.join(addon_dir, "textures", "Indica.png") if addon_dir else "",
        os.path.join(addon_dir, "textures", "Ruderalis.png") if addon_dir else "",
        r"C:\Users\authi\AppData\Roaming\Blender Foundation\Blender\5.0\scripts\addons\textures\Sativa.png",
        r"C:\Users\authi\AppData\Roaming\Blender Foundation\Blender\5.0\scripts\addons\textures\Feuillage_Regulier.png",
        r"C:\Users\authi\Downloads\Sativa.png",
        r"C:\Users\authi\Desktop\leaf_transparent.png"
    ]:
        if fallback and os.path.exists(fallback):
            try:
                return bpy.data.images.load(fallback, check_existing=True)
            except Exception:
                pass
    return None

def save_array_as_image(name, arr_rgba, filepath):
    """Sauvegarde un tableau numpy RGBA [0.0, 1.0] en image PNG via l'API Blender."""
    h, w, _ = arr_rgba.shape
    dir_path = os.path.dirname(filepath)
    if dir_path:
        try:
            os.makedirs(dir_path, exist_ok=True)
        except Exception:
            fallback_dir = r"C:\Users\authi\Desktop\Textures_PBR_Chanvre"
            os.makedirs(fallback_dir, exist_ok=True)
            filepath = os.path.join(fallback_dir, os.path.basename(filepath))
    
    existing = bpy.data.images.get(name)
    if existing:
        bpy.data.images.remove(existing)
        
    img = bpy.data.images.new(name, width=w, height=h, alpha=True, float_buffer=False)
    flat_px = np.clip(arr_rgba, 0.0, 1.0).astype(np.float32).ravel()
    img.pixels.foreach_set(flat_px)
    img.filepath_raw = filepath
    img.file_format = 'PNG'
    img.save()
    return img

def ensure_masks_and_textures_for_image(src_img, type_name="Sativa", out_dir=None):
    """
    Génère automatiquement les cartes TipMask, Veins et Roughness adaptées
    à la silhouette et aux nervures de l'image de feuille sélectionnée.
    
    SYMÉTRIE ET RÉPARTITION HOMOGÈNE :
    - Centre de jonction strict au milieu de la silhouette : center_x = (x_min + x_max) / 2.
    - Canal R (Tip Burn) : Pointes de TOUTES les folioles (100% symétrique gauche/droite).
    - Canal G (Margin Burn) : Marges crénelées de toutes les folioles.
    - Canal B (Gradient radial) : 0.0 à la base (pétiole / fleur) -> 1.0 aux pointes.
    """
    if out_dir is None:
        addon_base = get_addon_base_dir()
        if addon_base and os.path.isdir(os.path.join(addon_base, "textures")):
            out_dir = os.path.join(addon_base, "textures", "generated_masks")
        else:
            out_dir = r"C:\Users\authi\Desktop\Textures_PBR_Chanvre"
    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception:
        out_dir = r"C:\Users\authi\Desktop\Textures_PBR_Chanvre"
        os.makedirs(out_dir, exist_ok=True)

    mask_path = os.path.join(out_dir, f"T_{type_name}_TipMask.png")
    veins_path = os.path.join(out_dir, f"T_{type_name}_Veins.png")
    rough_path = os.path.join(out_dir, f"T_{type_name}_Roughness.png")

    w, h = src_img.size[0], src_img.size[1]
    px = np.array(src_img.pixels).reshape((h, w, 4))
    r, g, b, alpha = px[:, :, 0], px[:, :, 1], px[:, :, 2], px[:, :, 3]
    bin_alpha = (alpha > 0.18).astype(float)

    # Carte de distance au fond
    dist_to_bg = np.zeros_like(bin_alpha)
    curr = bin_alpha.copy()
    for step in range(1, 40):
        eroded = curr * np.roll(curr, 1, 0) * np.roll(curr, -1, 0) * np.roll(curr, 1, 1) * np.roll(curr, -1, 1)
        dist_to_bg += (curr - eroded) * step
        curr = eroded
    dist_to_bg += curr * 40

    # 0. Localisation du centre de jonction foliaire (Symétrie stricte gauche/droite)
    y_idxs, x_idxs = np.where(bin_alpha > 0.5)
    if len(y_idxs) == 0:
        return None, None, None
    center_x = (x_idxs.min() + x_idxs.max()) / 2.0
    y_min_leaf = y_idxs.min()
    y_max_leaf = y_idxs.max()
    y_span = max(1.0, float(y_max_leaf - y_min_leaf))
    junc_y = y_min_leaf + y_span * 0.12

    y_coords, x_coords = np.mgrid[0:h, 0:w]
    dx = (x_coords - center_x) / (w * 0.48)
    dy = (y_coords - junc_y) / (h * 0.72)
    rad_dist = np.sqrt(dx**2 + dy**2)

    # 1. Bouts brûlés (Canal R) : Toutes les pointes de toutes les folioles (100% symétrique)
    tip_outer = np.clip((rad_dist - 0.42) * 2.4, 0.0, 1.0) * np.clip((22.0 - dist_to_bg) / 16.0, 0.0, 1.0)
    tip_very = np.clip((rad_dist - 0.55) * 3.0, 0.0, 1.0) * np.clip((12.0 - dist_to_bg) / 9.0, 0.0, 1.0)
    tip_burn = np.clip(tip_outer * 0.65 + tip_very * 0.85, 0.0, 1.0) * alpha

    # 2. Marges crénelées brûlées (Canal G) : Marges de toutes les folioles (partout sur la feuille)
    margin_edge = np.clip((14.0 - dist_to_bg) / 11.0, 0.0, 1.0)
    margin_burn = np.clip(margin_edge * np.clip((rad_dist - 0.12) * 1.6, 0.0, 1.0), 0.0, 1.0) * alpha

    # 3. Distance radiale normalisée (Canal B) : 0 à la base/fleur, 1 aux pointes
    # Répartition équilibrée sur toute la feuille pour l'âge et les trichomes
    rad_norm = np.clip(rad_dist / 1.15, 0.0, 1.0) * alpha

    mask_out = np.dstack([tip_burn, margin_burn, rad_norm, alpha])
    mask_img = save_array_as_image(f"T_{type_name}_TipMask", mask_out, mask_path)

    # 4. Veines et nervures (Contraste pour variété violette)
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    blur_lum = (np.roll(lum, 1, 0) + np.roll(lum, -1, 0) + np.roll(lum, 1, 1) + np.roll(lum, -1, 1) + 4.0 * lum) / 8.0
    high_pass_veins = np.clip((lum - blur_lum) * 4.5, 0.0, 1.0)
    vein_green = np.clip((g - r) * 1.5, 0.0, 1.0)
    vein_combined = np.clip(high_pass_veins * 0.7 + vein_green * 0.5, 0.0, 1.0) * alpha
    veins_out = np.dstack([vein_combined, vein_combined, vein_combined, alpha])
    veins_img = save_array_as_image(f"T_{type_name}_Veins", veins_out, veins_path)

    # 5. Rugosité mate veloutée (0.62 nervures -> 0.76 limbe végétal)
    rough_base = np.clip(0.76 - vein_combined * 0.14, 0.60, 0.95) * alpha
    rough_out = np.dstack([rough_base, rough_base, rough_base, alpha])
    rough_img = save_array_as_image(f"T_{type_name}_Roughness", rough_out, rough_path)

    # Synchronisation miroir dans C:\Users\authi\Desktop\Textures_PBR_Chanvre si existant
    desktop_dir = r"C:\Users\authi\Desktop\Textures_PBR_Chanvre"
    if os.path.exists(desktop_dir) and os.path.abspath(out_dir).lower() != os.path.abspath(desktop_dir).lower():
        try:
            save_array_as_image(f"T_{type_name}_TipMask_Desk", mask_out, os.path.join(desktop_dir, f"T_{type_name}_TipMask.png"))
            save_array_as_image(f"T_{type_name}_Veins_Desk", veins_out, os.path.join(desktop_dir, f"T_{type_name}_Veins.png"))
            save_array_as_image(f"T_{type_name}_Rough_Desk", rough_out, os.path.join(desktop_dir, f"T_{type_name}_Roughness.png"))
        except Exception:
            pass

    return mask_img, veins_img, rough_img

# ==============================================================================
# 2. SHADER DYNAMIQUE PROCÉDURAL
# ==============================================================================

def setup_dynamic_leaf_shader(mat, base_color_img=None, type_name="Sativa"):
    """
    Construit le shader procédural temps réel dans le matériau avec :
    - Texture Base Color propre au type choisi
    - Chlorose jaune dorée orientée depuis la pointe Y+ vers la base Y-
    - Taches de rouille / marbrure
    - Bouts des feuilles brûlés / noirs en Y+
    - Variété Violette sombre avec nervures claires
    - Variété Blanche (neige / trichomes) orientée depuis la base / fleur Y- vers la pointe Y+
    - Surface mate botanique (specular 0.15, coat 0.0)
    """
    if not mat:
        return None
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    bsdf = None
    for n in nodes:
        if n.type == 'BSDF_PRINCIPLED':
            bsdf = n
            break
            
    if not bsdf:
        bsdf = nodes.new('ShaderNodeBsdfPrincipled')
        bsdf.location = (200, 300)

    bx, by = bsdf.location.x, bsdf.location.y

    # Configuration surface mate
    if 'Specular IOR Level' in bsdf.inputs:
        bsdf.inputs['Specular IOR Level'].default_value = 0.15
    elif 'Specular' in bsdf.inputs:
        bsdf.inputs['Specular'].default_value = 0.15
    if 'Coat Weight' in bsdf.inputs:
        bsdf.inputs['Coat Weight'].default_value = 0.0

    # Nettoyage des anciens nœuds
    for n in list(nodes):
        if n.type not in ('BSDF_PRINCIPLED', 'OUTPUT_MATERIAL'):
            nodes.remove(n)

    if not base_color_img:
        base_color_img = get_source_diffuse_image(None)

    # 1. Texture Base Color
    tex_base_color = nodes.new('ShaderNodeTexImage')
    tex_base_color.name = 'Tex_BaseColor_Source'
    tex_base_color.image = base_color_img
    tex_base_color.location = (bx - 1200, by + 100)

    # Génération des masques synchronisés pour ce type
    mask_img, veins_img, r_img = ensure_masks_and_textures_for_image(base_color_img, type_name)

    # 2. Masque vertical (TipMask)
    tex_mask_node = nodes.new('ShaderNodeTexImage')
    tex_mask_node.name = 'Tex_TipMask'
    tex_mask_node.image = mask_img
    if mask_img:
        tex_mask_node.image.colorspace_settings.name = 'Non-Color'
    tex_mask_node.location = (bx - 1200, by - 150)

    sep_mask = nodes.new('ShaderNodeSeparateColor')
    sep_mask.name = 'Sep_Mask'
    sep_mask.location = (bx - 950, by - 150)
    links.new(tex_mask_node.outputs['Color'], sep_mask.inputs['Color'])

    # 3. Trigger Âge
    node_age = nodes.new('ShaderNodeValue')
    node_age.name = 'Leaf_Age_Trigger'
    node_age.label = '🍃 Trigger Âge (0=Vert, 1=Vieux Marron)'
    node_age.location = (bx - 1200, by + 350)
    node_age.outputs[0].default_value = 0.0

    # 4. Chlorose jaune dorée (Pointe Y+ vers Y-)
    math_eff_age = nodes.new('ShaderNodeMath')
    math_eff_age.operation = 'MULTIPLY_ADD'
    math_eff_age.inputs[1].default_value = 0.70
    math_eff_age.inputs[2].default_value = 0.30
    links.new(sep_mask.outputs['Blue'], math_eff_age.inputs[0])

    mult_age_chlor = nodes.new('ShaderNodeMath')
    mult_age_chlor.operation = 'MULTIPLY'
    links.new(node_age.outputs['Value'], mult_age_chlor.inputs[0])
    links.new(math_eff_age.outputs['Value'], mult_age_chlor.inputs[1])

    map_chlor_fac = nodes.new('ShaderNodeMapRange')
    map_chlor_fac.inputs['From Min'].default_value = 0.05
    map_chlor_fac.inputs['From Max'].default_value = 0.80
    map_chlor_fac.inputs['To Min'].default_value = 0.0
    map_chlor_fac.inputs['To Max'].default_value = 0.95
    map_chlor_fac.clamp = True
    links.new(mult_age_chlor.outputs['Value'], map_chlor_fac.inputs['Value'])

    mix_chlor = nodes.new('ShaderNodeMix')
    mix_chlor.name = 'Mix_Chlorosis'
    mix_chlor.data_type = 'RGBA'
    mix_chlor.blend_type = 'COLOR'
    mix_chlor.location = (bx - 700, by + 200)
    mix_chlor.inputs[7].default_value = (0.98, 0.82, 0.05, 1.0)
    if tex_base_color:
        links.new(tex_base_color.outputs['Color'], mix_chlor.inputs[6])
    links.new(map_chlor_fac.outputs['Result'], mix_chlor.inputs[0])

    # 5. Coordonnées UV & bruit de taches
    tex_coord = nodes.new('ShaderNodeTexCoord')
    tex_coord.name = 'Tex_Coord_Aging'
    tex_coord.location = (bx - 1200, by - 400)

    noise_rust = nodes.new('ShaderNodeTexNoise')
    noise_rust.name = 'Noise_Rust'
    noise_rust.inputs['Scale'].default_value = 24.0
    noise_rust.inputs['Detail'].default_value = 4.0
    noise_rust.inputs['Roughness'].default_value = 0.70
    links.new(tex_coord.outputs['UV'], noise_rust.inputs['Vector'])

    map_rust_spots = nodes.new('ShaderNodeMapRange')
    map_rust_spots.inputs['From Min'].default_value = 0.50
    map_rust_spots.inputs['From Max'].default_value = 0.75
    map_rust_spots.inputs['To Min'].default_value = 0.0
    map_rust_spots.inputs['To Max'].default_value = 1.0
    map_rust_spots.clamp = True
    links.new(noise_rust.outputs['Fac'], map_rust_spots.inputs['Value'])

    map_age_rust = nodes.new('ShaderNodeMapRange')
    map_age_rust.inputs['From Min'].default_value = 0.35
    map_age_rust.inputs['From Max'].default_value = 1.00
    map_age_rust.inputs['To Min'].default_value = 0.0
    map_age_rust.inputs['To Max'].default_value = 0.70
    map_age_rust.clamp = True
    links.new(node_age.outputs['Value'], map_age_rust.inputs['Value'])

    mult_rust = nodes.new('ShaderNodeMath')
    mult_rust.operation = 'MULTIPLY'
    links.new(map_rust_spots.outputs['Result'], mult_rust.inputs[0])
    links.new(map_age_rust.outputs['Result'], mult_rust.inputs[1])

    # 6. Variété Sombre Violacée aux Nervures Claires
    tex_veins = nodes.new('ShaderNodeTexImage')
    tex_veins.name = 'Tex_Veins'
    tex_veins.image = veins_img
    if veins_img:
        tex_veins.image.colorspace_settings.name = 'Non-Color'
    tex_veins.location = (bx - 750, by - 120)

    mix_purple_veins = nodes.new('ShaderNodeMix')
    mix_purple_veins.name = 'Mix_Purple_Veins'
    mix_purple_veins.data_type = 'RGBA'
    mix_purple_veins.blend_type = 'MIX'
    mix_purple_veins.location = (bx - 520, by - 120)
    mix_purple_veins.inputs[6].default_value = (0.13, 0.08, 0.14, 1.0) # Limbe sombre violacé
    mix_purple_veins.inputs[7].default_value = (0.48, 0.52, 0.42, 1.0) # Nervures claires
    links.new(tex_veins.outputs['Color'], mix_purple_veins.inputs[0])

    mix_pheno = nodes.new('ShaderNodeMix')
    mix_pheno.name = 'Mix_Phenotype'
    mix_pheno.data_type = 'RGBA'
    mix_pheno.blend_type = 'COLOR'
    mix_pheno.location = (bx - 500, by + 100)
    mix_pheno.inputs[0].default_value = 0.0 # Standard Vert
    links.new(mix_chlor.outputs[2], mix_pheno.inputs[6])
    links.new(mix_purple_veins.outputs[2], mix_pheno.inputs[7])

    # 7. Variété Blanche : Givre de trichomes micro-fins strictement concentré au bas de la feuille (0.0 à 0.40)
    # Fondu smoothstep paramétrable entre fade_start (0.28) et fade_end (0.40)
    map_back_fade = nodes.new('ShaderNodeMapRange')
    map_back_fade.name = 'Map_Back_Fade'
    map_back_fade.interpolation_type = 'SMOOTHSTEP'
    map_back_fade.inputs['From Min'].default_value = 0.28  # Début fade (100% en-dessous)
    map_back_fade.inputs['From Max'].default_value = 0.40  # Fin fade / limite (0% au-dessus)
    map_back_fade.inputs['To Min'].default_value = 1.0     # 1.0 à la base (Y- proche de la fleur)
    map_back_fade.inputs['To Max'].default_value = 0.0     # 0.0 vers les pointes (Y+)
    map_back_fade.clamp = True
    map_back_fade.location = (bx - 360, by - 260)
    links.new(sep_mask.outputs['Blue'], map_back_fade.inputs['Value'])

    # Modulation fine sur les dentelures de bordure
    math_edge_mult = nodes.new('ShaderNodeMath')
    math_edge_mult.name = 'Math_Edge_Trichomes_Mult'
    math_edge_mult.operation = 'MULTIPLY'
    math_edge_mult.inputs[1].default_value = 0.50
    math_edge_mult.location = (bx - 360, by - 380)
    links.new(sep_mask.outputs['Green'], math_edge_mult.inputs[0])

    math_surf_factor = nodes.new('ShaderNodeMath')
    math_surf_factor.name = 'Math_Surf_Factor'
    math_surf_factor.operation = 'ADD'
    math_surf_factor.inputs[0].default_value = 1.0
    math_surf_factor.location = (bx - 200, by - 380)
    links.new(math_edge_mult.outputs['Value'], math_surf_factor.inputs[1])

    # Bruit micro-fin haute fréquence (Scale 140, Detail 6, Roughness 0.65)
    noise_frost = nodes.new('ShaderNodeTexNoise')
    noise_frost.name = 'Noise_Frost'
    noise_frost.inputs['Scale'].default_value = 140.0
    noise_frost.inputs['Detail'].default_value = 6.0
    noise_frost.inputs['Roughness'].default_value = 0.65
    noise_frost.location = (bx - 360, by - 120)
    links.new(tex_coord.outputs['UV'], noise_frost.inputs['Vector'])

    map_frost = nodes.new('ShaderNodeMapRange')
    map_frost.name = 'Map_Frost'
    map_frost.inputs['From Min'].default_value = 0.52
    map_frost.inputs['From Max'].default_value = 0.68
    map_frost.inputs['To Min'].default_value = 0.0
    map_frost.inputs['To Max'].default_value = 1.0
    map_frost.clamp = True
    map_frost.location = (bx - 200, by - 120)
    links.new(noise_frost.outputs['Fac'], map_frost.inputs['Value'])

    # Combinaison bruit et morphologie de surface
    mult_noise_surf = nodes.new('ShaderNodeMath')
    mult_noise_surf.name = 'Mult_Noise_Surf'
    mult_noise_surf.operation = 'MULTIPLY'
    mult_noise_surf.location = (bx - 40, by - 120)
    links.new(map_frost.outputs['Result'], mult_noise_surf.inputs[0])
    links.new(math_surf_factor.outputs['Value'], mult_noise_surf.inputs[1])

    # Application stricte du masque de hauteur Y (trichomes confinés à 0 - 0.40, fondu 0.28 - 0.40)
    mult_frost_back = nodes.new('ShaderNodeMath')
    mult_frost_back.name = 'Mult_Frost_Back'
    mult_frost_back.operation = 'MULTIPLY'
    mult_frost_back.location = (bx + 120, by - 120)
    links.new(mult_noise_surf.outputs['Value'], mult_frost_back.inputs[0])
    links.new(map_back_fade.outputs['Result'], mult_frost_back.inputs[1])

    # Multiplicateur de force visuelle et intensité temps réel
    math_frost_fac = nodes.new('ShaderNodeMath')
    math_frost_fac.name = 'Math_Frost_Fac'
    math_frost_fac.operation = 'MULTIPLY'
    math_frost_fac.inputs[1].default_value = 0.0
    math_frost_fac.location = (bx + 280, by - 120)
    links.new(mult_frost_back.outputs['Value'], math_frost_fac.inputs[0])

    mix_frost = nodes.new('ShaderNodeMix')
    mix_frost.name = 'Mix_Trichomes'
    mix_frost.data_type = 'RGBA'
    mix_frost.blend_type = 'MIX'
    mix_frost.location = (bx - 380, by + 100)
    mix_frost.inputs[7].default_value = (0.92, 0.95, 0.90, 1.0)
    links.new(mix_pheno.outputs[2], mix_frost.inputs[6])
    links.new(math_frost_fac.outputs['Value'], mix_frost.inputs[0])

    # 8. Taches de rouille / sénescence
    mix_rust = nodes.new('ShaderNodeMix')
    mix_rust.name = 'Mix_Rust'
    mix_rust.data_type = 'RGBA'
    mix_rust.blend_type = 'MIX'
    mix_rust.location = (bx - 260, by + 100)
    mix_rust.inputs[7].default_value = (0.35, 0.18, 0.05, 1.0)
    links.new(mix_frost.outputs[2], mix_rust.inputs[6])
    links.new(mult_rust.outputs['Value'], mix_rust.inputs[0])

    # 9. Bords crénelés brûlés (Y+ vers Y-)
    map_age_margin = nodes.new('ShaderNodeMapRange')
    map_age_margin.inputs['From Min'].default_value = 0.25
    map_age_margin.inputs['From Max'].default_value = 1.00
    map_age_margin.inputs['To Min'].default_value = 0.0
    map_age_margin.inputs['To Max'].default_value = 0.85
    map_age_margin.clamp = True
    links.new(node_age.outputs['Value'], map_age_margin.inputs['Value'])

    mult_margin = nodes.new('ShaderNodeMath')
    mult_margin.operation = 'MULTIPLY'
    links.new(map_age_margin.outputs['Result'], mult_margin.inputs[0])
    links.new(sep_mask.outputs['Green'], mult_margin.inputs[1])

    mix_margin = nodes.new('ShaderNodeMix')
    mix_margin.name = 'Mix_Margin'
    mix_margin.data_type = 'RGBA'
    mix_margin.blend_type = 'MIX'
    mix_margin.location = (bx - 200, by + 100)
    mix_margin.inputs[7].default_value = (0.22, 0.10, 0.03, 1.0)
    links.new(mix_rust.outputs[2], mix_margin.inputs[6])
    links.new(mult_margin.outputs['Value'], mix_margin.inputs[0])

    # 10. Bouts des feuilles brûlés noirs / charbon (Pointe Y+ vers Y-)
    map_age_tip = nodes.new('ShaderNodeMapRange')
    map_age_tip.inputs['From Min'].default_value = 0.20
    map_age_tip.inputs['From Max'].default_value = 0.85
    map_age_tip.inputs['To Min'].default_value = 0.0
    map_age_tip.inputs['To Max'].default_value = 1.00
    map_age_tip.clamp = True
    links.new(node_age.outputs['Value'], map_age_tip.inputs['Value'])

    mult_tip = nodes.new('ShaderNodeMath')
    mult_tip.operation = 'MULTIPLY'
    links.new(map_age_tip.outputs['Result'], mult_tip.inputs[0])
    links.new(sep_mask.outputs['Red'], mult_tip.inputs[1])

    mix_tip = nodes.new('ShaderNodeMix')
    mix_tip.name = 'Mix_Tip'
    mix_tip.data_type = 'RGBA'
    mix_tip.blend_type = 'MIX'
    mix_tip.location = (bx - 20, by + 100)
    mix_tip.inputs[7].default_value = (0.04, 0.02, 0.01, 1.0)
    links.new(mix_margin.outputs[2], mix_tip.inputs[6])
    links.new(mult_tip.outputs['Value'], mix_tip.inputs[0])

    links.new(mix_tip.outputs[2], bsdf.inputs['Base Color'])
    if tex_base_color:
        links.new(tex_base_color.outputs['Alpha'], bsdf.inputs['Alpha'])

    # 11. Rugosité mate veloutée (0.76 de base)
    tex_roughness = nodes.new('ShaderNodeTexImage')
    tex_roughness.name = 'Tex_Roughness_Procedural'
    tex_roughness.image = r_img
    if r_img:
        tex_roughness.image.colorspace_settings.name = 'Non-Color'
    tex_roughness.location = (bx - 300, by - 220)

    math_rough = nodes.new('ShaderNodeMath')
    math_rough.name = 'Math_Roughness'
    math_rough.operation = 'MULTIPLY_ADD'
    math_rough.location = (bx - 120, by - 220)
    math_rough.inputs[1].default_value = 0.20
    links.new(node_age.outputs['Value'], math_rough.inputs[0])
    links.new(tex_roughness.outputs['Color'], math_rough.inputs[2])

    clamp_rough = nodes.new('ShaderNodeMath')
    clamp_rough.name = 'Clamp_Roughness_Matte'
    clamp_rough.operation = 'MAXIMUM'
    clamp_rough.location = (bx + 80, by - 220)
    clamp_rough.inputs[1].default_value = 0.78
    links.new(math_rough.outputs['Value'], clamp_rough.inputs[0])
    links.new(clamp_rough.outputs['Value'], bsdf.inputs['Roughness'])

    return mat

def update_dynamic_leaf_age(self, context):
    """Callback temps réel : met à jour la valeur du nœud Leaf_Age_Trigger."""
    for mat in bpy.data.materials:
        if mat.node_tree:
            node = mat.node_tree.nodes.get('Leaf_Age_Trigger')
            if node:
                node.outputs[0].default_value = self.leaf_age

def update_dynamic_leaf_phenotype(self, context):
    """Callback temps réel pour basculer entre Classique, Violette et Blanche et régler les paramètres de trichomes."""
    for mat in bpy.data.materials:
        if not mat.node_tree:
            continue
        nodes = mat.node_tree.nodes
        mix_pheno = nodes.get('Mix_Phenotype')
        math_frost_fac = nodes.get('Math_Frost_Fac')
        mix_purple_veins = nodes.get('Mix_Purple_Veins')
        map_back_fade = nodes.get('Map_Back_Fade')
        math_edge_mult = nodes.get('Math_Edge_Trichomes_Mult')

        if not mix_pheno or not math_frost_fac:
            continue

        intensity = getattr(self, "phenotype_intensity", 1.0)
        pheno = self.leaf_phenotype

        if pheno == 'CLASSIC':
            mix_pheno.inputs[0].default_value = 0.0
            math_frost_fac.inputs[1].default_value = 0.0

        elif pheno == 'PURPLE':
            mix_pheno.inputs[0].default_value = float(intensity)
            math_frost_fac.inputs[1].default_value = 0.0
            if mix_purple_veins:
                mix_purple_veins.inputs[6].default_value = (0.13, 0.08, 0.14, 1.0)
                mix_purple_veins.inputs[7].default_value = (0.48, 0.52, 0.42, 1.0)

        elif pheno == 'WHITE':
            mix_pheno.inputs[0].default_value = 0.0
            t_strength = getattr(self, "trichome_strength", 1.0)
            math_frost_fac.inputs[1].default_value = float(intensity * t_strength)

        elif pheno == 'CUSTOM':
            mix_pheno.inputs[0].default_value = float(intensity)
            math_frost_fac.inputs[1].default_value = 0.0
            if mix_purple_veins:
                c = getattr(self, "custom_variety_color", (0.35, 0.05, 0.40, 1.0))
                mix_purple_veins.inputs[6].default_value = (c[0], c[1], c[2], 1.0)
                mix_purple_veins.inputs[7].default_value = (0.6, 0.65, 0.55, 1.0)

        # Mise à jour dynamique des limites de hauteur des trichomes (0.0 à 0.40, fade entre 0.28 et 0.40)
        if map_back_fade:
            f_start = getattr(self, "trichome_fade_start", 0.28)
            f_end = getattr(self, "trichome_fade_end", 0.40)
            map_back_fade.inputs['From Min'].default_value = float(f_start)
            map_back_fade.inputs['From Max'].default_value = max(float(f_start) + 0.001, float(f_end))

        if math_edge_mult:
            e_boost = getattr(self, "trichome_edge_boost", 0.50)
            math_edge_mult.inputs[1].default_value = float(e_boost)

# ==============================================================================
# 3. EXTRACTION DU CONTOUR ALPHA & GÉOMÉTRIE ADAPTATIVE
# ==============================================================================

def dilate_mask(mask, radius):
    """Dilatation morphologique orthogonale sans fermeture des échancrures."""
    if radius <= 0:
        return mask.copy()
    h, w = mask.shape
    dilated = mask.copy()
    for r in range(1, radius + 1):
        up = np.zeros_like(mask)
        down = np.zeros_like(mask)
        left = np.zeros_like(mask)
        right = np.zeros_like(mask)
        up[:-r, :] = dilated[r:, :]
        down[r:, :] = dilated[:-r, :]
        left[:, :-r] = dilated[:, r:]
        right[:, r:] = dilated[:, :-r]
        dilated = dilated | up | down | left | right
    return dilated

def trace_contour_moore(mask):
    """Extraction du contour extérieur 8-connecté selon Moore-Neighbor."""
    h, w = mask.shape
    y_idxs, x_idxs = np.where(mask)
    if len(y_idxs) == 0:
        return []
    start_y = y_idxs.min()
    start_x = x_idxs[y_idxs == start_y].min()
    start_pt = (int(start_x), int(start_y))

    dirs = [(0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1)]
    contour = [start_pt]
    curr = start_pt
    back_idx = 4

    max_steps = 15000
    for _ in range(max_steps):
        found = False
        scan_start = (back_idx + 1) % 8
        for i in range(8):
            d_idx = (scan_start + i) % 8
            dx, dy = dirs[d_idx]
            nx, ny = curr[0] + dx, curr[1] + dy
            if 0 <= nx < w and 0 <= ny < h and mask[ny, nx]:
                curr = (nx, ny)
                contour.append(curr)
                back_idx = (d_idx + 4) % 8
                found = True
                break
        if not found or curr == start_pt:
            break
    return contour

def rdp_simplify(points, epsilon):
    """Simplification polygonale de Ramer-Douglas-Peucker."""
    if len(points) < 3:
        return points
    p1 = np.array(points[0], dtype=float)
    p2 = np.array(points[-1], dtype=float)
    pts = np.array(points, dtype=float)

    line_vec = p2 - p1
    line_len = np.linalg.norm(line_vec)
    if line_len < 1e-6:
        dists = np.linalg.norm(pts - p1, axis=1)
    else:
        norm_line = line_vec / line_len
        vec_from_p1 = pts - p1
        proj = np.dot(vec_from_p1, norm_line)
        proj_pts = p1 + np.outer(proj, norm_line)
        dists = np.linalg.norm(pts - proj_pts, axis=1)

    max_idx = int(np.argmax(dists))
    max_dist = dists[max_idx]

    if max_dist > epsilon:
        left = rdp_simplify(points[:max_idx + 1], epsilon)
        right = rdp_simplify(points[max_idx:], epsilon)
        return left[:-1] + right
    else:
        return [points[0], points[-1]]

def generate_foliage_mesh(obj, alpha_map, dim_x=None, dim_y=None, 
                          margin_px=3, auto_adapt=True, contour_detail=4.5,
                          interior_subdiv=1, unsub_iters=0, triangulate=True,
                          v_fold=0.04, droop=0.05, bake_wind=True,
                          threshold=0.08, grid_res=24):
    """
    Génère le maillage détouré au contour exact avec détection des pixels, courbure 3D et triangles réguliers.
    Garantit la préservation immuable des dimensions de référence sans aucun rétrécissement.
    """
    h, w = alpha_map.shape
    bin_mask = (alpha_map > threshold)
    
    y_idxs, x_idxs = np.where(bin_mask)
    if len(y_idxs) == 0:
        return
        
    leaf_area = np.count_nonzero(bin_mask)
    leaf_w = x_idxs.max() - x_idxs.min() + 1
    leaf_h = y_idxs.max() - y_idxs.min() + 1

    # 1. Détection & Adaptation de la géométrie aux pixels réels
    if auto_adapt:
        norm_size = leaf_area / 150000.0
        eff_eps = float(np.clip(contour_detail / (norm_size**0.35), 2.5, 8.0))
        if leaf_area < 80000:
            eff_cuts = min(interior_subdiv, 1)
        else:
            eff_cuts = interior_subdiv
    else:
        eff_eps = contour_detail
        eff_cuts = interior_subdiv

    # 2. Dilatation serrée
    dilated = dilate_mask(bin_mask, margin_px)

    # 3. Traçage du contour & simplification
    raw_contour = trace_contour_moore(dilated)
    if len(raw_contour) < 3:
        raw_contour = [(x_idxs.min(), y_idxs.min()), (x_idxs.max(), y_idxs.min()),
                       (x_idxs.max(), y_idxs.max()), (x_idxs.min(), y_idxs.max())]
    simplified = rdp_simplify(raw_contour, eff_eps)

    # 4. Résolution et sauvegarde immuable des dimensions (CORRECTION DU RÉTRÉCISSEMENT)
    if dim_y is None or dim_x is None:
        if obj and "leaf_ref_dim_y" in obj:
            dim_y = float(obj["leaf_ref_dim_y"])
            dim_x = float(obj.get("leaf_ref_dim_x", dim_y * (w / h)))
        elif obj and obj.dimensions.y > 0.05:
            # Calcul en inversant le ratio réel de couverture pour ne pas réduire le canevas
            ratio_y = float(leaf_h) / float(h)
            dim_y = obj.dimensions.y / max(0.1, ratio_y)
            dim_x = dim_y * (w / h)
        else:
            dim_y = 0.75
            dim_x = 0.75 * (w / h)

    # Stockage de la référence sur l'objet
    if obj:
        obj["leaf_ref_dim_y"] = float(dim_y)
        obj["leaf_ref_dim_x"] = float(dim_x)

    # 5. Tessellation 2D via Curve GLU
    curve_data = bpy.data.curves.new(name="Temp_Leaf_Contour", type='CURVE')
    curve_data.dimensions = '2D'
    curve_data.fill_mode = 'BOTH'
    spline = curve_data.splines.new('POLY')
    spline.points.add(len(simplified) - 1)
    for i, pt in enumerate(simplified):
        u = pt[0] / max(1, w - 1)
        v = pt[1] / max(1, h - 1)
        spline.points[i].co = ((u - 0.5) * dim_x, (v - 0.5) * dim_y, 0.0, 1.0)
    spline.use_cyclic_u = True

    temp_obj = bpy.data.objects.new("Temp_Leaf_Curve_Obj", curve_data)
    bpy.context.scene.collection.objects.link(temp_obj)
    mesh_from_curve = bpy.data.meshes.new_from_object(temp_obj)
    bpy.data.objects.remove(temp_obj, do_unlink=True)
    bpy.data.curves.remove(curve_data)

    # 6. Découpe interne équilibrée et triangulation Delaunay
    bm = bmesh.new()
    bm.from_mesh(mesh_from_curve)

    if eff_cuts > 0:
        bmesh.ops.subdivide_edges(bm, edges=bm.edges, cuts=eff_cuts, use_grid_fill=True)

    if triangulate:
        bmesh.ops.triangulate(bm, faces=bm.faces, quad_method='BEAUTY', ngon_method='BEAUTY')
        bmesh.ops.beautify_fill(bm, faces=bm.faces, edges=bm.edges, method='AREA')

    # 7. Courbure 3D réaliste (pli en V et courbure longitudinale)
    uv_layer = bm.loops.layers.uv.verify()
    for vert in bm.verts:
        u = (vert.co.x / dim_x) + 0.5
        v = (vert.co.y / dim_y) + 0.5
        cx = (u - 0.5) * 2.0
        cy = (v - 0.5) * 2.0
        z_v = (1.0 - abs(cx)**0.8) * v_fold * (1.0 - abs(cy)*0.6)
        z_long = -droop * max(0.0, cy)**1.8
        z_side = -0.03 * (abs(cx)**1.5) * max(0.0, cy + 0.3)
        vert.co.z = z_long - z_v + z_side

    for f in bm.faces:
        for l in f.loops:
            u = (l.vert.co.x / dim_x) + 0.5
            v = (l.vert.co.y / dim_y) + 0.5
            l[uv_layer].uv = (u, v)
        f.smooth = True

    mat = obj.data.materials[0] if obj.data.materials else None
    new_mesh = bpy.data.meshes.new(obj.name + "_CutMesh")
    bm.to_mesh(new_mesh)
    bm.free()
    bpy.data.meshes.remove(mesh_from_curve)

    old_mesh = obj.data
    obj.data = new_mesh

    # 8. Réduction de sommets (Vertex Reducer)
    if unsub_iters > 0:
        mod_decim = obj.modifiers.new("Vertex_Reducer", 'DECIMATE')
        mod_decim.decimate_type = 'COLLAPSE'
        mod_decim.ratio = float(0.5 ** unsub_iters)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier='Vertex_Reducer')

    # 9. Vertex Colors pour le vent Unreal Engine
    if bake_wind:
        col_attr = obj.data.color_attributes.new(name="WindWeight", type='BYTE_COLOR', domain='POINT')
        y_coords = [v.co.y for v in obj.data.vertices]
        if y_coords:
            y_min = min(y_coords)
            junc_y = y_min + (max(y_coords) - y_min) * 0.25
            for idx, v_vert in enumerate(obj.data.vertices):
                if v_vert.co.y <= junc_y:
                    w_val = 0.0
                else:
                    w_val = float(np.clip((v_vert.co.y - junc_y) / (max(y_coords) - junc_y), 0.0, 1.0) ** 2)
                col_attr.data[idx].color = (w_val, w_val, w_val, 1.0)

    if mat:
        if not obj.data.materials:
            obj.data.materials.append(mat)
        else:
            obj.data.materials[0] = mat

    if old_mesh and old_mesh.users == 0:
        bpy.data.meshes.remove(old_mesh)

# ==============================================================================
# 4. MOTEUR DE BAKE TEXTURES PBR (UNREAL ENGINE)
# ==============================================================================

def bake_leaf_pbr(source_img, output_dir, age=0.0,
                  bake_col=True, bake_nm=True, bake_me=True,
                  bake_ao=True, bake_sss=True, bake_orm=True,
                  normal_strength=2.2):
    """
    Génère les textures PBR avec le rendu exact (bouts noirs, chlorose, matité).
    Alignement vertical corrigé de Y+ vers Y- pour l'âge.
    """
    w, h = source_img.size[0], source_img.size[1]
    px = np.array(source_img.pixels).reshape((h, w, 4))
    r, g, b, alpha = px[:, :, 0], px[:, :, 1], px[:, :, 2], px[:, :, 3]
    bin_alpha = (alpha > 0.35).astype(float)
    
    saved_textures = {}
    age_clamp = float(np.clip(age, 0.0, 1.0))
    lum = 0.299 * r + 0.587 * g + 0.114 * b

    dist_to_bg = np.zeros_like(bin_alpha)
    curr = bin_alpha.copy()
    for step in range(1, 40):
        eroded = curr * np.roll(curr, 1, 0) * np.roll(curr, -1, 0) * np.roll(curr, 1, 1) * np.roll(curr, -1, 1)
        dist_to_bg += (curr - eroded) * step
        curr = eroded
    dist_to_bg += curr * 40
    
    y_idxs, x_idxs = np.where(bin_alpha > 0.5)
    if len(y_idxs) == 0:
        center_x = w / 2.0
        junc_y = 0.0
    else:
        center_x = (x_idxs.min() + x_idxs.max()) / 2.0
        y_min_leaf = y_idxs.min()
        y_max_leaf = y_idxs.max()
        y_span = max(1.0, float(y_max_leaf - y_min_leaf))
        junc_y = y_min_leaf + y_span * 0.12

    y_coords, x_coords = np.mgrid[0:h, 0:w]
    dx = (x_coords - center_x) / (w * 0.48)
    dy = (y_coords - junc_y) / (h * 0.72)
    rad_dist = np.sqrt(dx**2 + dy**2)

    # Bouts brûlés et marges (Toutes les pointes de toutes les folioles, 100% symétrique)
    tip_outer = np.clip((rad_dist - 0.42) * 2.4, 0.0, 1.0) * np.clip((22.0 - dist_to_bg) / 16.0, 0.0, 1.0)
    tip_very = np.clip((rad_dist - 0.55) * 3.0, 0.0, 1.0) * np.clip((12.0 - dist_to_bg) / 9.0, 0.0, 1.0)
    tip_burn = np.clip(tip_outer * 0.65 + tip_very * 0.85, 0.0, 1.0) * alpha

    margin_edge = np.clip((14.0 - dist_to_bg) / 11.0, 0.0, 1.0)
    margin_burn = np.clip(margin_edge * np.clip((rad_dist - 0.12) * 1.6, 0.0, 1.0), 0.0, 1.0) * alpha

    rad_norm = np.clip(rad_dist / 1.15, 0.0, 1.0) * alpha

    # 1. Base Color
    if bake_col:
        eff_age = age_clamp * np.clip(0.30 + 0.70 * rad_norm, 0, 1)
        chlor_fac = np.clip((eff_age - 0.05) / 0.75, 0.0, 0.95)
        
        gold_r, gold_g, gold_b = 0.98, 0.82, 0.05
        lum_norm = lum / np.maximum(lum.max(), 1e-4)
        col_r = r * (1.0 - chlor_fac) + (gold_r * lum_norm) * chlor_fac
        col_g = g * (1.0 - chlor_fac) + (gold_g * lum_norm) * chlor_fac
        col_b = b * (1.0 - chlor_fac) + (gold_b * lum_norm) * chlor_fac
        
        if age_clamp > 0.35:
            rust_fac = np.clip((age_clamp - 0.35) / 0.65, 0.0, 0.70)
            noise_rust = (np.sin(x_coords * 0.035 + y_coords * 0.027) * 0.5 + 
                          np.cos(x_coords * 0.081 - y_coords * 0.063) * 0.5)
            rust_mask = np.clip((noise_rust - 0.15) * 2.2, 0.0, 1.0) * rust_fac
            rust_r, rust_g, rust_b = 0.35, 0.18, 0.05
            col_r = col_r * (1.0 - rust_mask) + rust_r * rust_mask
            col_g = col_g * (1.0 - rust_mask) + rust_g * rust_mask
            col_b = col_b * (1.0 - rust_mask) + rust_b * rust_mask

        if age_clamp > 0.25:
            margin_fac = np.clip((age_clamp - 0.25) / 0.75, 0.0, 0.85) * margin_burn
            col_r = col_r * (1.0 - margin_fac) + 0.22 * margin_fac
            col_g = col_g * (1.0 - margin_fac) + 0.10 * margin_fac
            col_b = col_b * (1.0 - margin_fac) + 0.03 * margin_fac

        if age_clamp > 0.20:
            tip_fac = np.clip((age_clamp - 0.20) / 0.65, 0.0, 1.00) * tip_burn
            col_r = col_r * (1.0 - tip_fac) + 0.04 * tip_fac
            col_g = col_g * (1.0 - tip_fac) + 0.02 * tip_fac
            col_b = col_b * (1.0 - tip_fac) + 0.01 * tip_fac

        col_out = np.dstack([np.clip(col_r, 0, 1) * alpha, np.clip(col_g, 0, 1) * alpha, np.clip(col_b, 0, 1) * alpha, alpha])
        path_col = os.path.join(output_dir, "T_Feuille_BaseColor.png")
        saved_textures["BaseColor"] = save_array_as_image("T_Feuille_BaseColor", col_out, path_col)

    # 2. Normal Map
    gx, gy = np.zeros_like(r), np.zeros_like(r)
    if bake_nm or bake_ao or bake_orm:
        height_map = (g * 0.7 + lum * 0.3) * alpha
        blur = (np.roll(height_map, 1, 0) + np.roll(height_map, -1, 0) + 
                np.roll(height_map, 1, 1) + np.roll(height_map, -1, 1) + 4.0 * height_map) / 8.0
        high_pass = height_map - blur
        enhanced_height = height_map + high_pass * 2.5
        
        gx[:, 1:-1] = (enhanced_height[:, 2:] - enhanced_height[:, :-2]) * 0.5
        gy[1:-1, :] = (enhanced_height[2:, :] - enhanced_height[:-2, :]) * 0.5
        
        nx = -gx * normal_strength
        ny = gy * normal_strength
        nz = np.ones_like(nx)
        norm_len = np.maximum(np.sqrt(nx*nx + ny*ny + nz*nz), 1e-6)
        nx /= norm_len; ny /= norm_len; nz /= norm_len
        
        nm_rgb = np.dstack([(nx * 0.5 + 0.5) * alpha, (ny * 0.5 + 0.5) * alpha, (nz * 0.5 + 0.5) * alpha, alpha])
        if bake_nm:
            path_nm = os.path.join(output_dir, "T_Feuille_Normal.png")
            saved_textures["Normal"] = save_array_as_image("T_Feuille_Normal", nm_rgb, path_nm)

    # 3. Roughness
    veins_contrast = np.clip((lum - np.roll(lum, 1, 0)) * 3.5, 0.0, 1.0)
    rough_base = np.clip(0.76 - veins_contrast * 0.14, 0.60, 0.95)
    rough_map = np.clip(rough_base + age_clamp * 0.18, 0.70, 0.98) * alpha
    if bake_me:
        rough_out = np.dstack([rough_map, rough_map, rough_map, alpha])
        path_rough = os.path.join(output_dir, "T_Feuille_Roughness.png")
        saved_textures["Roughness"] = save_array_as_image("T_Feuille_Roughness", rough_out, path_rough)

    # 4. Ambient Occlusion
    ao_map = 1.0 - np.clip(np.abs(gx) * 1.5 + np.abs(gy) * 1.5, 0.0, 0.45)
    ao_map = np.clip(ao_map, 0.55, 1.0) * alpha
    if bake_ao:
        ao_out = np.dstack([ao_map, ao_map, ao_map, alpha])
        path_ao = os.path.join(output_dir, "T_Feuille_AO.png")
        saved_textures["AO"] = save_array_as_image("T_Feuille_AO", ao_out, path_ao)

    # 5. Subsurface Scattering
    if bake_sss:
        sss_map = np.clip(g * 1.2 - r * 0.3, 0.15, 0.90)
        if age_clamp > 0.4:
            sss_map *= (1.0 - (age_clamp - 0.4) * 0.6)
        sss_map *= alpha
        sss_out = np.dstack([sss_map * 0.35, sss_map * 0.85, sss_map * 0.15, alpha])
        path_sss = os.path.join(output_dir, "T_Feuille_Subsurface.png")
        saved_textures["Subsurface"] = save_array_as_image("T_Feuille_Subsurface", sss_out, path_sss)

    # 6. Pack ORM
    if bake_orm:
        orm_out = np.dstack([ao_map, rough_map, np.zeros_like(ao_map), alpha])
        path_orm = os.path.join(output_dir, "T_Feuille_ORM.png")
        saved_textures["ORM"] = save_array_as_image("T_Feuille_ORM", orm_out, path_orm)

    return saved_textures

# ==============================================================================
# 5. PROPRIÉTÉS & OPÉRATEURS BLENDER
# ==============================================================================

def get_active_leaf_info(props):
    """
    Retourne (nom_affiche, chemin_image, nom_fichier_defaut)
    selon la famille végétale et la variété active, avec recherche de secours.
    """
    addon_dir = get_addon_base_dir()
    tex_dir = os.path.join(addon_dir, "textures") if addon_dir and os.path.isdir(addon_dir) else ""
    
    fam = props.plant_family
    if fam == 'CANNABIS':
        sub = props.leaf_type_cannabis
        if sub == 'SATIVA':
            type_name = "Sativa"
            user_path = props.path_sativa
            def_name = "Sativa.png"
        elif sub == 'INDICA':
            type_name = "Indica"
            user_path = props.path_indica
            def_name = "Indica.png"
        else:
            type_name = "Ruderalis"
            user_path = props.path_ruderalis
            def_name = "Ruderalis.png"

    elif fam == 'GARDEN':
        sub = props.leaf_type_garden
        if sub == 'REGULAR':
            type_name = "Feuillage_Regulier"
            user_path = props.path_garden_regular
            def_name = "Feuillage_Regulier.png"
        elif sub == 'POTATO':
            type_name = "Feuillage_Pomme_De_Terre"
            user_path = props.path_garden_potato
            def_name = "Feuillage_Pomme_De_Terre.png"
        else:
            type_name = "Feuillage_Rugueux"
            user_path = props.path_garden_rugose
            def_name = "Feuillage_Rugueux.png"

    elif fam == 'TREES':
        sub = props.leaf_type_trees
        if sub == 'OAK':
            type_name = "Chene"
            user_path = props.path_tree_oak
            def_name = "Chene.png"
        elif sub == 'MAPLE':
            type_name = "Erable"
            user_path = props.path_tree_maple
            def_name = "Erable.png"
        else:
            type_name = "Arbre_Custom"
            user_path = props.path_tree_custom
            def_name = ""

    elif fam == 'HOUSEPLANTS':
        sub = props.leaf_type_houseplants
        if sub == 'MONSTERA':
            type_name = "Monstera"
            user_path = props.path_house_monstera
            def_name = "Monstera.png"
        elif sub == 'FICUS':
            type_name = "Ficus"
            user_path = props.path_house_ficus
            def_name = "Ficus.png"
        else:
            type_name = "Plante_Custom"
            user_path = props.path_house_custom
            def_name = ""

    else: # CUSTOM
        type_name = "Feuille_Custom"
        user_path = props.path_custom_leaf
        def_name = ""

    # Résolution intelligente du chemin
    resolved_path = ""
    if user_path:
        cand1 = bpy.path.abspath(user_path)
        cand2 = os.path.abspath(user_path)
        cand3 = os.path.join(addon_dir, user_path) if addon_dir else ""
        for c in [cand1, cand2, cand3]:
            if c and os.path.exists(c):
                resolved_path = os.path.abspath(c)
                break

    if not resolved_path and def_name:
        fallbacks = []
        if tex_dir:
            fallbacks.append(os.path.join(tex_dir, def_name))
        fallbacks.append(os.path.join(r"C:\Users\authi\AppData\Roaming\Blender Foundation\Blender\5.0\scripts\addons\textures", def_name))
        fallbacks.append(os.path.join(r"C:\Users\authi\.gemini\antigravity\scratch\Foliage-Alpha-Cutter\textures", def_name))
        fallbacks.append(os.path.join(r"C:\Users\authi\Downloads", def_name))
        fallbacks.append(os.path.join(r"C:\Users\authi\Desktop", def_name))
        for fb in fallbacks:
            if fb and os.path.exists(fb):
                resolved_path = os.path.abspath(fb)
                break

    return type_name, resolved_path

class FoliageBakerProperties(bpy.types.PropertyGroup):
    # Dimension de référence standardisée (évite le rétrécissement lors des ré-applications)
    leaf_base_height: bpy.props.FloatProperty(
        name="Hauteur Référence (m)",
        description="Hauteur canonique en mètres de la feuille générée (standardisé à 0.75m)",
        default=0.75,
        min=0.05,
        max=5.0
    )

    # 1. Famille Végétale (Développable & Extensible)
    plant_family: bpy.props.EnumProperty(
        name="Famille Végétale",
        description="Famille ou catégorie botanique de la feuille",
        items=[
            ('CANNABIS', "🌿 Cannabis", "Famille du chanvre et cannabis (Sativa, Indica, Ruderalis)"),
            ('GARDEN', "🍅 Potager & Jardin", "Plantes du potager (Tomates : Régulier, Pomme de terre, Rugueux)"),
            ('TREES', "🌳 Arbres", "Arbres feuillus et d'ornement (Chêne, Érable, etc.)"),
            ('HOUSEPLANTS', "🪴 Plantes d'intérieur", "Plantes d'intérieur et maison (Monstera, Ficus, etc.)"),
            ('CUSTOM', "📁 Personnalisée / Import", "Importer n'importe quelle texture de feuille détourée"),
        ],
        default='CANNABIS'
    )

    # 1.1 Variétés Cannabis
    leaf_type_cannabis: bpy.props.EnumProperty(
        name="Variété Cannabis",
        description="Phénotype botanique de cannabis",
        items=[
            ('SATIVA', "🌱 Sativa (9 folioles)", "Folioles longues, fines et effilées"),
            ('INDICA', "🌿 Indica (7 folioles)", "Folioles larges, denses et couvrantes"),
            ('RUDERALIS', "🌾 Ruderalis (5 folioles)", "Forme compacte, rustique et conique"),
        ],
        default='SATIVA'
    )

    # 1.2 Variétés Potager / Jardin (Tomates, solanacées)
    leaf_type_garden: bpy.props.EnumProperty(
        name="Morphologie Potager",
        description="Type de feuillage potager (dans l'ordre de la planche botanique)",
        items=[
            ('REGULAR', "🍃 À gauche – Feuillage régulier", "Feuillage régulier standard (à gauche)"),
            ('POTATO', "🥔 Au milieu – Feuillage pomme de terre", "Feuillage type pomme de terre / Potato Leaf (au milieu)"),
            ('RUGOSE', "🌿 À droite – Feuillage rugueux ou nain", "Feuillage rugueux plissé ou nain / Rugose Leaf (à droite)"),
        ],
        default='REGULAR'
    )

    # 1.3 Variétés Arbres
    leaf_type_trees: bpy.props.EnumProperty(
        name="Essence d'Arbre",
        description="Essence forestière ou ornementale",
        items=[
            ('OAK', "🍂 Chêne (Quercus)", "Feuille de chêne lobée"),
            ('MAPLE', "🍁 Érable (Acer)", "Feuille d'érable palmée"),
            ('CUSTOM_TREE', "📁 Arbre personnalisé...", "Image personnalisée d'arbre"),
        ],
        default='OAK'
    )

    # 1.4 Variétés Plantes d'Intérieur
    leaf_type_houseplants: bpy.props.EnumProperty(
        name="Plante d'Intérieur",
        description="Plantes décoratives d'intérieur",
        items=[
            ('MONSTERA', "🪴 Monstera Deliciosa", "Feuille de monstera fenestrée"),
            ('FICUS', "🌿 Ficus Elastica", "Feuille de ficus ovale coriace"),
            ('CUSTOM_HOUSE', "📁 Plante personnalisée...", "Image personnalisée de plante d'intérieur"),
        ],
        default='MONSTERA'
    )

    # Panneau dépliant pour les chemins d'accès
    show_inputs_box: bpy.props.BoolProperty(
        name="Déplier Chemins d'Images",
        description="Afficher ou masquer les champs de chemins de fichiers d'images de la famille sélectionnée",
        default=False
    )

    # Chemins des images
    path_sativa: bpy.props.StringProperty(name="Image Sativa", default="textures/Sativa.png", subtype='FILE_PATH')
    path_indica: bpy.props.StringProperty(name="Image Indica", default="textures/Indica.png", subtype='FILE_PATH')
    path_ruderalis: bpy.props.StringProperty(name="Image Ruderalis", default="textures/Ruderalis.png", subtype='FILE_PATH')

    path_garden_regular: bpy.props.StringProperty(name="Image Feuillage Régulier", default="textures/Feuillage_Regulier.png", subtype='FILE_PATH')
    path_garden_potato: bpy.props.StringProperty(name="Image Pomme de Terre", default="textures/Feuillage_Pomme_De_Terre.png", subtype='FILE_PATH')
    path_garden_rugose: bpy.props.StringProperty(name="Image Feuillage Rugueux", default="textures/Feuillage_Rugueux.png", subtype='FILE_PATH')

    path_tree_oak: bpy.props.StringProperty(name="Image Chêne", default="textures/Chene.png", subtype='FILE_PATH')
    path_tree_maple: bpy.props.StringProperty(name="Image Érable", default="textures/Erable.png", subtype='FILE_PATH')
    path_tree_custom: bpy.props.StringProperty(name="Image Arbre Libre", default="", subtype='FILE_PATH')

    path_house_monstera: bpy.props.StringProperty(name="Image Monstera", default="textures/Monstera.png", subtype='FILE_PATH')
    path_house_ficus: bpy.props.StringProperty(name="Image Ficus", default="textures/Ficus.png", subtype='FILE_PATH')
    path_house_custom: bpy.props.StringProperty(name="Image Intérieur Libre", default="", subtype='FILE_PATH')

    path_custom_leaf: bpy.props.StringProperty(name="Image Personnalisée", default="", subtype='FILE_PATH')

    # 2. Découpe & Topologie Adaptative
    auto_adapt_mesh: bpy.props.BoolProperty(
        name="Adaptation Pixels Auto",
        description="Adapte la géométrie à l'emprise réelle en pixels",
        default=True
    )
    margin: bpy.props.IntProperty(
        name="Marge Silhouette (px)",
        description="Marge de découpe en pixels autour du limbe",
        default=3,
        min=0,
        max=30
    )
    contour_detail: bpy.props.FloatProperty(
        name="Tolérance Contour (px)",
        description="Tolérance RDP du contour",
        default=4.5,
        min=1.0,
        max=15.0
    )
    interior_subdiv: bpy.props.IntProperty(
        name="Subdivision Intérieure",
        description="Subdivision de la surface pour la courbure 3D",
        default=1,
        min=0,
        max=3
    )
    unsub_iters: bpy.props.IntProperty(
        name="Vertex Reducer (Décimation)",
        description="Réduit la densité des polygones (0 = aucun, 1 = -50%, 2 = -75%)",
        default=0,
        min=0,
        max=3
    )
    triangulate: bpy.props.BoolProperty(
        name="Triangles bien répartis",
        description="Équilibre les triangles via Delaunay / Beautify Fill",
        default=True
    )
    grid_res: bpy.props.IntProperty(name="Résolution Grille", default=24, min=8, max=60)
    threshold: bpy.props.FloatProperty(name="Seuil Alpha", default=0.08, min=0.01, max=0.90)
    v_fold: bpy.props.FloatProperty(name="Creux en V (3D)", default=0.04, min=0.0, max=0.15)
    droop: bpy.props.FloatProperty(name="Courbure pointe", default=0.05, min=0.0, max=0.15)
    bake_wind: bpy.props.BoolProperty(name="Vertex Colors (Vent UE)", default=True)

    # 3. Variété / Phénotype Couleurs
    leaf_phenotype: bpy.props.EnumProperty(
        name="Variété / Couleur",
        description="Phénotype et pigmentation de la variété",
        items=[
            ('CLASSIC', "🍃 Classique (Verte / Dorée)", "Variété verte naturelle avec sénescence dorée"),
            ('PURPLE', "🍇 Violette / Purple (Anthocyanines)", "Teintes sombres violacées avec nervures claires"),
            ('WHITE', "❄️ Blanche / Frost (Trichomes)", "Givre de trichomes blancs dégradé depuis la base (Y-)"),
            ('CUSTOM', "🎨 Personnalisée", "Couleur de variété personnalisée"),
        ],
        default='CLASSIC',
        update=update_dynamic_leaf_phenotype
    )
    phenotype_intensity: bpy.props.FloatProperty(
        name="Intensité Variété",
        default=1.0,
        min=0.0,
        max=1.0,
        subtype='FACTOR',
        update=update_dynamic_leaf_phenotype
    )
    custom_variety_color: bpy.props.FloatVectorProperty(
        name="Couleur Personnalisée",
        subtype='COLOR',
        size=4,
        default=(0.35, 0.05, 0.40, 1.0),
        min=0.0,
        max=1.0,
        update=update_dynamic_leaf_phenotype
    )
    # Déclencheur et Paramètres Trichomes / Givre (Variété Blanche : 0 à 0.40, fade 0.28 à 0.40)
    trichome_strength: bpy.props.FloatProperty(
        name="Force Visuelle (Trichomes)",
        description="Force visuelle / densité du givre de résine",
        default=1.0,
        min=0.0,
        max=2.5,
        subtype='FACTOR',
        update=update_dynamic_leaf_phenotype
    )
    trichome_fade_start: bpy.props.FloatProperty(
        name="Début Fade (Y)",
        description="Position relative Y (0=base, 1=pointe) où le fondu commence (100% de trichomes en-dessous)",
        default=0.28,
        min=0.0,
        max=0.80,
        subtype='FACTOR',
        update=update_dynamic_leaf_phenotype
    )
    trichome_fade_end: bpy.props.FloatProperty(
        name="Fin Fade / Limite (Y)",
        description="Position relative Y maximale au-delà de laquelle les trichomes sont absents",
        default=0.40,
        min=0.05,
        max=1.0,
        subtype='FACTOR',
        update=update_dynamic_leaf_phenotype
    )
    trichome_edge_boost: bpy.props.FloatProperty(
        name="Accentuation Bords Crénelés",
        description="Renforcement des trichomes sur les dentelures de la marge foliaire dans la zone active",
        default=0.50,
        min=0.0,
        max=2.0,
        subtype='FACTOR',
        update=update_dynamic_leaf_phenotype
    )

    # 4. Cycle de Vie Dynamique
    leaf_age: bpy.props.FloatProperty(
        name="Trigger Âge / Cycle de Vie",
        description="Trigger temps réel (de la pointe Y+ vers le bas Y-) : 0.0 = Jeune saine -> 1.0 = Bouts noirs brûlés",
        default=0.0,
        min=0.0,
        max=1.0,
        subtype='FACTOR',
        update=update_dynamic_leaf_age
    )

    # 5. Options Export / Bake PBR
    bake_col: bpy.props.BoolProperty(name="Colour (Col)", default=True)
    bake_nm: bpy.props.BoolProperty(name="Normal Map (Nm)", default=True)
    bake_me: bpy.props.BoolProperty(name="Metallic / Rough (Me)", default=True)
    bake_ao: bpy.props.BoolProperty(name="Ambient Occlusion (AO)", default=True)
    bake_sss: bpy.props.BoolProperty(name="Subsurface (SSS)", default=True)
    bake_orm: bpy.props.BoolProperty(name="Pack ORM (Unreal Engine)", default=True)
    normal_strength: bpy.props.FloatProperty(name="Force Relief (Nm)", default=2.2, min=0.1, max=8.0)
    output_dir: bpy.props.StringProperty(
        name="Dossier Textures",
        default=r"C:\Users\authi\Desktop\Textures_PBR_Chanvre",
        subtype='DIR_PATH'
    )

class MESH_OT_GenerateFoliageByType(bpy.types.Operator):
    """Génère la feuille 3D selon la famille et la variété choisies"""
    bl_idname = "mesh.generate_foliage_by_type"
    bl_label = "Générer la Feuille 3D"
    bl_description = "Charge l'image du type sélectionné, crée les vertex détourés selon l'alpha et applique le matériau dynamique"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.foliage_baker
        type_name, img_path = get_active_leaf_info(props)

        if not img_path or not os.path.exists(img_path):
            self.report({'ERROR'}, f"Fichier image introuvable pour {type_name} : {img_path}")
            return {'CANCELLED'}

        try:
            leaf_img = bpy.data.images.load(img_path, check_existing=True)
            leaf_img.name = f"T_Leaf_{type_name}"
        except Exception as e:
            self.report({'ERROR'}, f"Erreur lors du chargement de l'image : {e}")
            return {'CANCELLED'}

        w, h = leaf_img.size[0], leaf_img.size[1]
        px = np.array(leaf_img.pixels).reshape((h, w, 4))
        alpha_map = px[:, :, 3]

        obj_name = f"Feuille_{type_name}_3D"
        obj = context.active_object if (context.active_object and context.active_object.type == 'MESH') else None
        if not obj or "Feuille_" not in obj.name:
            obj = bpy.data.objects.get(obj_name)
        if not obj or obj.type != 'MESH':
            mesh_tmp = bpy.data.meshes.new(obj_name + "_Mesh")
            obj = bpy.data.objects.new(obj_name, mesh_tmp)
            context.scene.collection.objects.link(obj)
        else:
            obj.name = obj_name
            if obj.data:
                obj.data.name = obj_name + "_Mesh"

        context.view_layer.objects.active = obj
        obj.select_set(True)

        # Standardisation stricte des dimensions (hauteur de référence = props.leaf_base_height)
        dim_y = float(props.leaf_base_height)
        dim_x = float(dim_y * (w / h))

        obj["leaf_ref_dim_y"] = float(dim_y)
        obj["leaf_ref_dim_x"] = float(dim_x)
        obj["leaf_type_name"] = type_name
        obj["leaf_family"] = props.plant_family

        mat_name = f"Mat_{type_name}_3D"
        mat = bpy.data.materials.get(mat_name)
        if not mat:
            mat = bpy.data.materials.new(name=mat_name)
        if not obj.data.materials:
            obj.data.materials.append(mat)
        else:
            obj.data.materials[0] = mat

        generate_foliage_mesh(
            obj=obj,
            alpha_map=alpha_map,
            dim_x=dim_x,
            dim_y=dim_y,
            margin_px=props.margin,
            auto_adapt=props.auto_adapt_mesh,
            contour_detail=props.contour_detail,
            interior_subdiv=props.interior_subdiv,
            unsub_iters=props.unsub_iters,
            triangulate=props.triangulate,
            v_fold=props.v_fold,
            droop=props.droop,
            bake_wind=props.bake_wind,
            threshold=props.threshold,
            grid_res=props.grid_res
        )

        setup_dynamic_leaf_shader(mat, base_color_img=leaf_img, type_name=type_name)
        update_dynamic_leaf_phenotype(props, context)
        update_dynamic_leaf_age(props, context)

        n_verts = len(obj.data.vertices)
        n_faces = len(obj.data.polygons)
        self.report({'INFO'}, f"Feuille {type_name} 3D générée : {n_verts} sommets ({n_faces} triangles) à échelle standard {dim_y}m !")
        return {'FINISHED'}

class MESH_OT_FoliageAlphaCut(bpy.types.Operator):
    """Recalcule la découpe alpha et l'unsubdivide sur l'objet mesh sélectionné sans modifier son échelle"""
    bl_idname = "mesh.foliage_alpha_cut"
    bl_label = "Découper selon l'Alpha"
    bl_description = "Recalcule la silhouette alpha, la marge, l'unsubdivide et les triangles en conservant fidèlement l'échelle de l'objet"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.foliage_baker
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Veuillez sélectionner un objet Mesh !")
            return {'CANCELLED'}

        img, alpha_map = get_image_alpha_from_object(obj)
        if alpha_map is None:
            self.report({'ERROR'}, "Aucune texture image avec canal Alpha trouvée sur cet objet !")
            return {'CANCELLED'}

        w, h = img.size[0], img.size[1]
        # CORRECTION ANTI-RÉTRÉCISSEMENT : Récupération de la référence absolue sauvegardée
        ref_dim_y = float(obj.get("leaf_ref_dim_y", props.leaf_base_height))
        ref_dim_x = float(obj.get("leaf_ref_dim_x", ref_dim_y * (w / h)))

        generate_foliage_mesh(
            obj=obj,
            alpha_map=alpha_map,
            dim_x=ref_dim_x,
            dim_y=ref_dim_y,
            margin_px=props.margin,
            auto_adapt=props.auto_adapt_mesh,
            contour_detail=props.contour_detail,
            interior_subdiv=props.interior_subdiv,
            unsub_iters=props.unsub_iters,
            triangulate=props.triangulate,
            v_fold=props.v_fold,
            droop=props.droop,
            bake_wind=props.bake_wind,
            threshold=props.threshold,
            grid_res=props.grid_res
        )

        n_verts = len(obj.data.vertices)
        n_faces = len(obj.data.polygons)
        self.report({'INFO'}, f"Découpe mise à jour : {n_verts} sommets ({n_faces} triangles) - Échelle {ref_dim_y}m préservée !")
        return {'FINISHED'}

class MESH_OT_SetupDynamicShader(bpy.types.Operator):
    """Initialise ou réinitialise les nœuds procéduraux temps réel sur l'objet sélectionné"""
    bl_idname = "mesh.setup_dynamic_shader"
    bl_label = "Réinitialiser Nœuds Shader"
    bl_description = "Réinitialise le graphe de shader procédural (Trigger Âge, Variétés et surface mate)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if not obj or not obj.data or not obj.data.materials:
            self.report({'ERROR'}, "Veuillez sélectionner un objet doté d'un matériau !")
            return {'CANCELLED'}
        
        props = context.scene.foliage_baker
        mat = obj.data.materials[0]
        src_img = get_source_diffuse_image(obj)
        type_name = obj.get("leaf_type_name", "Leaf")
        setup_dynamic_leaf_shader(mat, base_color_img=src_img, type_name=type_name)
        update_dynamic_leaf_phenotype(props, context)
        update_dynamic_leaf_age(props, context)
            
        self.report({'INFO'}, f"Shader dynamique réinitialisé sur {mat.name} !")
        return {'FINISHED'}

class MESH_OT_BakePBRTextures(bpy.types.Operator):
    """Bake les textures PBR actuelles à l'état du trigger et les sauvegarde sur le disque"""
    bl_idname = "mesh.bake_pbr_textures"
    bl_label = "Bake Textures PBR"
    bl_description = "Génère les fichiers PBR standard (Col, Nm, Me, AO, SSS, ORM) selon l'état actuel pour Unreal Engine"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.foliage_baker
        obj = context.active_object
        
        source_img = get_source_diffuse_image(obj)
        if not source_img:
            self.report({'ERROR'}, "Impossible de trouver une texture image source pour le bake !")
            return {'CANCELLED'}

        saved = bake_leaf_pbr(
            source_img=source_img,
            output_dir=bpy.path.abspath(props.output_dir),
            age=props.leaf_age,
            bake_col=props.bake_col,
            bake_nm=props.bake_nm,
            bake_me=props.bake_me,
            bake_ao=props.bake_ao,
            bake_sss=props.bake_sss,
            bake_orm=props.bake_orm,
            normal_strength=props.normal_strength
        )

        names = ", ".join(saved.keys())
        self.report({'INFO'}, f"Bake réussi ! Fichiers générés : {names} -> {props.output_dir}")
        return {'FINISHED'}

# ==============================================================================
# 6. PANNEAU DE L'INTERFACE UTILISATEUR (UI N-PANEL)
# ==============================================================================

class VIEW3D_PT_FoliageCutterPanel(bpy.types.Panel):
    """Panneau Foliage Cut & Dynamic Shading dans la barre latérale N"""
    bl_label = "Foliage Cut & Dynamic Shading"
    bl_idname = "VIEW3D_PT_foliage_alpha_cutter"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Foliage Cut'

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        props = context.scene.foliage_baker

        # Info objet actif
        box_info = layout.box()
        box_info.label(text="Objet Actif :", icon='MESH_DATA')
        if obj and obj.type == 'MESH':
            n_v = len(obj.data.vertices)
            n_f = len(obj.data.polygons)
            ref_h = obj.get("leaf_ref_dim_y", obj.dimensions.y)
            box_info.label(text=f"• Nom : {obj.name}")
            box_info.label(text=f"• Sommets : {n_v} | Triangles : {n_f}")
            box_info.label(text=f"• Échelle standard : {ref_h:.2f} m")
        else:
            box_info.label(text="Aucun mesh sélectionné", icon='INFO')

        layout.separator()

        # ==========================================
        # 1. CHOIX DE LA FAMILLE, VARIÉTÉ & GÉNÉRATION
        # ==========================================
        box_type = layout.box()
        box_type.label(text="1. Famille & Espèce Végétale", icon='OUTLINER_OB_ARMATURE')
        
        # Sélecteur déroulant de famille
        box_type.prop(props, "plant_family", text="Famille")

        # Sous-sélection de variété selon la famille
        box_leaf = box_type.box()
        if props.plant_family == 'CANNABIS':
            box_leaf.label(text="Variétés de Cannabis :", icon='FILE_IMAGE')
            box_leaf.prop(props, "leaf_type_cannabis", expand=True)
        elif props.plant_family == 'GARDEN':
            box_leaf.label(text="Morphologie du Potager :", icon='IMAGE_RGB')
            box_leaf.prop(props, "leaf_type_garden")
        elif props.plant_family == 'TREES':
            box_leaf.label(text="Essences d'Arbres :", icon='OUTLINER_OB_POINTCLOUD')
            box_leaf.prop(props, "leaf_type_trees")
        elif props.plant_family == 'HOUSEPLANTS':
            box_leaf.label(text="Plantes d'Intérieur :", icon='HOME')
            box_leaf.prop(props, "leaf_type_houseplants")
        else: # CUSTOM
            box_leaf.label(text="Import Libre :", icon='FILE_FOLDER')
            box_leaf.prop(props, "path_custom_leaf", text="Image Alpha")

        # Déplier / Replier les chemins d'images (Inputs)
        row_toggle = box_type.row()
        icon_fold = 'DOWNARROW_HLT' if props.show_inputs_box else 'RIGHTARROW'
        row_toggle.prop(props, "show_inputs_box", text="📁 Déplier Chemins d'Images", icon=icon_fold, toggle=True)
        
        if props.show_inputs_box:
            box_inputs = box_type.box()
            if props.plant_family == 'CANNABIS':
                box_inputs.prop(props, "path_sativa", text="🌱 Sativa")
                box_inputs.prop(props, "path_indica", text="🌿 Indica")
                box_inputs.prop(props, "path_ruderalis", text="🌾 Ruderalis")
            elif props.plant_family == 'GARDEN':
                box_inputs.prop(props, "path_garden_regular", text="🍃 Feuillage régulier")
                box_inputs.prop(props, "path_garden_potato", text="🥔 Pomme de terre")
                box_inputs.prop(props, "path_garden_rugose", text="🌿 Rugueux / Nain")
            elif props.plant_family == 'TREES':
                box_inputs.prop(props, "path_tree_oak", text="🍂 Chêne")
                box_inputs.prop(props, "path_tree_maple", text="🍁 Érable")
                box_inputs.prop(props, "path_tree_custom", text="📁 Arbre Personnalisé")
            elif props.plant_family == 'HOUSEPLANTS':
                box_inputs.prop(props, "path_house_monstera", text="🪴 Monstera")
                box_inputs.prop(props, "path_house_ficus", text="🌿 Ficus")
                box_inputs.prop(props, "path_house_custom", text="📁 Plante Personnalisée")
            else:
                box_inputs.prop(props, "path_custom_leaf", text="📁 Image Alpha")

        # Bouton principal de génération
        col_gen = box_type.column(align=True)
        col_gen.scale_y = 1.4
        col_gen.operator("mesh.generate_foliage_by_type", text="🌱 Générer la Feuille 3D (Image + Vertex)", icon='MESH_PLANE')

        layout.separator()

        # ==========================================
        # 2. DÉCOUPE & TOPOLOGIE ADAPTATIVE (PIXELS)
        # ==========================================
        box_mesh = layout.box()
        box_mesh.label(text="2. Découpe & Topologie Adaptative", icon='MOD_DECIM')

        col_topo = box_mesh.column(align=True)
        col_topo.prop(props, "leaf_base_height", text="Hauteur Référence (m)")
        col_topo.prop(props, "auto_adapt_mesh", text="Adaptation Pixels Auto", icon='AUTO')
        col_topo.prop(props, "margin", text="Marge Silhouette (px)")
        col_topo.prop(props, "contour_detail", text="Tolérance Contour (px)")
        col_topo.prop(props, "interior_subdiv", text="Subdivision Intérieure")
        col_topo.prop(props, "unsub_iters", text="Vertex Reducer (Décimation)")
        col_topo.prop(props, "triangulate", text="Triangles bien répartis")

        col_reapply = box_mesh.column(align=True)
        col_reapply.operator("mesh.foliage_alpha_cut", text="✂️ Ré-appliquer Découpe & Topologie", icon='SCULPTMODE_HLT')

        layout.separator()

        # ==========================================
        # 3. VARIÉTÉ & COULEURS (PHÉNOTYPE)
        # ==========================================
        box_var = layout.box()
        box_var.label(text="3. Variété & Couleurs", icon='COLOR')
        box_var.prop(props, "leaf_phenotype", text="Variété")
        if props.leaf_phenotype != 'CLASSIC':
            box_var.prop(props, "phenotype_intensity", slider=True, text="Intensité")
        if props.leaf_phenotype == 'CUSTOM':
            box_var.prop(props, "custom_variety_color", text="Couleur")

        if props.leaf_phenotype == 'CLASSIC':
            box_var.label(text="🍃 Feuillage vert naturel standard", icon='CHECKMARK')
        elif props.leaf_phenotype == 'PURPLE':
            box_var.label(text="🍇 Sombre violacé aux veines claires", icon='INFO')
        elif props.leaf_phenotype == 'WHITE':
            box_var.label(text="❄️ Givre de résine blanche dégradé depuis la fleur (Y-)", icon='FREEZE')
            box_tri = box_var.box()
            box_tri.label(text="Trigger Trichomes / Givre (Bas Y: 0.0 à 0.40) :", icon='BRUSH_DATA')
            box_tri.prop(props, "trichome_strength", slider=True, text="Force Visuelle")
            row_fade = box_tri.row(align=True)
            row_fade.prop(props, "trichome_fade_start", slider=True, text="Début Fade (0.28)")
            row_fade.prop(props, "trichome_fade_end", slider=True, text="Fin Fade / Limite (0.40)")
            box_tri.prop(props, "trichome_edge_boost", slider=True, text="Accentuation Bords")

        layout.separator()

        # ==========================================
        # 4. TRIGGER TEMPS RÉEL (CYCLE DE VIE)
        # ==========================================
        box_dyn = layout.box()
        box_dyn.label(text="4. Trigger Dynamique : Cycle de Vie", icon='TIME')

        box_slider = box_dyn.box()
        box_slider.prop(props, "leaf_age", slider=True, text="Trigger Âge")

        if props.leaf_age < 0.25:
            box_slider.label(text="🌱 Jeune & Saine (Fini mat velouté)", icon='CHECKMARK')
        elif props.leaf_age < 0.70:
            box_slider.label(text="🌿 Floraison (Chlorose dorée depuis la pointe Y+)", icon='FILE_IMAGE')
        else:
            box_slider.label(text="🍁 Récolte (Bouts noirs brûlés en Y+, rouille)", icon='ERROR')

        if props.leaf_phenotype == 'WHITE':
            box_slider.separator()
            box_slider.prop(props, "trichome_strength", slider=True, text="Trigger Givre / Trichomes", icon='FREEZE')

        col_init = box_dyn.column(align=True)
        col_init.operator("mesh.setup_dynamic_shader", text="Réinitialiser Nœuds Shader", icon='NODE')

        layout.separator()

        # ==========================================
        # 5. BAKE TEXTURES PBR (UNREAL ENGINE)
        # ==========================================
        box_pbr = layout.box()
        box_pbr.label(text="5. Export / Bake PBR (Unreal Engine)", icon='RENDER_RESULT')

        col_chk = box_pbr.column(align=True)
        row1 = col_chk.row(align=True)
        row1.prop(props, "bake_col", text="Colour (Col)", toggle=True)
        row1.prop(props, "bake_nm", text="Normal (Nm)", toggle=True)

        row2 = col_chk.row(align=True)
        row2.prop(props, "bake_me", text="Metallic / Rough (Me)", toggle=True)
        row2.prop(props, "bake_ao", text="Occlusion (AO)", toggle=True)

        row3 = col_chk.row(align=True)
        row3.prop(props, "bake_sss", text="Subsurface (SSS)", toggle=True)
        row3.prop(props, "bake_orm", text="Pack ORM (UE5)", toggle=True)

        box_pbr.separator()
        box_pbr.prop(props, "normal_strength", text="Force Relief (Nm)")
        box_pbr.prop(props, "output_dir", text="Dossier")

        col_bake = box_pbr.column(align=True)
        col_bake.scale_y = 1.3
        col_bake.operator("mesh.bake_pbr_textures", text="Bake Textures de l'État Actuel", icon='TEXTURE')

# ==============================================================================
# 7. ENREGISTREMENT DE L'ADD-ON
# ==============================================================================

classes = (
    FoliageBakerProperties,
    MESH_OT_GenerateFoliageByType,
    MESH_OT_FoliageAlphaCut,
    MESH_OT_SetupDynamicShader,
    MESH_OT_BakePBRTextures,
    VIEW3D_PT_FoliageCutterPanel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.foliage_baker = bpy.props.PointerProperty(type=FoliageBakerProperties)

def unregister():
    if hasattr(bpy.types.Scene, "foliage_baker"):
        del bpy.types.Scene.foliage_baker
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
