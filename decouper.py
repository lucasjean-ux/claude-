"""Découpe script.txt en scènes et rédige les prompts d'images.

Entrées (dans episodes/<episode>/) :
  script.txt   le texte de la voix off
  plan.json    (optionnel) le plan de scènes : pour chaque scène, l'ancre de début (premiers mots
               du passage), le mouvement de caméra et le sujet de l'illustration (en anglais).
               Sans plan.json, le script est découpé automatiquement phrase par phrase et les sujets
               sont à compléter (marqués TODO).

Les prompts suivent le modèle « Highly detailed 2D cartoon illustration… » et sont remplis avec la bible
des civilisations (assets/civilisations.json) : costume, monument signature, éléments de décor (piochés en
rotation pour varier les images) et ambiance lumineuse.

Sorties :
  scenes.json  id, texte, mouvement, format, prompt + negative_prompt (prêts à coller dans Higgsfield)…
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

from commun import (CIVILISATIONS, CIVS, EPISODES, LUMIERES, NEGATIF_ICONE, NEGATIF_SCENE, NEGATIF_TUILE,
                    etape, logger, prompt_icone, prompt_personnage, prompt_recap, prompt_tuile, tokeniser)

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
    compo = Composeur(plan["civilisation"])
    scenes = []
    for k, sc in enumerate(plan["scenes"]):
        fin = debuts[k + 1] if k + 1 < len(debuts) else len(script)
        mvt = sc["mouvement"]
        if mvt not in MOUVEMENTS:
            sys.exit(f"ERREUR : mouvement inconnu « {mvt} » pour {sc['id']} (attendus : {sorted(MOUVEMENTS)})")
        scenes.append(_scene(sc, script[debuts[k]:fin].strip(), compo))
    return scenes


class Composeur:
    """Remplit le modèle de prompt avec la bible, en variant décor et lumière d'une scène à l'autre."""

    def __init__(self, civ_episode: str):
        if civ_episode not in CIVS:
            sys.exit(f"ERREUR : civilisation inconnue « {civ_episode} » (attendues : {', '.join(CIVS)})")
        self.civ = civ_episode
        self.rot_decor: dict[str, int] = {}
        self.rot_lumiere = 0
        self.rot_objet = 0

    def decor(self, civ_id: str, imposes: list[str]) -> list[str]:
        """2 à 3 éléments : ceux imposés par le plan, complétés par la rotation de la bible jusqu'à 3."""
        res = list(imposes)
        n = 3 if len(res) < 2 else len(res)
        pool = CIVS[civ_id]["decor"]
        i = self.rot_decor.get(civ_id, 0)
        essais = 0
        while len(res) < n and essais < len(pool):
            el = pool[i % len(pool)]
            i += 1
            essais += 1
            if el not in res:
                res.append(el)
        self.rot_decor[civ_id] = i
        return res

    def lumiere(self, imposee: str | None) -> str:
        if imposee:
            return imposee
        l = LUMIERES[self.rot_lumiere % 3]  # rotation des ambiances de jour ; nuit/torches : à imposer
        self.rot_lumiere += 1
        return l

    def construire(self, sc: dict) -> tuple[str | None, str | None, dict]:
        mvt = sc["mouvement"]
        ep = CIVS[self.civ]
        if mvt == "white_screen":
            return None, None, {"monument": False}
        if mvt == "icon_dark":
            return prompt_icone(sc.get("objet", "TODO: describe the object")), NEGATIF_ICONE, {"monument": False}
        if sc.get("outro"):
            symboles = sc.get("symboles") or ["TODO: key symbols of the episode"]
            p = prompt_recap(symboles=symboles, monument=ep["monument"], costume=ep["costume"],
                             lumiere=self.lumiere(sc.get("lumiere")))
            return p, NEGATIF_SCENE, {"monument": True, "symboles": symboles}
        c_costume = CIVS[sc.get("costume_de", self.civ)]
        c_monument = CIVS[sc.get("monument_de", self.civ)]
        variante = sc.get("variante")
        if variante and variante not in c_costume["variantes"]:
            sys.exit(f"ERREUR : {sc['id']} : variante « {variante} » absente de la bible pour "
                     f"{c_costume['id']} (disponibles : {', '.join(c_costume['variantes']) or 'aucune'})")
        costume = c_costume["variantes"][variante] if variante else c_costume["costume"]
        objet = sc.get("objet")
        if not objet:
            objet = c_costume["objets"][self.rot_objet % len(c_costume["objets"])]
            self.rot_objet += 1
        decor = self.decor(c_monument["id"], sc.get("decor", []))
        lumiere = self.lumiere(sc.get("lumiere"))
        p = prompt_personnage(mouvement=mvt, costume=costume, action=sc.get("action", "TODO: action"),
                              objet=objet, monument=c_monument["monument"], decor=decor, lumiere=lumiere,
                              expression=sc.get("expression", ""), habitants=sc.get("habitants", ""),
                              position_monument=sc.get("position_monument", ""),
                              premier_plan=sc.get("premier_plan", ""))
        meta = {"monument": not sc.get("sans_monument", False), "costume_de": c_costume["id"],
                "variante": variante, "monument_de": c_monument["id"], "decor": decor, "lumiere": lumiere}
        return p, NEGATIF_SCENE, meta


