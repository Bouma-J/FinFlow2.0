# Gouvernance des paramètres et héritage Groupe / filiales

## Périmètre

Le Centre de configuration administre désormais les socles Groupe et les adaptations filiale avec le même cycle : brouillon, validation, publication, retrait, nouvelle version. La publication exige un acteur habilité distinct du créateur et du dernier rédacteur. Les profils publiés sont immuables par l'API.

Les valeurs existantes des modèles `CreditInstructionPolicy` et `AnalysisThreshold` restent le socle initial compatible avec les dossiers historiques. Leur modification directe est fermée dans les anciennes administrations ; les changements doivent désormais être préparés dans le Centre et publiés. La lecture des administrations historiques peut restituer la politique générique résolue, sans enregistrer ses valeurs dans les modèles de base.

Ce mécanisme gouverne les sections effectivement consommées par le moteur : politique, seuils, exigences d'analyse, éligibilité, scoring et tarification. Il ne déclare pas versionnés les calendriers, circuits, modèles documentaires ou réglages de notification qui disposent d'administrations distinctes.

## Composition réelle

1. Valeurs initiales de la filiale, ou défauts existants si aucun socle n'est enregistré.
2. Profils Groupe publiés applicables à la clientèle et au profil particulier.
3. Profils filiale publiés dans l'ordre de spécificité existant : agence, clientèle, profil particulier, produit.

Le Groupe ne référence jamais le produit ou l'agence d'une filiale. Le produit reste une référence locale ; le Groupe peut définir un socle général ou par clientèle, que les profils produits locaux adaptent lorsque les clés ne sont pas verrouillées. Un barème Groupe avec une devise explicite doit être adapté au périmètre opérationnel couvert : aucun taux de change ou rapprochement de devise n'est inventé.

Un profil Groupe est identifié techniquement par `tenant = NULL`. L'accès est explicitement contrôlé ; cela n'élargit pas le périmètre des dossiers, clients ou autres données métier. Une série Groupe et une série filiale peuvent utiliser le même code sans se remplacer mutuellement.

## Verrous Groupe

Les verrous sont une liste de clés `section.paramètre`, choisies parmi les valeurs explicitement définies dans le profil Groupe. Ils s'appliquent à la clé entière : une grille de scoring, un barème ou une liste d'exigences constitue une seule valeur atomique.

Les profils filiale ne peuvent pas définir de verrous. La publication d'un profil filiale qui tente d'adapter une clé verrouillée dans un périmètre de clientèle compatible est refusée, y compris pour les socles Groupe déjà programmés et connus au moment de publier. Une publication Groupe ultérieure peut aussi neutraliser une adaptation filiale déjà publiée : le moteur conserve alors la valeur Groupe et restitue l'adaptation ignorée dans `ignored_overrides`. L'aperçu rend ce conflit visible. Il appartient au gestionnaire de préparer une nouvelle version locale sans cette adaptation.

Un verrou s'applique uniquement aux contextes correspondant au profil Groupe. Son retrait passe par une nouvelle version Groupe publiée, ou par le retrait explicite du profil. Les profils Groupe plus spécifiques peuvent préciser les valeurs du socle Groupe ; les verrous empêchent les substitutions par les filiales.

Les publications Groupe et filiale utilisent un même verrou transactionnel de gouvernance avant les vérifications de périmètre/version. Les horodatages de brouillons restent contrôlés pour éviter l'écrasement d'une modification concurrente.

## Interface et aperçu

Pour un utilisateur Groupe habilité, l'absence de filiale sélectionnée ouvre le socle Groupe. Avec une filiale sélectionnée, la case « Administrer le socle Groupe » bascule entre les deux administrations. Les permissions de configuration habituelles restent requises.

Les champs et composants existants sont conservés ; aucun style global n'est modifié. Le formulaire Groupe présente les clés explicitement définies et permet de sélectionner leurs verrous.

Avec une filiale sélectionnée dans la barre supérieure, l'aperçu d'un candidat Groupe utilise les valeurs de cette filiale et peut évaluer un dossier accessible. Sans filiale, il compare le socle Groupe aux défauts du moteur, sans données de dossier. Il restitue les origines, versions, clés verrouillées et adaptations ignorées, sans écriture dans les dossiers. Les comptages d'impact respectent également le périmètre agence/propriétaire ; ils sont nuls sans permission de consulter les crédits.

API : même ressource `configuration-profiles`, paramètre `?scope=group` pour administrer le Groupe ; ce périmètre est réservé aux utilisateurs `is_group_level` habilités. Le paramètre n'autorise aucune lecture transversale des crédits. La sélection de filiale reste contrôlée par le contexte de requête existant.

## Dossiers et preuves

Les nouvelles captures conservent les sources Groupe et filiale, les valeurs résolues et l'empreinte du même schéma 3. Les captures déjà conservées en schémas 1, 2 ou 3 gardent leurs valeurs et leur empreinte. Aucun recalcul rétrospectif n'est imposé par l'introduction de l'héritage.

Les trois clés d'organisation continuent de suivre la configuration courante : exécutant de la transmission CBS, séparation autorisateur/exécutant et séparation demandeur/exécutant. Cette règle s'applique aussi aux dossiers historiques sans capture.

Les contrôles obligatoires de l'administrateur crédit et la confirmation positive CBS restent protégés. Ce lot n'ajoute ni interface CBS, ni règle réglementaire, ni valeur fiscale.

## Vérifications

`tests/test_delivery_inheritance.py` couvre l'héritage, les verrous conditionnels, la neutralisation d'adaptations locales, le candidat Groupe sans effacement de série locale homonyme, l'isolation API, les références locales interdites au Groupe, les quatre yeux, les clés de verrou invalides, les révisions, l'aperçu sur filiale et la conservation des captures avec organisation courante.

La recette automatisée utilise SQLite en mémoire et ne constitue pas une homologation bancaire ni un test de concurrence PostgreSQL. La migration `configuration.0003` doit être appliquée à l'environnement cible avant son redémarrage.
