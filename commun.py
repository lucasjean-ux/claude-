"""Fonctions et constantes partagées par tout le pipeline « Toutes les civilisations expliquées ».

Contient : chemins, logs, polices (téléchargées depuis Google Fonts), données des 9 civilisations,
mise en page de l'affiche d'intro, blocs de style pour les prompts d'images, découpage du texte en mots.
"""
from __future__ import annotations

import hashlib
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
# Ordre de lecture de la grille 3x3 de l'affiche.
CIVILISATIONS = [
    {"id": "mesopotamienne", "libelle": "MÉSOPOTAMIENNE", "fond": "#D8B47A", "boule": "#B8683D",
     "fond_en": "sandy ochre",
     "perso": "a clay-colored (terracotta) countryball with a long neatly braided black beard, "
              "holding a small cuneiform clay tablet with a white cartoon glove"},
    {"id": "egyptienne", "libelle": "ÉGYPTIENNE", "fond": "#F1BE2C", "boule": "#2C5BB8",
     "fond_en": "golden yellow",
     "perso": "a countryball wearing a blue and gold striped nemes headdress, with an Eye of Horus "
              "painted on its skin"},
    {"id": "grecque", "libelle": "GRECQUE", "fond": "#3C7DD4", "boule": "#F4F4F4",
     "fond_en": "bright blue",
     "perso": "a white and blue countryball wearing a golden laurel wreath, standing next to a small "
              "white marble Greek column"},
    {"id": "romaine", "libelle": "ROMAINE", "fond": "#C7302E", "boule": "#F1D9A6",
     "fond_en": "crimson red",
     "perso": "a countryball wearing a shiny Roman legionary helmet with a tall red crest"},
    {"id": "viking", "libelle": "VIKING", "fond": "#6B8197", "boule": "#E2C79C",
     "fond_en": "slate grey-blue",
     "perso": "a countryball wearing a round iron Viking helmet with a nose guard, long blond braids, "
              "holding a Viking axe with a white cartoon glove"},
    {"id": "chinoise", "libelle": "CHINOISE", "fond": "#7A1D2B", "boule": "#D9412E",
     "fond_en": "deep burgundy",
     "perso": "a red countryball whose skin is covered in golden dragon scales, wearing a black "
              "imperial Chinese hat"},
    {"id": "maya", "libelle": "MAYA", "fond": "#2E9C72", "boule": "#C27A45",
     "fond_en": "jade green",
     "perso": "a countryball wearing a tall colorful feathered headdress, next to a round carved stone "
              "Maya calendar"},
    {"id": "azteque", "libelle": "AZTÈQUE", "fond": "#27B2AE", "boule": "#B5663A",
     "fond_en": "turquoise",
     "perso": "a countryball wearing a headdress of long green quetzal feathers, with a small green "
              "feathered serpent coiled around it"},
    {"id": "inca", "libelle": "INCA", "fond": "#EF8A22", "boule": "#C98A4B",
     "fond_en": "warm orange",
     "perso": "a countryball wearing a golden sun crown, standing next to a small cute white llama"},
]
CIVS = {c["id"]: c for c in CIVILISATIONS}

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


# --------------------------------------------------------------------------- style des prompts (anglais)
STYLE_BASE = (
    "2D cartoon vector illustration, countryball style. Characters are perfectly round balls with a "
    "thick black outline and big expressive white cartoon eyes (often half-closed, frowning eyebrows "
    "or a half-moon smile), no mouth. The ball's skin carries a pattern related to the theme, "
    "accessories are symbolic, hands (when present) are white cartoon gloves. "
)
STYLE_FOND_CHAUD = (
    "Soft warm gradient background (ochre, sand, gold, orange, red), simple flat-color ground, soft "
    "drop shadow under the characters, subtle glow and small floating light particles. "
)
STYLE_FOND_NUIT = (
    "Deep navy-blue starry night background, simple flat-color ground, soft drop shadow under the "
    "characters, subtle glow and small floating light particles. "
)
CADRAGE_VERTICAL = (
    "Vertical 9:16 framing, main subject centered in the upper half of the image, bottom third kept "
    "clear and uncluttered (reserved for subtitles). "
)
CADRAGE_PAN = {
    "pan_right": "Wide horizontal 16:9 panorama. The character stands in the far LEFT third of the "
                 "image; the center and right part show only scenery, so a camera pan to the right "
                 "leaves the character out of frame. Keep the bottom quarter simple. ",
    "pan_left": "Wide horizontal 16:9 panorama. The character stands in the far RIGHT third of the "
                "image; the center and left part show only scenery, so a camera pan to the left "
                "leaves the character out of frame. Keep the bottom quarter simple. ",
}
SANS_TEXTE = "Absolutely no text, no letters, no numbers, no watermark, no signature."
SANS_TEXTE_SAUF_CHIFFRES = "No words, no letters, no watermark (only the digits explicitly described)."


CADRAGE_OUTRO = (
    "Vertical 9:16 framing. The symbols float in the upper half of the image; the main character is "
    "small, at the bottom center of the image, with a calm uncluttered area around it. "
)


def prompt_scene(sujet: str, mouvement: str, nuit: bool = False, chiffres: bool = False,
                 outro: bool = False) -> str:
    fin = SANS_TEXTE_SAUF_CHIFFRES if chiffres else SANS_TEXTE
    if mouvement == "icon_dark":
        return (
            f"Single isolated icon: {sujet}. Flat 2D cartoon vector style with a thick black outline and "
            "simple cel shading, centered in the frame, on a plain solid dark charcoal background "
            "(#22272E) with a soft warm luminous halo glowing behind the icon. Nothing else in the "
            f"image. Vertical 9:16, icon centered slightly above the middle. {fin}"
        )
    fond = STYLE_FOND_NUIT if nuit else STYLE_FOND_CHAUD
    cadrage = CADRAGE_OUTRO if outro else CADRAGE_PAN.get(mouvement, CADRAGE_VERTICAL)
    return f"{STYLE_BASE}Scene: {sujet}. {fond}{cadrage}{fin}"


def prompt_tuile(civ: dict) -> str:
    return (
        f"{STYLE_BASE}Square 1:1 tile, solid flat {civ['fond_en']} background ({civ['fond']}). "
        f"A single character perfectly centered: {civ['perso']}. Soft drop shadow under the ball, "
        f"subtle glow. Clean, iconic, readable at small size. {SANS_TEXTE}"
    )


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
