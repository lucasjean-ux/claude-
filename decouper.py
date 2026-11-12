"""Découpe script.txt en scènes et rédige les prompts d'images.

Entrées (dans episodes/<episode>/) :
  script.txt   le texte de la voix off
  plan.json    (optionnel) le plan de scènes : pour chaque scène, l'ancre de début (premiers mots
               du passage), le mouvement de caméra et le sujet de l'illustration (en anglais).
               Sans plan.json, le script est découpé automatiquement phrase par phrase et les sujets
               sont à compléter (marqués TODO).

Sorties :
  scenes.json  id, texte, mouvement, format, prompt (prêt à coller dans Higgsfield)…
  prompts.txt  tous les prompts d'images de l'épisode + les 9 tuiles de l'intro

Usage : python decouper.py --episode 01_mesopotamie
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import unicodedata

from commun import (CIVILISATIONS, CIVS, EPISODES, etape, logger, prompt_scene, prompt_tuile, tokeniser)

MOUVEMENTS = {"push_in", "pan_left", "pan_right", "impact_zoom", "icon_dark", "white_screen"}
MOTS_PAR_SECONDE = 2.7  # débit estimé d'un conteur posé


def _norm_avec_index(texte: str):
    """Texte normalisé (lettres/chiffres sans accents) + index du caractère d'origine pour chaque lettre."""
    norm, idx = [], []
    for i, ch in enumerate(texte):
        base = unicodedata.normalize("NFD", ch.lower())
        base = "".join(c for c in base if unicodedata.category(c) != "Mn").replace("œ", "oe").replace("æ", "ae")
        for c in base:
            if c.isalnum():
                norm.append(c)
                idx.append(i)
    return "".join(norm), idx


def duree_estimee(texte: str) -> float:
    mots = tokeniser(texte)
    return len(mots) / MOTS_PAR_SECONDE + sum(m["pause"] for m in mots) * 0.5


def decouper_avec_plan(script: str, plan: dict, log) -> list[dict]:
    norm, idx = _norm_avec_index(script)
    debuts, curseur = [], 0
    for sc in plan["scenes"]:
        ancre, _ = _norm_avec_index(sc["debut"])
        pos = norm.find(ancre, curseur)
        if pos < 0:
            sys.exit(f"ERREUR : l'ancre « {sc['debut']} » de {sc['id']} est introuvable dans script.txt "
                     f"(après la scène précédente). Corrige plan.json.")
        debuts.append(idx[pos])
        curseur = pos + len(ancre)
    if debuts[0] != 0 and script[:debuts[0]].strip():
        log.warning("Le début du script précède l'ancre de %s : il est rattaché à cette scène.", plan["scenes"][0]["id"])
        debuts[0] = 0
    perso = plan.get("personnage", "a countryball")
    scenes = []
    for k, sc in enumerate(plan["scenes"]):
        fin = debuts[k + 1] if k + 1 < len(debuts) else len(script)
        mvt = sc["mouvement"]
        if mvt not in MOUVEMENTS:
            sys.exit(f"ERREUR : mouvement inconnu « {mvt} » pour {sc['id']} (attendus : {sorted(MOUVEMENTS)})")
        sujet = sc.get("sujet", "").replace("{perso}", perso)
        scenes.append(_scene(sc["id"], script[debuts[k]:fin].strip(), mvt, sujet,
                             outro=sc.get("outro", False), nuit=sc.get("nuit", False),
                             chiffres=sc.get("chiffres", False)))
    return scenes


def _scene(id_, texte, mvt, sujet, outro=False, nuit=False, chiffres=False) -> dict:
    d = {"id": id_, "texte": texte, "mouvement": mvt,
         "format": "16:9" if mvt.startswith("pan_") else "9:16",
         "image": f"images/{id_}.png", "outro": outro, "sujet": sujet}
    if mvt == "white_screen":
        d["image"] = None
        d["prompt"] = None
    else:
        d["prompt"] = prompt_scene(sujet, mvt, nuit=nuit, chiffres=chiffres, outro=outro)
    return d


