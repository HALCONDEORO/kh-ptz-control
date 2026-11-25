<p align="center">
  <a href="../../README.md">🇬🇧 English</a> ·
  <a href="README.es.md">🇪🇸 Español</a> ·
  <a href="README.pt.md">🇵🇹 Português</a> ·
  <a href="README.fr.md">🇫🇷 Français</a> ·
  <a href="README.de.md">🇩🇪 Deutsch</a> ·
  <a href="README.it.md">🇮🇹 Italiano</a>
</p>

# KH PTZ Control : résumé en français

Pilotage tactile de caméras PTZ VISCA-over-IP sur Raspberry Pi. Le plan numéroté des places permet de rappeler des cadrages enregistrés. L’écran utilisateur propose un bouton compact pour mettre les caméras en veille et les rallumer, avec confirmation (sans coupure d’alimentation), et Comments → Home enregistre un cadrage propre en maintenant le bouton cinq secondes.

## Sécurité : STOP d’abord

- Répétez CALL, SET, STOP et la reprise sur les deux caméras en dehors d’une réunion.
- STOP est prioritaire dans la file, mais l’arrêt physique dépend de la caméra et du réseau. Connaissez la solution physique si la connexion est perdue.
- SET peut écraser des positions dans la mémoire de la caméra. Ne répétez pas un enregistrement échoué et n’effacez pas de données pour tenter une réparation.
- N’ouvrez pas un second contrôleur ou diagnostic réseau pendant que l’interface est utilisée. Retirez noms, adresses et identifiants avant de partager des journaux.

## Prérequis et installation

Cible d’installation : Pi 4 ou 5, Raspberry Pi OS Bookworm 64 bits avec bureau, Python 3.11 du système, PyQt5 via `apt`, écran tactile et caméras compatibles sur un réseau accessible. Utilisez une session **X11**, pas Wayland. Pi 4 avec Bullseye/Python 3.9.2 est l’ancienne base ; Trixie n’est pas validé.

1. Choisissez une version ou un commit relu et approuvé, et faites une sauvegarde avant de modifier une installation existante.
2. Depuis le bureau, avec votre utilisateur normal, clonez le dépôt et lancez `bash install_khptz_rpi.sh --guide`.
3. Lancez le contrôle de préparation avec le bon utilisateur. N’installez que s’il réussit ; en cas d’échec, arrêtez-vous et suivez l’instruction affichée.
4. Suivez la sortie de l’installeur et l’assistant initial. Validez physiquement caméras, cadrages et STOP avant l’usage en direct. N’utilisez pas de mot de passe par défaut. Sous Bookworm, n’ajoutez ni `--atem` ni `--dev` à l’installeur.

Consultez le [guide d’installation en anglais](../INSTALL_RPI.md) et le [README en anglais](../../README.md) pour ATEM, les licences et les limites.
