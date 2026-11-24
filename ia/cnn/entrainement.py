"""
Diagnostic des maladies de la tomate — entraînement d'un CNN léger et export ONNX.

Données : sous-ensemble « tomate » du jeu PlantVillage (images de feuilles, 10 classes).
Organisez les images ainsi (une classe = un dossier) :

    donnees/
      train/Tomato___Early_blight/*.jpg
      train/Tomato___healthy/*.jpg
      ...
      val/Tomato___Early_blight/*.jpg
      ...

Utilisez le script preparer_donnees.py pour découper un dossier PlantVillage en train/val.

    pip install torch torchvision onnx onnxruntime
    python entrainement.py --donnees donnees --epoques 5
    → produit tomate_mobilenetv3.onnx et classes.json

Sur CPU, 3 à 5 époques de fine-tuning donnent déjà un modèle exploitable pour le projet
(prévoir un sous-échantillonnage si la machine est lente : --max-par-classe 400).
"""
import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

import torch
from torch import nn
from torch.utils.data import DataLoader, Subset
from torchvision import datasets, models, transforms

TAILLE = 224
MOY, ECART = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]  # normalisation ImageNet


def sous_echantillon(ds, max_par_classe: int):
    if not max_par_classe:
        return ds
    par_classe = defaultdict(list)
    for i, (_, c) in enumerate(ds.samples):
        par_classe[c].append(i)
    idx = [i for lst in par_classe.values() for i in random.sample(lst, min(len(lst), max_par_classe))]
    return Subset(ds, idx)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--donnees", default="donnees")
    ap.add_argument("--epoques", type=int, default=5)
    ap.add_argument("--lot", type=int, default=32)
    ap.add_argument("--max-par-classe", type=int, default=0)
    ap.add_argument("--sortie", default="tomate_mobilenetv3.onnx")
    a = ap.parse_args()
    random.seed(0)
    torch.manual_seed(0)
    if torch.cuda.is_available():
        dev = torch.device("cuda")
    elif torch.backends.mps.is_available():
        dev = torch.device("mps")
    else:
        dev = torch.device("cpu")

    print(f"Entraînement sur : {dev}")

    tf_train = transforms.Compose([
        transforms.RandomResizedCrop(TAILLE, scale=(0.7, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.ColorJitter(0.3, 0.3, 0.3),     # photos prises au champ ≠ photos de labo
        transforms.ToTensor(), transforms.Normalize(MOY, ECART)])
    tf_val = transforms.Compose([
        transforms.Resize(256), transforms.CenterCrop(TAILLE),
        transforms.ToTensor(), transforms.Normalize(MOY, ECART)])

    train = datasets.ImageFolder(Path(a.donnees) / "train", tf_train)
    val = datasets.ImageFolder(Path(a.donnees) / "val", tf_val)
    if train.class_to_idx != val.class_to_idx:
        ap.error("Les partitions train et val doivent contenir les mêmes classes")
    classes = train.classes
    print(f"{len(classes)} classes, {len(train)} images d'entraînement, {len(val)} de validation")
    dl_train = DataLoader(sous_echantillon(train, a.max_par_classe), batch_size=a.lot, shuffle=True, num_workers=2)
    dl_val = DataLoader(val, batch_size=a.lot, num_workers=2)

    # MobileNetV3-Small pré-entraîné sur ImageNet : léger (≈2,5 M de paramètres), exportable, embarquable
    modele = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.DEFAULT)
    modele.classifier[3] = nn.Linear(modele.classifier[3].in_features, len(classes))
    modele.to(dev)

    opt = torch.optim.AdamW(modele.parameters(), lr=1e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=a.epoques)
    perte = nn.CrossEntropyLoss(label_smoothing=0.1)

    for ep in range(1, a.epoques + 1):
        modele.train()
        for x, y in dl_train:
            x, y = x.to(dev), y.to(dev)
            opt.zero_grad()
            perte(modele(x), y).backward()
            opt.step()
        sched.step()
        modele.eval()
        ok = n = 0
        with torch.no_grad():
            for x, y in dl_val:
                ok += (modele(x.to(dev)).argmax(1).cpu() == y).sum().item()
                n += len(y)
        print(f"époque {ep}/{a.epoques} — exactitude validation : {ok / n:.3f}")

    # Export ONNX (lot de taille variable) + classes
    modele.eval().cpu()
    torch.onnx.export(
        modele, torch.randn(1, 3, TAILLE, TAILLE), a.sortie,
        input_names=["image"], output_names=["logits"],
        dynamic_axes={"image": {0: "lot"}, "logits": {0: "lot"}}, opset_version=17)
    fichier_classes = Path(a.sortie).with_name("classes.json")
    fichier_classes.write_text(json.dumps(classes, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Modèle exporté : {a.sortie} ; classes : {fichier_classes}")

    # Vérification : mêmes sorties avec ONNX Runtime
    import numpy as np
    import onnxruntime as ort
    x = torch.randn(2, 3, TAILLE, TAILLE)
    ref = modele(x).detach().numpy()
    out = ort.InferenceSession(a.sortie).run(None, {"image": x.numpy()})[0]
    print("écart max PyTorch / ONNX :", float(np.abs(ref - out).max()))


if __name__ == "__main__":
    main()
