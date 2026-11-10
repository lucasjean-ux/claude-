---
name: video-remotion-tiktok
description: Fabriquer une vidéo TikTok de l'Usine avec Remotion (gratuit pour Lucas, particulier) — format 9:16, plus d'1 min 01, sous-titres mot à mot, à partir du pack.json, de la voix off et des images d'une production. À utiliser quand Lucas demande de « faire la vidéo avec Remotion », d'ajouter des sous-titres à ses clips de nettoyage, ou de monter une tier list, du stoïcisme ou de la finance.
---
# Vidéo TikTok avec Remotion

Remotion = vidéos écrites en React, rendues en MP4. Gratuit pour Lucas (licence « Free » : particulier,
usage commercial autorisé). Les skills officiels `remotion-*` sont installés : lis `remotion-best-practices`
pour savoir lequel ouvrir (`remotion-create`, `remotion-markup`, `remotion-captions`, `remotion-render`…).

## Le projet
- Un seul projet Remotion pour toute l'usine : `04_atelier/remotion-tiktok/`.
  S'il n'existe pas, le créer avec le skill `remotion-create` (TypeScript, sans template payant).
- Une composition par format : `Nettoyage`, `TierList`, `Stoicisme`, `Finance`. Le countryball garde
  `04_atelier/render/render_countryball.py`, déjà réglé sur son format.

## Format obligatoire (toutes les compositions)
- 1080 × 1920, 30 fps.
- Durée calculée avec `calculateMetadata` à partir de la durée réelle de la voix off, jamais sous 61 s.
  Si la voix fait moins de 61 s : le dire à Lucas et demander à l'agent Script d'allonger, ne pas étirer.
- Sous-titres mot à mot (skill `remotion-captions`) : gros, centrés au tiers bas, contour noir,
  mot prononcé surligné. Transcription locale gratuite (Whisper), jamais un service payant sans accord.
- Plan 1 : le texte écran du SEO (mot-clé principal) en grand pendant les 3 premières secondes.
- Rien dans les 15 % du bas ni sur le bord droit (interface TikTok).

## Entrées (dans 03_productions/AAAA-MM-JJ_niche_sujet/)
- `pack.json` : scènes (`texte_ecran`, `voix_off`, `prompt_image`) — source de vérité du découpage.
- `voix.mp3` (ou une piste par scène) : voix Henri (edge-tts) ou Piper, gratuites.
- `images/01.png…` ou, pour le nettoyage auto, les clips de Lucas dans `clips/`.
- Copier les médias dans `public/` du projet Remotion avant le rendu (`staticFile()`).

## Par niche
- Nettoyage auto : clips de Lucas plein écran, coupés selon le plan de découpe de l'agent Visuels,
  sous-titres mot à mot, révélation gardée pour la fin.
- Tier list flippante : tableau d'ouverture animé (lignes qui apparaissent du plus calme au plus
  terrifiant), puis un plan par élément avec son numéro.
- Stoïcisme : images lentes (zoom doux), citation en serif au centre au moment où elle est dite.
- Stickman finance : images stickman, chiffres clés animés (compteur), fond blanc.

## Rendu et livraison
- Prévisualiser avec `remotion-studio` si Lucas veut voir avant.
- Rendre avec `remotion-render` vers `03_productions/<dossier>/video.mp4`, puis vérifier avec ffprobe :
  1080x1920, durée ≥ 61 s, piste audio présente.
- Interdit : Higgsfield, et tout fournisseur payant sans l'accord de Lucas.
- Mettre à jour `01_ceo/etat.js` (agent Montage « fait ») et les compteurs.
