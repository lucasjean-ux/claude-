"""Rendu final d'un épisode « Toutes les civilisations expliquées » (TikTok 1080x1920, 30 fps).

Étapes : polices -> scènes -> voix (voix.mp3 ou ElevenLabs) -> normalisation -14 LUFS ->
transcription faster-whisper (mots horodatés) -> réalignement sur script.txt -> calage des scènes ->
images (ou placeholders) -> rendu image par image (intro + zoom, caméras, plans spéciaux, sous-titres) ->
encodage H.264 + AAC.

Usage :
  python render.py --episode 01_mesopotamie --tuile mesopotamienne
  python render.py --episode 01_mesopotamie --preview           # 540x960, encodage rapide
  python render.py --episode 01_mesopotamie --voix-test         # sans voix : piste muette + timings estimés
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

import commun
from commun import (ASSETS, CIVS, EPISODES, FPS, HAUTEUR, LARGEUR, charger_env, dessiner_boule, etape,
                    hash_fichiers, hex_rgb, layout_tuiles, logger, normaliser, police,
                    telecharger_polices, tokeniser, trouver_image)

log = logger()

# --------------------------------------------------------------------------- réglages du style
T_INTRO_FIXE = 2.2          # affiche fixe
T_INTRO_FIN = 3.8           # fin du zoom vers la tuile -> coupe sèche
PUSH_IN = (1.00, 1.12)
IMPACT = (0.90, 1.15, 0.8)  # de 90 % à 115 % en 0,8 s
IMPACT_DERIVE = 0.04        # dérive lente après l'impact
ICON_ZOOM = (1.00, 1.06)
FOND_ICONE = "#22272E"
FOCUS = (0.5, 0.42)         # point visé par les zooms (sujet dans la moitié haute)
SOUS_TITRE = {"taille": 52, "contour": 3, "ligne_base": 0.78, "silence_max": 0.4}
MIN_ECRAN_BLANC_FINAL = 2.0
DUREE_CIBLE = (80, 90)


# =========================================================================== utilitaires ffmpeg
def ffmpeg_dispo() -> None:
    for b in ("ffmpeg", "ffprobe"):
        if not shutil.which(b):
            sys.exit(f"ERREUR : {b} est introuvable. Installe ffmpeg (voir README).")


def duree_audio(f: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                          "default=nw=1:nk=1", str(f)], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def mesurer_loudness(f: Path, cible: float = -14.0) -> dict:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(f), "-af",
                        f"loudnorm=I={cible}:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S)
    if not m:
        raise RuntimeError("mesure loudnorm impossible :\n" + r.stderr[-800:])
    return json.loads(m.group(0))


# =========================================================================== voix
def voix_elevenlabs(texte: str, sortie: Path) -> None:
    cle = os.environ["ELEVENLABS_API_KEY"]
    voix = os.environ.get("ELEVENLABS_VOICE_ID", "onwK4e9ZLuTAKqWW03F9")
    modele = os.environ.get("ELEVENLABS_MODEL", "eleven_multilingual_v2")
    reglages = {"stability": float(os.environ.get("ELEVENLABS_STABILITY", 0.6)),
                "similarity_boost": 0.8, "style": float(os.environ.get("ELEVENLABS_STYLE", 0.15)),
                "use_speaker_boost": True, "speed": float(os.environ.get("ELEVENLABS_SPEED", 1.0))}
    log.info("ElevenLabs : voix %s, modèle %s, vitesse %.2f", voix, modele, reglages["speed"])
    corps = json.dumps({"text": texte, "model_id": modele, "voice_settings": reglages}).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voix}?output_format=mp3_44100_192",
        data=corps, method="POST",
        headers={"xi-api-key": cle, "Content-Type": "application/json", "Accept": "audio/mpeg"})
    try:
        data = urllib.request.urlopen(req, timeout=300).read()
    except urllib.error.HTTPError as e:
        sys.exit(f"ERREUR ElevenLabs {e.code} : {e.read().decode('utf-8', 'replace')[:500]}")
    sortie.write_bytes(data)
    log.info("Voix ElevenLabs enregistrée : %s (%.0f Ko)", sortie, len(data) / 1024)


def obtenir_voix(dossier: Path, texte: str, voix_test: bool) -> Path | None:
    for ext in (".mp3", ".wav", ".m4a"):
        f = dossier / f"voix{ext}"
        if f.exists():
            log.info("Voix off fournie : %s", f.name)
            return f
    if os.environ.get("ELEVENLABS_API_KEY"):
        f = dossier / "voix.mp3"
        log.info("Pas de voix.mp3 -> génération avec l'API ElevenLabs")
        voix_elevenlabs(texte, f)
        return f
    if voix_test:
        log.warning("MODE TEST : aucune voix -> piste muette et timings estimés (pas de transcription).")
        return None
    sys.exit("ERREUR : aucune voix off. Ajoute episodes/<episode>/voix.mp3, ou ELEVENLABS_API_KEY dans .env, "
             "ou relance avec --voix-test pour valider le rendu sans voix.")


def normaliser_voix(src: Path, cache: Path) -> Path:
    sortie = cache / f"voix_norm_{hash_fichiers(src)}.wav"
    if sortie.exists():
        log.info("Voix normalisée (cache) : %s", sortie.name)
        return sortie
    m = mesurer_loudness(src)
    log.info("Loudness d'origine : %s LUFS, true peak %s dBTP", m["input_i"], m["input_tp"])
    filtre = ("loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={input_i}:measured_TP={input_tp}:"
              "measured_LRA={input_lra}:measured_thresh={input_thresh}:offset={target_offset}:linear=true"
              ).format(**m)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-af", filtre, "-ar", "48000",
                    "-ac", "2", str(sortie)], check=True)
    log.info("Voix normalisée : %s LUFS", mesurer_loudness(sortie)["input_i"])
    return sortie


# =========================================================================== mots horodatés
def transcrire(voix: Path, modele: str, device: str, lexique: list[str], cache: Path) -> list[dict]:
    f_cache = cache / f"whisper_{modele}_{hash_fichiers(voix)}.json"
    if f_cache.exists():
        log.info("Transcription (cache) : %s", f_cache.name)
        return json.loads(f_cache.read_text(encoding="utf-8"))
    from faster_whisper import WhisperModel  # import tardif : lourd
    if device == "auto":
        try:
            import ctranslate2
            device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:
            device = "cpu"
    log.info("Chargement de faster-whisper « %s » sur %s (premier lancement : téléchargement du modèle)…",
             modele, device)
    model = WhisperModel(modele, device=device, compute_type="float16" if device == "cuda" else "int8")
    t0 = time.time()
    segments, info = model.transcribe(str(voix), language="fr", word_timestamps=True, beam_size=5,
                                      initial_prompt=", ".join(lexique) + "." if lexique else None,
                                      condition_on_previous_text=False)
    mots = []
    for seg in segments:
        for w in seg.words or []:
            mots.append({"texte": w.word.strip(), "debut": round(w.start, 3), "fin": round(w.end, 3)})
    log.info("Transcription : %d mots en %.0f s", len(mots), time.time() - t0)
    f_cache.write_text(json.dumps(mots, ensure_ascii=False, indent=1), encoding="utf-8")
    return mots


def aligner(tokens: list[dict], mots_w: list[dict]) -> list[dict]:
    """Réaligne les mots reconnus sur l'orthographe exacte du script (alignement caractère par caractère).
    Les mots du script non reconnus sont interpolés entre leurs voisins."""
    S, proprio = [], []
    for i, t in enumerate(tokens):
        for c in t["norm"]:
            S.append(c)
            proprio.append(i)
    Wc, t_deb, t_fin = [], [], []
    for w in mots_w:
        n = "".join(m["norm"] for m in tokeniser(w["texte"]))
        if not n:
            continue
        d = max(0.0, w["fin"] - w["debut"])
        for j, c in enumerate(n):
            Wc.append(c)
            t_deb.append(w["debut"] + d * j / len(n))
            t_fin.append(w["debut"] + d * (j + 1) / len(n))
    sm = SequenceMatcher(None, "".join(S), "".join(Wc), autojunk=False)
    deb = [math.inf] * len(tokens)
    fin = [-math.inf] * len(tokens)
    for a, b, n in sm.get_matching_blocks():
        for q in range(n):
            i = proprio[a + q]
            deb[i] = min(deb[i], t_deb[b + q])
            fin[i] = max(fin[i], t_fin[b + q])
    trouves = sum(1 for d in deb if d != math.inf)
    taux = trouves / max(1, len(tokens))
    (log.info if taux > 0.8 else log.warning)("Alignement script/voix : %d/%d mots retrouvés (%.0f %%)",
                                               trouves, len(tokens), 100 * taux)
    return _completer(tokens, deb, fin, mots_w[-1]["fin"] if mots_w else 1.0)


def _completer(tokens, deb, fin, duree):
    """Interpole les mots sans timing et garantit un ordre croissant."""
    n = len(tokens)
    i = 0
    while i < n:
        if deb[i] != math.inf:
            i += 1
            continue
        j = i
        while j < n and deb[j] == math.inf:
            j += 1
        t0 = fin[i - 1] if i > 0 else 0.0
        t1 = deb[j] if j < n else duree
        poids = [len(tokens[k]["norm"]) + 2 for k in range(i, j)]
        tot, cur = sum(poids), t0
        for k, p in zip(range(i, j), poids):
            deb[k] = cur
            cur += (t1 - t0) * p / tot
            fin[k] = cur
        i = j
    res, prec = [], 0.0
    for k in range(n):
        d = max(deb[k], prec)
        f = max(fin[k], d + 0.06)
        res.append({"mot": tokens[k]["mot"], "debut": round(d, 3), "fin": round(f, 3)})
        prec = d + 0.01
    return res


def estimer(tokens: list[dict], duree: float) -> list[dict]:
    """Timings estimés (sans transcription) : proportionnels à la longueur des mots + pauses de ponctuation."""
    pauses = sum(t["pause"] for t in tokens)
    parole = max(duree * 0.5, duree - 0.4 - pauses)
    k_pause = 1.0 if duree - 0.4 - pauses > duree * 0.5 else (duree * 0.5 - 0.4) / max(pauses, 1e-6)
    poids = [len(t["norm"]) + 2 for t in tokens]
    tot, cur, res = sum(poids), 0.15, []
    for t, p in zip(tokens, poids):
        d = parole * p / tot
        res.append({"mot": t["mot"], "debut": round(cur, 3), "fin": round(cur + d, 3)})
        cur += d + t["pause"] * k_pause
    return res


# =========================================================================== images
PALETTES = [("#FBE3A1", "#E07B39"), ("#F9D27E", "#C8553D"), ("#FFE9B8", "#E8A33D"),
            ("#F6C77F", "#B8452C"), ("#FDEBC4", "#D98C3A"), ("#F7D9A0", "#CF6A32")]


def _degrade(w, h, haut, bas) -> Image.Image:
    a, b = hex_rgb(haut), hex_rgb(bas)
    col = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        col.putpixel((0, y), tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3)))
    return col.resize((w, h))


def placeholder(scene: dict, idx: int, couleur_boule: str) -> Image.Image:
    """Image de test : cercles de couleur sur un dégradé (avec une boule pour visualiser le cadrage)."""
    mvt = scene["mouvement"]
    if mvt == "icon_dark":  # icône détourée (RGBA) : une roue stylisée
        t = 900
        ic = Image.new("RGBA", (t, t), (0, 0, 0, 0))
        d = ImageDraw.Draw(ic)
        d.ellipse((60, 60, t - 60, t - 60), fill="#C98B4A", outline="black", width=28)
        d.ellipse((190, 190, t - 190, t - 190), fill="#E7B66E", outline="black", width=20)
        for a in range(0, 360, 45):
            r = math.radians(a)
            d.line((t / 2, t / 2, t / 2 + 270 * math.cos(r), t / 2 + 270 * math.sin(r)), fill="black", width=22)
        d.ellipse((t / 2 - 60, t / 2 - 60, t / 2 + 60, t / 2 + 60), fill="#7A4A22", outline="black", width=16)
        return ic
    pan = mvt.startswith("pan_")
    w, h = (3414, 1920) if pan else (1080, 1920)
    haut, bas = PALETTES[idx % len(PALETTES)]
    img = _degrade(w, h, haut, bas)
    d = ImageDraw.Draw(img, "RGBA")
    sol = int(h * 0.64)
    d.rectangle((0, sol, w, h), fill=hex_rgb(bas) + (255,))
    d.rectangle((0, sol, w, sol + 10), fill=(0, 0, 0, 40))
    # cercles de couleur (décor)
    for k in range(9 if pan else 5):
        x = (k + 0.5) * w / (9 if pan else 5)
        y = h * (0.18 + 0.12 * ((k * 7 + idx) % 3))
        r = 60 + 25 * ((k + idx) % 3)
        d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, 70))
    # sujet
    if pan:
        cx = w * (0.17 if mvt == "pan_right" else 0.83)
        dessiner_boule(img, cx, sol - 170, 180, couleur_boule, idx)
        for k in range(4):  # décor de l'autre côté : pyramides
            x = w * (0.45 + 0.13 * k) if mvt == "pan_right" else w * (0.55 - 0.13 * k)
            d.polygon([(x - 200, sol), (x, sol - 330 - 40 * (k % 2)), (x + 200, sol)], fill=(150, 90, 50, 220),
                      outline=(0, 0, 0, 255), width=8)
    elif scene.get("outro"):
        for k, c in enumerate(["#C98B4A", "#E7B66E", "#B8683D", "#F4D35E"]):
            x, y = w * (0.3 + 0.4 * (k % 2)), h * (0.18 + 0.18 * (k // 2))
            d.ellipse((x - 120, y - 120, x + 120, y + 120), fill=c, outline="black", width=10)
        dessiner_boule(img, w / 2, h * 0.86, 90, couleur_boule, idx)
    else:
        dessiner_boule(img, w / 2, h * 0.40, 250, couleur_boule, idx)
    d.text((40, 40), f"PLACEHOLDER {scene['id']} · {mvt}", font=police("Poppins-SemiBold.ttf", 34),
           fill=(0, 0, 0, 150))
    return img


def preparer(img: Image.Image, W: int, H: int, marge: float) -> Image.Image:
    """Redimensionne pour que l'image couvre le cadre avec `marge` (=> zooms nets, sans sur-échantillonnage)."""
    sw, sh = img.size
    f = marge * max(W / sw, H / sh)
    return img.resize((max(1, round(sw * f)), max(1, round(sh * f))), Image.LANCZOS)


