# Formulaires, KYC et référentiels clients configurables

## Configuration publiée

Le Centre de configuration dispose de trois rubriques supplémentaires, composées avec les profils Groupe et filiale :

| Rubrique | Valeurs atomiques héritées | Consommateurs |
|---|---|---|
| `forms` | Listes de champs client, champs d'analyse, organisation des sections | Formulaires client et analyse, sérialiseurs, contrôle de soumission |
| `kyc` | Informations requises, pièces requises, contrôle d'expiration, validité de la revue | Validation KYC, import client CBS, préparation/soumission et contrôles de mise en place |
| `references` | Civilités, situations matrimoniales, types de pièces, formes juridiques | Saisie client, validation serveur, correspondances confirmées disponibles à l'import CBS |

Chaque liste explicitement définie remplace la liste héritée. Les boutons « Hériter » suppriment l'adaptation ; une liste de champs vide signifie qu'aucun champ additionnel n'est requis. Les verrous Groupe s'appliquent aux clés entières de ces rubriques. Les publications utilisent les mêmes permissions, versions et séparation entre rédacteur et publieur.

Les valeurs par défaut ne créent aucune obligation réglementaire nouvelle : aucune information ou pièce additionnelle, aucune durée de revue, aucun contrôle d'expiration additionnel ne sont activés par défaut. Les contrôles obligatoires déjà présents dans le parcours continuent de s'appliquer. Ces réglages internes doivent être validés par l'établissement.

## Champs additionnels

Les types autorisés sont texte, nombre, oui/non, date et choix. Une définition contient un identifiant stable, un libellé, le type, son caractère requis et les choix éventuels. Aucun script, formule ou expression exécutable n'est accepté.

Limites serveur : 50 définitions par formulaire, 100 choix par champ, identifiant de 40 caractères en minuscules/chiffres/soulignement, libellé de 150 caractères, texte saisi de 4000 caractères. Les nombres doivent être finis, avoir au plus six décimales et une valeur absolue inférieure à 10^18 ; ils sont conservés sous forme décimale textuelle pour éviter les pertes de précision. Les dates suivent strictement le format ISO `AAAA-MM-JJ`.

Les valeurs sont persistées dans `Client.custom_fields` et `FinancialAnalysis.custom_fields`. La saisie conserve les valeurs anciennes lorsque leur définition disparaît ; un utilisateur ne peut pas injecter un identifiant inconnu ni modifier une valeur retirée du schéma courant. Un changement de type ou de choix n'effectue pas de conversion implicite des données existantes : leur adaptation exige une décision de migration des données ou une correction explicite selon le nouveau schéma.

La validation du type intervient à l'enregistrement. Le caractère requis est contrôlé à la validation KYC pour les champs client, à la soumission pour les champs d'analyse, ainsi que dans les contrôles KYC du dossier. Un brouillon peut rester incomplet. Un booléen faux et un nombre zéro sont des valeurs renseignées ; une chaîne vide ou contenant seulement des espaces est manquante.

L'interface conserve les composants et styles existants et présente des contrôles typés. Elle ne propose aucun éditeur JSON brut.

## Organisation de l'analyse

La liste des sections permet de changer leur ordre. L'ordre de navigation et celui des éléments du formulaire sont réellement réorganisés ; le parcours clavier suit les éléments présentés.

Les paramètres, la conclusion et les sections financières ne peuvent pas être masqués. Seules les sections informatives sectorielle et environnementale/sociale peuvent l'être. Si une exigence d'analyse nécessite un champ de l'une de ces sections, le moteur la rend visible et la restitue dans `protected_analysis_sections`, même lorsqu'un profil demande son masquage.

La visibilité ne supprime aucune donnée. Les états déjà renseignés restent dans le formulaire et sont transmis lors de l'enregistrement ; les validations serveur et les contrôles de soumission continuent de traiter ces données.

## Contextes KYC

