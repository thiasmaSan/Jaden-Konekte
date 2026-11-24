# Fiche technique — Arrosage et humidité du sol

> Fiche pédagogique simplifiée, rédigée pour le projet Jaden Konekté. Les seuils sont indicatifs et doivent être ajustés selon le type de sol, la culture et le capteur.

## Comprendre la mesure
Les capteurs du projet mesurent l'**humidité volumique du sol** (en %), c'est-à-dire la part du volume de sol occupée par l'eau.
- **Capacité au champ :** quantité d'eau que le sol retient après ressuyage (l'excès s'est écoulé). Au-delà, le sol est saturé.
- **Point de flétrissement :** en dessous, la plante ne parvient plus à extraire l'eau.
- La **réserve utile** se situe entre les deux. Un sol argileux retient beaucoup plus d'eau qu'un sol sableux.

## Seuils indicatifs pour le projet
| Humidité du sol | Interprétation | Conduite |
|---|---|---|
| > 45 % | Sol très humide, proche de la saturation | Ne pas arroser |
| 30 – 45 % | Confort hydrique | Ne pas arroser |
| 20 – 30 % | Début de dessèchement | Arroser si aucune pluie n'est prévue |
| < 20 % | Sol sec, stress probable | Arroser rapidement |

## Bonnes pratiques d'arrosage
- Arroser tôt le matin ou en fin d'après-midi ; éviter les heures les plus chaudes.
- Préférer plusieurs apports modérés à un apport massif (le sol sableux ne retient pas l'excès).
- Ne pas arroser si une pluie significative est prévue dans les prochaines heures : c'est l'intérêt d'une API météo.
- Arroser au pied des plantes et non sur le feuillage, pour limiter les maladies.
- Surveiller les valeurs aberrantes du capteur (valeur négative, nulle ou supérieure à 100 %) : elles signalent une panne, pas un sol sec.

## Saisons
- **Carême (saison sèche, environ de janvier à avril) :** besoins d'arrosage élevés, paillage conseillé.
- **Hivernage (saison des pluies, environ de juillet à novembre) :** averses fréquentes et intenses ; risque d'excès d'eau et de maladies. L'arrosage automatique doit tenir compte de la pluie mesurée et prévue.

## Exemple de règle automatique
SI humidité du sol < seuil de la parcelle ET cumul de pluie prévu sur 6 h < 2 mm ET heure entre 5 h et 9 h ou entre 16 h et 19 h
ALORS ouvrir la vanne pendant 10 minutes, puis attendre au moins 2 heures avant de réévaluer.
