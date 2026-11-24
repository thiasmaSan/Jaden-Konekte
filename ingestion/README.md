# Ingestion MQTT

Ce service Python indépendant de FastAPI utilise Paho MQTT pour recevoir les
messages et psycopg pour les transactions PostgreSQL. Il ne charge ni JWT ni `.env`
de l'API : Compose fournit son URL de base et le chemin du secret MQTT.

## Démarrer avec l'exploitation existante

Préparer la configuration Compose et créer une exploitation en suivant le
[démarrage du projet](../README.md#démarrage-et-démonstration). Depuis la racine,
utiliser le code saisi à l’inscription, ou l’identifiant SQL si on le connaît.

```bash
sh infra/demarrer_simulation.sh --code CODE_EXPLOITATION
```

Ce script démarre la base, prépare les parcelles p1/p2/p3 et les vannes manquantes,
lit le vrai code d'exploitation, génère les comptes MQTT, recharge le broker et
lance l'ingestion et le simulateur. Il ne remplace pas les parcelles existantes,
ne crée pas d'utilisateur et ne modifie pas `.env`. Il redémarre le broker pour
appliquer les ACL et provoque donc une brève interruption MQTT. Les volumes de
données et mots de passe existants sont conservés. L'API locale peut rester ouverte.

Le code de l'exploitation autorisée est mémorisé dans le volume `mqtt-auth` et
fourni au simulateur dans son volume de configuration. Les démarrages suivants
avec `docker compose --profile simu up -d` réutilisent ce code. Une seule exploitation
de simulation est sélectionnée à la fois ; les droits du simulateur ne couvrent
pas les autres exploitations. Pour sélectionner une autre exploitation existante,
relancer le script avec son code ou son identifiant. Un code contenant des espaces, slashs ou
caractères hors lettres ASCII/chiffres/tiret/underscore sera refusé.

Depuis `infra/` :

```bash
docker compose ps -a
docker compose logs --tail 30 ingestion
docker compose exec db psql -U jaden -d jaden -c "SELECT count(*) AS total, count(*) FILTER (WHERE valide) AS valides, count(*) FILTER (WHERE NOT valide) AS aberrantes FROM mesure;"
```

Le service `mqtt-init` doit être terminé avec le code 0 ; c'est un service de
préparation, pas un serveur permanent. Le broker doit être sain et l'ingestion
doit afficher des mesures enregistrées. Le simulateur publie toutes les cinq
secondes en temps réel (`--acceleration 1` dans Compose).

## Vérification réelle de la chaîne

Après le démarrage précédent, depuis `infra/`, pour l’exploitation
simulée d’identifiant 1 :

```bash
docker compose --profile test run --rm --no-deps verification
```

Le test crée une nouvelle parcelle `test-ingestion-…` dans l'exploitation 1 et la
conserve avec ses données ; son identifiant est affiché. Il vérifie le refus de
l'accès anonyme et d'une publication dans une autre exploitation, puis publie une
mesure valide, son doublon et une valeur aberrante. Il attend exactement deux
lignes dans TimescaleDB : une valide et une invalide. Aucun nettoyage destructif
n'est effectué. Pour une exploitation simulée d’un autre identifiant, passer son identifiant
à la commande. Exemple pour l’identifiant 2 :

```bash
docker compose --profile test run --rm --no-deps verification python -m app.verifier_chaine --exploitation-id 2
```

Ces vérifications nécessitent les services actifs et ne sont pas exécutées par
la suite de tests unitaires. Une publication refusée par les ACL ne garantit pas
un message d'erreur au producteur MQTT 3.1.1 ; le test utilise donc un observateur
authentifié en lecture pour vérifier qu'elle n'est pas distribuée.

Dans Swagger, après connexion et autorisation JWT, consulter :

- `GET /api/v1/parcelles` pour relever les identifiants ;
- `GET /api/v1/parcelles/{id}/mesures` pour les mesures brutes ;
- `GET /api/v1/parcelles/{id}/mesures/agregats?intervalle=heure&jours=1` pour les
  moyennes, minimums, maximums et nombres par capteur sur 24 heures ;
- `intervalle=jour&jours=7` pour les sept derniers jours.

Les agrégats excluent `valide=false` et les mesures datées dans le futur. Les
bornes temporelles reposent sur l'heure PostgreSQL et les intervalles sont en UTC.

## Validation et stockage

`app/validation.py` valide la structure du topic, le JSON (4 Ko au plus), les
champs obligatoires, les nombres finis, l'unité et l'identifiant capteur du kit
(`<parcelle>-<type>`, par exemple `p1-air`). L'heure doit être ISO 8601 avec fuseau
ou un timestamp Unix en secondes. Elle est normalisée en UTC. Les messages de
statut et de vanne ne font pas partie des abonnements de ce service.

`app/stockage.py` recherche la parcelle par les codes du topic. Une parcelle
inconnue est rejetée et journalisée ; aucun message ne crée une exploitation.
Les capteurs sont déclarés à la première mesure selon la paire `(type, grandeur)`.
Un verrou sur la parcelle sérialise cette déclaration, même avec plusieurs
transactions. Plusieurs capteurs existants pour la même paire sont considérés
ambigus et provoquent un rejet. Un capteur inactif est également refusé.

| Grandeur | Unité | Bornes par défaut incluses |
|---|---|---|
| Humidité du sol | % | 0 à 100 |
| Température de l'air | °C | -20 à 65 |
| Luminosité | lx | 0 à 150000 |
| Intensité de pluie | mm/h | 0 à 500 |

Ces bornes sont pédagogiques. Les colonnes `min_valide` et `max_valide` permettent
de les adapter. Les valeurs hors bornes sont conservées avec `valide=false`.
Un zéro d'humidité reste physiquement plausible et n'est pas détecté comme panne
à lui seul ; -1 et 999 sont invalides. Les nombres NaN/infinis et les messages
mal formés sont rejetés sans insertion.

La clé primaire `(capteur, ts)` existante et `ON CONFLICT DO NOTHING` ignorent les
doublons. Un premier message conserve sa valeur ; une retransmission au même
instant ne le remplace pas. Aucune migration SQL n'est nécessaire.

`app/main.py` accuse réception après le commit. Une erreur SQL interrompt le
processus sans acquittement ; Docker le redémarre et la session MQTT persistante
permet la redistribution des messages QoS 1 en attente. Un message définitivement
invalide est journalisé puis acquitté. Cette stratégie ne constitue pas une
garantie de conservation illimitée : elle dépend de la persistance du broker, de
ses limites de file et de la survie de ses volumes. QoS 0 n'offre pas cette reprise.

## Comptes MQTT

`infra/mosquitto/initialiser.sh` crée des mots de passe aléatoires dans des volumes
Docker séparés et un fichier haché avec `mosquitto_passwd`. Aucun mot de passe
n'est affiché ou ajouté au dépôt. Les fichiers de secret sont montés en lecture
seule dans les clients concernés.

| Compte | Droits |
|---|---|
| ingestion | Lire les quatre topics de mesures, et la version du broker pour son contrôle de santé |
| simulateur | Publier mesures, états et statuts dans l'exploitation sélectionnée ; lire ses commandes de vanne |
| api | Publier les commandes de vanne ; lire états et statuts |

La connexion anonyme est désactivée sur MQTT et WebSocket. L'authentification et
les ACL ne chiffrent pas le transport : TLS reste à ajouter pour un déploiement
hors du réseau de développement. L'ESP32 fourni doit encore recevoir un compte
et un broker adaptés ; il n'est pas déclaré opérationnel par cette intégration.

## Tests locaux sans Docker

Depuis la racine, dans un environnement Python activé :

```bash
python -m pip install -r ingestion/requirements.txt
cd ingestion
python -B -m unittest discover -s tests -v
```

La suite couvre la validation, la déclaration, les bornes, le dédoublonnage,
la préparation et l’acquittement. Les accès SQL et le client MQTT y sont simulés.
Les [tests API](../README.md#tests-locaux) se lancent séparément depuis `api/`.

Références utilisées : [Paho Client et manual_ack](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html),
[Mosquitto : password_file et acl_file](https://mosquitto.org/man/mosquitto-conf-5.html),
[mosquitto_passwd](https://mosquitto.org/man/mosquitto_passwd-1.html).