def _scene(sc: dict, texte: str, compo: Composeur) -> dict:
    mvt = sc["mouvement"]
    prompt, negatif, meta = compo.construire(sc)
    return {"id": sc["id"], "texte": texte, "mouvement": mvt,
            "format": "16:9" if mvt.startswith("pan_") else "9:16",
            "image": None if mvt == "white_screen" else f"images/{sc['id']}.png",
            "outro": bool(sc.get("outro")), "prompt": prompt, "negative_prompt": negatif, "elements": meta}


def decouper_auto(script: str, civ: str, log) -> list[dict]:
    """Sans plan : regroupe les phrases en scènes de ~6 s (3 à 10 s), alterne les mouvements."""
    log.warning("Pas de plan.json : découpage automatique. Complète les actions/objets marqués TODO.")
    compo = Composeur(civ)
    phrases = [p.strip() for p in re.split(r"(?<=[.!?…])\s+", script.strip()) if p.strip()]
    # dernière phrase = appel aux commentaires (écran blanc), avant-dernière = outro
    fin = phrases[-1:] if len(phrases) > 2 else []
    reste = phrases[:len(phrases) - len(fin)]
    outro = []  # outro : dernières phrases, jusqu'à ~6 s (avec l'écran blanc final ≈ 10 s)
    while len(reste) > 3 and duree_estimee(" ".join(outro)) < 6:
        outro.insert(0, reste.pop())
    outro = [" ".join(outro)] if outro else []
    corps = reste
    groupes, courant = [], ""
    for p in corps:
        essai = (courant + " " + p).strip()
        if courant and duree_estimee(essai) > 9.5:
            groupes.append(courant)
            courant = p
        else:
            courant = essai
        if duree_estimee(courant) >= 6.5:
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
        sc = {"id": f"scene_{n:02d}", "mouvement": mvt,
              "action": f"TODO: describe the action illustrating « {g} »",
              "objet": "TODO: describe the object" if mvt == "icon_dark" else None}
        scenes.append(_scene({k: v for k, v in sc.items() if v}, g, compo))
    for p in outro:
        n += 1
        scenes.append(_scene({"id": f"scene_{n:02d}", "mouvement": "push_in", "outro": True}, p, compo))
    for p in fin:
        n += 1
        scenes.append(_scene({"id": f"scene_{n:02d}", "mouvement": "white_screen"}, p, compo))
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
                   f"Texte : {s['texte']}", "", "PROMPT :", s["prompt"], "",
                   "NEGATIVE PROMPT :", s["negative_prompt"], "", "-" * 70, ""]
    lignes += ["", "TUILES DE L'INTRO (communes à toute la série) — format 1:1",
               "Enregistrer sous assets/tuiles/<id>.png puis relancer : python generer_intro.py", ""]
    for c in CIVILISATIONS:
        marque = "  <== tuile de cet épisode" if c["id"] == civ_id else ""
        lignes += [f"### tuile {c['id']}  —  fichier : assets/tuiles/{c['id']}.png{marque}", "",
                   "PROMPT :", prompt_tuile(c), "", "NEGATIVE PROMPT :", NEGATIF_TUILE, "", "-" * 70, ""]
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
    civ = args.tuile or plan.get("civilisation")
    if civ not in CIVS:
        sys.exit(f"ERREUR : civilisation « {civ} » inconnue : précise --tuile ou \"civilisation\" dans plan.json "
                 f"(attendues : {', '.join(CIVS)})")
    plan["civilisation"] = civ
    log.info("Bible : %s — monument signature : %s", CIVS[civ]["libelle"], CIVS[civ]["monument_fr"])
    if plan.get("scenes"):
        scenes = decouper_avec_plan(script, plan, log)
        log.info("Plan de scènes lu depuis plan.json (%d scènes)", len(scenes))
    else:
        scenes = decouper_auto(script, civ, log)

    log.info("%-9s %-13s %-6s %6s  %s", "scène", "mouvement", "format", "≈durée", "texte")
    for s in scenes:
        d = duree_estimee(s["texte"])
        alerte = "  ⚠ hors 3–10 s" if not (2.5 <= d <= 10.5) and s["mouvement"] != "white_screen" else ""
        log.info("%-9s %-13s %-6s %5.1fs  %s%s", s["id"], s["mouvement"], s["format"], d,
                 (s["texte"][:55] + "…") if len(s["texte"]) > 56 else s["texte"], alerte)
    illustrees = [s for s in scenes if s["mouvement"] != "white_screen"]
    avec_monument = [s for s in illustrees if s["elements"]["monument"]]
    taux = len(avec_monument) / max(1, len(illustrees))
    (log.info if taux >= 0.7 else log.warning)(
        "Monument signature visible : %d/%d scènes illustrées (%.0f %%, règle : ≥ 70 %%)%s",
        len(avec_monument), len(illustrees), 100 * taux,
        "" if taux >= 0.7 else " — ajoute le monument à d'autres scènes")
    log.info("Plans spéciaux : %d icon_dark, %d white_screen", sum(s["mouvement"] == "icon_dark" for s in scenes),
             sum(s["mouvement"] == "white_screen" for s in scenes))
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
