# Corpus pour l'assistant agronome (RAG)

- `fiches/` : six fiches techniques simplifiées (Markdown), à indexer.
  Découpez-les par section (titres `##`) : chaque passage garde le nom du fichier et le titre de section, pour citer les sources.
- `questions_reference.json` : 20 questions de référence pour **évaluer** votre assistant
  (source attendue + éléments attendus). La question 20 est volontairement hors corpus :
  l'assistant doit le dire au lieu d'inventer.

Le service FastAPI découpe les fiches, calcule des embeddings de 384 dimensions
avec EmbeddingGemma via Ollama, puis stocke les passages dans pgvector. La
recherche renvoie jusqu’à quatre passages par distance cosinus. Qwen génère
la réponse en français à partir de ces passages et l’API relaie les fragments
et les citations en SSE.

Depuis la racine, une fois Compose lancé et les modèles téléchargés,
exécuter `python ia/rag/evaluer.py` avec un JWT valide. L’évaluation couvre les
questions 1 à 10 et la question 20 hors corpus. Le JSONL conserve la réponse,
les citations et les éléments attendus. Relire la justesse, la couverture et
l’abstention avant de reporter les résultats. Choisir un autre chemin avec
`--sortie` pour conserver un essai précédent.

Ces fiches sont pédagogiques et simplifiées.
