
let jeton = null;
let parcelleSelectionnee = null;
let capteursActuels = [];
let generationHistorique = 0;

let controleurFlux = null;
let generationFlux = 0;

function modifierEtatConnexion(etat, message) {
    const voyant = $("voyant-connexion");

    voyant.className = `voyant voyant-${etat}`;
    $("texte-connexion").textContent = message;
}

function arreterFlux() {
    generationFlux++;

    if (controleurFlux) {
        controleurFlux.abort();
        controleurFlux = null;
    }
}

function attendre(ms, signal) {
    return new Promise((resolve, reject) => {
        if (signal.aborted) {
            reject(new DOMException(
                "Annulé", "AbortError"
            ));
            return;
        }

        const minuterie = setTimeout(() => {
            signal.removeEventListener(
                "abort", annuler
            );
            resolve();
        }, ms);

        function annuler() {
            clearTimeout(minuterie);
            reject(new DOMException(
                "Annulé", "AbortError"
            ));
        }

        signal.addEventListener(
            "abort", annuler, { once: true }
        );
    });
}


const $ = (id) => document.getElementById(id);

function afficherMessage(message) {
    $("message").textContent = message;
}

async function lireFluxSSE(reponse, recevoir) {
    if (!reponse.body) {
        throw new Error(
            "Flux HTTP non disponible"
        );
    }

    const lecteur = reponse.body.getReader();
    const decodeur = new TextDecoder();

    let tampon = "";

    try {
        while (true) {
            const { value, done } =
                await lecteur.read();

            if (done) break;

            tampon += decodeur.decode(
                value, { stream: true }
            );

            // Normalisation des fins de ligne SSE.
            tampon = tampon.replace(/\r\n/g, "\n");

            let separation;

            while (
                (separation = tampon.indexOf("\n\n"))
                !== -1
            ) {
                const bloc = tampon.slice(
                    0, separation
                );

                tampon = tampon.slice(
                    separation + 2
                );

                let nom = "message";
                const donnees = [];

                for (const ligne of bloc.split("\n")) {
                    if (ligne.startsWith("event:")) {
                        nom = ligne.slice(6).trim();
                    }

                    if (ligne.startsWith("data:")) {
                        donnees.push(
                            ligne.slice(5).trimStart()
                        );
                    }
                }

                if (donnees.length > 0) {
                    recevoir(
                        nom,
                        JSON.parse(donnees.join("\n"))
                    );
                }
            }
        }
    } finally {
        lecteur.releaseLock();
    }
}


async function demarrerFlux(idParcelle) {
    arreterFlux();

    const controleur = new AbortController();
    controleurFlux = controleur;

    const generation = generationFlux;

    while (!controleur.signal.aborted) {
        try {
            modifierEtatConnexion(
                "attente",
                "Connexion au flux..."
            );

            const reponse = await fetch(
                `/api/v1/parcelles/${idParcelle}/evenements`,
                {
                    headers: {
                        Authorization: `Bearer ${jeton}`,
                        Accept: "text/event-stream"
                    },
                    cache: "no-store",
                    signal: controleur.signal
                }
            );

            if (!reponse.ok) {
                if (
                    reponse.status === 401 ||
                    reponse.status === 403 ||
                    reponse.status === 404
                ) {
                    modifierEtatConnexion(
                        "erreur",
                        "Accès au flux refusé"
                    );

                    if (reponse.status === 401) {
                        deconnecter();
                    }

                    return;
                }

                throw new Error(
                    `Erreur SSE ${reponse.status}`
                );
            }

            modifierEtatConnexion(
                "connecte",
                "Flux temps réel connecté"
            );

            await lireFluxSSE(
                reponse,
                (nom, donnees) => {
                    if (
                        controleur.signal.aborted ||
                        generation !== generationFlux
                    ) {
                        return;
                    }

                    if (nom === "tableau_de_bord") {
                        appliquerTableauDeBord(donnees);
                    }

                    if (nom === "erreur") {
                        throw new Error(
                            donnees.message
                        );
                    }
                }
            );

            if (!controleur.signal.aborted) {
                throw new Error(
                    "Connexion interrompue"
                );
            }

        } catch (erreur) {
            if (controleur.signal.aborted) {
                break;
            }

            modifierEtatConnexion(
                "erreur",
                "Connexion perdue : reconnexion..."
            );

            try {
                await attendre(
                    3000,
                    controleur.signal
                );
            } catch {
                break;
            }
        }
    }
}


