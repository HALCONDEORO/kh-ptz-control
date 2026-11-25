<p align="center">
  <a href="../../README.md">🇬🇧 English</a> ·
  <a href="README.es.md">🇪🇸 Español</a> ·
  <a href="README.pt.md">🇵🇹 Português</a> ·
  <a href="README.fr.md">🇫🇷 Français</a> ·
  <a href="README.de.md">🇩🇪 Deutsch</a> ·
  <a href="README.it.md">🇮🇹 Italiano</a>
</p>

# KH PTZ Control: riepilogo in italiano

Controllo touch di telecamere PTZ VISCA-over-IP su Raspberry Pi. La mappa numerata dei posti richiama le inquadrature salvate. La schermata utente ha un pulsante compatto per mettere le telecamere in standby e riaccenderle, con conferma (senza togliere l’alimentazione), e Comments → Home salva un’inquadratura propria tenendo premuto il pulsante per cinque secondi.

## Sicurezza: prima STOP

- Prova CALL, SET, STOP e il ripristino su entrambe le telecamere fuori da una riunione.
- STOP ha la priorità nella coda, ma l’arresto fisico dipende dalla telecamera e dalla rete. Conosci l’alternativa fisica se la connessione si perde.
- SET può sovrascrivere posizioni nella memoria della telecamera. Non ripetere un salvataggio fallito e non cancellare dati per tentare una riparazione.
- Non aprire un secondo controller o diagnostica di rete mentre l’interfaccia è in uso. Rimuovi nomi, indirizzi e credenziali prima di condividere i log.

## Requisiti e installazione

Obiettivo di installazione: Pi 4 o 5, Raspberry Pi OS Bookworm a 64 bit con desktop, Python 3.11 di sistema, PyQt5 da `apt`, touchscreen e telecamere compatibili su una rete raggiungibile. Usa una sessione **X11**, non Wayland. Pi 4 con Bullseye/Python 3.9.2 è la base precedente; Trixie non è validato.

1. Scegli una versione o un commit rivisto e approvato e fai un backup prima di modificare un’installazione esistente.
2. Dal desktop, con il tuo utente normale, clona il repository ed esegui `bash install_khptz_rpi.sh --guide`.
3. Esegui il controllo di preparazione con l’utente desktop corretto. Installa solo se passa; se fallisce, fermati e segui l’istruzione mostrata.
4. Segui l’output dell’installer e la procedura guidata iniziale. Verifica fisicamente telecamere, inquadrature e STOP prima dell’uso dal vivo. Non usare una password predefinita. Su Bookworm non aggiungere `--atem` né `--dev` all’installer.

Consulta la [guida all’installazione in inglese](../INSTALL_RPI.md) e il [README in inglese](../../README.md) per ATEM, licenze e limiti.
