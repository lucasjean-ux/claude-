"""Rendu d'une vidéo countryball verticale à partir d'un pack de l'Usine à TikTok.

Usage :
    python render/render_countryball.py exemple/pack-singapour.json exemple/images sortie.mp4

Le pack (JSON) contient "scenes" : [{"voix_off": "...", "texte_ecran": "...", "visuel": 1}, ...]
Les images s'appellent 01.png, 02.png... (ou .jpg / .webp) dans le dossier images.
Voix : Henri (fr-FR-HenriNeural) via edge-tts à 1,3x, gratuit. Musique facultative : assets/musique.mp3.
"""
import asyncio, json, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1080, 1920, 30
VOIX = "fr-FR-HenriNeural"
VITESSE = "+30%"         # voix à 1,3x : réglage préféré de Lucas
POP = 0.35               # durée de l'apparition « pop » en secondes
CARTE = 0.86             # largeur de l'illustration par rapport à l'écran
MIN_SCENE = 1.3          # aucune scène plus courte (référence : 1,3 à 4 s)
CIBLE = 61.0             # durée minimum Creator Rewards

POLICES = [
    "C:/Windows/Fonts/ariblk.ttf", "C:/Windows/Fonts/impact.ttf", "C:/Windows/Fonts/arialbd.ttf",
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def police(taille):
    for p in POLICES:
        if os.path.exists(p):
            return ImageFont.truetype(p, taille)
    return ImageFont.load_default()


def ffprobe_duree(f):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(f)], capture_output=True, text=True).stdout
    return float(out.strip() or 0)


async def tts(texte, sortie):
    import edge_tts
    await edge_tts.Communicate(texte, VOIX, rate=VITESSE).save(str(sortie))


def voix_scene(texte, dossier, i):
    """Crée l'audio d'une scène. Si edge-tts ne marche pas, silence calé sur le nombre de mots."""
    f = dossier / f"voix_{i:02d}.mp3"
    texte = re.sub(r"\[[^\]]*\]", "", texte or "").strip()
    if texte:
        try:
            asyncio.run(tts(texte, f))
            if f.exists() and f.stat().st_size > 0:
                return f, ffprobe_duree(f)
        except Exception as e:
            print(f"  ! voix indisponible ({e.__class__.__name__}), silence de secours pour la scène {i}")
    mots = max(1, len(texte.split()))
    d = max(MIN_SCENE, mots / 3.4)   # ≈ débit de Henri à 1,3x
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                    "-t", f"{d:.3f}", "-q:a", "9", str(f)], check=True)
    return f, d


def trouver_image(dossier, n):
    for ext in ("png", "jpg", "jpeg", "webp"):
        for nom in (f"{n:02d}.{ext}", f"{n}.{ext}"):
            p = Path(dossier) / nom
            if p.exists():
                return p
    return None


def couleur_fond(img):
    """Couleur du bord de l'illustration, pour un fond uni raccord (comme la référence)."""
    a = np.asarray(img.convert("RGB").resize((64, 64)))
    bord = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    return tuple(int(x) for x in np.median(bord, axis=0))


def ease_back(t):
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def texte_ecran(draw, txt, y_bas, fond):
    if not txt:
        return
    txt = txt.upper()
    lum = sum(fond) / 3
    coul, contour = ((20, 20, 20), (255, 255, 255)) if lum > 140 else ((255, 255, 255), (20, 20, 20))
    taille = 96
    while taille > 48:
        f = police(taille)
        if draw.textlength(txt, font=f) <= W * 0.9:
            break
        taille -= 6
    f = police(taille)
    lignes, ligne = [], ""
    for mot in txt.split():
        essai = (ligne + " " + mot).strip()
        if draw.textlength(essai, font=f) <= W * 0.9:
            ligne = essai
        else:
            lignes.append(ligne); ligne = mot
    lignes.append(ligne)
    y = y_bas - len(lignes) * (taille + 10)
    for l in lignes:
        x = (W - draw.textlength(l, font=f)) / 2
        draw.text((x, y), l, font=f, fill=coul, stroke_width=6, stroke_fill=contour)
        y += taille + 10


