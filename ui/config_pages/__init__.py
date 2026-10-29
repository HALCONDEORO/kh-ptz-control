# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# ui/config_pages/ — page/section builders extracted from the ConfigDialog god-object (#894).
#
# Each builder is a plain function taking the ConfigDialog instance as its first
# argument (`dialog`) plus the target layout, so it can use the dialog's shared
# helpers (dialog._btn, dialog._toast, dialog._status_pill, …) without ConfigDialog
# having to own the body. See docs/CONFIG_DIALOG_SPLIT_PLAN.md.