let signatureMesures = null;

function appliquerTableauDeBord(donnees) {
    if (
        !parcelleSelectionnee ||
        donnees.parcelle.id !==
            parcelleSelectionnee.id
    ) {
        return;
    }

    const ancienneSelection =
        $("capteur-graphique").value;

    const nouvelleSignature = JSON.stringify(
        donnees.capteurs.map(capteur => ({
            id: capteur.id,
            derniere_mesure:
                capteur.derniere_mesure
        }))
    );

    $("nom-parcelle").textContent =
        donnees.parcelle.nom;

    const resume = donnees.resume_capteurs;

    $("resume").replaceChildren(
        creerCarte(
            "Capteurs enregistrés",
            resume.total
        ),
        creerCarte(
            "Capteurs actifs",
            resume.actifs
        ),
        creerCarte(
            "Données récentes",
            resume.en_ligne
        )
    );

    afficherCapteurs(donnees.capteurs);
    afficherVannes(donnees.vannes);

    const select = $("capteur-graphique");

    if (
        [...select.options].some(
            option =>
                option.value === ancienneSelection
        )
    ) {
        select.value = ancienneSelection;
    }

    $("date-actualisation").textContent =
        "Dernière consultation : " +
        formaterDate(donnees.actualise_le);

    if (
        nouvelleSignature !== signatureMesures
    ) {
        signatureMesures = nouvelleSignature;

        chargerHistorique().catch(
            erreur => afficherMessage(
                erreur.message
            )
        );
    }
}


async function requeteAPI(chemin, options = {}) {
    const headers = {
        ...(options.headers || {})
    };

    if (jeton) {
        headers.Authorization = `Bearer ${jeton}`;
    }

    const reponse = await fetch(chemin, {
        ...options,
        headers
    });

    if (!reponse.ok) {
        if (reponse.status === 401 && jeton) deconnecter();

        const probleme = await reponse.json().catch(() => ({}));
        const erreur = new Error(probleme.detail || `Erreur HTTP ${reponse.status}`);
        erreur.statut = reponse.status;
        throw erreur;
    }

    if (reponse.status === 204) {
        return null;
    }

    return reponse.json();
}

function deconnecter() {
    arreterFlux();
    requeteAssistant?.abort();
    $("form-assistant").reset();
    $("resultat-assistant").textContent = "";
    $("sources-assistant").replaceChildren();
    $("statut-assistant").textContent = "";
    signatureMesures = null;
    jeton = null;
    parcelleSelectionnee = null;
    capteursActuels = [];

    $("dashboard").hidden = true;
    $("connexion").hidden = false;
    $("mot-de-passe").value = "";
}

$("form-connexion").addEventListener(
    "submit",
    async (evenement) => {
        evenement.preventDefault();
        afficherMessage("");

        const courriel = $("courriel").value;
        const motDePasse = $("mot-de-passe").value;

        try {
            const reponse = await requeteAPI(
                "/api/v1/auth/connexion",
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        courriel,
                        mot_de_passe: motDePasse
                    })
                }
            );

            jeton = reponse.access_token;

            $("connexion").hidden = true;
            $("dashboard").hidden = false;
            $("mot-de-passe").value = "";

            await chargerParcelles();

        } catch (erreur) {
            afficherMessage(erreur.message);
        }
    }
);

async function chargerParcelles() {
    const parcelles = await requeteAPI(
        "/api/v1/parcelles?limit=100&offset=0"
    );

    const select = $("parcelle");
    select.replaceChildren();

    for (const parcelle of parcelles) {
        const option = document.createElement("option");
        option.value = parcelle.id;
        option.textContent = parcelle.nom;
        select.appendChild(option);
    }

    if (parcelles.length === 0) {
        afficherMessage(
            "Aucune parcelle disponible pour ce compte."
        );
        return;
    }

    await chargerTableauDeBord();
}

$("parcelle").addEventListener(
    "change",
    chargerTableauDeBord
);

$("actualiser").addEventListener(
    "click",
    chargerTableauDeBord
);

$("deconnexion").addEventListener(
    "click",
    deconnecter
);


