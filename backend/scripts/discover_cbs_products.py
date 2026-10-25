"""Small, sequential read-only discovery of the user-confirmed product catalog."""
import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import requests
from apps.corebanking.services import RestAdapter, resolve_active_connector
from apps.tenants.models import Tenant


def main():
    root = Path.cwd()
    out = root / 'uat-artifacts/journey-20261020T223709Z/product-discovery'
    out.mkdir(exist_ok=True)
    os.environ['REQUESTS_CA_BUNDLE'] = str(root / 'backend/certs/cbs-system-trust.pem')
    adapter = RestAdapter(resolve_active_connector(Tenant.objects.get(code='FIL01').pk))
    session = requests.Session()
    last_end = None
    results = []
    def clean(value):
        if isinstance(value, dict):
            return {k: '[REDACTED]' if k.lower() in {'accesstoken','access_token','token','password','authorization','refresh_token','refreshtoken'} else clean(v) for k,v in value.items()}
        if isinstance(value, list): return [clean(v) for v in value]
        return value
    def request(method, url, **kwargs):
        nonlocal last_end
        if last_end is not None: time.sleep(max(0, 3 - (time.monotonic() - last_end)))
        kwargs.update(timeout=(8, 20), verify=True, allow_redirects=False)
        response = session.request(method, url, **kwargs)
        last_end = time.monotonic()
        if response.status_code == 429: raise RuntimeError('HTTP 429; discovery stopped')
        return response
    with patch('requests.post', lambda url, **kw: request('POST', url, **kw)):
        token = adapter._resolve_bearer_token()
    # Standard OpenAPI locations, followed by the product-reference naming
    # convention already used by the documented ref/*-list routes.
    paths = os.environ.get('CBS_DISCOVERY_PATHS',
        'gateway-perfect/v3/api-docs,gateway-perfect/v2/api-docs,'
        'gateway-perfect/ref/produit-crd-list,gateway-perfect/ref/produit-epg-list,'
        'gateway-perfect/ref/produit-remb-list').split(',')
    for path in paths:
        response = request('GET', adapter._build_url(path), headers={'Accept':'application/json','Authorization':f'Bearer {token}'})
        try: body = response.json()
        except ValueError: body = {'non_json_preview': response.text[:1500]}
        entry = {'path':path,'http':response.status_code,'body':clean(body)}
        results.append(entry)
        filename = path.replace('/','_') + '.json'
        (out / filename).write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding='utf-8')
        rows = body.get('datas') if isinstance(body,dict) else None
        print(json.dumps({'path':path,'http':response.status_code,'keys':list(body)[:12] if isinstance(body,dict) else [], 'row_count':len(rows) if isinstance(rows,list) else None},ensure_ascii=False),flush=True)
    all_results = [json.loads(p.read_text(encoding='utf-8')) for p in sorted(out.glob('gateway*.json'))]
    all_results += [json.loads(p.read_text(encoding='utf-8')) for p in sorted(out.glob('v3*.json'))]
    all_results += [json.loads(p.read_text(encoding='utf-8')) for p in sorted(out.glob('swagger*.json'))]
    (out/'summary.json').write_text(json.dumps([{k:v for k,v in row.items() if k!='body'} for row in all_results],indent=2),encoding='utf-8')


main()
