# Appairer un téléphone par QR code

Assistant Botanique 3.3 permet d'associer un téléphone au compagnon web local sans recopier d'adresse ni conserver le jeton global du serveur.

## Procédure

1. Connecter l'ordinateur et le téléphone au même réseau Wi-Fi privé.
2. Ouvrir **Outils > Associer un téléphone par QR code**.
3. Confirmer l'activation du compagnon sur le réseau local.
4. Scanner le QR code affiché avec l'appareil photo du téléphone.
5. Nommer le téléphone puis choisir **Associer et synchroniser**.

Le QR code est à usage unique et expire après cinq minutes. Une fois l'association terminée, le navigateur du téléphone conserve un cookie propre à cet appareil.

## Données synchronisées

Le téléphone travaille directement avec la base SQLite de l'ordinateur :

- consultation de la collection ;
- contrôles et soins prévus aujourd'hui ;
- actions rapides de soin ;
- prise et envoi de photos ;
- consultation des mesures de capteurs exposées par le compagnon.

Les modifications sont donc visibles immédiatement sur l'ordinateur. Il ne s'agit pas d'une copie hors ligne de toute la base sur le téléphone.

## Gérer les appareils

**Outils > Gérer les téléphones associés** affiche :

- le nom de l'appareil ;
- sa date d'association ;
- sa dernière connexion.

La révocation coupe son accès dès la requête suivante. Le téléphone devra scanner un nouveau QR code pour être associé de nouveau.

## Conditions et sécurité

- l'ordinateur doit rester allumé et Assistant Botanique ouvert ;
- le compagnon doit être actif sur le réseau local ;
- le téléphone et l'ordinateur doivent se trouver sur le même réseau ;
- ne pas activer cette fonction sur un Wi-Fi public ;
- aucun mot de passe ni jeton brut de téléphone n'est enregistré dans SQLite : seule son empreinte SHA-256 est conservée ;
- le QR temporaire ne contient pas le jeton global permanent du compagnon ;
- le trafic reste en HTTP local, car le compagnon ne possède pas de certificat HTTPS local.

La fonction ne synchronise pas les données à travers Internet. Pour plusieurs ordinateurs, utiliser les snapshots chiffrés dans un dossier de synchronisation choisi.
