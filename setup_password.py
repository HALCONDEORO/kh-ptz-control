#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# setup_password.py - Wrapper de compatibilidad para fijar la contrasena local.
#
# Comando canonico:
#
#     python3 -m runtime.setup_password
#
# Este wrapper existe para que la forma documentada en guias y mensajes de error
# (`python3 setup_password.py`, ejecutada desde la raiz del repo) siga funcionando.

from __future__ import annotations

from runtime.setup_password import main

if __name__ == "__main__":
    main()
