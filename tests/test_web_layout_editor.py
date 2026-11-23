"""Synthetic, hardware-free editor transaction and HTTP safety tests."""
import copy
import json
import threading
import urllib.error
import urllib.request

import pytest

from application.web_layout_editor import EditorError, WebLayoutEditor, validate_document
from runtime.web_layout_editor import make_handler, prepare_workspace, BoundedEditorServer


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
    lease = editor.acquire('a')
    result = editor.save('a', revision, doc, lease['generation'])
    assert result['saved']
    assert (editor.backups / result['backup']).read_bytes() == old
    restarted = WebLayoutEditor(editor.path.parent)
    assert restarted.read('b')['document']['seats'][0]['id'] == 'stable-1'
    assert result['revision'] != revision


def test_exclusive_lease_and_expiry(editor):
    now = [1]
    editor.clock = lambda: now[0]
    lease = editor.acquire('a')
    with pytest.raises(EditorError, match='editor_busy'):
        editor.acquire('b')
    assert editor.read('b')['lease'] == 'busy'
    now[0] = 100
    editor.acquire('b')
    revision, doc = populated(editor)
    with pytest.raises(EditorError, match='lease_required'):
        editor.save('a', revision, doc, lease['generation'])


def test_stale_revision_cannot_overwrite_master(editor):
    revision, doc = populated(editor)
    lease = editor.acquire('a')
    editor.save('a', revision, doc, lease['generation'])
    saved = editor.path.read_bytes()
    with pytest.raises(EditorError, match='revision_conflict'):
        editor.save('a', revision, doc, lease['generation'])
    assert editor.path.read_bytes() == saved


def test_external_change_detected(editor):
    revision, doc = populated(editor)
    lease = editor.acquire('a')
    changed = copy.deepcopy(doc)
    changed['room_name'] = 'External update'
    editor.path.write_text(json.dumps(changed))
    with pytest.raises(EditorError, match='revision_conflict'):
        editor.save('a', revision, doc, lease['generation'])


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
    lease = editor.acquire('a')
    monkeypatch.setattr(editor._service, 'save', lambda layout: False)
    with pytest.raises(EditorError, match='save_failed'):
        editor.save('a', revision, doc, lease['generation'])
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
    server = BoundedEditorServer(('127.0.0.1', 0), make_handler(editor, 'unused'))
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


@pytest.mark.parametrize('field,value', [('x', 60.5), ('y', 100.5), ('row', 1.5),
                                        ('column', 2.5), ('row', True)])
def test_fractional_coordinates_never_silently_truncate(editor, field, value):
    revision, doc = populated(editor)
    doc['seats'][0][field] = value
    lease = editor.acquire('a')
    previous = editor.path.read_bytes()
    with pytest.raises(EditorError):
        editor.save('a', revision, doc, lease['generation'])
    assert editor.path.read_bytes() == previous


def test_save_returns_exact_canonical_document_including_row_column(editor):
    revision, doc = populated(editor)
    doc['seats'][0].update(row=2, column=3)
    lease = editor.acquire('a')
    result = editor.save('a', revision, doc, lease['generation'])
    assert result['document'] == doc == editor.read('a')['document']


def test_expired_generation_cannot_renew_or_save_after_other_tab_leaves(editor):
    now = [0]
    editor.clock = lambda: now[0]
    revision, doc = populated(editor)
    old = editor.acquire('old')
    now[0] = 91
    other = editor.acquire('other')
    editor.release('other', other['generation'])
    for action in (lambda: editor.renew('old', old['generation']),
                   lambda: editor.save('old', revision, doc, old['generation'])):
        with pytest.raises(EditorError, match='lease_required'):
            action()
    fresh = editor.acquire('old')  # Only an explicit acquire grants a new turn.
    assert fresh['generation'] != old['generation']
    with pytest.raises(EditorError, match='lease_required'):
        editor.renew('old', old['generation'])
    assert editor.renew('old', fresh['generation']) == {'renewed': True}


def test_symlinked_ancestor_marker_and_nested_history_rejected(tmp_path):
    real = tmp_path / 'real'
    real.mkdir()
    link = tmp_path / 'link'
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError, match='Symlink'):
        prepare_workspace(link / 'child')
    assert not (real / 'child').exists()
    sandbox, lock = prepare_workspace(tmp_path / 'safe')
    lock.close()
    marker = sandbox / '.kh-web-editor-sandbox'
    marker.write_text('')
    with pytest.raises(ValueError, match='marker'):
        prepare_workspace(sandbox)
    from runtime.web_layout_editor import MARKER
    marker.write_bytes(MARKER)
    nested = sandbox / 'history' / 'nested'
    nested.mkdir(parents=True)
    (nested / 'outside').symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError, match='regular'):
        prepare_workspace(sandbox)


def test_marker_not_created_when_tree_is_invalid(tmp_path):
    sandbox = tmp_path / 'bad'
    sandbox.mkdir()
    (sandbox / 'link').symlink_to(tmp_path / 'missing')
    with pytest.raises(ValueError):
        prepare_workspace(sandbox)
    assert not (sandbox / '.kh-web-editor-sandbox').exists()


def test_backup_exclusive_reservation_preserves_competing_content(editor):
    revision, doc = populated(editor)
    editor.backups.mkdir()
    backup = editor.backups / (revision + '.json')
    backup.write_bytes(b'competing reservation')
    lease = editor.acquire('a')
    previous = editor.path.read_bytes()
    with pytest.raises(EditorError, match='backup_mismatch'):
        editor.save('a', revision, doc, lease['generation'])
    assert backup.read_bytes() == b'competing reservation'
    assert editor.path.read_bytes() == previous


