# Comando vs Evento — política de uso de EventBus

## Regla central

```
ApplicationController = comandos (cambian estado)
AsyncEventBus         = eventos  (informan de lo ocurrido)
```

La UI nunca emite eventos directamente para iniciar una acción de producto.
El bus informa de resultados; no ejecuta trabajo por sí mismo.

---

## Patrón correcto

```
UI → ApplicationController.método()
       → policy / service / port
       → bus.emit(EventoOcurrido)

UI / logging / support → subscribe o graba evento
```

`ApplicationController` es el único punto de entrada para acciones
UI-originadas con política (CALL/SET, sesión activa, cámara disponible).

`AsyncEventBus` es para notificaciones, diagnóstico, logging,
FlightRecorder y desacoplamiento de integraciones.

---

## Tabla de flujos por workflow

| Workflow | Comando owner | Eventos emitidos | Va a UI | Va a FlightRecorder |
|---|---|---|---|---|
| Seat recall | `ApplicationController.recall_seat()` | `SEAT_SELECTED` | sí | sí |
| Session start | `ApplicationController.start_session()` | `SESSION_START` | sí | sí |
| Session end | `ApplicationController.end_session()` | `SESSION_END` | sí | sí |
| Joystick move | `JoystickAdapter` → bus.emit | `CAMERA_MOVE` | no | no |
| Joystick stop | `JoystickAdapter` → bus.emit | `CAMERA_STOP` | no | no |
| Camera unavailable | `ViscaCameraAdapter` / `CameraWorker` | `CONNECTION_CHANGED` | sí | sí |
| ATEM status change | `AtemMonitor` | (pendiente) | sí | no |
| Backup start/completed | `BackupService` | (pendiente) | sí | sí |
| Preset save (named) | `Controller._on_preset_save_requested()` | `PRESET_SAVED` | sí | sí |
| Chairman assigned | `Controller._on_chairman_assigned()` | — | no | no |

### Nota sobre joystick

`JoystickAdapter` es un adaptador de entrada de hardware continuo (PTZ
analógico). Emite `CAMERA_MOVE` / `CAMERA_STOP` directamente al bus
porque no hay política CALL/SET aplicable: no hay sesión que validar,
no hay preset que sobreescribir y la cadencia de eventos es demasiado alta
para pasar por `ApplicationController`. Esto es correcto para hardware
continuo; no es un antipatrón.

---

## Antipatrones a evitar

1. **Evento como comando oculto** — un listener que dispara una acción de
   negocio sin que la UI haya llamado a `ApplicationController` primero.
   Ejemplo incorrecto: emitir `SESSION_START` desde un timer interno sin
   pasar por `start_session()`.

2. **Adapter de entrada saltándose ApplicationController para acciones con
   política** — si la acción tiene reglas CALL/SET, sesión activa o
   disponibilidad de cámara, debe pasar por `ApplicationController`.
   El joystick (hardware continuo) es la única excepción documentada.

3. **UI esperando un evento para conocer el resultado de su propia acción**
   — `ApplicationController` devuelve `CommandResult` de forma síncrona.
   La UI lee ese resultado directamente; no necesita suscribirse al bus
   para saber si su acción se aceptó.

4. **Emit de eventos en el hilo de la UI sin pasar por el bus** — toda
   emisión pasa por `AsyncEventBus.emit()`, que encola y despacha en el
   worker thread. Nunca llamar a handlers directamente desde la UI.

---

## Estado de migración

- [x] Seat recall: migrado por `ApplicationController.recall_seat()`
- [x] Session start/end: migrado por `ApplicationController.start_session()` / `end_session()`
- [x] Joystick: `JoystickAdapter` → bus (correcto, excepción documentada)
- [ ] Session home lifecycle completo: pendiente #684
- [ ] Camera failure events: parcialmente en `CONNECTION_CHANGED`
- [ ] ATEM status events: pendiente (AtemMonitor)
- [ ] Backup start/completed events: pendiente (BackupService)

---

## Referencias

- `core/events.py` — `AsyncEventBus` y `EventType` enum
- `application/app_controller.py` — implementación de referencia
- `core/controller.py` — suscriptores del bus (ejecutan acciones tras evento)
- `docs/DECISIONS.md` — regla breve en sección "Architecture decisions"
- Issue #690 — origen de esta política
