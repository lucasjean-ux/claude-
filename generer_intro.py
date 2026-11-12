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


def _tuile(civ: dict, taille: int, log) -> Image.Image:
    """Image carrée de la tuile (sans coins arrondis)."""
    chemin = trouver_image(DOSSIER_TUILES, civ["id"])
    if chemin:
        img = Image.open(chemin).convert("RGB")
        return ImageOps.fit(img, (taille, taille), Image.LANCZOS)
    log.warning("Tuile manquante : %s -> placeholder", civ["id"])
    img = Image.new("RGB", (taille, taille), hex_rgb(civ["fond"]))
    # léger glow derrière la boule
    glow = Image.new("L", (taille, taille), 0)
    ImageDraw.Draw(glow).ellipse((taille * 0.15, taille * 0.1, taille * 0.85, taille * 0.8), fill=90)
    glow = glow.filter(ImageFilter.GaussianBlur(taille * 0.08))
    img.paste((255, 250, 230), (0, 0), glow)
    dessiner_boule(img, taille / 2, taille * 0.46, taille * 0.3, civ["boule"])
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
    f_lib = police("Poppins-ExtraBold.ttf", int(30 * echelle))
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