@pytest.mark.parametrize('framing', [b'Transfer-Encoding: chunked\r\n',
                                     b'Content-Length: 2\r\nContent-Length: 3\r\n'])
def test_ambiguous_http_framing_rejected(http_editor, framing):
    import socket
    from urllib.parse import urlsplit
    parts = urlsplit(http_editor)
    with socket.create_connection((parts.hostname, parts.port), timeout=2) as sock:
        sock.sendall(b'POST /api/lease HTTP/1.1\r\nHost: ' + parts.netloc.encode()
                     + b'\r\n' + framing + b'\r\n{}')
        assert b'400' in sock.recv(4096)
    assert request(http_editor).status == 200


def test_slow_partial_headers_and_body_cannot_exhaust_server(http_editor):
    import socket
    import time
    from urllib.parse import urlsplit
    parts = urlsplit(http_editor)
    sockets = []
    try:
        # Fill worker quota with incomplete headers, then verify forced close and recovery.
        for _ in range(8):
            sock = socket.create_connection((parts.hostname, parts.port), timeout=3)
            sockets.append(sock)
            sock.sendall(b'GET / HTTP/1.1\r\nHost: ')
        time.sleep(2.3)
        assert request(http_editor).status == 200
        for sock in sockets:
            assert sock.recv(4096) == b''
        root = request(http_editor)
        cookie = root.headers['Set-Cookie'].split(';')[0]
        sock = socket.create_connection((parts.hostname, parts.port), timeout=3)
        sockets.append(sock)
        headers = (f'POST /api/lease HTTP/1.1\r\nHost: {parts.netloc}\r\n'
                   f'Origin: {http_editor}\r\nCookie: {cookie}\r\n'
                   'Content-Type: application/json\r\nX-KH-Editor: 1\r\n'
                   'X-KH-Tab: test-tab-abcdefghijklmnop\r\nContent-Length: 200\r\n\r\n{')
        sock.sendall(headers.encode())
        time.sleep(2.3)
        response = sock.recv(4096)
        assert not response or b'408' in response
        assert request(http_editor).status == 200
    finally:
        for sock in sockets:
            sock.close()


def test_cookie_pool_expires_and_purges(editor):
    now = [0]
    server = BoundedEditorServer(('127.0.0.1', 0), make_handler(editor, 'unused'))
    origin = f'http://127.0.0.1:{server.server_port}'
    server.RequestHandlerClass = make_handler(editor, origin, clock=lambda: now[0])
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        for _ in range(100):
            assert request(origin).status == 200
        assert request(origin).status == 503
        now[0] = 1801
        assert request(origin).status == 200
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


def test_dripping_request_line_has_absolute_deadline(http_editor):
    import socket
    import time
    from urllib.parse import urlsplit
    parts = urlsplit(http_editor)
    sockets = []
    try:
        for _ in range(8):
            sock = socket.create_connection((parts.hostname, parts.port), timeout=3)
            sockets.append(sock)
        # No first CRLF is ever sent. Traffic stays well below inactivity timeout.
        for _ in range(5):
            for sock in sockets:
                try:
                    sock.sendall(b'G')
                except OSError:
                    pass
            time.sleep(0.65)
        assert request(http_editor).status == 200
        for sock in sockets:
            assert sock.recv(4096) == b''
    finally:
        for sock in sockets:
            sock.close()


def test_authenticated_mode_requires_admin_and_rate_limits(editor):
    server = BoundedEditorServer(('127.0.0.1', 0), make_handler(editor, 'unused'))
    origin = f'http://127.0.0.1:{server.server_port}'
    server.RequestHandlerClass = make_handler(editor, origin,
                                              authenticator=lambda candidate: candidate == 'fixture-only')
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        root = request(origin)
        cookie = root.headers['Set-Cookie'].split(';')[0]
        headers = {'Cookie': cookie, 'Content-Type': 'application/json', 'X-KH-Editor': '1',
                   'X-KH-Tab': 'test-tab-abcdefghijklmnop', 'Origin': origin}
        assert request(origin, '/api/layout', **headers).status == 401
        assert request(origin, '/api/lease', {}, **headers).status == 401
        assert request(origin, '/api/login', {'password': 'wrong'}, **headers).status == 401
        assert request(origin, '/api/login', {'password': 'fixture-only'}, **headers).status == 200
        assert request(origin, '/api/layout', **headers).status == 200
        assert request(origin, '/api/logout', {}, **headers).status == 200
        assert request(origin, '/api/layout', **headers).status == 401
        for _ in range(3):
            assert request(origin, '/api/login', {'password': 'wrong'}, **headers).status == 401
        assert request(origin, '/api/login', {'password': 'fixture-only'}, **headers).status == 429
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


@pytest.mark.parametrize('address', ['0.0.0.0', '8.8.8.8', '224.0.0.1', '::1'])
def test_lan_adapter_rejects_wildcard_public_and_unsupported_interfaces(editor, address):
    from runtime.web_layout_editor_lan import build_lan_server
    with pytest.raises(ValueError, match='private IPv4'):
        build_lan_server(editor, address=address, port=8766,
                         certificate='unused', private_key='unused', authenticator=lambda _: False)
