// État de l'usine, affiché par ESPACE-DE-TRAVAIL.html.
// Le CEO (Claude) met ce fichier à jour à chaque étape. Statuts possibles : "attente", "en_cours", "fait".
window.ETAT = {
  date: "2026-11-09",
  niche_en_cours: "nettoyage",  // département actif : nettoyage, tierlist, countryball, stoicisme, finance
  video_en_cours: "",            // ex. "Nettoyage auto — la Clio de mamie"
  dossier: "",                   // ex. "03_productions/2026-11-09_nettoyage_clio"
  message_ceo: "Priorité du jour : la première vidéo de nettoyage auto. Envoie ton clip et on démarre.",
  agents: {
    ceo:         { statut: "en_cours", note: "Prêt à lancer la journée" },
    angle:       { statut: "attente",  note: "" },
    script:      { statut: "attente",  note: "" },
    seo:         { statut: "attente",  note: "" },
    visuels:     { statut: "attente",  note: "" },
    montage:     { statut: "attente",  note: "" },
    publication: { statut: "attente",  note: "" },
    analyste:    { statut: "attente",  note: "" }
  },
  journee: [
    { etape: "Nettoyage auto n°1", fait: false },
    { etape: "Nettoyage auto n°2", fait: false },
    { etape: "Tier list flippante", fait: false },
    { etape: "Countryball", fait: false }
  ],
  non_postees: 0,
  total_videos: 0,
  total_postees: 0,
  gains: 0
};