def cadrer(src: Image.Image, W: int, H: int, zoom: float, fx: float = 0.5, fy: float = 0.5,
           cx: float | None = None) -> Image.Image:
    """Fenêtre W x H dans src : zoom relatif à la couverture du cadre, centrée sur (fx, fy) (bornée)."""
    sw, sh = src.size
    k = min(sw / W, sh / H) / zoom
    vw, vh = W * k, H * k
    x = fx * sw if cx is None else cx
    y = fy * sh
    x = min(max(x, vw / 2), sw - vw / 2) if vw <= sw else sw / 2
    y = min(max(y, vh / 2), sh - vh / 2) if vh <= sh else sh / 2
    return src.transform((W, H), Image.AFFINE, (k, 0, x - vw / 2, 0, k, y - vh / 2), resample=Image.BICUBIC)


# =========================================================================== segments (plans)
class Plan:
    def __init__(self, debut: float, fin: float, nom: str):
        self.debut, self.fin, self.nom = debut, fin, nom

    def rendu(self, t: float) -> Image.Image:  # t relatif au début du plan
        raise NotImplementedError


class PlanCamera(Plan):
    def __init__(self, debut, fin, nom, img: Image.Image, mouvement: str, W: int, H: int):
        super().__init__(debut, fin, nom)
        self.mvt, self.W, self.H = mouvement, W, H
        self.duree = max(fin - debut, 1e-3)
        if mouvement == "push_in":
            self.src = preparer(img, W, H, PUSH_IN[1])
        elif mouvement == "impact_zoom":
            self.src = preparer(img, W, H, (IMPACT[1] + IMPACT_DERIVE) / IMPACT[0])
        elif mouvement.startswith("pan_"):
            large = img.width / img.height >= 1.2 * W / H
            self.zoom_pan = 1.0 if large else 1.35  # image non panoramique : on zoome pour avoir de la course
            self.src = preparer(img, W, H, self.zoom_pan)
        else:
            raise ValueError(mouvement)

    def rendu(self, t):
        p = min(max(t / self.duree, 0.0), 1.0)
        W, H = self.W, self.H
        if self.mvt == "push_in":
            return cadrer(self.src, W, H, PUSH_IN[0] + (PUSH_IN[1] - PUSH_IN[0]) * p, *FOCUS)
        if self.mvt == "impact_zoom":
            z0, z1, dt = IMPACT
            if t < dt:
                e = 1 - (1 - t / dt) ** 3  # ease-out : coup de zoom rapide
                z = z0 + (z1 - z0) * e
            else:
                z = z1 + IMPACT_DERIVE * (t - dt) / max(self.duree - dt, 1e-3)
            return cadrer(self.src, W, H, z / z0, *FOCUS)  # 90 % = image qui couvre juste le cadre
        # pan : traversée complète, vitesse constante
        sw = self.src.width
        k = min(sw / W, self.src.height / H) / self.zoom_pan
        vw = W * k
        x0, x1 = vw / 2, sw - vw / 2
        cx = x0 + (x1 - x0) * p if self.mvt == "pan_right" else x1 - (x1 - x0) * p
        return cadrer(self.src, W, H, self.zoom_pan, 0.5, 0.5, cx=cx)


