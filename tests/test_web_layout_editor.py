"""Synthetic, hardware-free editor transaction and HTTP safety tests."""
import copy
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from application.web_layout_editor import EditorError, WebLayoutEditor, validate_document
from runtime.web_layout_editor import make_handler, prepare_workspace


@pytest.fixture
def editor(tmp_path):
    service = WebLayoutEditor(tmp_path)
    service.initialize()
    return service


def populated(editor):
    result = editor.read('a')
    document = result['document']
    document['seats'] = [{'id': 'stable-1', 'label': '1', 'preset': 0,
                          'camera_role': 'comments', 'x': 60, 'y': 100,
                          'type': 'delegate', 'visible': True,
                          'locked': False, 'calibrated': False}]
    return result['revision'], document


def test_save_persists_and_keeps_exact_previous_bytes(editor):
    revision, doc = populated(editor)
    old = editor.path.read_bytes()
    editor.acquire('a')
    result = editor.save('a', revision, doc)
    assert result['saved']
    assert (editor.backups / result['backup']).read_bytes() == old
    restarted = WebLayoutEditor(editor.path.parent)
    assert restarted.read('b')['document']['seats'][0]['id'] == 'stable-1'
    assert result['revision'] != revision


def test_exclusive_lease_and_expiry(editor):
    now = [1]
    editor.clock = lambda: now[0]
    editor.acquire('a')
    with pytest.raises(EditorError, match='editor_busy'):
        editor.acquire('b')
    assert editor.read('b')['lease'] == 'busy'
    now[0] = 100
    editor.acquire('b')
    revision, doc = populated(editor)
    with pytest.raises(EditorError, match='lease_required'):
        editor.save('a', revision, doc)


def test_stale_revision_cannot_overwrite_master(editor):
    revision, doc = populated(editor)
    editor.acquire('a')
    editor.save('a', revision, doc)
    saved = editor.path.read_bytes()
    with pytest.raises(EditorError, match='revision_conflict'):
        editor.save('a', revision, doc)
    assert editor.path.read_bytes() == saved


def test_external_change_detected(editor):
    revision, doc = populated(editor)
    editor.acquire('a')
    changed = copy.deepcopy(doc)
    changed['room_name'] = 'External update'
    editor.path.write_text(json.dumps(changed))
    with pytest.raises(EditorError, match='revision_conflict'):
        editor.save('a', revision, doc)


@pytest.mark.parametrize('field,value', [('x', float('nan')), ('y', -1), ('preset', True),
                                        ('preset', 133), ('visible', 1), ('label', ''),
                                        ('calibrated', True)])
def test_invalid_seat_rejected(editor, field, value):
    _, doc = populated(editor)
    doc['seats'][0][field] = value
    with pytest.raises(EditorError):
        validate_document(doc)


def test_duplicate_ids_rejected(editor):
    _, doc = populated(editor)
    doc['seats'].append(copy.deepcopy(doc['seats'][0]))
    with pytest.raises(EditorError, match='duplicate_id'):
        validate_document(doc)


def test_multiple_unassigned_seats_allowed_but_duplicate_binding_not(editor):
    _, doc = populated(editor)
    other = copy.deepcopy(doc['seats'][0])
    other['id'] = 'stable-2'
    doc['seats'].append(other)
    validate_document(doc)
    for seat in doc['seats']:
        seat['preset'] = 4
    with pytest.raises(EditorError, match='duplicate_binding'):
        validate_document(doc)


def test_failed_save_does_not_change_master(editor, monkeypatch):
    revision, doc = populated(editor)
    old = editor.path.read_bytes()
    editor.acquire('a')
    monkeypatch.setattr(editor._service, 'save', lambda layout: False)
    with pytest.raises(EditorError, match='save_failed'):
        editor.save('a', revision, doc)
    assert editor.path.read_bytes() == old


def test_corruption_is_reported_not_regenerated(editor):
    editor.path.write_text('{broken')
    with pytest.raises(ValueError):
        editor.read('a')
    assert editor.path.read_text() == '{broken'


def test_workspace_rejects_live_data_and_second_owner(tmp_path):
    occupied = tmp_path / 'production'
    occupied.mkdir()
    (occupied / 'room_layout.json').write_text('{}')
    with pytest.raises(ValueError, match='empty'):
        prepare_workspace(occupied)
    sandbox, lock = prepare_workspace(tmp_path / 'sandbox')
    try:
        with pytest.raises(ValueError, match='Another editor'):
            prepare_workspace(sandbox)
    finally:
        lock.close()


@pytest.fixture
def http_editor(editor):
    # Reserve port before constructing the expected origin.
    server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(editor, 'unused'))
    origin = f'http://127.0.0.1:{server.server_port}'
    server.RequestHandlerClass = make_handler(editor, origin)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    yield origin
    server.shutdown()
    server.server_close()
    worker.join()


def request(origin, path='/', data=None, **headers):
    req = urllib.request.Request(origin + path,
                                 data=None if data is None else json.dumps(data).encode(),
                                 headers=headers)
    try:
        return urllib.request.urlopen(req)
    except urllib.error.HTTPError as error:
        return error


def test_http_session_origin_and_host_checks(http_editor):
    origin = http_editor
    root = request(origin)
    assert root.status == 200
    cookie = root.headers['Set-Cookie'].split(';')[0]
    assert 'HttpOnly' in root.headers['Set-Cookie']
    assert 'default-src' in root.headers['Content-Security-Policy']
    assert request(origin, '/api/layout').status == 403
    assert request(origin, '/', Host='attacker.invalid').status == 403
    headers = {'Cookie': cookie, 'Content-Type': 'application/json', 'X-KH-Editor': '1', 'X-KH-Tab': 'test-tab-abcdefghijklmnop'}
    assert request(origin, '/api/lease', {}, Origin='http://attacker.invalid', **headers).status == 403
    assert request(origin, '/api/lease', {}, Origin=origin, **headers).status == 200
    assert request(origin, '/api/layout', **headers).status == 200
    assert request(origin, '/../../config.yaml').status == 404
    assert request(origin, '/api/save', [], Origin=origin, **headers).status == 400


def test_two_tabs_in_one_cookie_cannot_share_writer(http_editor):
    origin = http_editor
    root = request(origin)
    cookie = root.headers['Set-Cookie'].split(';')[0]
    headers = {'Cookie': cookie, 'Content-Type': 'application/json', 'X-KH-Editor': '1',
               'Origin': origin}
    assert request(origin, '/api/lease', {}, **headers,
                   **{'X-KH-Tab': 'first-tab-abcdefghijklmnop'}).status == 200
    assert request(origin, '/api/lease', {}, **headers,
                   **{'X-KH-Tab': 'second-tab-abcdefghijklmnop'}).status == 423


def test_theme_uses_existing_camera_app_tokens(http_editor):
    from ui.styles import BRAND_DARK, BRAND_MID, FIELD_BG
    response = request(http_editor, '/theme.css')
    text = response.read().decode()
    for value in (BRAND_DARK, BRAND_MID, FIELD_BG):
        assert value in text
