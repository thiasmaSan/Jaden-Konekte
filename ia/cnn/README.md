# Diagnostic par image (CNN)

Le modèle MobileNetV3-Small fourni classe une photo de feuille de tomate
parmi dix classes PlantVillage, dont la classe saine. Le service d’inférence
charge `tomate_mobilenetv3.onnx` sur CPU avec ONNX Runtime. Il utilise
`classes.json` pour associer les indices de sortie aux classes et
`classes_fr.json` pour afficher les libellés français.

## Tester le modèle fourni

Après le [démarrage du projet](../../README.md#démarrage-et-démonstration),
ouvrir une parcelle dans le tableau de bord et envoyer un JPEG ou un PNG de
5 Mio maximum. Le diagnostic affiche la classe, le score et la version du
modèle. L’API conserve le résultat dans l’historique de la parcelle.

Pour tester directement l’inférence locale, préparer un fichier
`feuille.jpg` dans le répertoire courant et exécuter les commandes suivantes.

```sh
curl -fsS http://127.0.0.1:8001/health
curl -fsS -F 'image=@feuille.jpg;type=image/jpeg' http://127.0.0.1:8001/predictions
```

Le service accepte des images d’au moins 32 × 32 pixels et d’au plus
20 millions de pixels. Après correction de l’orientation EXIF, il convertit
en RGB, redimensionne le côté court à 256 pixels, recadre le centre à
224 × 224 pixels et applique la normalisation ImageNet. Le score renvoyé
correspond à la probabilité softmax maximale.

## Réentraîner et exporter

Télécharger les images PlantVillage en version couleur. Le dossier source
doit contenir les sous-dossiers de classes `Tomato___…`. Depuis la racine,
dans un environnement Python activé, indiquer le chemin réel du corpus.
L’exemple place l’export dans un dossier temporaire pour préserver le modèle fourni.

```sh
python -m pip install torch torchvision onnx onnxscript onnxruntime
cd ia/cnn
travail_cnn=$(mktemp -d)
python preparer_donnees.py --source /chemin/vers/color --sortie "$travail_cnn/donnees"
python entrainement.py --donnees "$travail_cnn/donnees" --epoques 5 \
  --sortie "$travail_cnn/tomate_mobilenetv3.onnx"
```

Le script sépare les images par classe entre entraînement et validation.
L’entraînement affiche l’exactitude de validation par époque, exporte
`classes.json` à côté du modèle et mesure l’écart maximal entre les sorties
PyTorch et ONNX Runtime. Ajouter `--max-par-classe 400` à la commande
d’entraînement pour limiter le nombre d’images d’entraînement par classe.

Les photos PlantVillage sont prises dans des conditions contrôlées. Pour estimer
les performances au champ, il faut une évaluation distincte sur des photos
réelles. Le résultat du modèle sert d’aide au diagnostic et demande une
confirmation humaine.