function creerCarte(titre, valeur, details = "") {
    const carte = document.createElement("article");
    carte.className = "carte";

    const h3 = document.createElement("h3");
    h3.textContent = titre;

    const p = document.createElement("p");
    p.className = "valeur";
    p.textContent = valeur;

    const secondaire = document.createElement("p");
    secondaire.className = "secondaire";
    secondaire.textContent = details;

    carte.append(h3, p, secondaire);
    return carte;
}

function formaterDate(date) {
    if (!date) return "Date inconnue";

    return new Date(date).toLocaleString("fr-FR");
}


async function chargerTableauDeBord() {
    const id = $("parcelle").value;

    arreterFlux();
    generationHistorique++;
    const chargement = generationFlux;
    $("form-regle").reset();
    $("latitude-exploitation").value = "";
    $("longitude-exploitation").value = "";
    $("statut-regle").textContent = "";
    $("resultat-diagnostic").textContent = "";
    $("image-diagnostic").value = "";
    $("resultat-irrigation").textContent = "";
    signatureMesures = null;
    parcelleSelectionnee = null;

    if (!id) return;

    try {
        afficherMessage("");

        const donnees = await requeteAPI(
            `/api/v1/parcelles/${id}/tableau-de-bord`
        );

        // Ignore une réponse devenue obsolète
        // si l'utilisateur a changé de parcelle.
        if (chargement !== generationFlux || $("parcelle").value !== id) {
            return;
        }

        parcelleSelectionnee = donnees.parcelle;

        appliquerTableauDeBord(donnees);

        demarrerFlux(id);
        chargerRegle(id, generationFlux);

    } catch (erreur) {
        afficherMessage(erreur.message);
    }
}


function afficherCapteurs(capteurs) {
    const conteneur = $("capteurs");
    conteneur.replaceChildren();

    for (const capteur of capteurs) {
        const mesure = capteur.derniere_mesure;

        conteneur.appendChild(
            creerCarte(
                capteur.grandeur,
                mesure
                    ? `${mesure.valeur} ${capteur.unite}`
                    : "Aucune mesure",
                capteur.en_ligne
                    ? "Données récentes"
                    : "Données anciennes ou absentes"
            )
        );
    }

    const select = $("capteur-graphique");
    select.replaceChildren();

    for (const capteur of capteurs) {
        const option = document.createElement("option");
        option.value = capteur.id;
        option.textContent =
            `${capteur.grandeur} (${capteur.unite})`;

        select.appendChild(option);
    }
}

function afficherVannes(vannes) {
    const conteneur = $("vannes");
    conteneur.replaceChildren();

    for (const vanne of vannes) {
        conteneur.appendChild(
            creerCarte(
                `Vanne ${vanne.id}`,
                vanne.etat,
                "Dernière mise à jour : " +
                formaterDate(vanne.maj_le)
            )
        );
    }

    if (vannes.length === 0) {
        conteneur.appendChild(
            creerCarte(
                "Vannes",
                "Aucune vanne",
                "Aucun équipement enregistré"
            )
        );
    }
}


async function chargerHistorique() {
    if (!parcelleSelectionnee) return;
    const generation = ++generationHistorique;
    const idParcelle = parcelleSelectionnee.id;
    const jours = $("periode-graphique").value;

    const agregats = await requeteAPI(
        `/api/v1/parcelles/${parcelleSelectionnee.id}` +
        `/mesures/agregats?intervalle=heure&jours=${jours}`
    );
    if (
        generation !== generationHistorique ||
        !parcelleSelectionnee ||
        parcelleSelectionnee.id !== idParcelle
    ) {
        return;
    }

    const dessiner = () => {
        const idCapteur = Number(
            $("capteur-graphique").value
        );

        const valeurs = agregats
            .filter(m => m.capteur === idCapteur)
            .sort(
                (a, b) =>
                    new Date(a.ts) - new Date(b.ts)
            );

        dessinerGraphique(valeurs);
    };

    $("capteur-graphique").onchange = dessiner;
    dessiner();
}

