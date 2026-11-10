---
name: script-depuis-clip
description: Écrire le script d'une vidéo nettoyage auto à partir du clip que Lucas envoie (ce qu'on voit vraiment dans la vidéo) et de ce qui buzze dans la niche. À utiliser dès que Lucas envoie un clip de nettoyage ou demande « fais le script de ma vidéo ».
---
# Script à partir du clip de Lucas

## 1. Regarder le clip (ne jamais inventer ce qu'on ne voit pas)
Ranger le clip dans 03_productions/AAAA-MM-JJ_nettoyage_<sujet>/clips/, puis :
- durée et format : ffprobe
- planche : ffmpeg -i clip.mp4 -vf "fps=40/<durée>,scale=180:-1,tile=8x5" -frames:v 1 planche.png
- coupes : ffmpeg -i clip.mp4 -vf "select='gt(scene,0.3)',showinfo" -f null - (pts_time)
- 3-4 images pleine taille aux moments clés (pire saleté, mousse, boue qui tombe, résultat)
Noter : véhicule (type, couleur, état), type de saleté (boue, poils, sable, moisissure, tâches…),
endroits les plus sales, étapes filmées dans l'ordre avec leur minutage, plan de la révélation.

## 2. Ce qui buzze (gratuit d'abord)
- Les références analysées dans 05_references/videos/ (format @js_nettoyage : accroche client + « mais »,
  enjeu, étapes, bascule, révélation, chute morale).
- Les mots-clés ✅ de 02_seo/mots-cles.md et le bilan de l'Analyste.
- Si Lucas envoie d'autres vidéos qui buzzent : les analyser pareil et ajouter ce qu'on apprend ici.
- vidIQ (outlier search TikTok, FR) seulement si son compte a des crédits — sinon ne pas insister.
Choisir l'angle de l'histoire qui colle à CE que montre le clip (pas une histoire hors sujet).
L'histoire du client est un storytime : rester crédible, pas de faits techniques faux, pas de
diffamation de personnes ou de marques réelles.

## 3. Livrer (dans le dossier de la vidéo)
- angle.txt : 3 hooks (max 15 mots) collés aux images du clip + le recommandé.
- script.txt : 210-230 mots (voix Henri à 1,3x → ≥ 1 min 02), structure montage-nettoyage,
  chaque étape racontée au moment où elle apparaît dans le clip.
- decoupe.txt : pour chaque phrase, le passage du clip (début–fin en secondes) + texte des sous-titres.
  Si le clip est trop court pour couvrir la voix : le dire et lister les plans à filmer en plus.
- seo.txt et publication.txt (skill seo-tiktok).
Puis montage : skill video-remotion-tiktok (composition Nettoyage) ou CapCut.
Mettre à jour 01_ceo/etat.js et le tableau de bord.
