# SmartRoute - Regles Metier Des Sources De Verite

## Person

`Person` est l'identite civile centrale. Le NIF valide contient exactement 10 chiffres en entree ou une valeur normalisable vers `XXX-XXX-XXX-X`. Le NIF peut etre nul selon le contexte, mais une valeur fournie doit respecter la normalisation.

## AgentProfile

Le badge agent contient exactement 11 chiffres en entree ou une valeur normalisable vers `XX-XX-XX-XXXXX`. Les roles reels sont `ADMIN`, `AGENT_SAISIE`, `AGENT_TERRAIN`.

## Driver

Le numero de dossier permis respecte le format `XX-YYYYY-XX`. Les dates d'expiration ne doivent pas preceder les dates d'emission. La recherche peut se faire par dossier ou par NIF de la personne.

## Owner Et VehicleOwnership

`Owner` represente le proprietaire administratif. `VehicleOwnership` conserve l'historique de possession et synchronise le proprietaire courant du vehicule quand une possession devient courante.

## Vehicle

La plaque et le numero moteur sont normalises a l'enregistrement. `Vehicle.owner` represente le proprietaire courant pour les lectures rapides; l'historique reste dans `VehicleOwnership`.

## Documents Et Assurance

Les documents vehicule et polices d'assurance conservent les metadonnees en base. Les fichiers sont stockes via le systeme de medias, avec validation MIME/extension/taille.

## Infractions

Le catalogue officiel est fourni par le backend. Les codes metier stables (`I001`, etc.) sont utilises dans les payloads. Les IDs SQL restent internes.

## Tickets Et Snapshots

Un PV conserve des snapshots: dossier conducteur, nom conducteur, NIF, plaque, infractions et montants. Ces snapshots preservent l'etat au moment de la verbalisation.

## Alertes

Les alertes peuvent etre terrain ou administratives selon role. Les alertes automatiques doivent rester non modifiables manuellement selon les tests existants.

## Delits

Les dossiers delits peuvent provenir d'une observation, d'un ticket, d'une verbalisation, d'une alerte, d'un scan, d'une recherche conducteur ou d'un controle vehicule. L'envoi DCPJ present est un flux demo.

## Regle Stricte

Une fixture ou donnee valide ne doit pas utiliser d'ancien identifiant lisible dans un champ strict (`nif`, `badge_number`, `dossier_number`). Les tests negatifs peuvent conserver des valeurs invalides quand ils verifient un rejet.