function dessinerGraphique(mesures) {
    const canvas = $("graphique");
    const largeur = canvas.clientWidth || 700;
    const hauteur = 240;
    const ratio = window.devicePixelRatio || 1;

    canvas.width = largeur * ratio;
    canvas.height = hauteur * ratio;

    const ctx = canvas.getContext("2d");
    ctx.scale(ratio, ratio);

    ctx.clearRect(0, 0, largeur, hauteur);

    if (mesures.length === 0) {
        ctx.fillStyle = "#68786d";
        ctx.font = "15px sans-serif";
        ctx.fillText(
            "Aucune mesure disponible",
            20,
            40
        );
        return;
    }

    const valeurs = mesures.map(m => m.moyenne);

    let minimum = Math.min(...valeurs);
    let maximum = Math.max(...valeurs);

    if (minimum === maximum) {
        minimum -= 1;
        maximum += 1;
    }

    const marge = 35;
    const zoneLargeur = largeur - 2 * marge;
    const zoneHauteur = hauteur - 2 * marge;

    const x = (i) =>
        marge + (
            mesures.length === 1
                ? zoneLargeur / 2
                : i * zoneLargeur / (mesures.length - 1)
        );

    const y = (valeur) =>
        hauteur - marge -
        (valeur - minimum) /
        (maximum - minimum) * zoneHauteur;

    ctx.strokeStyle = "#267348";
    ctx.lineWidth = 2;
    ctx.beginPath();

    valeurs.forEach((valeur, i) => {
        if (i === 0) {
            ctx.moveTo(x(i), y(valeur));
        } else {
            ctx.lineTo(x(i), y(valeur));
        }
    });

    ctx.stroke();

    ctx.fillStyle = "#267348";

    valeurs.forEach((valeur, i) => {
        ctx.beginPath();
        ctx.arc(x(i), y(valeur), 3, 0, 2 * Math.PI);
        ctx.fill();
    });

    ctx.fillStyle = "#68786d";
    ctx.font = "12px sans-serif";

    ctx.fillText(maximum.toFixed(1), 3, marge);
    ctx.fillText(
        minimum.toFixed(1),
        3,
        hauteur - marge
    );

    const debut = formaterDate(mesures[0].ts);
    const fin = formaterDate(
        mesures[mesures.length - 1].ts
    );

    ctx.fillText(debut, marge, hauteur - 8);

    const largeurTexte = ctx.measureText(fin).width;
    ctx.fillText(
        fin,
        Math.max(marge, largeur - largeurTexte - 8),
        hauteur - 8
    );
}


let commandeEnCours = false;

async function envoyerCommandeVanne(action) {
    if (!parcelleSelectionnee || commandeEnCours) {
        return;
    }

    const duree = Number(
        $("duree-arrosage").value
    );

    if (
        action === "ouvrir" &&
        (!Number.isInteger(duree) ||
         duree < 10 ||
         duree > 3600)
    ) {
        afficherMessage(
            "Durée autorisée : 10 à 3600 secondes."
        );
        return;
    }

    const corps = { action };

    if (action === "ouvrir") {
        corps.duree_s = duree;
    }

    commandeEnCours = true;

    $("ouvrir-vanne").disabled = true;
    $("fermer-vanne").disabled = true;

    $("statut-commande").textContent =
        "Envoi de la commande...";

    try {
        const idParcelle = parcelleSelectionnee.id;

        const commande = await requeteAPI(
            `/api/v1/parcelles/${idParcelle}` +
            "/vanne/commandes",
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(corps)
            }
        );

        $("statut-commande").textContent =
            `Commande ${commande.id} : ${commande.statut}`;

        await suivreCommande(
            idParcelle,
            commande.id
        );

    } catch (erreur) {
        $("statut-commande").textContent =
            "Erreur : " + erreur.message;

    } finally {
        commandeEnCours = false;
        $("ouvrir-vanne").disabled = false;
        $("fermer-vanne").disabled = false;
    }
}

async function suivreCommande(idParcelle, commandeId) {
    const debut = Date.now();

    while (Date.now() - debut < 15000) {
        const commande = await requeteAPI(
            `/api/v1/parcelles/${idParcelle}` +
            `/vanne/commandes/${commandeId}`
        );

        if (commande.statut === "confirmee") {
            $("statut-commande").textContent =
                "Commande confirmée par le simulateur.";
            return;
        }

        if (commande.statut === "echec") {
            $("statut-commande").textContent =
                "La commande a échoué.";
            return;
        }

        await new Promise(
            resolve => setTimeout(resolve, 1000)
        );
    }

    $("statut-commande").textContent =
        "Confirmation non reçue. Vérifiez l'état de la vanne avant de réessayer.";
}

$("ouvrir-vanne").addEventListener(
    "click",
    () => envoyerCommandeVanne("ouvrir")
);

$("fermer-vanne").addEventListener(
    "click",
    () => envoyerCommandeVanne("fermer")
);


