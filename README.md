# Toutes les civilisations expliquées : pipeline vidéo TikTok

Pipeline Python (Pillow + ffmpeg + faster-whisper) qui monte automatiquement les vidéos verticales
de la série (1080x1920, 30 fps, H.264 + AAC, voix seule à -14 LUFS, sous-titres mot à mot).
D'un épisode à l'autre, seuls changent le script, les illustrations et la tuile ciblée par le zoom d'intro.

```
.
├── commun.py            # constantes, polices, civilisations, style des prompts, découpage en mots
├── generer_intro.py     # dessine assets/intro.png (affiche + grille 3x3)
├── decouper.py          # script.txt (+ plan.json) -> scenes.json + prompts.txt
├── render.py            # voix -> transcription -> calage -> rendu -> final.mp4
├── assets/
│   ├── civilisations.json  # BIBLE : costume, variantes, monument signature, décor, couleur de tuile
│   ├── intro.png        # affiche 1080x1920 (générée)
│   ├── intro_hd.png     # même affiche x3, pour un zoom net vers la tuile
│   ├── fonts/           # Poppins / Montserrat (téléchargées depuis Google Fonts)
│   └── tuiles/          # mesopotamienne.png, egyptienne.png, … (9 tuiles carrées)
└── episodes/
    └── 01_mesopotamie/
        ├── script.txt   # texte de la voix off
        ├── plan.json    # plan de scènes (ancres, mouvements, action/objet/décor de chaque image)
        ├── scenes.json  # généré par decouper.py
        ├── prompts.txt  # généré : prompts d'images (+ negative prompts)
        ├── prompts_chatgpt.txt  # généré : les mêmes, en messages à coller un par un dans ChatGPT
        ├── voix.mp3     # optionnel (sinon ElevenLabs)
        ├── images/      # scene_01.png … scene_13.png (pas d'image pour les white_screen)
        └── cache/       # voix normalisée, transcription, placeholders (régénérable)
```

## Installation

1. **Python 3.10+** et **ffmpeg** (avec ffprobe) :
   - macOS : `brew install ffmpeg`
   - Ubuntu / Debian : `sudo apt install ffmpeg`
   - Windows : `winget install ffmpeg`
2. Dépendances Python :
   ```bash
   python -m venv .venv && source .venv/bin/activate   # Windows : .venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. (Optionnel) Voix ElevenLabs : copie `.env.example` en `.env` et renseigne `ELEVENLABS_API_KEY`
   (et `ELEVENLABS_VOICE_ID` pour choisir la voix).

Les polices Poppins et Montserrat sont téléchargées automatiquement depuis Google Fonts au premier lancement
(déjà présentes dans `assets/fonts/`). Le modèle faster-whisper `medium` (environ 1,5 Go) est téléchargé au
premier rendu.

## Utilisation (épisode 1)

```bash
# 1. Affiche d'intro (à relancer quand tu ajoutes les vraies tuiles dans assets/tuiles/)
python generer_intro.py

# 2. Découpage en scènes + prompts d'images
python decouper.py --episode 01_mesopotamie
#    -> episodes/01_mesopotamie/scenes.json et prompts.txt (scènes + 9 tuiles)

# 3. Test rapide sans voix ni images (placeholders + piste muette, 540x960)
python render.py --episode 01_mesopotamie --tuile mesopotamienne --preview --voix-test

