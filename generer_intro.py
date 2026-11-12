"""Dessine l'affiche d'intro « TOUTES LES CIVILISATIONS EXPLIQUÉES » (grille 3x3 de tuiles).

Sorties :
  assets/intro.png     1080x1920 (affiche finale)
  assets/intro_hd.png  version x3, utilisée par render.py pour le zoom net vers une tuile

Les tuiles sont lues dans assets/tuiles/<id>.png (ou .jpg/.webp), ex. assets/tuiles/mesopotamienne.png.
Une tuile manquante est remplacée par un placeholder (fond uni + boule de couleur).

Usage : python generer_intro.py [--echelle-hd 3]
"""
from __future__ import annotations

import argparse

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from commun import (ASSETS, CIVILISATIONS, DOSSIER_TUILES, HAUTEUR, LARGEUR, dessiner_boule, etape,
                    hex_rgb, layout_tuiles, logger, police, telecharger_polices, trouver_image,
                    HAUTEUR_LIBELLE)

TITRE = ["TOUTES LES CIVILISATIONS", "EXPLIQUÉES"]
SOUS_TITRE = "Et leurs plus grandes inventions."


def silhouette_monument(taille: int, forme: str) -> Image.Image:
    """Silhouette simplifiée du monument signature (masque L, 255 = plein) pour les placeholders."""
    m = Image.new("L", (taille, taille), 0)
    d = ImageDraw.Draw(m)
    t = taille
    sol = t * 0.72
    if forme in ("ziggourat", "pyramide_etagee", "double_temple"):
        for k in range(4):
            demi, h = t * (0.36 - 0.07 * k), t * 0.09
            y = sol - h * (k + 1)
            d.rectangle((t / 2 - demi, y, t / 2 + demi, y + h), fill=255)
        haut = sol - t * 0.36
        if forme == "pyramide_etagee":
            d.rectangle((t * 0.43, haut - t * 0.08, t * 0.57, haut), fill=255)
        elif forme == "double_temple":
            d.rectangle((t * 0.33, haut - t * 0.08, t * 0.47, haut), fill=255)
            d.rectangle((t * 0.53, haut - t * 0.08, t * 0.67, haut), fill=255)
        else:
            d.rectangle((t * 0.47, sol - t * 0.36, t * 0.53, sol), fill=0)  # escalier central
    elif forme == "pyramides":
        for cx, demi in ((0.3, 0.2), (0.62, 0.26), (0.85, 0.13)):
            d.polygon([(t * (cx - demi), sol), (t * cx, sol - t * demi * 1.3), (t * (cx + demi), sol)], fill=255)
    elif forme == "temple":
        d.rectangle((t * 0.15, sol - t * 0.05, t * 0.85, sol), fill=255)
        for k in range(6):
            x = t * (0.19 + 0.12 * k)
            d.rectangle((x, sol - t * 0.33, x + t * 0.05, sol - t * 0.05), fill=255)
        d.rectangle((t * 0.15, sol - t * 0.38, t * 0.85, sol - t * 0.33), fill=255)
        d.polygon([(t * 0.15, sol - t * 0.38), (t * 0.5, sol - t * 0.52), (t * 0.85, sol - t * 0.38)], fill=255)
    elif forme == "arches":
        d.rectangle((t * 0.1, sol - t * 0.42, t * 0.9, sol), fill=255)
        for lig in range(3):
            for k in range(7):
                x, y = t * (0.14 + 0.108 * k), sol - t * (0.38 - 0.13 * lig)
                d.rounded_rectangle((x, y, x + t * 0.06, y + t * 0.1), radius=int(t * 0.03), fill=0)
    elif forme == "drakkar":
        d.chord((t * 0.1, sol - t * 0.25, t * 0.9, sol + t * 0.05), 0, 180, fill=255)
        d.rectangle((t * 0.49, sol - t * 0.55, t * 0.52, sol - t * 0.1), fill=255)
        d.polygon([(t * 0.32, sol - t * 0.5), (t * 0.68, sol - t * 0.5), (t * 0.64, sol - t * 0.18),
                   (t * 0.36, sol - t * 0.18)], fill=255)
        d.polygon([(t * 0.86, sol - t * 0.1), (t * 0.9, sol - t * 0.32), (t * 0.97, sol - t * 0.3)], fill=255)
    elif forme == "pagode":
        for k in range(4):
            demi, y = t * (0.3 - 0.05 * k), sol - t * 0.12 * (k + 1)
            d.polygon([(t / 2 - demi - t * 0.04, y + t * 0.03), (t / 2, y - t * 0.05),
                       (t / 2 + demi + t * 0.04, y + t * 0.03)], fill=255)
            d.rectangle((t / 2 - demi * 0.7, y + t * 0.03, t / 2 + demi * 0.7, y + t * 0.12), fill=255)
    elif forme == "terrasses":
        d.polygon([(t * 0.05, sol), (t * 0.45, sol - t * 0.5), (t * 0.62, sol - t * 0.3),
                   (t * 0.75, sol - t * 0.42), (t * 0.95, sol)], fill=255)
        for k in range(4):
            y = sol - t * 0.07 * (k + 1)
            d.line((t * (0.12 + 0.06 * k), y, t * (0.88 - 0.04 * k), y), fill=0, width=max(1, t // 80))
    return m


def _tuile(civ: dict, taille: int, log) -> Image.Image:
    """Image carrée de la tuile (sans coins arrondis)."""
    chemin = trouver_image(DOSSIER_TUILES, civ["id"])
    if chemin:
        img = Image.open(chemin).convert("RGB")
        return ImageOps.fit(img, (taille, taille), Image.LANCZOS)
    log.warning("Tuile manquante : %s -> placeholder", civ["id"])
    img = Image.new("RGB", (taille, taille), hex_rgb(civ["fond"]))
    # monument signature en petit, en transparence légère
    masque = silhouette_monument(taille, civ.get("silhouette", "ziggourat")).point(lambda v: v * 70 // 255)
    img.paste((255, 255, 255), (0, int(-taille * 0.12)), masque)
    # léger glow derrière la boule
    glow = Image.new("L", (taille, taille), 0)
    ImageDraw.Draw(glow).ellipse((taille * 0.12, taille * 0.4, taille * 0.88, taille * 1.1), fill=80)
    glow = glow.filter(ImageFilter.GaussianBlur(taille * 0.08))
    img.paste((255, 250, 230), (0, 0), glow)
    # countryball en buste : coupée par le bas de la tuile
    dessiner_boule(img, taille / 2, taille * 0.86, taille * 0.36, civ["boule"])
    return img


def dessiner_affiche(echelle: float = 1.0) -> Image.Image:
    log = logger()
    W, H = int(LARGEUR * echelle), int(HAUTEUR * echelle)
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)

    # --- titre : 2 lignes, même taille, ajustée à la largeur disponible
    largeur_max = (LARGEUR - 2 * 56) * echelle
    taille = int(110 * echelle)
    while taille > 10:
        f = police("Poppins-Black.ttf", taille)
        if max(d.textlength(l, font=f) for l in TITRE) <= largeur_max:
            break
        taille -= 2
    f_titre = police("Poppins-Black.ttf", taille)
    y = 215 * echelle
    interligne = taille * 1.2
    for ligne in TITRE:
        d.text((W / 2, y), ligne, font=f_titre, fill="black", anchor="ms")
        y += interligne
    f_sous = police("Poppins-SemiBold.ttf", int(40 * echelle))
    d.text((W / 2, y - interligne + 70 * echelle), SOUS_TITRE, font=f_sous, fill=(135, 135, 135), anchor="ms")

    # --- grille 3x3
    for civ in CIVILISATIONS:
        x, yt, t = layout_tuiles(echelle)[civ["id"]]
        x, yt, t = round(x), round(yt), round(t)
        tuile = _tuile(civ, t, log)
        masque = Image.new("L", (t * 4, t * 4), 0)
        ImageDraw.Draw(masque).rounded_rectangle((0, 0, t * 4 - 1, t * 4 - 1), radius=int(t * 4 * 0.13), fill=255)
        masque = masque.resize((t, t), Image.LANCZOS)
        # petite ombre douce sous la tuile
        ombre = Image.new("L", (W, H), 0)
        ImageDraw.Draw(ombre).rounded_rectangle((x + 4 * echelle, yt + 10 * echelle, x + t, yt + t + 8 * echelle),
                                                radius=int(t * 0.13), fill=60)
        ombre = ombre.filter(ImageFilter.GaussianBlur(10 * echelle))
        img.paste((0, 0, 0), (0, 0), ombre)
        img.paste(tuile, (x, yt), masque)
        # libellé : réduit si trop large
        tl = int(30 * echelle)
        while d.textlength(civ["libelle"], font=police("Poppins-ExtraBold.ttf", tl)) > t + 30 * echelle and tl > 8:
            tl -= 1
        d.text((x + t / 2, yt + t + HAUTEUR_LIBELLE * 0.62 * echelle), civ["libelle"],
               font=police("Poppins-ExtraBold.ttf", tl), fill="black", anchor="ms")
    return img


def generer(echelle_hd: int = 3) -> None:
    log = logger()
    etape("Affiche d'intro")
    telecharger_polices()
    ASSETS.mkdir(exist_ok=True)
    DOSSIER_TUILES.mkdir(parents=True, exist_ok=True)
    hd = dessiner_affiche(echelle_hd)
    hd.save(ASSETS / "intro_hd.png", optimize=True)
    log.info("Écrit : %s (%dx%d)", ASSETS / "intro_hd.png", *hd.size)
    hd.resize((LARGEUR, HAUTEUR), Image.LANCZOS).save(ASSETS / "intro.png")
    log.info("Écrit : %s (%dx%d)", ASSETS / "intro.png", LARGEUR, HAUTEUR)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--echelle-hd", type=int, default=3, help="facteur de la version HD pour le zoom (défaut 3)")
    generer(ap.parse_args().echelle_hd)