class PlanIcone(Plan):
    """icon_dark : icône centrée sur fond #22272E avec halo doux, léger push-in."""

    def __init__(self, debut, fin, nom, img: Image.Image, W, H):
        super().__init__(debut, fin, nom)
        self.W, self.H, self.duree = W, H, max(fin - debut, 1e-3)
        if img.mode == "RGBA" and img.getextrema()[3][0] < 250:  # icône détourée -> on compose
            base = Image.new("RGB", (W, H), hex_rgb(FOND_ICONE))
            halo = Image.new("L", (W, H), 0)
            r = W * 0.42
            cy = H * 0.45
            ImageDraw.Draw(halo).ellipse((W / 2 - r, cy - r, W / 2 + r, cy + r), fill=120)
            halo = halo.filter(ImageFilter.GaussianBlur(W * 0.12))
            base.paste((255, 214, 150), (0, 0), halo)
            t = int(W * 0.58)
            ic = img.copy()
            ic.thumbnail((t, t), Image.LANCZOS)
            base.paste(ic, (int(W / 2 - ic.width / 2), int(cy - ic.height / 2)), ic)
            img = base
        self.src = preparer(img.convert("RGB"), W, H, ICON_ZOOM[1])

    def rendu(self, t):
        p = min(max(t / self.duree, 0.0), 1.0)
        return cadrer(self.src, self.W, self.H, ICON_ZOOM[0] + (ICON_ZOOM[1] - ICON_ZOOM[0]) * p, 0.5, 0.45)


