"""
Prépare le sous-ensemble « tomate » de PlantVillage en dossiers train/ et val/.

1. Téléchargez PlantVillage (version « color »), par exemple depuis Kaggle
   (jeu « PlantVillage Dataset ») ou via TensorFlow Datasets (plant_village).
2. Lancez :
       python preparer_donnees.py --source chemin/vers/plantvillage/color --sortie donnees
   Seuls les dossiers dont le nom commence par « Tomato » sont conservés.
"""
import argparse
import random
import shutil
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--sortie", default="donnees")
    ap.add_argument("--val", type=float, default=0.2, help="part des images en validation")
    ap.add_argument("--prefixe", default="Tomato")
    a = ap.parse_args()
    if not 0 < a.val < 1:
        ap.error("--val doit être strictement compris entre 0 et 1")
    sortie = Path(a.sortie)
    if (sortie / "train").exists() or (sortie / "val").exists():
        ap.error("Choisir un dossier de sortie sans partitions existantes")
    random.seed(0)

    dossiers = sorted(d for d in Path(a.source).iterdir() if d.is_dir() and d.name.startswith(a.prefixe))
    if not dossiers:
        raise SystemExit(f"Aucun dossier « {a.prefixe}* » dans {a.source}")
    images_par_classe = {
        dossier: sorted(p for p in dossier.iterdir() if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png"})
        for dossier in dossiers
    }
    classes_incompletes = [d.name for d, images in images_par_classe.items() if len(images) < 2]
    if classes_incompletes:
        ap.error("Au moins deux images par classe sont requises : " + ", ".join(classes_incompletes))

    for d, images in images_par_classe.items():
        random.shuffle(images)
        n_val = min(len(images) - 1, max(1, int(len(images) * a.val)))
        for i, img in enumerate(images):
            dest = sortie / ("val" if i < n_val else "train") / d.name
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(img, dest / img.name)
        print(f"{d.name:<55} {len(images) - n_val:>5} train  {n_val:>5} val")


if __name__ == "__main__":
    main()