La fiche client générique utilise sa filiale, son agence et son type de clientèle, sans produit. Le dossier utilise sa configuration résolue ou sa capture conservée, comprenant son produit et son profil particulier. Une exigence de produit ne devient donc pas une obligation générale sur tous les clients.

Pour saisir une information additionnelle propre à un dossier, le formulaire d'un client existant propose les dossiers accessibles de ce client. Ce choix charge les règles conservées du dossier et envoie `configuration_application` lors de la modification. Le serveur vérifie le droit de consulter les crédits, le client du dossier, la filiale et le périmètre agence/propriétaire. Ce paramètre n'est pas une donnée persistée et ne permet pas d'adopter les règles d'un autre client.

L'API `GET /clients/form-configuration/` fournit le contexte sans produit. Les paramètres `application` et `client` permettent de demander le contexte d'un dossier accessible. Le moteur des formulaires client ne dépend pas de la disponibilité d'un calendrier du simulateur.

Le passage ou renouvellement explicite à `VALIDATED` vérifie les exigences applicables ; sa date de revue provient du serveur. La date ne peut pas être antidatée ou repoussée par le client API. Une fiche déjà validée qui devient incomplète ne peut pas conserver silencieusement sa validation pendant une modification : elle doit être complétée ou replacée en attente.

Le contrôle d'expiration utilise la pièce du client pour une personne physique, celle du gérant pour une personne morale ou un groupement. Lorsqu'il est activé, la date doit être présente et non échue. Une durée de revue positive impose une date de validation encore valable ; zéro désactive cette limite additionnelle.

L'import CBS ne transforme pas un retour CBS favorable en KYC local complet lorsque les exigences internes manquent. Le client est importé en attente de revue et l'alerte KYC est maintenue. Les données CBS sources restent conservées.

Le helper `kyc_evidence` conserve les champs requis, les noms des pièces requises, les dates utiles, le statut/date de revue et les données additionnelles. La gouvernance du dossier les intègre à ses preuves pour rendre nécessaire une nouvelle revue après modification. Il ne constitue pas une signature électronique d'un fichier ni un moteur de certification de son authenticité.

## Référentiels extensibles

Les codes sont bornés aux tailles des champs natifs et ne sont jamais remplacés par les libellés. Les valeurs désactivées ne sont plus proposées à une nouvelle affectation ; une valeur déjà présente sur un client reste visible et peut être conservée pendant une modification. La désactivation est préférable à une suppression ou à une réutilisation de code.

Les référentiels sont administrés sous forme de tableaux typés dans le Centre, avec un code stable, un libellé, un état actif et un code CBS facultatif. Les codes et correspondances CBS répétés dans un même référentiel sont refusés. Aucune correspondance CBS n'est préremplie ou déduite arbitrairement.

Les correspondances explicites de civilité et situation matrimoniale sont consommées par l'import CBS, dont ces champs sont déjà connus. Les autres correspondances restent conservées comme référentiel confirmé : leur transmission automatique nécessitera un contrat d'API CBS qui expose réellement ces données. Ce lot n'invente pas ces champs externes.

## Compatibilité et vérifications

Les anciennes captures sans ces rubriques reçoivent des valeurs de lecture neutres, sans changement de leur empreinte. Une publication nouvelle n'injecte pas ses exigences dans les dossiers déjà soumis. Les nouvelles soumissions conservent les listes et paramètres applicables dans leur capture.

Migrations : `clients.0012_client_custom_fields` et le champ `FinancialAnalysis.custom_fields` dans `credits.0036`. Elles doivent être appliquées avant le redémarrage du serveur cible.

`test_delivery_forms.py` couvre types, bornes, données inconnues, conservation historique, multipart, KYC natif/pièces/date, revue datée côté serveur, contexte produit conservé, isolation des dossiers, référentiels actifs/inactifs, correspondances, protection des sections requises et capture ancienne. La recette utilise SQLite en mémoire et des appels CBS simulés pour les tests d'import existants ; elle ne constitue pas une homologation réglementaire ou une recette d'intégration bancaire réelle.