def decouper_auto(script: str, log) -> list[dict]:
    """Sans plan : regroupe les phrases en scènes de ~6 s (3 à 10 s), alterne les mouvements."""
    log.warning("Pas de plan.json : découpage automatique. Complète les sujets marqués TODO.")
    phrases = [p.strip() for p in re.split(r"(?<=[.!?…])\s+", script.strip()) if p.strip()]
    # dernière phrase = appel aux commentaires (écran blanc), avant-dernière = outro
    fin = phrases[-1:] if len(phrases) > 2 else []
    outro = phrases[-2:-1] if len(phrases) > 2 else []
    corps = phrases[:len(phrases) - len(fin) - len(outro)]
    groupes, courant = [], ""
    for p in corps:
        essai = (courant + " " + p).strip()
        if courant and duree_estimee(essai) > 9.5:
            groupes.append(courant)
            courant = p
        else:
            courant = essai
        if duree_estimee(courant) >= 5.5:
            groupes.append(courant)
            courant = ""
    if courant:
        groupes.append(courant)
    cycle = ["push_in", "pan_right", "impact_zoom", "push_in", "pan_left", "impact_zoom"]
    scenes, n = [], 0
    for i, g in enumerate(groupes):
        n += 1
        if i in (3, 7):
            mvt = "icon_dark"
        elif i == 5 and duree_estimee(g) <= 3.5:
            mvt = "white_screen"
        else:
            mvt = cycle[i % len(cycle)]
        scenes.append(_scene(f"scene_{n:02d}", g, mvt, f"TODO: describe an image illustrating « {g} »"))
    for p in outro:
        n += 1
        scenes.append(_scene(f"scene_{n:02d}", p, "push_in", "TODO: recap of the key symbols of the episode, "
                             "main character small at the bottom", outro=True))
    for p in fin:
        n += 1
        scenes.append(_scene(f"scene_{n:02d}", p, "white_screen", ""))
    return scenes


def ecrire_prompts(dossier, episode, scenes, civ_id, log) -> None:
    lignes = [f"PROMPTS D'IMAGES — épisode {episode}", "=" * 70, "",
              "Scènes en 9:16 : générer en vertical (1080x1920 ou plus).",
              "Scènes pan_left / pan_right : générer en 16:9 (1920x1080 ou plus).",
              "Enregistrer chaque image sous episodes/%s/images/<id>.png" % episode, ""]
    for s in scenes:
        if not s["prompt"]:
            continue
        lignes += [f"### {s['id']}  —  {s['mouvement']}  —  format {s['format']}  —  fichier : {s['image']}",
                   f"Texte : {s['texte']}", "", s["prompt"], "", "-" * 70, ""]
    lignes += ["", "TUILES DE L'INTRO (communes à toute la série) — format 1:1",
               "Enregistrer sous assets/tuiles/<id>.png puis relancer : python generer_intro.py", ""]
    for c in CIVILISATIONS:
        marque = "  <== tuile de cet épisode" if c["id"] == civ_id else ""
        lignes += [f"### tuile {c['id']}  —  fichier : assets/tuiles/{c['id']}.png{marque}", "",
                   prompt_tuile(c), "", "-" * 70, ""]
    (dossier / "prompts.txt").write_text("\n".join(lignes), encoding="utf-8")
    log.info("Écrit : %s", dossier / "prompts.txt")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--episode", required=True, help="nom du dossier dans episodes/, ex. 01_mesopotamie")
    ap.add_argument("--tuile", help="id de la civilisation (sinon lu dans plan.json)")
    args = ap.parse_args()
    log = logger()
    dossier = EPISODES / args.episode
    etape(f"Découpage du script — {args.episode}")
    f_script = dossier / "script.txt"
    if not f_script.exists():
        sys.exit(f"ERREUR : {f_script} introuvable.")
    script = re.sub(r"\s+", " ", f_script.read_text(encoding="utf-8")).strip()
    log.info("Script : %d mots, durée de voix estimée ≈ %.0f s", len(script.split()), duree_estimee(script))

    plan = {}
    if (dossier / "plan.json").exists():
        plan = json.loads((dossier / "plan.json").read_text(encoding="utf-8"))
        scenes = decouper_avec_plan(script, plan, log)
        log.info("Plan de scènes lu depuis plan.json (%d scènes)", len(scenes))
    else:
        scenes = decouper_auto(script, log)

    civ = args.tuile or plan.get("civilisation")
    if civ and civ not in CIVS:
        sys.exit(f"ERREUR : tuile inconnue « {civ} » (attendues : {', '.join(CIVS)})")

    log.info("%-9s %-13s %-6s %6s  %s", "scène", "mouvement", "format", "≈durée", "texte")
    for s in scenes:
        d = duree_estimee(s["texte"])
        alerte = "  ⚠ hors 3–10 s" if not (2.5 <= d <= 10.5) and s["mouvement"] != "white_screen" else ""
        log.info("%-9s %-13s %-6s %5.1fs  %s%s", s["id"], s["mouvement"], s["format"], d,
                 (s["texte"][:55] + "…") if len(s["texte"]) > 56 else s["texte"], alerte)
    if not 10 <= len(scenes) <= 14:
        log.warning("%d scènes (recommandé : 10 à 14).", len(scenes))

    sortie = dossier / "scenes.json"
    if sortie.exists():
        shutil.copy(sortie, dossier / "scenes.json.bak")
        log.info("Ancien scenes.json sauvegardé en scenes.json.bak")
    data = {"episode": args.episode, "civilisation": civ, "lexique": plan.get("lexique", []), "scenes": scenes}
    sortie.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Écrit : %s", sortie)
    ecrire_prompts(dossier, args.episode, scenes, civ, log)


if __name__ == "__main__":
    main()