# 4. Rendu final
python render.py --episode 01_mesopotamie --tuile mesopotamienne
#    -> episodes/01_mesopotamie/final.mp4
```

### Options de `render.py`

| Option | Effet |
|---|---|
| `--tuile <id>` | tuile ciblée par le zoom d'intro : `mesopotamienne`, `egyptienne`, `grecque`, `romaine`, `viking`, `chinoise`, `maya`, `azteque`, `inca` (par défaut : celle de `plan.json`) |
| `--preview` | export 540x960, encodage rapide → `final_preview.mp4` |
| `--voix-test` | sans voix.mp3 ni clé ElevenLabs : piste muette et timings estimés |
| `--sans-whisper` | timings estimés à partir du texte, sans transcription |
| `--modele-whisper medium` | modèle faster-whisper (`small` pour aller plus vite) |
| `--device auto\|cpu\|cuda` | matériel utilisé par whisper |
| `--voix-debut 2.2` | instant où démarre la voix. Par défaut, la voix démarre avec le zoom d'intro, donc aucun mot pendant l'affiche fixe. |
| `--sortie chemin.mp4` | fichier de sortie |

## Voix off

Ordre de priorité :
1. `episodes/<épisode>/voix.mp3` (ou `.wav` / `.m4a`) si le fichier existe ;
2. sinon, l'API ElevenLabs si `ELEVENLABS_API_KEY` est dans `.env`. Le résultat est enregistré en `voix.mp3`
   puis réutilisé : supprime ce fichier pour en régénérer un. Réglages possibles : `ELEVENLABS_VOICE_ID`,
   `ELEVENLABS_MODEL`, `ELEVENLABS_STABILITY`, `ELEVENLABS_STYLE` et `ELEVENLABS_SPEED`. Pour viser 80 à 90 s,
   la vitesse se règle entre 0.9 et 1.1.
3. sinon, une erreur, sauf avec `--voix-test`.

La voix est normalisée à -14 LUFS (loudnorm en deux passes, true peak -1,5 dBTP). La vidéo n'a ni musique
ni bruitage.

## Synchronisation

- faster-whisper (modèle `medium`, langue `fr`) donne l'horodatage de chaque mot. Les noms propres du
  `lexique` de `plan.json` servent d'indice au modèle.
- Les mots reconnus sont **réalignés caractère par caractère sur `script.txt`**. Les sous-titres reprennent
  donc l'orthographe exacte du script (Sumériens, Uruk, ziggourat, Gilgamesh, Sargon d'Akkad…), même quand
  whisper s'est trompé. Les nombres sont écrits comme ils sont prononcés : 3300 devient « trois mille trois
  cents ».
- Chaque scène commence sur le premier mot de son texte, et la coupe tombe juste avant ce mot. La scène dure
  jusqu'au début de la suivante.
- La transcription est mise en cache dans `cache/`. Pour la refaire, il suffit de supprimer le cache.
- Les mots alignés sont enregistrés dans `cache/mots_alignes.json`, pour vérification.

## Structure de la vidéo

| Partie | Rendu |
|---|---|
| 0 – 2,2 s | affiche fixe (titre, sous-titre gris, grille 3x3 de countryballs en buste devant leur monument), sans sous-titres |
| 2,2 – 3,8 s | zoom accéléré (ease-in) vers la tuile `--tuile` jusqu'au plein écran, puis coupe sèche |
| corps | une illustration fixe par scène. `push_in` zoome de 100 à 112 %. `pan_left` et `pan_right` traversent une image 16:9 à vitesse constante : le personnage sort du cadre et le plan finit sur le décor et le monument. `impact_zoom` passe de 90 à 115 % en 0,8 s, puis dérive lentement. |
| `icon_dark` | icône centrée sur fond #22272E avec un halo doux. Si l'image est détourée (PNG transparent), le fond et le halo sont composés automatiquement. |
| `white_screen` | écran blanc, sous-titres seuls |
| outro | illustration récapitulative pendant la question finale, puis écran blanc (au moins 2 s) sur « Dites-le-nous dans les commentaires », puis 1 image noire |

Toutes les transitions sont des coupes sèches.

**Sous-titres** : un mot à la fois, en minuscules, sans ponctuation. Police Poppins SemiBold 52 px (pour
1080 px de large), blanche, contour noir de 3 px et ombre douce, centrée, ligne de base à 78 % de la
hauteur. Le mot apparaît sans animation et reste affiché jusqu'au suivant. Il est effacé quand le silence
dépasse 0,4 s.

Les réglages (durées, zooms, taille des sous-titres…) sont regroupés en haut de `render.py`.

## Illustrations et prompts

### Bible des civilisations : `assets/civilisations.json`

La bible contient, pour chaque civilisation :
- **le costume complet**, en anglais pour les prompts, avec sa référence en français ;
- **des variantes** de costume (roi, scribe, prêtre, hoplite, empereur, guerrier…) ;
- **les objets** que la boule tient dans ses gants ;
- **le monument signature** ;
- **une liste d'éléments de décor** ;
- **les couleurs de la tuile et de la boule**, et la silhouette utilisée pour les placeholders.

`decouper.py` injecte automatiquement ces données dans chaque prompt, selon la civilisation de l'épisode :
- **Costume** : celui de la civilisation de l'épisode, ou la variante demandée par la scène.
- **Monument** : il est placé derrière le personnage. Dans un pan, il est placé du côté que le mouvement
  révèle à la fin.
- **Décor** : chaque image reçoit 2 à 3 éléments. Ce sont ceux que la scène impose. S'il y en a moins de 2,
  ils sont complétés par une rotation dans la bible, pour que les images varient.
- **Lumière** : heure dorée, aube brumeuse ou coucher de soleil, en rotation, sauf si la scène impose la sienne.

`decouper.py` vérifie aussi la règle des 70 % : le monument signature doit être visible dans au moins 70 %
des scènes illustrées. L'épisode 1 l'a dans 10 scènes sur 12 (83 %). Les deux exceptions sont les icônes.

### Les modèles de prompts (anglais)

- **Scène avec personnage** (`push_in`, `impact_zoom`, `pan_*`) : « Highly detailed 2D cartoon illustration,
  premium children's book style, vertical 9:16. A countryball character (…) dressed in a full detailed
  [COSTUME], [ACTION], white cartoon gloves holding [OBJET]. Rich detailed historical background with the
  [MONUMENT] clearly visible behind the character, plus [DÉCOR], other small countryball inhabitants… »
  Pour les pans, le format devient un panorama 16:9. Le personnage est placé d'un côté et le monument de
  l'autre.
- **`icon_dark`** : un objet seul et détaillé, sur fond uni #22272E, avec un halo doux derrière.
- **Outro** : les symboles de l'épisode flottent dans un ciel doré devant le monument, avec la countryball en
  costume, en petit, en bas.
- **Tuiles** (1:1) : la countryball en buste et en costume complet, le monument en petit et en transparence
  derrière, sur un fond de la couleur de la tuile.
- **Negative prompt** : « text, letters, words, watermark, realistic human, human body, legs, mouth, flat
  simple background, gradient background, minimalist, empty scene, blurry character ». Les icônes et les
  tuiles ont leur propre negative prompt, adapté au fond uni.

### Produire les images avec ChatGPT (gratuit)

`decouper.py` écrit aussi `prompts_chatgpt.txt`. Ouvre une nouvelle conversation ChatGPT par épisode et
colle d'abord le MESSAGE 0, qui fixe le style et le personnage principal. Colle ensuite chaque MESSAGE dans
l'ordre, un par un, puis enregistre chaque image sous le nom indiqué. Les tuiles se font dans une autre
conversation (section en bas du fichier). ChatGPT produit du 2:3 ou du 3:2 au lieu du 9:16 ou du 16:9 :
c'est sans conséquence, car `render.py` recadre automatiquement et les pans fonctionnent aussi en 3:2.

### Produire les images (autre générateur)

1. Ouvre `episodes/<épisode>/prompts.txt`. Pour chaque image, il donne le PROMPT, le NEGATIVE PROMPT, le
   format (9:16, ou 16:9 pour les `pan_*`) et le nom du fichier à enregistrer.
2. Enregistre chaque image sous `images/<id>.png` (`.jpg` et `.webp` sont aussi acceptés).
3. Les 9 tuiles d'intro vont dans `assets/tuiles/<id>.png`. Relance ensuite `python generer_intro.py`.

Si `images/` est vide, `render.py` génère des placeholders : des cercles de couleur sur un dégradé, une boule
et la silhouette du monument. Ils suffisent à valider le montage, les cadrages et les pans (le pan doit finir
sur le monument). Une image manquante isolée est elle aussi remplacée par un placeholder, avec un
avertissement dans les logs. Les tuiles manquantes sont remplacées par une boule en buste devant la
silhouette transparente du monument.

## Nouvel épisode

1. Crée `episodes/02_egypte/` avec `script.txt` et `plan.json`. Copie le plan de l'épisode 1 et adapte-le.
   - Champs généraux :
     - `civilisation` : l'id de la tuile et de la bible ;
     - `lexique` : les noms propres, pour aider whisper.
   - Champs de chaque scène (seuls `id`, `debut` et `mouvement` sont obligatoires) :

| Champ | Rôle |
|---|---|
| `id`, `debut`, `mouvement` | identifiant, premiers mots du passage dans le script, mouvement de caméra |
| `action`, `expression`, `objet` | ce que fait la boule, son regard, ce qu'elle tient (par défaut, un objet de la bible) |
| `variante` | costume alternatif de la bible (`roi`, `pretre`, `hoplite`, `empereur`, `guerrier`, `jaguar`…) |
| `costume_de`, `monument_de` | prendre le costume ou le monument d'une autre civilisation (ex. la boule grecque dans l'épisode 1) |
| `decor`, `habitants`, `premier_plan` | éléments de décor imposés, habitants du plan moyen, objets du premier plan |
| `lumiere`, `position_monument` | ambiance lumineuse imposée, position du monument (« through a doorway », « far in the distance »…) |
| `sans_monument` | `true` pour exclure le monument (attention à la règle des 70 %) |
| `objet` (icon_dark) / `symboles` + `outro: true` (outro) | contenu des plans spéciaux |

   Sans `plan.json` (ou sans `scenes`), `decouper.py --tuile <id>` découpe le script tout seul et marque les
   actions à rédiger avec `TODO`. Les prompts sont tout de même remplis avec la bible.
2. Lance `python decouper.py --episode 02_egypte`. Il affiche la durée estimée de chaque scène et le taux de
   monuments, et signale ce qui sort des règles.
3. Génère les images, puis lance `python render.py --episode 02_egypte --tuile egyptienne`.

## Logs

Chaque étape est annoncée (`ÉTAPE n : …`). Les logs affichent aussi :
- le tableau de calage des scènes : début, fin, durée et premiers mots, avec une alerte si une scène sort
  de 3 à 10 s ;
- la durée totale, avec une alerte si elle sort de 80 à 90 s ;
- la progression du rendu ;
- le contrôle final : codecs, résolution et loudness mesurée.
