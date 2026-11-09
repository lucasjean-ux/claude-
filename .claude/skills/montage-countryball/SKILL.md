---
name: montage-countryball
description: Format vidéo countryball (« bulles ») de l'Usine à TikTok — rythme, mise en page, animation, voix. À lire avant d'écrire un pack countryball ou de lancer render_countryball.py.
---
# Format countryball (analysé sur references/countryball_reference.mp4, 1 min 13)

Structure
- Plan 1 : miniature-liste (4 countryballs sous un grand titre, ex. « FILMS INTERDITS »), puis on raconte UNE histoire.
- Un plan nouveau toutes les 1,3 à 4 s (moyenne ≈ 2,5 s). Une phrase de voix off = un ou deux plans.
- Chaque plan : fond uni de la couleur de l'illustration, illustration centrée (≈ 86 % de la largeur),
  2 à 4 mots en majuscules au-dessus (« LA PIRE PUNITION », « 2 MIN 37 COUPÉES »).
- Entrée de chaque illustration : petit « pop » (zoom de 55 % à 100 % avec léger rebond, ≈ 0,35 s), puis zoom lent.
- La boule France sert de narrateur récurrent ; fin sur une question au spectateur pour les commentaires.
- Voix : Henri (fr-FR-HenriNeural) à +8 %, ton complice, phrases courtes.

Style des images (identique sur toute la vidéo)
countryball = sphère parfaite aux couleurs du drapeau, gros contour noir épais, deux yeux blancs ovales
sans pupille, couleurs plates, fond uni, style webcomic. Jamais de texte dans l'image : le texte est ajouté par le moteur.

Vérifications avant rendu
- 14 à 20 scènes, total ≥ 61 s une fois la voix générée.
- Faits vérifiables uniquement ; dates et chiffres exacts.
- Une image par scène, nommée 01.png, 02.png…
