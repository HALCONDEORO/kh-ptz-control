<p align="center">
  <a href="../../README.md">🇬🇧 English</a> ·
  <a href="README.es.md">🇪🇸 Español</a> ·
  <a href="README.pt.md">🇵🇹 Português</a> ·
  <a href="README.fr.md">🇫🇷 Français</a> ·
  <a href="README.de.md">🇩🇪 Deutsch</a> ·
  <a href="README.it.md">🇮🇹 Italiano</a>
</p>

# KH PTZ Control: Zusammenfassung auf Deutsch

Touch-Steuerung für VISCA-over-IP-PTZ-Kameras auf einem Raspberry Pi. Der nummerierte Sitzplan ruft gespeicherte Bildausschnitte ab. Der Benutzerbildschirm hat eine kompakte Taste, um die Kameras in den Standby zu schalten und wieder einzuschalten, jeweils mit Bestätigung (keine Stromtrennung). Comments → Home speichert einen eigenen Ausschnitt, wenn die Taste fünf Sekunden gehalten wird.

## Sicherheit: zuerst STOP

- Üben Sie CALL, SET, STOP und Wiederherstellung mit beiden Kameras außerhalb einer Versammlung.
- STOP hat Vorrang in der Warteschlange, aber der physische Stopp hängt von Kamera und Netzwerk ab. Kennen Sie die physische Alternative, falls die Verbindung abbricht.
- SET kann Positionen im Kameraspeicher überschreiben. Wiederholen Sie ein fehlgeschlagenes Speichern nicht und löschen Sie keine Daten als Reparaturversuch.
- Öffnen Sie keinen zweiten Controller oder Netzwerkdiagnose neben der laufenden Oberfläche. Entfernen Sie Namen, Adressen und Zugangsdaten, bevor Sie Logs teilen.

## Voraussetzungen und Installation

Installationsziel: Pi 4 oder 5, Raspberry Pi OS Bookworm 64 Bit mit Desktop, System-Python 3.11, PyQt5 über `apt`, Touchscreen und kompatible Kameras in einem erreichbaren Netzwerk. Verwenden Sie eine **X11**-Sitzung, nicht Wayland. Pi 4 mit Bullseye/Python 3.9.2 ist die ältere Basis; Trixie ist nicht validiert.

1. Wählen Sie eine geprüfte, freigegebene Version oder einen Commit und sichern Sie vor Änderungen an einer bestehenden Installation.
2. Klonen Sie auf dem Desktop mit Ihrem normalen Benutzer das Repository und führen Sie `bash install_khptz_rpi.sh --guide` aus.
3. Führen Sie die Bereitschaftsprüfung mit dem richtigen Desktop-Benutzer aus. Installieren Sie nur, wenn sie besteht; bei einem Fehler anhalten und der Anweisung folgen.
4. Folgen Sie der Ausgabe des Installers und dem Einrichtungsassistenten. Prüfen Sie Kameras, Ausschnitte und STOP physisch, bevor Sie live arbeiten. Verwenden Sie kein Standardpasswort. Unter Bookworm fügen Sie dem Installer weder `--atem` noch `--dev` hinzu.

Siehe die [Installationsanleitung (Englisch)](../INSTALL_RPI.md) und die [englische README](../../README.md) für ATEM, Lizenzen und Grenzen.