class PlanUni(Plan):
    def __init__(self, debut, fin, nom, couleur, W, H):
        super().__init__(debut, fin, nom)
        self.img = Image.new("RGB", (W, H), couleur)

    def rendu(self, t):
        return self.img.copy()


class PlanIntro(Plan):
    """Affiche fixe puis zoom accéléré (ease-in) vers la tuile, jusqu'à ce qu'elle remplisse l'écran."""

    def __init__(self, tuile: str, W, H):
        super().__init__(0.0, T_INTRO_FIN, "intro")
        self.W, self.H = W, H
        f_hd, f_sd = ASSETS / "intro_hd.png", ASSETS / "intro.png"
        if not f_hd.exists() and not f_sd.exists():
            log.info("assets/intro.png absent -> génération automatique (generer_intro.py)")
            import generer_intro
            generer_intro.generer()
        src = Image.open(f_hd if f_hd.exists() else f_sd).convert("RGB")
        E_max = src.width / LARGEUR
        # pyramide de résolutions : on choisit pour chaque image le niveau le plus proche de 1:1
        self.niveaux = []
        for E in sorted({W / LARGEUR, 1.0, 1.5, 2.0, E_max}):
            if E <= E_max:
                self.niveaux.append((E, src if E == E_max else src.resize(
                    (round(LARGEUR * E), round(HAUTEUR * E)), Image.LANCZOS)))
        self.fixe = src.resize((W, H), Image.LANCZOS)
        x, y, t = layout_tuiles(1.0)[tuile]
        # fenêtre finale : 9:16 inscrite dans la tuile carrée (marge 4 % pour ne pas voir les bords arrondis)
        self.s1 = (t * 0.96) / HAUTEUR
        c0 = (LARGEUR / 2, HAUTEUR / 2)
        c1 = (x + t / 2, y + t / 2)
        # point fixe du zoom : c(s) = F + (c0 - F) * s, avec c(1) = c0 et c(s1) = c1
        self.F = tuple((c1[i] - c0[i] * self.s1) / (1 - self.s1) for i in range(2))
        self.c0 = c0

    def rendu(self, t):
        if t < T_INTRO_FIXE:
            return self.fixe.copy()
        # la dernière image avant la coupe montre la tuile plein écran
        p = min((t - T_INTRO_FIXE) / (T_INTRO_FIN - T_INTRO_FIXE - 1 / FPS), 1.0)
        s = self.s1 ** (p ** 2.4)  # ease-in : lent puis de plus en plus rapide
        cx = self.F[0] + (self.c0[0] - self.F[0]) * s
        cy = self.F[1] + (self.c0[1] - self.F[1]) * s
        vh = HAUTEUR * s  # hauteur de la fenêtre dans le repère 1080x1920
        E, src = self.niveaux[-1]
        for E_, src_ in self.niveaux:
            if vh * E_ / self.H >= 1.0:
                E, src = E_, src_
                break
        k = vh * E / self.H
        x0, y0 = (cx - LARGEUR * s / 2) * E, (cy - vh / 2) * E
        return src.transform((self.W, self.H), Image.AFFINE, (k, 0, x0, 0, k, y0), resample=Image.BICUBIC)


