"""Fonctions et constantes partagées par tout le pipeline « Toutes les civilisations expliquées ».

Contient : chemins, logs, polices (téléchargées depuis Google Fonts), données des 9 civilisations,
mise en page de l'affiche d'intro, blocs de style pour les prompts d'images, découpage du texte en mots.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# --------------------------------------------------------------------------- chemins / format
RACINE = Path(__file__).resolve().parent
ASSETS = RACINE / "assets"
DOSSIER_POLICES = ASSETS / "fonts"
DOSSIER_TUILES = ASSETS / "tuiles"
EPISODES = RACINE / "episodes"

LARGEUR, HAUTEUR, FPS = 1080, 1920, 30
EXTENSIONS_IMAGES = (".png", ".jpg", ".jpeg", ".webp")

# --------------------------------------------------------------------------- logs
_LOGGER: logging.Logger | None = None


def logger() -> logging.Logger:
    global _LOGGER
    if _LOGGER is None:
        _LOGGER = logging.getLogger("civilisations")
        _LOGGER.setLevel(logging.INFO)
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", "%H:%M:%S"))
        _LOGGER.addHandler(h)
        _LOGGER.propagate = False
    return _LOGGER


_NUM_ETAPE = [0]


def etape(titre: str) -> None:
    _NUM_ETAPE[0] += 1
    logger().info("━━━━━━━━ ÉTAPE %d : %s", _NUM_ETAPE[0], titre)


def charger_env() -> None:
    """Charge le fichier .env à la racine (sans dépendance externe)."""
    f = RACINE / ".env"
    if not f.exists():
        return
    for ligne in f.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        k, v = ligne.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def hash_fichiers(*elements) -> str:
    h = hashlib.sha1()
    for e in elements:
        if isinstance(e, Path):
            h.update(e.read_bytes() if e.exists() else b"absent")
        else:
            h.update(str(e).encode("utf-8"))
    return h.hexdigest()[:12]


def trouver_image(dossier: Path, nom: str) -> Path | None:
    for ext in EXTENSIONS_IMAGES:
        p = dossier / f"{nom}{ext}"
        if p.exists():
            return p
    return None


# --------------------------------------------------------------------------- polices
# fichier local -> (famille Google Fonts, graisse)
POLICES_GOOGLE = {
    "Poppins-SemiBold.ttf": ("Poppins", 600),
    "Poppins-Bold.ttf": ("Poppins", 700),
    "Poppins-ExtraBold.ttf": ("Poppins", 800),
    "Poppins-Black.ttf": ("Poppins", 900),
    "Montserrat-Bold.ttf": ("Montserrat", 700),
}
POLICES_SECOURS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


def telecharger_polices() -> None:
    """Télécharge les polices manquantes depuis l'API Google Fonts (fichiers .ttf)."""
    DOSSIER_POLICES.mkdir(parents=True, exist_ok=True)
    log = logger()
    for fichier, (famille, graisse) in POLICES_GOOGLE.items():
        cible = DOSSIER_POLICES / fichier
        if cible.exists() and cible.stat().st_size > 10_000:
            continue
        url_css = f"https://fonts.googleapis.com/css2?family={famille}:wght@{graisse}"
        try:
            req = urllib.request.Request(url_css, headers={"User-Agent": "curl/8.0"})
            css = urllib.request.urlopen(req, timeout=20).read().decode("utf-8")
            m = re.search(r"url\((https://[^)]+?\.ttf)\)", css)
            if not m:
                raise RuntimeError("aucun lien .ttf dans la réponse Google Fonts")
            data = urllib.request.urlopen(m.group(1), timeout=30).read()
            cible.write_bytes(data)
            log.info("Police téléchargée : %s (%d Ko)", fichier, len(data) // 1024)
        except Exception as exc:  # pas de réseau, etc.
            log.warning("Impossible de télécharger %s (%s) — police de secours utilisée.", fichier, exc)


_CACHE_POLICES: dict = {}


def police(fichier: str, taille: int) -> ImageFont.FreeTypeFont:
    cle = (fichier, taille)
    if cle not in _CACHE_POLICES:
        candidats = [DOSSIER_POLICES / fichier]
        if fichier.startswith("Poppins-SemiBold"):
            candidats.append(DOSSIER_POLICES / "Montserrat-Bold.ttf")
        candidats += [Path(p) for p in POLICES_SECOURS]
        for c in candidats:
            if c.exists():
                _CACHE_POLICES[cle] = ImageFont.truetype(str(c), taille)
                break
        else:
            _CACHE_POLICES[cle] = ImageFont.load_default(taille)
    return _CACHE_POLICES[cle]


# --------------------------------------------------------------------------- civilisations
FICHIER_BIBLE = ASSETS / "civilisations.json"


def charger_bible() -> dict:
    """Bible des civilisations (assets/civilisations.json) : costume, monument, décor, couleurs."""
    data = json.loads(FICHIER_BIBLE.read_text(encoding="utf-8"))
    civs = {}
    for cid in data["ordre"]:
        c = dict(data["civilisations"][cid])
        c.update(id=cid, fond=c["couleur_tuile"], boule=c["couleur_boule"])
        civs[cid] = c
    return civs


CIVS = charger_bible()
CIVILISATIONS = list(CIVS.values())  # ordre de lecture de la grille 3x3

# --------------------------------------------------------------------------- mise en page de l'affiche
MARGE_X_GRILLE = 72
ECART_X = 42
TAILLE_TUILE = (LARGEUR - 2 * MARGE_X_GRILLE - 2 * ECART_X) // 3  # 284 px
HAUTEUR_LIBELLE = 64
ECART_Y = 30
Y_GRILLE = 540


def layout_tuiles(echelle: float = 1.0) -> dict:
    """Position de chaque tuile : {id: (x, y, taille)} dans le repère 1080x1920 multiplié par `echelle`."""
    res = {}
    for i, civ in enumerate(CIVILISATIONS):
        lig, col = divmod(i, 3)
        x = MARGE_X_GRILLE + col * (TAILLE_TUILE + ECART_X)
        y = Y_GRILLE + lig * (TAILLE_TUILE + HAUTEUR_LIBELLE + ECART_Y)
        res[civ["id"]] = (x * echelle, y * echelle, TAILLE_TUILE * echelle)
    return res


# --------------------------------------------------------------------------- modèles de prompts (anglais)
ENTETE = "Highly detailed 2D cartoon illustration, premium children's book style"
BOULE = ("perfectly round ball, thick black outline, big expressive white cartoon eyes{expr}, no mouth")
AMBIANCE = ("atmospheric haze, soft depth of field, vibrant warm colors, detailed textures on fabric, "
            "metal and stone")
FIN = "No text, no letters, no watermark."
LUMIERES = [
    "golden hour sunlight with volumetric light rays and dust floating in the air",
    "misty dawn light with soft volumetric rays and a richly painted cloudy sky",
    "warm sunset glow with dramatic clouds and drifting smoke",
    "flickering torchlight with a warm glow and floating embers",
    "starry night with silver moonlight and warm torchlight",
]
NEGATIF_SCENE = ("text, letters, words, watermark, realistic human, human body, legs, mouth, flat simple "
                 "background, gradient background, minimalist, empty scene, blurry character")
NEGATIF_ICONE = ("text, letters, words, numbers, watermark, character, countryball, human, landscape, "
                 "scenery, busy background, gradient background, flat minimalist icon")
NEGATIF_TUILE = ("text, letters, words, watermark, realistic human, human body, legs, mouth, busy "
                 "background, blurry character")


def _liste(elements: list[str]) -> str:
    elements = [e for e in elements if e]
    if len(elements) <= 1:
        return "".join(elements)
    return ", ".join(elements[:-1]) + " and " + elements[-1]


def prompt_personnage(*, mouvement: str, costume: str, action: str, objet: str, monument: str,
                      decor: list[str], lumiere: str, expression: str = "", habitants: str = "",
                      position_monument: str = "", premier_plan: str = "") -> str:
    """Modèle principal : countryball en costume complet dans un décor historique à trois profondeurs."""
    expr = f" {expression}" if expression else ""
    habitants = habitants or "other small countryball inhabitants in period costumes"
    if mouvement == "pan_right":
        fmt = "wide horizontal 16:9 panorama"
        pos = position_monument or "clearly visible in the background on the RIGHT side of the panorama"
        cadrage = ("The character stands in the far LEFT third of the panorama; the center and right part "
                   "reveal the scenery and the monument, so a slow camera pan to the right lets the "
                   "character leave the frame and ends on the monument. Lower third darker and less busy.")
    elif mouvement == "pan_left":
        fmt = "wide horizontal 16:9 panorama"
        pos = position_monument or "clearly visible in the background on the LEFT side of the panorama"
        cadrage = ("The character stands in the far RIGHT third of the panorama; the center and left part "
                   "reveal the scenery and the monument, so a slow camera pan to the left lets the "
                   "character leave the frame and ends on the monument. Lower third darker and less busy.")
    else:
        fmt = "vertical 9:16"
        pos = position_monument or "clearly visible behind the character"
        cadrage = "Character centered in upper half, lower third darker and less busy."
    pp = f" ({premier_plan})" if premier_plan else ""
    return (f"{ENTETE}, {fmt}. A countryball character ({BOULE.format(expr=expr)}) dressed in a full "
            f"detailed {costume}, {action}, white cartoon gloves holding {objet}. Rich detailed historical "
            f"background with the {monument} {pos}, plus {_liste(decor)}, {habitants} in the midground, "
            f"layered depth with foreground props{pp}, {lumiere}, {AMBIANCE}. {cadrage} {FIN}")


def prompt_icone(objet: str) -> str:
    return (f"{ENTETE}, vertical 9:16. A single isolated, richly detailed object: {objet}. Detailed "
            "textures (wood grain, worn metal, clay, carved details), thick black cartoon outline, soft "
            "shading, centered slightly above the middle of the frame, on a plain solid dark charcoal "
            "background (#22272E) with a soft warm luminous halo glowing behind the object. Nothing else "
            f"in the image. {FIN}")


def prompt_recap(*, symboles: list[str], monument: str, costume: str, lumiere: str) -> str:
    return (f"{ENTETE}, vertical 9:16. Recap composition: {_liste(symboles)} float and glow in a golden "
            f"sky in the upper half of the image, with the {monument} rising majestic into the golden sky in the background. At the "
            f"bottom center, a small countryball character ({BOULE.format(expr=' with a proud half-moon smile')}) "
            f"dressed in a full detailed {costume}, looking up at them. {lumiere[:1].upper() + lumiere[1:]}, {AMBIANCE}. "
            f"Symbols in the upper half, lower third slightly darker and calm. {FIN}")


def prompt_tuile(civ: dict) -> str:
    return (f"{ENTETE}, square 1:1 tile. Bust portrait of a countryball character "
            f"({BOULE.format(expr='')}) dressed in a full detailed {civ['costume']}, holding "
            f"{civ['objets'][0]} with white cartoon gloves, centered, the ball cut at chest level by the "
            f"bottom edge. Behind it, the {civ['monument']} drawn small, semi-transparent and faded like a "
            f"soft low-contrast silhouette, on a solid flat {civ['couleur_tuile_en']} background "
            f"({civ['couleur_tuile']}). Soft rim light, clean and readable at small size. {FIN}")


# --------------------------------------------------------------------------- texte -> mots
_UNITES = ("zéro un deux trois quatre cinq six sept huit neuf dix onze douze treize quatorze quinze "
           "seize dix-sept dix-huit dix-neuf").split()
_DIZAINES = {2: "vingt", 3: "trente", 4: "quarante", 5: "cinquante", 6: "soixante"}


def _moins_de_100(n: int) -> str:
    if n < 20:
        return _UNITES[n]
    d, u = divmod(n, 10)
    if d == 7:
        return "soixante et onze" if u == 1 else "soixante-" + _UNITES[10 + u]
    if d == 8:
        return "quatre-vingts" if u == 0 else "quatre-vingt-" + _UNITES[u]
    if d == 9:
        return "quatre-vingt-" + _UNITES[10 + u]
    if u == 0:
        return _DIZAINES[d]
    if u == 1:
        return _DIZAINES[d] + " et un"
    return _DIZAINES[d] + "-" + _UNITES[u]


def _moins_de_1000(n: int) -> str:
    c, r = divmod(n, 100)
    if c == 0:
        return _moins_de_100(r)
    pref = "cent" if c == 1 else _UNITES[c] + " cent"
    if r == 0:
        return pref + ("s" if c > 1 else "")
    return pref + " " + _moins_de_100(r)


def nombre_en_lettres(n: int) -> str:
    """Entier -> français (orthographe traditionnelle), jusqu'à 999 999."""
    if n < 1000:
        return _moins_de_1000(n)
    if n < 1_000_000:
        m, r = divmod(n, 1000)
        pref = "mille" if m == 1 else re.sub(r"(cent|vingt)s$", r"\1", _moins_de_1000(m)) + " mille"
        return pref if r == 0 else pref + " " + _moins_de_1000(r)
    return str(n)


PAUSES = {",": 0.25, ";": 0.35, ":": 0.35, ".": 0.55, "!": 0.55, "?": 0.55, "…": 0.6}
_PONCT = " ,.;:!?…«»\"“”()[]—–"


def normaliser(s: str) -> str:
    """Forme de comparaison : minuscules, sans accents, lettres et chiffres uniquement."""
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = s.replace("œ", "oe").replace("æ", "ae")
    return re.sub(r"[^a-z0-9]", "", s)


def tokeniser(texte: str) -> list[dict]:
    """Découpe un texte en mots « tels que prononcés » : minuscules, sans ponctuation,
    nombres écrits en toutes lettres. Chaque mot porte la pause (s) suggérée par la ponctuation qui suit."""
    texte = texte.replace("’", "'").replace("ʼ", "'").replace("...", "…")
    mots: list[dict] = []
    for brut in texte.split():
        fin_ponct = re.search(r"[,.;:!?…]+[»\"”)]*$", brut)
        pause = max((PAUSES.get(c, 0) for c in fin_ponct.group(0)), default=0) if fin_ponct else 0
        coeur = brut.strip(_PONCT)
        if not coeur:  # ponctuation isolée (« ? » typographie française)
            if mots:
                mots[-1]["pause"] = max(mots[-1]["pause"], max((PAUSES.get(c, 0) for c in brut), default=0))
            continue
        if re.fullmatch(r"\d+", coeur):
            morceaux = nombre_en_lettres(int(coeur)).split()
        else:
            morceaux = [coeur.lower()]
        for i, m in enumerate(morceaux):
            mots.append({"mot": m, "norm": normaliser(m), "pause": pause if i == len(morceaux) - 1 else 0})
    return mots


# --------------------------------------------------------------------------- dessin : boule placeholder
def hex_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def dessiner_boule(img: Image.Image, cx: float, cy: float, r: float, couleur, humeur: int = 0) -> None:
    """Dessine une boule « countryball » simple (contour noir épais, grands yeux blancs)."""
    d = ImageDraw.Draw(img, "RGBA")
    # ombre portée douce
    ombre = Image.new("L", img.size, 0)
    ImageDraw.Draw(ombre).ellipse((cx - r * 0.9, cy + r * 0.85, cx + r * 0.9, cy + r * 1.12), fill=110)
    ombre = ombre.filter(ImageFilter.GaussianBlur(max(2, r * 0.08)))
    img.paste((0, 0, 0), (0, 0), ombre)
    ep = max(2, int(r * 0.07))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=couleur if isinstance(couleur, tuple) else hex_rgb(couleur),
              outline=(0, 0, 0), width=ep)
    for sx in (-1, 1):
        ex, ey, er = cx + sx * r * 0.36, cy - r * 0.12, r * 0.26
        d.ellipse((ex - er * 0.8, ey - er, ex + er * 0.8, ey + er), fill="white", outline="black",
                  width=max(1, ep // 2))
        # paupière mi-close
        if humeur % 2 == 0:
            d.chord((ex - er * 0.8, ey - er, ex + er * 0.8, ey + er), 180, 360,
                    fill=couleur if isinstance(couleur, tuple) else hex_rgb(couleur), outline="black",
                    width=max(1, ep // 2))
        pr = er * 0.3
        d.ellipse((ex - pr, ey + er * 0.1, ex + pr, ey + er * 0.1 + 2 * pr), fill="black")
        # sourcil froncé
        d.line((ex - sx * er * 0.9, ey - er * 0.95, ex + sx * er * 0.7, ey - er * 1.3), fill="black",
               width=max(2, ep))
