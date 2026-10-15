import importlib.util
import json
from pathlib import Path
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills' / 'market-observer'


def module(name):
    spec = importlib.util.spec_from_file_location(name, SKILL / 'scripts' / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_bootstrap_preserves_existing_and_assets(tmp_path):
    helper = module('bootstrap')
    target = helper.bootstrap(tmp_path / 'installed')
    assert (target / 'a_share_monitor' / 'ui' / 'index.html').is_file()
    assert (target / 'pyproject.toml').is_file()
    assert not (target / '.venv').exists()
    assert not (target / 'data').exists()
    original = (target / 'pyproject.toml').read_bytes()
    with pytest.raises(ValueError, match='not empty'):
        helper.bootstrap(target)
    assert (target / 'pyproject.toml').read_bytes() == original
    with pytest.raises(ValueError, match='outside'):
        helper.bootstrap(SKILL / 'assets' / 'app' / 'nested')


@pytest.mark.parametrize('code', ['../bad', '000001?key=x', '600000/../../', 'bad', '1'])
def test_invalid_code(code):
    with pytest.raises(ValueError):
        module('research_bundle').canonical_code(code)


def test_real_http_bundle_and_no_overwrite(tmp_path):
    helper = module('research_bundle')
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.headers.get('X-API-Key') != 'local-test-key':
                self.send_error(401)
                return
            payload = {'status': 'ok'} if self.path.endswith('/status') else {
                'meta': {'is_demo': False, 'stale': True, 'source': 'test', 'version': 'abc'},
                'data': {'code': '000001', 'name': '测试股票', 'price': 10}}
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode())
        def log_message(self, *_):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = helper.collect_bundle('000001', f'http://127.0.0.1:{server.server_port}', 'local-test-key')
        assert result['stock']['data']['code'] == '000001'
        assert any('STALE' in warning for warning in result['warnings'])
        output = tmp_path / 'evidence.json'
        helper.write_bundle(result, output)
        assert 'local-test-key' not in output.read_text(encoding='utf-8')
        with pytest.raises(ValueError):
            helper.write_bundle(result, output)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_demo_is_rejected(monkeypatch):
    helper = module('research_bundle')
    monkeypatch.setattr(helper, 'get_json', lambda *_: {'meta': {'is_demo': True}, 'data': {'code': '000001'}})
    with pytest.raises(ValueError, match='Demo'):
        helper.collect_bundle('000001', 'http://127.0.0.1:8000')


def test_remote_plaintext_key_rejected():
    helper = module('research_bundle')
    with pytest.raises(ValueError, match='HTTPS'):
        helper.get_json('http://example.com', '/status', 'key')


def test_references_resolve():
    import re
    for document in [SKILL / 'SKILL.md', *(SKILL / 'references').glob('*.md')]:
        for link in re.findall(r'\]\(([^)]+)\)', document.read_text(encoding='utf-8')):
            if not link.startswith(('https://', 'http://')):
                assert (document.parent / link).exists(), (document, link)