# =========================================================================== sous-titres
class SousTitres:
    def __init__(self, W, H):
        self.W, self.H = W, H
        e = W / LARGEUR
        self.taille = round(SOUS_TITRE["taille"] * e)
        self.contour = max(1, round(SOUS_TITRE["contour"] * e))
        self.font = police("Poppins-SemiBold.ttf", self.taille)
        self.y_base = SOUS_TITRE["ligne_base"] * H
        self.y0 = int(self.y_base - self.taille * 2)
        self.h = int(self.taille * 3.2)
        self.cache: dict[str, Image.Image] = {}

    def bandeau(self, mot: str) -> Image.Image:
        if mot not in self.cache:
            e = self.W / LARGEUR
            yb = self.y_base - self.y0
            ombre = Image.new("RGBA", (self.W, self.h), (0, 0, 0, 0))
            ImageDraw.Draw(ombre).text((self.W / 2, yb + 4 * e), mot, font=self.font, anchor="ms",
                                       fill=(0, 0, 0, 150), stroke_width=self.contour + 1,
                                       stroke_fill=(0, 0, 0, 150))
            ombre = ombre.filter(ImageFilter.GaussianBlur(5 * e))
            ImageDraw.Draw(ombre).text((self.W / 2, yb), mot, font=self.font, anchor="ms", fill="white",
                                       stroke_width=self.contour, stroke_fill="black")
            self.cache[mot] = ombre
        return self.cache[mot]

    def appliquer(self, img: Image.Image, mot: str) -> None:
        b = self.bandeau(mot)
        img.paste(b, (0, self.y0), b)


