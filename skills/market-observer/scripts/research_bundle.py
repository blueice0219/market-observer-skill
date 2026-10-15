"""Collect one stock snapshot as evidence; does not invent news or call an LLM."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not forward a custom API key to another endpoint via redirects.
        return None


def canonical_code(code):
    value = str(code).strip().lower()
    if re.fullmatch(r'(sh|sz|bj)\d{6}', value):
        return value
    if re.fullmatch(r'\d{6}(\.(sh|sz|bj))?', value):
        return value
    raise ValueError('Use a six-digit A-share code, sh600000 or 600000.SH')


def get_json(base, route, key):
    parsed = urlparse(base)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Base URL must be HTTP(S), without credentials, query or fragment')
    if key and parsed.scheme != 'https' and parsed.hostname not in ('127.0.0.1', 'localhost', '::1'):
        raise ValueError('API keys over non-loopback HTTP are not supported; use HTTPS or a local tunnel')
    handlers = [NoRedirect()]
    if parsed.hostname in ('127.0.0.1', 'localhost', '::1'):
        handlers.append(ProxyHandler({}))
    request = Request(base.rstrip('/') + route, headers={'X-API-Key': key} if key else {})
    with build_opener(*handlers).open(request, timeout=20) as response:
        content = response.read(4 * 1024 * 1024 + 1)
    if len(content) > 4 * 1024 * 1024:
        raise ValueError('Response exceeds evidence size limit')
    return json.loads(content)


def collect_bundle(code, base, key=''):
    code = canonical_code(code)
    stock = get_json(base, '/api/v1/stocks/' + code, key)
    meta = stock.get('meta', {})
    if meta.get('is_demo'):
        raise ValueError('Demo data cannot be packaged as real stock research evidence')
    if not meta or not isinstance(stock.get('data'), dict):
        raise ValueError('Unexpected quote response')
    status = get_json(base, '/api/v1/status', key)
    warnings = ['Quote snapshot only; news, financial statements and historical bars are not included.',
                'Collection time is not verified exchange time; market coverage is unverified.']
    if meta.get('stale'):
        warnings.append('STALE: do not describe this snapshot as fresh or real-time.')
    return {'schema_version': 1, 'retrieved_at': datetime.now(timezone.utc).isoformat(),
            'evidence_type': 'stock_snapshot', 'source_url': base.rstrip('/') + '/api/v1/stocks/' + code,
            'stock': stock, 'service_status': status, 'warnings': warnings}


def write_bundle(payload, out):
    out = Path(out)
    if out.exists():
        raise ValueError('Evidence file exists; use a new timestamped filename')
    out.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation preserves existing report evidence even on repeated runs.
    with out.open('x', encoding='utf-8') as stream:
        json.dump(payload, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--code', required=True)
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = collect_bundle(args.code, args.base_url, os.getenv('MONITOR_API_KEY', ''))
        write_bundle(payload, args.out)
        print(json.dumps({'file': str(args.out.resolve()), 'code': payload['stock']['data']['code'],
                          'source': payload['stock']['meta']['source'], 'warnings': payload['warnings']}, ensure_ascii=False))
    except HTTPError as exc:
        parser.exit(1, f'HTTP {exc.code}: verify API status and authentication\n')
    except (ValueError, OSError, URLError) as exc:
        parser.exit(1, f'Could not create evidence bundle: {exc}\n')


if __name__ == '__main__':
    main()
