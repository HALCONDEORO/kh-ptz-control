#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/event_builder.py — Convenience factory for BlackBoxEvent instances (#489)
#
# Centralises the timestamp/version/mode boilerplate so service code stays readable.
# No I/O, no Qt, no network dependencies.

from __future__ import annotations

import uuid
from typing import Any

from domain.blackbox_event import (
    BlackBoxEvent,
    EventLevel,
    EventResult,
    EventSource,
    SCHEMA_VERSION,
)
from domain.time_utils import utc_now_iso as _utc_now


def _new_correlation_id() -> str:
    return str(uuid.uuid4())


class EventBuilder:
    """
    Builds BlackBoxEvent instances with service-level context pre-filled.

    Instantiate once per service, passing the runtime context fields that are
    stable across a process lifetime (version, profile, mode, installation_id).
    Call event() for individual events.
    """

    def __init__(
        self,
        app_version: str = "unknown",
        installation_profile: str = "unknown",
        runtime_mode: str = "production",
        installation_id: str = "unknown",
        git_commit: str | None = None,
        session_id: str = "none",
        source: str = EventSource.SYSTEM,
    ) -> None:
        self._app_version          = app_version
        self._installation_profile = installation_profile
        self._runtime_mode         = runtime_mode
        self._installation_id      = installation_id
        self._git_commit           = git_commit
        self._session_id           = session_id
        self._source               = source

    def event(
        self,
        event_type: str,
        level: str = EventLevel.INFO,
        result: str = EventResult.UNKNOWN,
        correlation_id: str | None = None,
        message: str = "",
        **kwargs: Any,
    ) -> BlackBoxEvent:
        return BlackBoxEvent(
            schema_version=SCHEMA_VERSION,
            timestamp=_utc_now(),
            level=level,
            event_type=event_type,
            app_version=self._app_version,
            installation_profile=self._installation_profile,
            runtime_mode=self._runtime_mode,
            installation_id=self._installation_id,
            git_commit=self._git_commit,
            session_id=self._session_id,
            correlation_id=correlation_id or _new_correlation_id(),
            source=self._source,
            result=result,
            message=message,
            **kwargs,
        )