def intervalles_sous_titres(mots_abs: list[dict], t_min: float, t_max: float) -> list[tuple]:
    """Un mot affiché de son début jusqu'au mot suivant ; effacé si le silence dépasse 0,4 s."""
    res = []
    for i, m in enumerate(mots_abs):
        if i + 1 < len(mots_abs):
            suivant = mots_abs[i + 1]["debut"]
            fin = suivant if suivant - m["fin"] <= SOUS_TITRE["silence_max"] else m["fin"]
        else:
            fin = m["fin"] + 0.3
        deb, fin = max(m["debut"], t_min), min(fin, t_max)
        if fin > deb:
            res.append((deb, fin, m["mot"]))
    return res


# =========================================================================== calage des scènes
def plages_scenes(scenes: list[dict], tokens: list[dict]) -> list[tuple[int, int]]:
    """Pour chaque scène, l'intervalle [a, b) de ses mots dans le script."""
    res, p = [], 0
    for s in scenes:
        tks = tokeniser(s["texte"])
        cle = [t["norm"] for t in tks[:3]]
        a = p
        for i in range(p, len(tokens) - len(cle) + 1):
            if [t["norm"] for t in tokens[i:i + len(cle)]] == cle:
                a = i
                break
        else:
            log.warning("%s : début du texte introuvable dans script.txt, calage approximatif.", s["id"])
        b = min(len(tokens), a + len(tks))
        res.append((a, b))
        p = b
    return res


