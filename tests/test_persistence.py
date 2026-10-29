#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_persistence.py — Tests unitarios para la capa de persistencia de datos.

Cobertura:
  - chairman_presets : save / load / .bak / next_available / get_preset_for_name
  - config           : save_names_data / load_names_data / .bak
  - schedule_config  : save_schedule / load_schedule / .bak
  - data_paths       : migrate_legacy_files / export_backup / import_backup

Los tests usan monkeypatch de pytest para apuntar las rutas de archivos a
tmp_path, de forma que nunca tocan ~/.config/hallptz/ del sistema.
"""

import json
import zipfile

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
#  Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def preset_file(tmp_path, monkeypatch):
    """Apunta CHAIRMAN_PRESETS_FILE al directorio temporal."""
    import application.chairman_presets as cp
    f = tmp_path / 'chairman_presets.json'
    monkeypatch.setattr(cp, 'CHAIRMAN_PRESETS_FILE', f)
    return f


@pytest.fixture()
def names_file(tmp_path, monkeypatch):
    """Apunta NAMES_FILE al directorio temporal."""
    import config as cfg
    f = tmp_path / 'seat_names.json'
    monkeypatch.setattr(cfg, 'NAMES_FILE', f)
    return f


@pytest.fixture()
def schedule_file(tmp_path, monkeypatch):
    """Apunta SCHEDULE_FILE al directorio temporal."""
    import application.schedule_config as sc
    f = tmp_path / 'schedule.json'
    monkeypatch.setattr(sc, 'SCHEDULE_FILE', f)
    return f


# ═══════════════════════════════════════════════════════════════════════════════
#  chairman_presets
# ═══════════════════════════════════════════════════════════════════════════════

class TestChairmanPresets:

    def test_roundtrip(self, preset_file):
        from application.chairman_presets import save_chairman_presets, load_chairman_presets
        data = {'PersonA': 10, 'PersonB': 11, 'PersonC': 12}
        save_chairman_presets(data)
        assert load_chairman_presets() == data

    def test_load_missing_file_returns_empty(self, preset_file):
        from application.chairman_presets import load_chairman_presets
        assert load_chairman_presets() == {}

    def test_load_corrupted_json_returns_empty(self, preset_file):
        from application.chairman_presets import load_chairman_presets
        preset_file.write_text("NOT JSON", encoding='utf-8')
        assert load_chairman_presets() == {}

    def test_load_filters_out_of_range_presets(self, preset_file):
        from application.chairman_presets import load_chairman_presets
        # Escribir directamente JSON con valores fuera de rango
        preset_file.write_text(
            json.dumps({'PersonA': 10, 'PersonB': 5, 'PersonC': 90}),
            encoding='utf-8'
        )
        result = load_chairman_presets()
        assert 'PersonA' in result      # 10 — OK
        assert 'PersonB' not in result    # 5 — por debajo de CHAIRMAN_PRESET_START (10)
        assert 'PersonC' not in result  # 90 — por encima de CHAIRMAN_PRESET_MAX (89)

    def test_second_save_creates_bak(self, preset_file):
        from application.chairman_presets import save_chairman_presets, load_chairman_presets
        assert save_chairman_presets({'PersonA': 10}) is True
        assert save_chairman_presets({'PersonA': 10, 'PersonB': 11}) is True

        assert load_chairman_presets() == {'PersonA': 10, 'PersonB': 11}
        bak = preset_file.with_suffix('.bak')
        assert bak.exists()
        assert json.loads(bak.read_text()) == {'PersonA': 10}
        assert list(preset_file.parent.glob('.tmp_*.json')) == []

    def test_no_bak_on_first_save(self, preset_file):
        from application.chairman_presets import save_chairman_presets
        save_chairman_presets({'PersonA': 10})
        assert not preset_file.with_suffix('.bak').exists()

    def test_tmp_cleaned_up_on_success(self, preset_file):
        from application.chairman_presets import save_chairman_presets
        save_chairman_presets({'PersonA': 10})
        assert not preset_file.with_suffix('.tmp').exists()

    def test_next_available_preset_starts_at_10(self, preset_file):
        from application.chairman_presets import next_available_preset
        assert next_available_preset({}) == 10

    def test_next_available_preset_skips_used(self, preset_file):
        from application.chairman_presets import next_available_preset
        used = {f'Person{i}': i for i in range(10, 15)}  # nombres reales como claves
        assert next_available_preset(used) == 15

    def test_next_available_preset_returns_none_when_full(self, preset_file):
        from application.chairman_presets import next_available_preset, CHAIRMAN_PRESET_START, CHAIRMAN_PRESET_MAX
        full = {str(i): i for i in range(CHAIRMAN_PRESET_START, CHAIRMAN_PRESET_MAX + 1)}
        assert next_available_preset(full) is None

    def test_get_preset_for_name_known(self, preset_file):
        from application.chairman_presets import get_preset_for_name
        presets = {'PersonA': 10}
        assert get_preset_for_name(presets, 'PersonA') == 10

    def test_get_preset_for_name_fallback(self, preset_file):
        from application.chairman_presets import get_preset_for_name, CHAIRMAN_GENERIC_PRESET
        assert get_preset_for_name({}, 'Unknown') == CHAIRMAN_GENERIC_PRESET


# ═══════════════════════════════════════════════════════════════════════════════
#  config — save_names_data / load_names_data
# ═══════════════════════════════════════════════════════════════════════════════

class TestNamesData:

    def test_roundtrip(self, names_file):
        from config import save_names_data, load_names_data
        names = ['PersonA', 'PersonB']
        seats = {'4': 'PersonA', '5': 'PersonB'}
        assert save_names_data(names, seats) is True
        result = load_names_data()
        assert result['names'] == names
        assert result['seats'] == seats

    def test_load_missing_file_returns_empty(self, names_file):
        from config import load_names_data
        result = load_names_data()
        assert result == {'names': [], 'seats': {}}

    def test_load_corrupted_returns_empty(self, names_file):
        from config import load_names_data
        names_file.write_text("{bad json", encoding='utf-8')
        assert load_names_data() == {'names': [], 'seats': {}}

    def test_save_rejects_wrong_types(self, names_file):
        from config import save_names_data
        assert save_names_data("not a list", {}) is False
        assert save_names_data([], "not a dict") is False

    def test_bak_created_on_second_save(self, names_file):
        from config import save_names_data
        save_names_data(['PersonA'], {'4': 'PersonA'})
        save_names_data(['PersonA', 'PersonB'], {'4': 'PersonA', '5': 'PersonB'})
        bak = names_file.with_suffix('.bak')
        assert bak.exists()
        bak_data = json.loads(bak.read_text())
        assert bak_data['names'] == ['PersonA']

    def test_no_bak_on_first_save(self, names_file):
        from config import save_names_data
        save_names_data(['PersonA'], {})
        assert not names_file.with_suffix('.bak').exists()

    def test_tmp_cleaned_up_on_success(self, names_file):
        from config import save_names_data
        save_names_data(['PersonA'], {})
        assert not names_file.with_suffix('.tmp').exists()


# ═══════════════════════════════════════════════════════════════════════════════
#  schedule_config
# ═══════════════════════════════════════════════════════════════════════════════

class TestScheduleConfig:

    def _sample(self):
        return {
            'monday': {'enabled': True, 'start': '09:00', 'end': '17:00'},
            'tuesday': {'enabled': False, 'start': '09:00', 'end': '17:00'},
        }

    def test_roundtrip(self, schedule_file):
        from application.schedule_config import save_schedule, load_schedule
        assert save_schedule(self._sample()) is True
        result = load_schedule()
        assert result['monday']['enabled'] is True
        assert result['monday']['start'] == '09:00'

    def test_load_missing_returns_defaults(self, schedule_file):
        from application.schedule_config import load_schedule, DEFAULT_SCHEDULE, DAYS
        result = load_schedule()
        for day in DAYS:
            assert day in result
            assert result[day]['enabled'] == DEFAULT_SCHEDULE[day]['enabled']

    def test_load_partial_json_fills_defaults(self, schedule_file):
        from application.schedule_config import save_schedule, load_schedule
        save_schedule({'monday': {'enabled': True, 'start': '08:00', 'end': '16:00'}})
        result = load_schedule()
        assert result['monday']['enabled'] is True
        assert result['tuesday']['enabled'] is False  # default

    def test_second_save_creates_bak(self, schedule_file):
        from application.schedule_config import save_schedule, load_schedule
        assert save_schedule(self._sample()) is True
        updated = {**self._sample(), 'wednesday': {'enabled': True, 'start': '10:00', 'end': '18:00'}}
        assert save_schedule(updated) is True

        result = load_schedule()
        assert result['wednesday']['enabled'] is True
        bak = schedule_file.with_suffix('.bak')
        assert bak.exists()
        assert list(schedule_file.parent.glob('.tmp_*.json')) == []

    def test_no_bak_on_first_save(self, schedule_file):
        from application.schedule_config import save_schedule
        save_schedule(self._sample())
        assert not schedule_file.with_suffix('.bak').exists()


# ═══════════════════════════════════════════════════════════════════════════════
#  data_paths — migrate_legacy_files / export_backup / import_backup
# ═══════════════════════════════════════════════════════════════════════════════

class TestDataPaths:

    @pytest.fixture()
    def isolated(self, tmp_path, monkeypatch):
        """Aísla CONFIG_DIR y todas las rutas derivadas en tmp_path."""
        import data_paths
        config_dir = tmp_path / 'config'
        config_dir.mkdir()
        monkeypatch.setattr(data_paths, 'CONFIG_DIR', config_dir)
        monkeypatch.setattr(data_paths, 'CHAIRMAN_PRESETS_FILE', config_dir / 'chairman_presets.json')
        monkeypatch.setattr(data_paths, 'SEAT_NAMES_FILE',       config_dir / 'seat_names.json')
        monkeypatch.setattr(data_paths, 'SCHEDULE_FILE',         config_dir / 'schedule.json')
        monkeypatch.setattr(data_paths, '_DATA_FILES', (
            config_dir / 'chairman_presets.json',
            config_dir / 'seat_names.json',
            config_dir / 'schedule.json',
        ))
        return config_dir

    def test_migrate_copies_existing_files(self, tmp_path, isolated):
        import data_paths
        app_dir = tmp_path / 'app'
        app_dir.mkdir()
        (app_dir / 'chairman_presets.json').write_text('{"PersonA": 10}', encoding='utf-8')
        (app_dir / 'seat_names.json').write_text('{"names":[], "seats":{}}', encoding='utf-8')
        # schedule.json no existe en app_dir

        data_paths.migrate_legacy_files(app_dir=app_dir)

        assert (isolated / 'chairman_presets.json').exists()
        assert (isolated / 'seat_names.json').exists()
        assert not (isolated / 'schedule.json').exists()

    def test_migrate_does_not_overwrite_existing(self, tmp_path, isolated):
        import data_paths
        app_dir = tmp_path / 'app'
        app_dir.mkdir()
        legacy = app_dir / 'chairman_presets.json'
        legacy.write_text('{"legacy": 99}', encoding='utf-8')

        existing_dst = isolated / 'chairman_presets.json'
        existing_dst.write_text('{"current": 10}', encoding='utf-8')

        data_paths.migrate_legacy_files(app_dir=app_dir)

        assert json.loads(existing_dst.read_text()) == {'current': 10}
        assert json.loads(legacy.read_text()) == {}
    def test_export_creates_zip_with_existing_files(self, tmp_path, isolated, monkeypatch):
        import data_paths
        (isolated / 'chairman_presets.json').write_text('{"PersonA": 10}', encoding='utf-8')
        (isolated / 'seat_names.json').write_text('{"names": [], "seats": {}}', encoding='utf-8')
        # schedule.json no existe — no se incluye

        zip_path = tmp_path / 'backup.zip'
        included = data_paths.export_backup(zip_path)

        assert zip_path.exists()
        assert 'chairman_presets.json' in included
        assert 'seat_names.json' in included
        assert 'schedule.json' not in included

        with zipfile.ZipFile(zip_path) as zf:
            names_in_zip = zf.namelist()
        assert 'chairman_presets.json' in names_in_zip
        assert 'seat_names.json' in names_in_zip

    def test_export_empty_when_no_files(self, tmp_path, isolated, monkeypatch):
        import data_paths
        zip_path = tmp_path / 'empty.zip'
        empty_app = tmp_path / 'empty_app'
        empty_app.mkdir()
        included = data_paths.export_backup(zip_path, app_dir=empty_app)
        assert included == []

    def test_import_restores_files(self, tmp_path, isolated, monkeypatch):
        import data_paths
        # Crear un ZIP con datos
        zip_path = tmp_path / 'backup.zip'
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('chairman_presets.json', '{"PersonA": 10}')
            zf.writestr('seat_names.json', '{"names": ["PersonA"], "seats": {"4": "PersonA"}}')

        restored = data_paths.import_backup(zip_path)

        assert 'chairman_presets.json' in restored
        assert 'seat_names.json' in restored
        assert json.loads((isolated / 'chairman_presets.json').read_text()) == {'PersonA': 10}

    def test_import_creates_bak_for_existing_files(self, tmp_path, isolated, monkeypatch):
        import data_paths
        existing = isolated / 'chairman_presets.json'
        existing.write_text('{"original": 10}', encoding='utf-8')

        zip_path = tmp_path / 'backup.zip'
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('chairman_presets.json', '{"new": 20}')

        data_paths.import_backup(zip_path)

        bak = existing.with_suffix('.bak')
        assert bak.exists()
        assert json.loads(bak.read_text()) == {'original': 10}
        assert json.loads(existing.read_text()) == {'new': 20}

    def test_import_raises_on_invalid_json(self, tmp_path, isolated, monkeypatch):
        import data_paths
        zip_path = tmp_path / 'bad.zip'
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('chairman_presets.json', 'NOT JSON')

        with pytest.raises(json.JSONDecodeError):
            data_paths.import_backup(zip_path)

    def test_import_raises_on_empty_recognized_json(self, tmp_path, isolated, monkeypatch):
        import data_paths
        zip_path = tmp_path / 'empty_json.zip'
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('chairman_presets.json', '')

        with pytest.raises(json.JSONDecodeError):
            data_paths.import_backup(zip_path)

    def test_import_raises_on_valid_json_with_wrong_shape(self, tmp_path, isolated, monkeypatch):
        import data_paths
        existing = isolated / 'seat_names.json'
        existing.write_text('{"names": ["Original"], "seats": {}}', encoding='utf-8')
        zip_path = tmp_path / 'wrong_shape.zip'
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('seat_names.json', '["PersonA"]')

        with pytest.raises(ValueError, match="objeto JSON"):
            data_paths.import_backup(zip_path)
        assert json.loads(existing.read_text()) == {"names": ["Original"], "seats": {}}
        assert not existing.with_suffix('.bak').exists()

    def test_import_raises_on_no_recognized_files(self, tmp_path, isolated, monkeypatch):
        import data_paths
        zip_path = tmp_path / 'unknown.zip'
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('unrelated.txt', 'hello')

        with pytest.raises(ValueError, match="reconocidos"):
            data_paths.import_backup(zip_path)

    def test_import_raises_on_bad_zip_file(self, tmp_path, isolated, monkeypatch):
        import data_paths
        zip_path = tmp_path / 'corrupt.zip'
        zip_path.write_text('esto no es un zip', encoding='utf-8')

        with pytest.raises(zipfile.BadZipFile):
            data_paths.import_backup(zip_path)

    def test_export_then_import_roundtrip(self, tmp_path, isolated, monkeypatch):
        import data_paths
        app_dir = tmp_path / 'app'
        app_dir.mkdir()

        # Crear datos originales
        (isolated / 'chairman_presets.json').write_text('{"PersonA": 10, "PersonB": 11}', encoding='utf-8')
        (isolated / 'seat_names.json').write_text(
            '{"names": ["PersonA", "PersonB"], "seats": {"4": "PersonA"}}', encoding='utf-8'
        )

        # Exportar (sin .txt — app_dir vacío)
        zip_path = tmp_path / 'roundtrip.zip'
        data_paths.export_backup(zip_path, app_dir=app_dir)

        # Borrar datos
        (isolated / 'chairman_presets.json').unlink()
        (isolated / 'seat_names.json').unlink()

        # Importar
        restored = data_paths.import_backup(zip_path, app_dir=app_dir)
        assert len(restored) == 2
        assert json.loads((isolated / 'chairman_presets.json').read_text()) == {'PersonA': 10, 'PersonB': 11}


# ═══════════════════════════════════════════════════════════════════════════════
#  Nuevos tests de robustez (bugs corregidos)
# ═══════════════════════════════════════════════════════════════════════════════

class TestScheduleRobustness:
    """Tests para los bugs de schedule_config corregidos."""

    @pytest.fixture()
    def sf(self, tmp_path, monkeypatch):
        import application.schedule_config as sc
        f = tmp_path / 'schedule.json'
        monkeypatch.setattr(sc, 'SCHEDULE_FILE', f)
        return f

    def test_overnight_schedule_within(self, sf):
        """22:00–06:00: una hora de madrugada debe quedar dentro del intervalo."""
        from application.schedule_config import is_within_schedule, save_schedule
        from unittest.mock import patch
        from datetime import datetime as dt
        save_schedule({'monday': {'enabled': True, 'start': '22:00', 'end': '06:00'},
                       **{d: {'enabled': False, 'start': '09:00', 'end': '17:00'}
                          for d in ['tuesday','wednesday','thursday','friday','saturday','sunday']}})
        # Simular lunes a las 23:30
        fake_now = dt(2024, 1, 1, 23, 30)  # lunes
        with patch('application.schedule_config.datetime') as mock_dt:
            mock_dt.now.return_value = fake_now
            assert is_within_schedule() is True

    def test_overnight_schedule_outside(self, sf):
        """22:00–06:00: las 10:00 del mismo día NO debe quedar dentro."""
        from application.schedule_config import is_within_schedule, save_schedule
        from unittest.mock import patch
        from datetime import datetime as dt
        save_schedule({'monday': {'enabled': True, 'start': '22:00', 'end': '06:00'},
                       **{d: {'enabled': False, 'start': '09:00', 'end': '17:00'}
                          for d in ['tuesday','wednesday','thursday','friday','saturday','sunday']}})
        fake_now = dt(2024, 1, 1, 10, 0)  # lunes a las 10:00
        with patch('application.schedule_config.datetime') as mock_dt:
            mock_dt.now.return_value = fake_now
            assert is_within_schedule() is False

    def test_invalid_hours_rejected(self, sf):
        """Horas fuera de rango (25:00) deben devolver False sin excepción."""
        from application.schedule_config import is_within_schedule, save_schedule
        from unittest.mock import patch
        from datetime import datetime as dt
        save_schedule({'monday': {'enabled': True, 'start': '25:00', 'end': '30:00'},
                       **{d: {'enabled': False, 'start': '09:00', 'end': '17:00'}
                          for d in ['tuesday','wednesday','thursday','friday','saturday','sunday']}})
        fake_now = dt(2024, 1, 1, 12, 0)
        with patch('application.schedule_config.datetime') as mock_dt:
            mock_dt.now.return_value = fake_now
            assert is_within_schedule() is False

    def test_normal_schedule_within(self, sf):
        """Verificar que el horario normal sigue funcionando tras los cambios."""
        from application.schedule_config import is_within_schedule, save_schedule
        from unittest.mock import patch
        from datetime import datetime as dt
        save_schedule({'monday': {'enabled': True, 'start': '09:00', 'end': '17:00'},
                       **{d: {'enabled': False, 'start': '09:00', 'end': '17:00'}
                          for d in ['tuesday','wednesday','thursday','friday','saturday','sunday']}})
        fake_now = dt(2024, 1, 1, 12, 0)
        with patch('application.schedule_config.datetime') as mock_dt:
            mock_dt.now.return_value = fake_now
            assert is_within_schedule() is True

    def test_normal_schedule_outside(self, sf):
        from application.schedule_config import is_within_schedule, save_schedule
        from unittest.mock import patch
        from datetime import datetime as dt
        save_schedule({'monday': {'enabled': True, 'start': '09:00', 'end': '17:00'},
                       **{d: {'enabled': False, 'start': '09:00', 'end': '17:00'}
                          for d in ['tuesday','wednesday','thursday','friday','saturday','sunday']}})
        fake_now = dt(2024, 1, 1, 18, 0)
        with patch('application.schedule_config.datetime') as mock_dt:
            mock_dt.now.return_value = fake_now
            assert is_within_schedule() is False


class TestChairmanPresetsReturnValue:
    """save_chairman_presets ahora devuelve bool."""

    @pytest.fixture()
    def preset_file(self, tmp_path, monkeypatch):
        import application.chairman_presets as cp
        f = tmp_path / 'chairman_presets.json'
        monkeypatch.setattr(cp, 'CHAIRMAN_PRESETS_FILE', f)
        return f

    def test_save_returns_true_on_success(self, preset_file):
        from application.chairman_presets import save_chairman_presets
        assert save_chairman_presets({'PersonA': 10}) is True

    def test_save_returns_false_on_io_error(self, tmp_path, monkeypatch):
        import application.chairman_presets as cp
        blocker = tmp_path / 'not_a_dir'
        blocker.write_text('bloqueo', encoding='utf-8')
        monkeypatch.setattr(cp, 'CHAIRMAN_PRESETS_FILE',
                            blocker / 'chairman_presets.json')
        assert cp.save_chairman_presets({'PersonA': 10}) is False

class TestImportBackupAtomic:
    """import_backup usa escritura atómica (.tmp → replace)."""

    @pytest.fixture()
    def isolated(self, tmp_path, monkeypatch):
        import data_paths
        config_dir = tmp_path / 'config'
        config_dir.mkdir()
        monkeypatch.setattr(data_paths, 'CONFIG_DIR', config_dir)
        monkeypatch.setattr(data_paths, 'CHAIRMAN_PRESETS_FILE', config_dir / 'chairman_presets.json')
        monkeypatch.setattr(data_paths, 'SEAT_NAMES_FILE',       config_dir / 'seat_names.json')
        monkeypatch.setattr(data_paths, 'SCHEDULE_FILE',         config_dir / 'schedule.json')
        monkeypatch.setattr(data_paths, '_DATA_FILES', (
            config_dir / 'chairman_presets.json',
            config_dir / 'seat_names.json',
            config_dir / 'schedule.json',
        ))
        return config_dir

    def test_tmp_not_left_after_successful_import(self, tmp_path, isolated):
        import data_paths
        import zipfile
        zip_path = tmp_path / 'backup.zip'
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('chairman_presets.json', '{"PersonA": 10}')

        data_paths.import_backup(zip_path)
        assert not (isolated / 'chairman_presets.tmp').exists()

    def test_tmp_not_left_when_json_replace_fails(self, tmp_path, isolated, monkeypatch):
        import data_paths
        import zipfile
        zip_path = tmp_path / 'backup.zip'
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('chairman_presets.json', '{"PersonA": 10}')

        def fail_replace(_src, _dst):
            raise OSError("replace failed")

        monkeypatch.setattr(data_paths.os, 'replace', fail_replace)

        assert data_paths.import_backup(zip_path) == []
        assert not (isolated / 'chairman_presets.tmp').exists()
        assert not (isolated / 'chairman_presets.json').exists()

    def test_existing_json_backup_survives_when_replace_fails(self, tmp_path, isolated, monkeypatch):
        import data_paths
        import zipfile
        existing = isolated / 'chairman_presets.json'
        existing.write_text('{"original": 10}', encoding='utf-8')
        zip_path = tmp_path / 'backup.zip'
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('chairman_presets.json', '{"new": 20}')

        def fail_replace(_src, _dst):
            raise OSError("replace failed")

        monkeypatch.setattr(data_paths.os, 'replace', fail_replace)

        assert data_paths.import_backup(zip_path) == []
        assert json.loads(existing.read_text(encoding='utf-8')) == {'original': 10}
        assert json.loads(existing.with_suffix('.bak').read_text(encoding='utf-8')) == {'original': 10}
        assert not existing.with_suffix('.tmp').exists()

    def test_tmp_not_left_when_txt_replace_fails(self, tmp_path, isolated, monkeypatch):
        import data_paths
        import zipfile
        app_dir = tmp_path / 'app'
        app_dir.mkdir()
        zip_path = tmp_path / 'backup.zip'
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('config/PTZ1IP.txt', '172.16.1.11')

        def fail_replace(_src, _dst):
            raise OSError("replace failed")

        monkeypatch.setattr(data_paths.os, 'replace', fail_replace)

        assert data_paths.import_backup(zip_path, app_dir=app_dir) == []
        assert not (app_dir / 'PTZ1IP.tmp').exists()
        assert not (app_dir / 'PTZ1IP.txt').exists()

    def test_import_does_not_corrupt_on_partial_zip(self, tmp_path, isolated):
        """Si un archivo del ZIP es JSON inválido, los anteriores ya restaurados
        quedan intactos pero la excepción se lanza para el archivo corrupto."""
        import data_paths
        import zipfile
        zip_path = tmp_path / 'partial.zip'
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('chairman_presets.json', '{"PersonA": 10}')  # válido
            zf.writestr('seat_names.json', 'INVALID JSON')         # inválido

        with pytest.raises(json.JSONDecodeError):
            data_paths.import_backup(zip_path)
        # El primer archivo debería haberse restaurado antes del error
        assert (isolated / 'chairman_presets.json').exists()


# ═══════════════════════════════════════════════════════════════════════════════
#  Idea 4 — Archivos .txt de configuración en el ZIP de backup
# ═══════════════════════════════════════════════════════════════════════════════

class TestBackupTxtFiles:
    """Export incluye .txt de red; import los restaura al directorio de la app."""

    @pytest.fixture()
    def isolated(self, tmp_path, monkeypatch):
        import data_paths
        config_dir = tmp_path / 'config'
        config_dir.mkdir()
        monkeypatch.setattr(data_paths, 'CONFIG_DIR', config_dir)
        monkeypatch.setattr(data_paths, 'CHAIRMAN_PRESETS_FILE', config_dir / 'chairman_presets.json')
        monkeypatch.setattr(data_paths, 'SEAT_NAMES_FILE',       config_dir / 'seat_names.json')
        monkeypatch.setattr(data_paths, 'SCHEDULE_FILE',         config_dir / 'schedule.json')
        monkeypatch.setattr(data_paths, '_DATA_FILES', (
            config_dir / 'chairman_presets.json',
            config_dir / 'seat_names.json',
            config_dir / 'schedule.json',
        ))
        return config_dir

    @pytest.fixture()
    def app_dir(self, tmp_path):
        d = tmp_path / 'app'
        d.mkdir()
        return d

    def _write_txt_files(self, app_dir):
        (app_dir / 'PTZ1IP.txt').write_text('172.16.1.11', encoding='utf-8')
        (app_dir / 'PTZ2IP.txt').write_text('172.16.1.12', encoding='utf-8')
        (app_dir / 'Cam1ID.txt').write_text('81', encoding='utf-8')
        (app_dir / 'Cam2ID.txt').write_text('82', encoding='utf-8')
        (app_dir / 'ATEMIP.txt').write_text('192.168.1.240', encoding='utf-8')
        (app_dir / 'Contact.txt').write_text('IT Support: ext 123', encoding='utf-8')

    def test_export_includes_txt_files(self, tmp_path, isolated, app_dir):
        import data_paths
        self._write_txt_files(app_dir)

        zip_path = tmp_path / 'backup.zip'
        included = data_paths.export_backup(zip_path, app_dir=app_dir)

        assert 'PTZ1IP.txt' in included
        assert 'Cam1ID.txt' in included
        assert 'ATEMIP.txt' in included
        assert 'Contact.txt' in included

        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
        assert 'config/PTZ1IP.txt' in names
        assert 'config/Cam2ID.txt' in names

    def test_export_skips_missing_txt(self, tmp_path, isolated, app_dir):
        import data_paths
        # Solo crear algunos .txt
        (app_dir / 'PTZ1IP.txt').write_text('172.16.1.11', encoding='utf-8')
        (app_dir / 'ATEMIP.txt').write_text('192.168.1.240', encoding='utf-8')

        zip_path = tmp_path / 'backup.zip'
        included = data_paths.export_backup(zip_path, app_dir=app_dir)

        assert 'PTZ1IP.txt' in included
        assert 'ATEMIP.txt' in included
        assert 'PTZ2IP.txt' not in included
        assert 'Cam1ID.txt' not in included

    def test_import_restores_txt_to_app_dir(self, tmp_path, isolated, app_dir):
        import data_paths

        zip_path = tmp_path / 'backup.zip'
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('config/PTZ1IP.txt', '172.16.1.11')
            zf.writestr('config/Cam1ID.txt', '81')
            zf.writestr('chairman_presets.json', '{"PersonA": 10}')

        restored = data_paths.import_backup(zip_path, app_dir=app_dir)

        assert 'PTZ1IP.txt' in restored
        assert 'Cam1ID.txt' in restored
        assert 'chairman_presets.json' in restored
        assert (app_dir / 'PTZ1IP.txt').read_text() == '172.16.1.11'
        assert (app_dir / 'Cam1ID.txt').read_text() == '81'

    def test_import_txt_bak_before_overwrite(self, tmp_path, isolated, app_dir):
        import data_paths
        (app_dir / 'PTZ1IP.txt').write_text('OLD_IP', encoding='utf-8')

        zip_path = tmp_path / 'backup.zip'
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('config/PTZ1IP.txt', 'NEW_IP')

        data_paths.import_backup(zip_path, app_dir=app_dir)

        assert (app_dir / 'PTZ1IP.bak').exists()
        assert (app_dir / 'PTZ1IP.bak').read_text() == 'OLD_IP'
        assert (app_dir / 'PTZ1IP.txt').read_text() == 'NEW_IP'

    def test_import_txt_strips_trailing_whitespace(self, tmp_path, isolated, app_dir):
        """Los .txt se guardan sin espacios/saltos de línea extra al final."""
        import data_paths
        zip_path = tmp_path / 'backup.zip'
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('config/PTZ1IP.txt', '172.16.1.11\n\n')

        data_paths.import_backup(zip_path, app_dir=app_dir)
        assert (app_dir / 'PTZ1IP.txt').read_text() == '172.16.1.11'

    def test_full_roundtrip_json_and_txt(self, tmp_path, isolated, app_dir):
        import data_paths
        # Datos JSON
        (isolated / 'chairman_presets.json').write_text('{"PersonA": 10}', encoding='utf-8')
        # Config TXT
        self._write_txt_files(app_dir)

        zip_path = tmp_path / 'full.zip'
        included = data_paths.export_backup(zip_path, app_dir=app_dir)
        assert len(included) == 7  # 1 JSON + 6 TXT

        # Borrar todo
        (isolated / 'chairman_presets.json').unlink()
        for f in app_dir.iterdir():
            f.unlink()

        restored = data_paths.import_backup(zip_path, app_dir=app_dir)
        assert len(restored) == 7
        assert (app_dir / 'PTZ1IP.txt').read_text() == '172.16.1.11'
        assert json.loads((isolated / 'chairman_presets.json').read_text()) == {'PersonA': 10}

    def test_zip_only_txt_recognized(self, tmp_path, isolated, app_dir):
        """Un ZIP que solo tiene .txt (sin JSON) debe ser aceptado."""
        import data_paths
        zip_path = tmp_path / 'txt_only.zip'
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('config/PTZ1IP.txt', '172.16.1.11')

        restored = data_paths.import_backup(zip_path, app_dir=app_dir)
        assert 'PTZ1IP.txt' in restored


# ═══════════════════════════════════════════════════════════════════════════════
#  Idea 5 — Detección de presets duplicados en load_chairman_presets
# ═══════════════════════════════════════════════════════════════════════════════

class TestDuplicatePresetDetection:

    @pytest.fixture()
    def preset_file(self, tmp_path, monkeypatch):
        import application.chairman_presets as cp
        f = tmp_path / 'chairman_presets.json'
        monkeypatch.setattr(cp, 'CHAIRMAN_PRESETS_FILE', f)
        return f

    def test_no_duplicates_loads_all(self, preset_file):
        from application.chairman_presets import load_chairman_presets
        preset_file.write_text('{"PersonA": 10, "PersonB": 11, "PersonC": 12}', encoding='utf-8')
        result = load_chairman_presets()
        assert result == {'PersonA': 10, 'PersonB': 11, 'PersonC': 12}

    def test_duplicate_preset_keeps_first(self, preset_file):
        from application.chairman_presets import load_chairman_presets
        # PersonA y PersonB comparten el preset 10
        preset_file.write_text('{"PersonA": 10, "PersonB": 10, "PersonC": 11}', encoding='utf-8')
        result = load_chairman_presets()
        assert 'PersonA' in result     # primera aparición → se mantiene
        assert 'PersonB' not in result   # segunda aparición → descartada
        assert 'PersonC' in result     # no afectada
        assert result['PersonA'] == 10
        assert result['PersonC'] == 11

    def test_all_duplicates_keeps_only_first(self, preset_file):
        """Tres personas con el mismo número: solo queda la primera."""
        from application.chairman_presets import load_chairman_presets
        preset_file.write_text('{"PersonA": 10, "PersonB": 10, "PersonC": 10}', encoding='utf-8')
        result = load_chairman_presets()
        assert len(result) == 1
        assert 'PersonA' in result

    def test_non_int_preset_logged_and_skipped(self, preset_file):
        from application.chairman_presets import load_chairman_presets
        preset_file.write_text('{"PersonA": "diez", "PersonB": 11}', encoding='utf-8')
        result = load_chairman_presets()
        assert 'PersonA' not in result
        assert 'PersonB' in result

    def test_out_of_range_preset_skipped(self, preset_file):
        from application.chairman_presets import load_chairman_presets
        preset_file.write_text('{"PersonA": 5, "PersonB": 90, "PersonC": 10}', encoding='utf-8')
        result = load_chairman_presets()
        assert 'PersonA' not in result   # 5 < CHAIRMAN_PRESET_START (10)
        assert 'PersonB' not in result     # 90 > CHAIRMAN_PRESET_MAX (89)
        assert 'PersonC' in result       # 10 — OK

    def test_duplicate_warning_emitted(self, preset_file, caplog):
        """El log debe mencionar el número de preset duplicado."""
        import logging
        from application.chairman_presets import load_chairman_presets
        preset_file.write_text('{"PersonA": 10, "PersonB": 10}', encoding='utf-8')
        with caplog.at_level(logging.WARNING, logger='application.chairman_presets'):
            load_chairman_presets()
        assert '10' in caplog.text   # el número de preset debe aparecer en el warning

    def test_save_load_resolves_duplicates_permanently(self, preset_file):
        """Tras cargar (eliminando duplicado) y guardar, el archivo queda sin duplicados."""
        from application.chairman_presets import load_chairman_presets, save_chairman_presets
        preset_file.write_text('{"PersonA": 10, "PersonB": 10, "PersonC": 11}', encoding='utf-8')
        clean = load_chairman_presets()
        save_chairman_presets(clean)
        reloaded = load_chairman_presets()
        assert reloaded == clean  # no hay duplicados en el archivo
        assert len(reloaded) == 2  # PersonA:10, PersonC:11
