# SmartRoute - Regles metier des sources de verite

## 1. Person

`Person` est la source officielle de l'identite civile dans SmartRoute :

- NIF ;
- prenom ;
- nom ;
- date de naissance.

Les comptes, conducteurs et proprietaires doivent referencer `Person` au lieu de dupliquer ces informations civiles en base.

## 2. Driver

`Driver` represente le dossier conducteur/permis simplifie lie a `Person`.

Il porte les informations propres au permis ou au dossier conducteur : numero de dossier, adresse permis, sexe, groupe sanguin, type de permis, lieu/date de delivrance et date d'expiration.

`Driver` ne doit pas dupliquer l'identite civile en base. Les donnees civiles exposees par l'API doivent venir de `Driver.person`.

## 3. Owner

`Owner` represente le profil proprietaire lie a `Person`.

Il porte les informations propres au profil proprietaire, comme le telephone, l'adresse de contact, l'etat actif et l'agent createur.

`Owner` ne doit pas dupliquer l'identite civile en base. Les donnees civiles exposees par l'API doivent venir de `Owner.person`.

## 4. VehicleOwnership

`VehicleOwnership` est la source officielle de l'historique de propriete vehicule.

Un seul `VehicleOwnership` courant par vehicule est autorise, via `is_current=True`. Les anciennes proprietes doivent etre conservees avec `is_current=False` et une `end_date` coherente.

Toute creation ou mutation du proprietaire courant doit passer par le service metier centralise d'ownership.

## 5. Vehicle.owner

`Vehicle.owner` est conserve comme cache courant synchronise.

Il existe pour la compatibilite mobile, les payloads historiques, la performance, Gemini/Scan, les alertes et les serializers vehicles.

`Vehicle.owner` ne doit jamais etre modifie directement sans creer ou terminer le `VehicleOwnership` officiel correspondant.

## 6. Snapshots PV

Les snapshots des PV sont des duplications legales volontaires.

Ils figent l'etat au moment de la verbalisation : identite conducteur, numero de dossier, NIF, plaque, libelles et montants d'infractions.

Ils ne doivent pas etre recalcules apres coup depuis les sources courantes.

## 7. Regle stricte

Toute mutation de proprietaire vehicule doit passer par le service centralise d'ownership.

La regle attendue est :

1. terminer l'ancien `VehicleOwnership` courant s'il existe ;
2. creer le nouveau `VehicleOwnership(is_current=True)` ;
3. synchroniser `Vehicle.owner` avec ce proprietaire courant ;
4. conserver les payloads mobiles existants.
