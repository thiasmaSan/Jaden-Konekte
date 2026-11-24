# Assistant agronome (RAG)

Le corpus comprend six fiches pédagogiques dans [fiches/](fiches/) et vingt
[questions de référence](questions_reference.json). L’API découpe les fiches
par titre de niveau 2 et conserve le fichier et le titre de chaque passage
pour les citations.

## Fonctionnement

Compose télécharge par défaut `embeddinggemma` et `qwen2.5:1.5b` dans
Ollama. La première question indexe les passages dans pgvector. L’index
utilise des vecteurs de 384 dimensions et l’empreinte du corpus tient compte
du contenu des fiches. La recherche sélectionne jusqu’à quatre passages
par distance cosinus et applique un seuil de pertinence.

Le tableau de bord appelle `POST /api/v1/assistant/questions` avec le jeton
JWT et un corps JSON contenant une `question` de 3 à 1 000 caractères après
suppression des espaces en début et en fin. Le flux SSE transmet les
événements `fragment`, `sources` et `fin`. Une génération interrompue
émet `erreur`. L’assistant est invité à répondre en français à partir des
passages retenus. Lorsque la recherche ne retient aucun passage, l’API
renvoie une réponse d’abstention avec une liste de sources vide.

## Essai et évaluation

1. Suivre le [démarrage Compose](../../README.md#démarrage-et-démonstration).
   Depuis `infra/`, vérifier que `ollama-init` s’est terminé avec le code 0
   via `docker compose ps -a ollama-init`.
2. Se connecter et poser une question dans le tableau de bord. La première
   réponse peut prendre davantage de temps à cause de l’indexation.
3. Récupérer un JWT auprès de `POST /api/v1/auth/connexion` dans Swagger,
   puis saisir sa valeur à l’invite du script. Depuis la racine, utiliser un
   environnement Python avec HTTPX installé.

```sh
python ia/rag/evaluer.py --sortie evaluation-rag.jsonl
```

Le script interroge les questions 1 à 10 et la question 20, volontairement
hors corpus. Le JSONL contient une ligne par question avec les éléments
attendus, la réponse et les sources, ou l’erreur rencontrée. Le script vérifie
la citation du fichier attendu ou la présence de la formule d’abstention sans
source. Relire les réponses pour juger leur exactitude et leur couverture.
La sortie doit être un nouveau fichier à chaque essai. L’option `--url`
permet de changer l’adresse de l’API, par défaut `http://127.0.0.1:8000`.
