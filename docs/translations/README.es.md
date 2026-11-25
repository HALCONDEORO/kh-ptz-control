<p align="center">
  <a href="../../README.md">🇬🇧 English</a> ·
  <a href="README.es.md">🇪🇸 Español</a> ·
  <a href="README.pt.md">🇵🇹 Português</a> ·
  <a href="README.fr.md">🇫🇷 Français</a> ·
  <a href="README.de.md">🇩🇪 Deutsch</a> ·
  <a href="README.it.md">🇮🇹 Italiano</a>
</p>

# KH PTZ Control: resumen en español

Control táctil de cámaras PTZ VISCA-over-IP en Raspberry Pi. El plano numerado de asientos permite recuperar encuadres guardados. La pantalla de usuario añade un botón compacto para poner las cámaras en standby y encenderlas con confirmación (sin corte eléctrico), y Comments → Home guarda un encuadre propio manteniendo el botón cinco segundos.

## Seguridad: STOP primero

- Ensaya CALL, SET, STOP y recuperación en ambas cámaras fuera de una reunión.
- STOP tiene prioridad en la cola, pero la parada física depende de la cámara y de la red. Conoce la alternativa física si se pierde la conexión.
- SET puede sobrescribir posiciones de la memoria de la cámara. No repitas un guardado fallido ni borres datos como intento de reparación.
- No abras un segundo controlador o diagnóstico de red junto a la GUI en uso. Revisa y elimina nombres, direcciones y credenciales antes de compartir logs.

## Requisitos e instalación

Objetivo de instalación: Pi 4 o 5, Raspberry Pi OS Bookworm de 64 bits con Escritorio, Python 3.11 del sistema, PyQt5 de `apt`, pantalla táctil y cámaras compatibles en una red accesible. Usa una sesión **X11**, no Wayland. Pi 4 con Bullseye/Python 3.9.2 es la base heredada; Trixie no está validado.

1. Elige una versión o commit revisado y aprobado, y guarda una copia de seguridad antes de modificar una instalación existente.
2. Desde el escritorio, con tu usuario normal, clona el repositorio y ejecuta `bash install_khptz_rpi.sh --guide`.
3. Ejecuta la comprobación de preparación con el usuario de escritorio correcto. Instala solo si pasa; si aparece un fallo, para y sigue la instrucción indicada.
4. Sigue la salida del instalador y el asistente inicial. Valida cámaras, encuadres y STOP físicamente antes de usar el sistema en directo. No uses una contraseña predeterminada. En Bookworm no añadas `--atem` ni `--dev` al instalador.

Consulta la [guía de instalación en español](../INSTALL_RPI_ES.md) y la [lista breve de instalación y entrega](../INSTALL_TODAY_ES.md). Para ATEM, revisa también las licencias y los límites descritos en el [README en inglés](../../README.md).