# =========================================================================== programme principal
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--episode", required=True, help="dossier dans episodes/, ex. 01_mesopotamie")
    ap.add_argument("--tuile", help="tuile ciblée par le zoom d'intro (mesopotamienne, egyptienne, …)")
    ap.add_argument("--preview", action="store_true", help="export rapide en 540x960")
    ap.add_argument("--voix-test", action="store_true", help="sans voix : piste muette + timings estimés")
    ap.add_argument("--sans-whisper", action="store_true", help="timings estimés au lieu de la transcription")
    ap.add_argument("--modele-whisper", default="medium", help="modèle faster-whisper (défaut : medium)")
    ap.add_argument("--device", default="auto", help="auto | cpu | cuda")
    ap.add_argument("--voix-debut", type=float, default=T_INTRO_FIXE,
                    help=f"instant où démarre la voix (défaut {T_INTRO_FIXE} s = début du zoom)")
    ap.add_argument("--sortie", help="chemin du MP4 (défaut : episodes/<episode>/final.mp4)")
    args = ap.parse_args()

    t_start = time.time()
    charger_env()
    ffmpeg_dispo()
    dossier = EPISODES / args.episode
    if not dossier.is_dir():
        sys.exit(f"ERREUR : dossier {dossier} introuvable.")
    cache = dossier / "cache"
    cache.mkdir(exist_ok=True)
    W, H = (540, 960) if args.preview else (LARGEUR, HAUTEUR)

    # ---------------------------------------------------------------- 1. polices + scènes
    etape("Polices et scènes")
    telecharger_polices()
    if not (dossier / "scenes.json").exists():
        log.info("scenes.json absent -> lancement de decouper.py")
        subprocess.run([sys.executable, str(commun.RACINE / "decouper.py"), "--episode", args.episode], check=True)
    data = json.loads((dossier / "scenes.json").read_text(encoding="utf-8"))
    scenes = data["scenes"]
    tuile = args.tuile or data.get("civilisation") or "mesopotamienne"
    if tuile not in CIVS:
        sys.exit(f"ERREUR : --tuile « {tuile} » inconnue. Choix : {', '.join(CIVS)}")
    log.info("Épisode %s — %d scènes — tuile d'intro : %s — sortie %dx%d", args.episode, len(scenes), tuile, W, H)

    script = re.sub(r"\s+", " ", (dossier / "script.txt").read_text(encoding="utf-8")).strip()
    tokens = tokeniser(script)

    # ---------------------------------------------------------------- 2. voix
    etape("Voix off")
    src_voix = obtenir_voix(dossier, script, args.voix_test)
    if src_voix:
        voix = normaliser_voix(src_voix, cache)
        d_voix = duree_audio(voix)
    else:
        d_voix = len(tokens) / 3.0 + 0.6 * sum(t["pause"] for t in tokens) + 0.6
        voix = cache / f"voix_muette_{d_voix:.2f}.wav"
        if not voix.exists():
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                            "anullsrc=r=48000:cl=stereo", "-t", f"{d_voix:.3f}", str(voix)], check=True)
    log.info("Durée de la voix : %.2f s", d_voix)

    # ---------------------------------------------------------------- 3. mots horodatés
    etape("Synchronisation mot à mot")
    if src_voix and not args.sans_whisper:
        try:
            mots_w = transcrire(voix, args.modele_whisper, args.device, data.get("lexique", []), cache)
            mots = aligner(tokens, mots_w)
        except ImportError:
            log.warning("faster-whisper n'est pas installé -> timings estimés (pip install faster-whisper)")
            mots = estimer(tokens, d_voix)
        except Exception as exc:
            log.error("Transcription impossible (%s: %s)", type(exc).__name__, str(exc)[:200])
            log.warning("-> REPLI sur des timings estimés : la synchro des sous-titres sera approximative.")
            mots = estimer(tokens, d_voix)
    else:
        log.info("Timings estimés à partir du texte (pas de transcription).")
        mots = estimer(tokens, d_voix)
    (cache / "mots_alignes.json").write_text(json.dumps(mots, ensure_ascii=False, indent=1), encoding="utf-8")
    off = args.voix_debut
    mots_abs = [{"mot": m["mot"], "debut": m["debut"] + off, "fin": m["fin"] + off} for m in mots]

    # ---------------------------------------------------------------- 4. calage des scènes
    etape("Calage des scènes sur la voix")
    plages = plages_scenes(scenes, tokens)
    debuts = []
    for k, (a, b) in enumerate(plages):
        if k == 0:
            debuts.append(T_INTRO_FIN)
            continue
        t = (mots_abs[a]["debut"] - 0.05) if a < len(mots_abs) else debuts[-1] + 2
        debuts.append(max(t, debuts[-1] + 0.5))
    fin_voix = mots_abs[-1]["fin"] if mots_abs else off + d_voix
    fin_totale = max(debuts[-1] + MIN_ECRAN_BLANC_FINAL, fin_voix + 0.4)
    fin_totale = math.ceil(fin_totale * FPS - 1e-6) / FPS  # calé sur une image : la suivante sera noire
    fins = debuts[1:] + [fin_totale]
    n_images = round(fin_totale * FPS) + 1  # + 1 image noire
    duree_totale = n_images / FPS

    log.info("%-9s %-13s %7s %7s %6s  %s", "scène", "mouvement", "début", "fin", "durée", "premiers mots")
    for s, d, f, (a, b) in zip(scenes, debuts, fins, plages):
        alerte = ""
        if s["mouvement"] != "white_screen" and not (3.0 <= f - d <= 10.0):
            alerte = "  ⚠ hors 3–10 s"
        log.info("%-9s %-13s %6.2fs %6.2fs %5.1fs  %s%s", s["id"], s["mouvement"], d, f, f - d,
                 " ".join(m["mot"] for m in mots[a:a + 6]), alerte)
    outro_debut = next((d for s, d in zip(scenes, debuts) if s.get("outro")), None)
    if outro_debut is not None:
        log.info("Outro : %.1f s (illustration récap + écran blanc final)", fin_totale - outro_debut)
    (log.info if DUREE_CIBLE[0] <= duree_totale <= DUREE_CIBLE[1] else log.warning)(
        "Durée totale : %.2f s (cible %d–%d s)", duree_totale, *DUREE_CIBLE)

    # ---------------------------------------------------------------- 5. images
    etape("Chargement des illustrations")
    dossier_img = dossier / "images"
    dossier_img.mkdir(exist_ok=True)
    n_reelles = sum(1 for s in scenes if s["mouvement"] != "white_screen" and trouver_image(dossier_img, s["id"]))
    if n_reelles == 0:
        log.warning("Dossier images/ vide -> placeholders générés automatiquement (mode validation).")
    coul = CIVS[tuile]["boule"]
    plans: list[Plan] = [PlanIntro(tuile, W, H)]
    for i, (s, d, f) in enumerate(zip(scenes, debuts, fins)):
        mvt = s["mouvement"]
        if mvt == "white_screen":
            plans.append(PlanUni(d, f, s["id"], "white", W, H))
            continue
        chemin = trouver_image(dossier_img, s["id"])
        if chemin:
            img = Image.open(chemin)
            img = img.convert("RGBA") if (img.mode in ("RGBA", "LA", "P") and mvt == "icon_dark") else img.convert("RGB")
            log.info("%s : %s (%dx%d)", s["id"], chemin.name, *img.size)
            if mvt.startswith("pan_") and img.width < img.height:
                log.warning("%s est un pan mais l'image n'est pas en 16:9 : le pan sera court.", s["id"])
        else:
            img = placeholder(s, i, coul)
            ph = cache / "placeholders"
            ph.mkdir(exist_ok=True)
            img.save(ph / f"{s['id']}.png")
            if n_reelles:
                log.warning("%s : image manquante -> placeholder", s["id"])
        if mvt == "icon_dark":
            plans.append(PlanIcone(d, f, s["id"], img, W, H))
        else:
            plans.append(PlanCamera(d, f, s["id"], img.convert("RGB"), mvt, W, H))
    plans.append(PlanUni(fin_totale, duree_totale + 1, "noir", "black", W, H))

    # ---------------------------------------------------------------- 6. rendu + encodage
    etape("Rendu des images et encodage")
    sortie = Path(args.sortie) if args.sortie else dossier / ("final_preview.mp4" if args.preview else "final.mp4")
    st = SousTitres(W, H)
    inter = intervalles_sous_titres(mots_abs, T_INTRO_FIXE, fin_totale)
    retard_ms = int(round(off * 1000))
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", str(voix),
           "-filter_complex", f"[1:a]adelay={retard_ms}|{retard_ms},apad,atrim=0:{duree_totale:.3f},"
                              f"asetpts=PTS-STARTPTS[a]",
           "-map", "0:v", "-map", "[a]",
           "-c:v", "libx264", "-preset", "veryfast" if args.preview else "medium",
           "-crf", "23" if args.preview else "18", "-pix_fmt", "yuv420p", "-profile:v", "high",
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
           "-movflags", "+faststart", "-t", f"{duree_totale:.3f}", str(sortie)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    ip, isub, t0, dernier_pct = 0, 0, time.time(), -1
    try:
        for n in range(n_images):
            t = n / FPS
            while ip + 1 < len(plans) and t >= plans[ip + 1].debut:
                ip += 1
            plan = plans[ip]
            img = plan.rendu(t - plan.debut)
            while isub < len(inter) and t >= inter[isub][1]:
                isub += 1
            if isub < len(inter) and inter[isub][0] <= t < inter[isub][1] and plan.nom != "noir":
                st.appliquer(img, inter[isub][2])
            proc.stdin.write(img.tobytes())
            pct = int(100 * (n + 1) / n_images)
            if pct // 10 != dernier_pct // 10:
                dernier_pct = pct
                ecoule = time.time() - t0
                log.info("Rendu %3d %% (%d/%d images, plan %s) — %.0f s écoulées, ~%.0f s restantes",
                         pct, n + 1, n_images, plan.nom, ecoule, ecoule / (n + 1) * (n_images - n - 1))
    finally:
        proc.stdin.close()
        code = proc.wait()
    if code != 0:
        sys.exit(f"ERREUR : ffmpeg a échoué (code {code}).")

    # ---------------------------------------------------------------- 7. contrôle
    etape("Contrôle du fichier final")
    info = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                           "stream=codec_name,width,height,r_frame_rate:format=duration", "-of", "json",
                           str(sortie)], capture_output=True, text=True).stdout
    j = json.loads(info)
    v = next(s for s in j["streams"] if s.get("width"))
    a = [s["codec_name"] for s in j["streams"] if not s.get("width")]
    log.info("Vidéo : %s %sx%s @ %s — audio : %s — durée %.2f s", v["codec_name"], v["width"], v["height"],
             v["r_frame_rate"], ",".join(a), float(j["format"]["duration"]))
    if src_voix:
        log.info("Loudness finale : %s LUFS (cible -14)", mesurer_loudness(sortie)["input_i"])
    log.info("✅ Terminé en %.0f s : %s", time.time() - t_start, sortie)


if __name__ == "__main__":
    main()
