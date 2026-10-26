# Recette gratuite de FinFlow sur Oracle Cloud

Ce guide décrit un environnement de test éphémère pour FinFlow sur une VM Oracle Cloud Infrastructure (OCI) Always Free. Il utilise Docker Compose et la variante de déploiement par IP du projet.

> **Données de test uniquement.** Ne pas importer de données CBS, clients ou secrets réels. Cette VM n’est pas une cible de production.

## 1. Ressources OCI

Créer les ressources dans la **région d’accueil** du compte OCI. La capacité gratuite Ampere A1 annoncée par OCI correspond actuellement à un maximum cumulé de 2 OCPU et 12 Go de mémoire par mois. Les ressources Always Free comprennent aussi un quota total de 200 Go de volumes de blocs. La disponibilité A1 dépend de la région et peut être temporairement épuisée. Vérifier l’étiquette **Always Free-eligible** avant de créer chaque ressource.

Dans la console OCI :

1. Créer une VM `VM.Standard.A1.Flex`, architecture ARM64, avec Ubuntu Server 24.04 ARM, 2 OCPU et 12 Go de RAM.
2. Garder le volume de démarrage dans le quota Always Free ; 50 Go suffisent pour une petite recette.
3. Placer la VM dans un sous-réseau public avec une passerelle Internet et une adresse IPv4 publique.
4. Ajouter la clé SSH publique de l’administrateur à la VM.
5. Dans la liste de sécurité du sous-réseau ou le pare-feu réseau de la VM, autoriser TCP 22 depuis l’adresse IP de l’administrateur et TCP 80, 443 et 9000 depuis les adresses de test nécessaires. Ne pas ouvrir 5432, 6379 ou 9001.

OCI annonce également 20 Go de stockage objet et 50 000 requêtes API mensuelles dans son offre Always Free. Le déploiement ci-dessous conserve toutefois MinIO dans la stack pour reproduire le Compose actuel ; ce quota objet n’est pas requis.

## 2. Préparer l’accès au dépôt

L’installateur et l’updater exécutent Git en tant que `root`. Pour un dépôt privé, créer sur la VM une clé dédiée **en lecture seule**, puis ajouter sa clé publique aux clés de déploiement du dépôt GitHub. La clé privée reste sur la VM ; ne pas la copier dans `.env` ou dans le dépôt.

```bash
sudo install -d -m 700 /root/.ssh
sudo ssh-keygen -t ed25519 -C finflow-oci-test -f /root/.ssh/finflow-oci -N ""
sudo cat /root/.ssh/finflow-oci.pub
```

Après avoir ajouté la clé publique dans GitHub → dépôt → **Settings → Deploy keys** avec accès en lecture seule, configurer l’alias SSH utilisé par le dépôt :

```bash
sudo tee -a /root/.ssh/config >/dev/null <<'EOF'
Host github-finflow
  HostName github.com
  User git
  IdentityFile /root/.ssh/finflow-oci
  IdentitiesOnly yes
EOF
sudo chmod 600 /root/.ssh/config /root/.ssh/finflow-oci
sudo chmod 644 /root/.ssh/finflow-oci.pub
```

Se connecter à GitHub pour vérifier l’empreinte du serveur lors de la première connexion, puis cloner le dépôt dans `/opt/finflow` :

```bash
sudo git clone git@github-finflow:Bouma-J/FinFlow2.0.git /opt/finflow
```

## 3. Installer FinFlow

Lancer l’installateur interactif IP :

```bash
cd /opt/finflow
sudo env REPO_URL=git@github-finflow:Bouma-J/FinFlow2.0.git bash deploy/ubuntu-install-ip.sh
```

Renseigner l’IPv4 publique OCI, garder des secrets générés distincts et forts, et laisser l’e-mail global non configuré pour cette recette si aucun relais SMTP de test n’est disponible. Pour éviter un avertissement TLS lié au certificat par IP, choisir le mode HTTPS proposé par le script ; le certificat auto-signé exige d’accepter l’avertissement du navigateur.

L’installateur construit la stack ARM64. Les images Python, Node, Nginx, PostgreSQL, Redis et le paquet MinIO utilisés par le projet publient des manifestes `linux/arm64`. Le paquet serveur MinIO de test provient de Chainguard (`cgr.dev/chainguard/minio`) et le client de sauvegarde de `cgr.dev/chainguard/minio-client`, car les images historiques `minio/minio` et `minio/mc` ne sont plus disponibles depuis Docker Hub. Les images Chainguard sont des paquets tiers du serveur MinIO ; cette recette ne valide pas à elle seule un choix de stockage objet de production.

## 4. Accès à la recette

L’installateur affiche l’URL de l’application et l’URL de santé de l’API à la fin. Depuis le navigateur, ouvrir l’URL de l’application et accepter le certificat auto-signé si ce mode a été choisi.

Commandes utiles :

```bash
sudo finflow ps
sudo finflow logs -f backend
sudo finflow-update
```

Les sauvegardes sont chiffrées et stockées sous `/var/backups/finflow`, hors du dépôt. Vérifier le résultat initial avec :

```bash
sudo ls -lh /var/backups/finflow/snapshots
sudo bash /opt/finflow/deploy/ubuntu-update.sh --check /opt/finflow
```

## 5. Nettoyer les ressources de recette

Après les tests, exporter les résultats nécessaires, puis supprimer la VM, son volume de démarrage, les volumes additionnels et les adresses réseau réservées dans la console OCI. Garder une copie chiffrée des seules données de recette qui doivent être conservées.

## Limites connues

- Une instance Always Free reste soumise au quota et à la capacité de la région ; OCI peut refuser temporairement la création d’une VM A1.
- Le premier build ARM64 est plus lent qu’un démarrage avec des images déjà construites.
- Le déploiement par IP n’offre pas un certificat public TLS traditionnel ; le certificat auto-signé est destiné aux tests.
- L’image Chainguard permet de tirer le serveur sur ARM64 et fait l’objet de mises à jour de son paquet. Le stockage MinIO local reste une dépendance à réévaluer avant la production.
- Les limites Always Free et les quotas peuvent changer. Vérifier la page des ressources Always Free dans la console avant de créer la VM.

Références : [ressources Always Free OCI](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm), [images MinIO et MinIO Client Chainguard](https://images.chainguard.dev/directory/image/minio/overview), [image MinIO Client Chainguard](https://images.chainguard.dev/directory/image/minio-client/overview).