def rendre_scene(img, txt, duree, pipe):
    fond = couleur_fond(img)
    base_w = int(W * CARTE)
    ratio = img.height / img.width
    n = max(1, round(duree * FPS))
    for k in range(n):
        t = k / FPS
        if t < POP:
            s = 0.55 + 0.45 * ease_back(t / POP)
        else:
            s = 1 + 0.04 * (t - POP) / max(0.01, duree - POP)
        w = max(2, int(base_w * s)); h = max(2, int(w * ratio))
        frame = Image.new("RGB", (W, H), fond)
        carte = img.resize((w, h), Image.LANCZOS)
        cy = int(H * 0.54)
        frame.paste(carte, ((W - w) // 2, cy - h // 2), carte if carte.mode == "RGBA" else None)
        d = ImageDraw.Draw(frame)
        haut_carte = cy - int(base_w * ratio) // 2
        texte_ecran(d, txt, haut_carte - 40, fond)
        pipe.write(frame.tobytes())


def main(pack_path, images_dir, sortie):
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg introuvable : lance installer.bat d'abord.")
    pack = json.loads(Path(pack_path).read_text(encoding="utf-8"))
    scenes = pack["scenes"]
    tmp = Path(tempfile.mkdtemp(prefix="usine_"))
    print(f"{len(scenes)} scènes, voix {VOIX}")

    audios, durees = [], []
    for i, sc in enumerate(scenes, 1):
        f, d = voix_scene(sc.get("voix_off", ""), tmp, i)
        audios.append(f); durees.append(max(MIN_SCENE, d + 0.12))
    total = sum(durees)
    if total < CIBLE:
        print(f"  ! vidéo de {total:.1f} s : sous 1 min 01, allonge le script pour le Creator Rewards")

    liste = tmp / "audio.txt"
    with open(liste, "w", encoding="utf-8") as fl:
        for f, d in zip(audios, durees):
            fl.write(f"file '{f.as_posix()}'\nduration {d:.3f}\n")
    voix = tmp / "voix.m4a"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(liste),
                    "-af", "apad", "-t", f"{total:.3f}", "-c:a", "aac", str(voix)], check=True)

    muet = tmp / "video.mp4"
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264",
                             "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", str(muet)],
                            stdin=subprocess.PIPE)
    for i, (sc, d) in enumerate(zip(scenes, durees), 1):
        num = sc.get("visuel")
        num = int(num) if str(num).strip().isdigit() else i
        p = trouver_image(images_dir, num) or trouver_image(images_dir, i)
        if p is None:
            img = Image.new("RGB", (900, 900), (230, 230, 230))
            ImageDraw.Draw(img).text((40, 420), f"IMAGE {i:02d} MANQUANTE", font=police(60), fill=(200, 0, 0))
            print(f"  ! image {i:02d} manquante")
        else:
            img = Image.open(p).convert("RGBA")
        print(f"  scène {i:02d}  {d:4.1f} s  {sc.get('texte_ecran', '')}")
        rendre_scene(img, sc.get("texte_ecran", ""), d, proc.stdin)
    proc.stdin.close(); proc.wait()

    musique = Path(__file__).resolve().parent.parent / "assets" / "musique.mp3"
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(muet), "-i", str(voix)]
    if musique.exists():
        cmd += ["-stream_loop", "-1", "-i", str(musique), "-filter_complex",
                "[2:a]volume=0.12[m];[1:a][m]amix=inputs=2:duration=first[a]", "-map", "0:v", "-map", "[a]"]
    else:
        cmd += ["-map", "0:v", "-map", "1:a"]
    cmd += ["-c:v", "copy", "-c:a", "aac", "-shortest", str(sortie)]
    subprocess.run(cmd, check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"OK : {sortie} ({total:.1f} s)")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