async function analyserIrrigation() {
    if (!parcelleSelectionnee) {
        afficherMessage(
            "Sélectionnez d'abord une parcelle."
        );
        return;
    }

    const latitudeTexte =
        $("latitude-exploitation").value;

    const longitudeTexte =
        $("longitude-exploitation").value;

    const latitude = Number(latitudeTexte);
    const longitude = Number(longitudeTexte);

    if (
        latitudeTexte.trim() === "" ||
        longitudeTexte.trim() === "" ||
        !Number.isFinite(latitude) ||
        !Number.isFinite(longitude) ||
        latitude < -90 ||
        latitude > 90 ||
        longitude < -180 ||
        longitude > 180
    ) {
        afficherMessage(
            "Saisissez des coordonnées GPS valides."
        );
        return;
    }

    const resultat = $("resultat-irrigation");

    resultat.textContent =
        "Analyse en cours...";

    const idParcelle = parcelleSelectionnee.id;

    try {
        const params = new URLSearchParams({
            latitude: String(latitude),
            longitude: String(longitude),
        });

        const donnees = await requeteAPI(
            `/api/v1/parcelles/${idParcelle}` +
            `/irrigation/recommandation?${params}`
        );

        if (
            !parcelleSelectionnee ||
            parcelleSelectionnee.id !== idParcelle
        ) {
            return;
        }

        const lignes = [
            `Décision : ${donnees.decision}`,
            `Humidité : ${
                donnees.humidite_sol ?? "inconnue"
            } %`,
            `Seuil sec : ${
                donnees.seuil_sec ?? "inconnu"
            } %`,
            `Pluie prévue : ${
                donnees.pluie_prevue_mm ?? "inconnue"
            } mm`,
            `Raison : ${donnees.raison}`,
            "Mode : simulation"
        ];

        resultat.replaceChildren();

        for (const ligne of lignes) {
            const paragraphe =
                document.createElement("p");

            paragraphe.textContent = ligne;
            resultat.appendChild(paragraphe);
        }

        afficherMessage("");

    } catch (erreur) {
        resultat.textContent =
            "Analyse indisponible.";

        afficherMessage(erreur.message);
    }
}

$("analyser-irrigation").addEventListener(
    "click",
    analyserIrrigation
);

$("afficher-inscription").addEventListener("click", () => {
    $("connexion").hidden = true;
    $("inscription").hidden = false;
    afficherMessage("");
});

$("retour-connexion").addEventListener("click", () => {
    $("inscription").hidden = true;
    $("connexion").hidden = false;
    afficherMessage("");
});

$("form-inscription").addEventListener(
    "submit",
    async (evenement) => {
        evenement.preventDefault();
        afficherMessage("");

        const donnees = {
            prenom: $("ins-prenom").value.trim(),
            nom: $("ins-nom").value.trim(),
            courriel: $("ins-courriel").value.trim(),
            mot_de_passe: $("ins-password").value,
            code_exploitation: $("ins-code").value.trim(),
            nom_exploitation: $("ins-exploitation").value.trim(),
            commune: $("ins-commune").value.trim()
        };

        try {
            await requeteAPI("/api/v1/auth/inscription", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(donnees)
            });

            $("form-inscription").reset();
            $("connexion").hidden = false;
            $("inscription").hidden = true;

            $("courriel").value = donnees.courriel;

            afficherMessage(
                "Compte créé avec succès ! Connectez-vous."
            );

        } catch (erreur) {
            afficherMessage(erreur.message);
        }
    }
);

$("periode-graphique").addEventListener("change", () => {
    chargerHistorique().catch(erreur => afficherMessage(erreur.message));
});

async function chargerRegle(id, generation) {
    try {
        const regle = await requeteAPI(`/api/v1/parcelles/${id}/regles/automatique`);
        if (generation !== generationFlux) return;
        $("regle-active").checked = regle.active;
        $("regle-seuil").value = regle.seuil;
        $("regle-duree").value = regle.duree_s;
        $("regle-delai").value = regle.delai_min_s / 60;
        $("latitude-exploitation").value = regle.latitude;
        $("longitude-exploitation").value = regle.longitude;
        $("statut-regle").textContent = regle.active ? "Règle active." : "Règle désactivée.";
    } catch (erreur) {
        if (generation === generationFlux) {
            $("statut-regle").textContent = erreur.statut === 404
                ? "Aucune règle configurée." : erreur.message;
        }
    }
}

