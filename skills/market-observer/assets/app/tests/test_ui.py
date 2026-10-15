from fastapi.testclient import TestClient
from a_share_monitor.api import create_app
from a_share_monitor.config import Settings


def test_ui_and_assets(tmp_path):
    with TestClient(create_app(Settings(tmp_path / 'ui.sqlite3', api_key='protected'))) as client:
        page = client.get('/')
        assert page.status_code == 200
        assert '观市' in page.text
        assert 'text/html' in page.headers['content-type']
        for asset in ('app.js', 'style.css', 'mark.svg'):
            assert client.get('/assets/' + asset).status_code == 200
        # Public UI does not bypass protected data endpoints.
        assert client.get('/api/v1/quotes').status_code == 401
        assert client.get('/assets/not-found.js').status_code == 404


def test_ui_does_not_depend_on_remote_assets(tmp_path):
    with TestClient(create_app(Settings(tmp_path / 'ui.sqlite3'))) as client:
        html = client.get('/').text
        assert 'src="https://' not in html
        assert 'href="https://' not in html
        assert 'textContent' in client.get('/assets/app.js').text
