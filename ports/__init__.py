#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# ports/ — Application-level hardware boundary interfaces.
#
# Ports define the contracts (Protocols) that adapters must satisfy.
# Application services import from here; they never import concrete adapters,
# VISCA protocol classes, PyQt, or socket modules directly.
