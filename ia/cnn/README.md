# Diagnostic par image (CNN)

1. Télécharger PlantVillage (version « color ») — par exemple le jeu « PlantVillage Dataset » sur Kaggle.
2. `python preparer_donnees.py --source <dossier_color> --sortie donnees` (ne garde que la tomate, 10 classes).
3. `python entrainement.py --donnees donnees --epoques 5` → `tomate_mobilenetv3.onnx` + `classes.json`.
4. Servir le modèle avec ONNX Runtime dans un **service séparé** de l'API (voir CM5) :
   pré-traitement identique à la validation (redimensionnement 256, recadrage central 224, normalisation ImageNet).

`classes_fr.json` donne les libellés français des classes, à afficher dans l'interface.

Limite connue (à discuter dans le rapport) : les images PlantVillage sont prises sur fond uni,
en conditions de laboratoire. Les performances chutent sur des photos prises au champ :
augmentation de données, collecte de quelques photos réelles, seuil de confiance et confirmation humaine.
