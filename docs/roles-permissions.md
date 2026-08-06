# Roles Et Permissions

## Roles Reels

- `AGENT_TERRAIN`: agent mobile terrain, scan, verification, PV, alertes terrain.
- `AGENT_SAISIE`: saisie administrative, donnees de reference vehicules/proprietaires/documents/assurances/conducteurs selon permissions.
- `ADMIN`: administration et rapports globaux selon endpoints.
- `PERSONAL`: compte personnel, refuse par les API professionnelles testees.

## Matrice Synthese

| Module ou action | AGENT_TERRAIN | AGENT_SAISIE | ADMIN | PERSONAL |
|---|---:|---:|---:|---:|
| Connexion mobile | Oui | Non | Non | Non |
| Lire vehicules | Oui | Oui | Oui | Non |
| Creer/modifier vehicule | Non | Oui | Non | Non |
| Lire proprietaires | Oui | Oui | Oui | Non |
| Creer proprietaire | Non | Oui | Non | Non |
| Lire conducteurs | Oui | Oui | Oui | Non |
| Creer/modifier conducteur | Non | Oui | Non | Non |
| Lire documents | Oui | Oui | Oui | Non |
| Creer/modifier document | Non | Oui | Non | Non |
| Lire assurances | Oui | Oui | Oui | Non |
| Creer/modifier assurance | Non | Oui | Non | Non |
| Scan plaque mobile | Oui | Non | Non | Non |
| Catalogue infractions lecture | Oui | Oui | Oui | Non |
| Creation PV | Oui | Non | Non | Non |
| Cloture PV | Non | Non | Oui | Non |
| Alertes terrain | Oui | Non | Non | Non |
| Alertes administratives | Non | Oui | Modification selon regles | Non |
| Rapports globaux | Non | Oui | Oui | Non |
| Synchronisation | Oui selon endpoint | Oui selon endpoint | A confirmer | Non |

## Regles Transversales

Un compte inactif, un profil agent absent ou un profil agent inactif doit etre refuse pour les actions exigeant un role agent. Le mobile applique aussi un controle cote client, mais le backend reste la source d'autorisation.

## Acces Futur Web

Le backoffice web est en cours de developpement. Les endpoints backend pour `ADMIN` et `AGENT_SAISIE` existent deja, mais les ecrans web ne sont pas documentes comme finalises.