$("form-regle").addEventListener("submit", async evenement => {
    evenement.preventDefault();
    const statut = $("statut-regle");
    const id = parcelleSelectionnee?.id;
    if (!id) return;
    const latitude = $("latitude-exploitation");
    const longitude = $("longitude-exploitation");
    if (latitude.value === "" || longitude.value === "" ||
        !latitude.checkValidity() || !longitude.checkValidity()) {
        statut.textContent = "Saisissez des coordonnées valides.";
        return;
    }
    const bouton = evenement.submitter;
    const generation = generationFlux;
    bouton.disabled = true;
    try {
        const regle = await requeteAPI(`/api/v1/parcelles/${id}/regles/automatique`, {
            method: "PUT",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                active: $("regle-active").checked, latitude: latitude.valueAsNumber,
                longitude: longitude.valueAsNumber, seuil: $("regle-seuil").valueAsNumber,
                duree_s: $("regle-duree").valueAsNumber, delai_min_s: $("regle-delai").valueAsNumber * 60
            })
        });
        if (generation === generationFlux) {
            statut.textContent = regle.active ? "Règle activée." : "Règle enregistrée et désactivée.";
        }
    } catch (erreur) {
        if (generation === generationFlux) statut.textContent = erreur.message;
    } finally {
        bouton.disabled = false;
    }
});

$("form-diagnostic").addEventListener("submit", async evenement => {
    evenement.preventDefault();
    const id = parcelleSelectionnee?.id;
    const image = $("image-diagnostic").files[0];
    if (!id || !image) {
        afficherMessage("Sélectionnez une parcelle et une image.");
        return;
    }
    const bouton = evenement.submitter;
    const generation = generationFlux;
    const resultat = $("resultat-diagnostic");
    bouton.disabled = true;
    resultat.textContent = "Analyse en cours…";
    const formulaire = new FormData();
    formulaire.append("image", image);
    try {
        const diagnostic = await requeteAPI(`/api/v1/parcelles/${id}/diagnostics`, {
            method: "POST", body: formulaire
        });
        if (generation === generationFlux) {
            const confiance = new Intl.NumberFormat("fr", {
                style: "percent", maximumFractionDigits: 1
            }).format(diagnostic.score);
            resultat.textContent = `${diagnostic.classe} · confiance ${confiance} · ${diagnostic.modele}`;
        }
    } catch (erreur) {
        if (generation === generationFlux) resultat.textContent = erreur.message;
    } finally {
        bouton.disabled = false;
    }
});

let requeteAssistant = null;

$("form-assistant").addEventListener("submit", async evenement => {
    evenement.preventDefault();
    const bouton = evenement.submitter;
    const resultat = $("resultat-assistant");
    const sources = $("sources-assistant");
    const statut = $("statut-assistant");
    const controleur = new AbortController();
    requeteAssistant = controleur;
    bouton.disabled = true;
    resultat.textContent = "";
    sources.replaceChildren();
    statut.textContent = "Recherche dans les fiches…";
    let termine = false;

    try {
        const reponse = await fetch("/api/v1/assistant/questions", {
            method: "POST", signal: controleur.signal,
            headers: {"Content-Type": "application/json", Authorization: `Bearer ${jeton}`},
            body: JSON.stringify({question: $("question-assistant").value})
        });
        if (reponse.status === 401) deconnecter();
        if (!reponse.ok) {
            const probleme = await reponse.json().catch(() => ({}));
            throw new Error(probleme.detail || `Erreur HTTP ${reponse.status}`);
        }
        await lireFluxSSE(reponse, (nom, donnees) => {
            if (nom === "fragment") resultat.textContent += donnees.texte;
            if (nom === "sources") {
                for (const source of donnees.sources) {
                    const ligne = document.createElement("li");
                    ligne.textContent = `[${source.numero}] ${source.source} — ${source.section}`;
                    sources.append(ligne);
                }
            }
            if (nom === "erreur") throw new Error(donnees.message);
            if (nom === "fin") termine = true;
        });
        if (!termine) throw new Error("Le flux de réponse s’est interrompu.");
        statut.textContent = "";
    } catch (erreur) {
        if (!controleur.signal.aborted) statut.textContent = erreur.message;
    } finally {
        requeteAssistant = null;
        bouton.disabled = false;
    }
});
