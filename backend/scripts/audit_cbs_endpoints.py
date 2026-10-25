"""Sequential, read-only live CBS audit. Run through Django manage.py shell.

Stores redacted response bodies locally; never submits crd/simple or imports data.
"""
import hashlib
import json
import os
import re
import ssl
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from unittest.mock import patch

import requests
from requests.adapters import HTTPAdapter

from apps.clients.models import Client
from apps.corebanking.perfect_defaults import PERFECT_ENDPOINTS
from apps.corebanking.services import (
    RestAdapter, get_adapter, normalize_client_situation,
    normalize_cbs_credit_rows, resolve_active_connector,
)
from apps.corebanking.disbursement import disbursement_mode
from apps.tenants.models import Tenant


class SystemTrustAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        kwargs['ssl_context'] = ssl.create_default_context()
        return super().init_poolmanager(*args, **kwargs)


class RateLimited(Exception):
    pass


def main():
    tenant = Tenant.objects.get(code='FIL01')
    connector = resolve_active_connector(tenant.pk)
    adapter = RestAdapter(connector)
    auth = connector.get_auth_config_decrypted()
    if connector.protocol != 'REST' or not connector.base_url.startswith('https://'):
        raise RuntimeError('Expected the configured HTTPS REST connector.')
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    root = Path.cwd() / 'uat-artifacts'
    root.mkdir(exist_ok=True)
    (root / '.gitignore').write_text('*\n', encoding='utf-8')
    out = root / ('cbs-' + run_id)
    out.mkdir()
    (out / 'responses').mkdir()
    secret_keys = {'password', 'username', 'authorization', 'accesstoken', 'access_token',
                   'refreshtoken', 'refresh_token', 'token', 'bearer_token', 'client_secret',
                   'secret', 'cookie', 'set-cookie', 'callback_secret'}
    secrets = [str(v) for k,v in auth.items() if v and k.lower() in secret_keys]
    def clean(value):
        if isinstance(value, dict):
            return {str(k): '[REDACTED]' if str(k).lower() in secret_keys else clean(v) for k,v in value.items()}
        if isinstance(value, (list, tuple)):
            return [clean(v) for v in value]
        if isinstance(value, str):
            for secret in sorted(secrets, key=len, reverse=True):
                value = value.replace(secret, '[REDACTED]')
            return re.sub(r'eyJ[A-Za-z0-9_.-]+', '[REDACTED-JWT]', value)
        return value
    def save(path, value):
        path.write_text(json.dumps(clean(value), ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    rules = connector.mapping_rules or {}
    endpoints = {**PERFECT_ENDPOINTS, **(rules.get('endpoints') or {})}
    summary = {
        'run_id': run_id, 'started_at': datetime.now(timezone.utc).isoformat(),
        'tenant': tenant.code, 'connector_id': str(connector.pk),
        'host': urlsplit(connector.base_url).hostname,
        'normal_adapter': type(get_adapter(connector)).__name__,
        'disbursement_mode': disbursement_mode(connector),
        'force_simulate': bool(rules.get('force_simulate')),
        'trust': 'System trust plus requests CA bundle; TLS verification enabled',
        'gap_after_each_response_seconds': 3, 'automatic_retries': 0,
        'inventory': endpoints, 'cases': [], 'blocked': [], 'draft_credit_only': True,
    }
    session = requests.Session()
    session.mount('https://', SystemTrustAdapter(max_retries=0))
    token = None
    last_end = None
    refs = {}
    portfolios = []
    stop = False
    client_only = os.environ.get('CBS_AUDIT_SCOPE') == 'client'
    creation_validation = os.environ.get('CBS_AUDIT_SCOPE') == 'creation_validation'
    supplied_client = os.environ.get('CBS_AUDIT_CLIENT_CODE', '').strip()
    summary['scope'] = 'creation_validation' if creation_validation else 'client_supplement' if client_only else 'full_read_only'
    if creation_validation:
        summary['draft_credit_only'] = False
        summary['complete_draft_not_submitted'] = True

    def flush():
        save(out / 'results.json', summary)

    def replay(response, endpoint_key, payload):
        with patch.object(adapter, '_resolve_bearer_token', return_value='OFFLINE-REPLAY'), \
             patch.object(adapter, '_http_post', return_value=response), \
             patch.object(adapter, '_http_get', return_value=response):
            if endpoint_key.startswith('ref_'):
                return adapter.fetch_ref_list(endpoint_key, default_path=endpoints[endpoint_key])
            if endpoint_key == 'adh_situation':
                value = adapter._adh_situation(payload)
                return {'adapter': value, 'client_mapping': normalize_client_situation(value['raw'])}
            if endpoint_key == 'crd_situation':
                return adapter._crd_situation(payload)
            if endpoint_key == 'crd_impayes':
                return adapter._crd_impayes(payload)
            return None

    def call(name, key, method, payload=None, expected='success', bearer=True, form=False):
        nonlocal last_end, stop
        if stop:
            summary['blocked'].append({'case': name, 'reason': 'Stopped following rate limiting or authentication failure.'})
            flush()
            return None
        if last_end is not None:
            time.sleep(max(0, 3 - (time.monotonic() - last_end)))
        path = endpoints[key]
        url = adapter._auth_url() if key == 'authentification' else adapter._build_url(path)
        if urlsplit(url).scheme != 'https' or urlsplit(url).hostname != urlsplit(connector.base_url).hostname:
            raise RuntimeError('Endpoint differs from the authorized HTTPS connector host.')
        index = len(summary['cases']) + 1
        case = {'case': name, 'endpoint_key': key, 'method': method, 'path': urlsplit(url).path,
                'expected': expected, 'started_at': datetime.now(timezone.utc).isoformat(),
                'gap_since_previous_end_seconds': round(time.monotonic()-last_end, 3) if last_end else None,
                'request_body': payload, 'bearer_present': bool(bearer and token)}
        prefix = f'{index:02d}-{name}'
        headers = {'Accept': 'application/json'}
        if bearer and token:
            headers['Authorization'] = 'Bearer ' + token
        started = time.monotonic()
        raw = None
        try:
            response = session.request(method, url, headers=headers,
                data=payload if form else None, json=payload if not form and method=='POST' else None,
                timeout=(8, 25), verify=True, allow_redirects=False)
            case.update(http_status=response.status_code, elapsed_seconds=round(time.monotonic()-started, 3),
                        content_type=response.headers.get('Content-Type',''), response_bytes=len(response.content),
                        retry_after=response.headers.get('Retry-After'))
            try:
                raw = response.json()
                case['json_valid'] = True
            except ValueError:
                raw = {'non_json_body': response.text}
                case['json_valid'] = False
            code = raw.get('responseCode') if isinstance(raw, dict) else None
            case['business_code'] = code
            try:
                business_ok = code in (None,'') or int(code) < 400
            except (ValueError, TypeError):
                business_ok = False
            case['result'] = 'PASS' if (200 <= response.status_code < 300 and business_ok and case['json_valid']) else 'FAIL'
            if expected == 'rejection':
                rejected = response.status_code in (400,401,403,404,422) or (200 <= response.status_code < 300 and not business_ok)
                case['result'] = 'PASS' if rejected else 'FAIL'
            if expected == 'discovery_only':
                case['result'] = 'OBSERVED_ONLY'
                case['allow_header'] = response.headers.get('Allow')
            save(out / 'responses' / (prefix + '.response.json'), raw)
            case['response_file'] = 'responses/' + prefix + '.response.json'
            if key not in ('authentification', 'crd_simple') and bearer:
                try:
                    normalized = replay(response, key, payload or {})
                    save(out / 'responses' / (prefix + '.normalized.json'), normalized)
                    case['normalized_file'] = 'responses/' + prefix + '.normalized.json'
                    case['adapter_accepts'] = True
                    if isinstance(normalized, list):
                        case['normalized_rows'] = len(normalized)
                    if expected == 'rejection':
                        case['adapter_false_success'] = True
                except Exception as exc:
                    case['adapter_accepts'] = False
                    case['adapter_error'] = clean(str(exc))[:500]
                    if expected == 'success' and case['result'] == 'PASS':
                        case['result'] = 'ADAPTER_FAILURE'
            if response.status_code == 429:
                stop = True
                case['result'] = 'RATE_LIMIT_STOP'
            if key == 'authentification' and case['result'] != 'PASS':
                stop = True
        except requests.RequestException as exc:
            case.update(result='NETWORK_FAILURE', error=clean(str(exc))[:500], elapsed_seconds=round(time.monotonic()-started,3))
            if key == 'authentification':
                stop = True
        finally:
            last_end = time.monotonic()
            summary['cases'].append(case)
            flush()
            print(f"{index:02d} {name}: {case['result']} HTTP={case.get('http_status','-')}", flush=True)
        return raw

    try:
        login_body = {'username': auth.get('username',''), 'password': auth.get('password',''), 'scope': auth.get('scope') or 'perfect'}
        response = call('auth-valid', 'authentification', 'POST', login_body, bearer=False, form=True)
        if response and isinstance(response, dict):
            token = response.get('accessToken') or response.get('access_token') or response.get('token')
            if token:
                secrets.append(token)
            else:
                stop = True
                summary['blocked'].append({'case':'authenticated_calls','reason':'No bearer token returned.'})
        if creation_validation:
            if not supplied_client:
                raise RuntimeError('An explicitly supplied UAT client code is required.')
            summary['uat_code_only_creation_requested_by_user'] = True
            raw = call('credit-create-code-only','crd_simple','POST',{'codeAdherent':supplied_client},expected='rejection')
            case = summary['cases'][-1]
            summary['creation_http_status'] = case.get('http_status')
            summary['creation_business_code'] = case.get('business_code')
            if raw and case.get('http_status') == 200 and case.get('business_code') in (200,'200'):
                summary['unexpected_creation_success'] = True
                ref = raw.get('refDemande') or raw.get('numDemande')
                if ref:
                    call('loan-after-code-only-creation','crd_situation','POST',{'refDemande':str(ref),'codeAdherent':supplied_client})
            else:
                summary['creation_confirmed'] = False
                summary['blocked'].append({'case':'successful_credit_creation','reason':'CBS requires complete credit terms; client code alone was not accepted.'})
            return
        for key in ([] if client_only else sorted(k for k in endpoints if k.startswith('ref_'))):
            raw = call(key.replace('_','-'), key, 'GET')
            if isinstance(raw,dict):
                refs[key] = raw.get('datas') or raw.get('data') or []
                case = summary['cases'][-1]
                rows = refs[key]
                if isinstance(rows, list):
                    case['raw_rows'] = len(rows)
                    case['missing_id_count'] = sum(not isinstance(r,dict) or not r.get('id') for r in rows)
                    case['missing_code_count'] = sum(not isinstance(r,dict) or not r.get('code') for r in rows)
                    case['missing_label_count'] = sum(not isinstance(r,dict) or not (r.get('libelle') or r.get('label') or r.get('name')) for r in rows)
                    case['duplicate_id_count'] = len([r for r in rows if isinstance(r,dict) and r.get('id')]) - len({str(r['id']) for r in rows if isinstance(r,dict) and r.get('id')})
        if not client_only:
            call('ref-no-bearer','ref_devise_list','GET',expected='rejection',bearer=False)
        for label, body in ([] if client_only else [('credits-overdue', {'impayes':True,'uniquementImpayes':True}), ('credits-all', {})]):
            raw = call(label,'crd_impayes','POST',body)
            if raw and summary['cases'][-1]['result'] == 'PASS':
                portfolios.extend(normalize_cbs_credit_rows(raw))
        loans = []
        clients = [supplied_client] if supplied_client else []
        for item in portfolios:
            ref = item.get('ref_demande') or item.get('loan_ref')
            code = item.get('code_adherent')
            if ref and code and not any(row['refDemande']==ref for row in loans):
                loans.append({'refDemande':ref,'codeAdherent':code})
            if code and code not in clients:
                clients.append(code)
        if not clients:
            for client in Client.all_tenants.filter(tenant_id=tenant.pk).exclude(cbs_client_id='').order_by('-cbs_synced_at')[:20]:
                situation = client.cbs_situation or {}
                simulated = situation.get('simulated') or (situation.get('raw') or {}).get('simulated')
                if client.cbs_synced_at and not simulated:
                    clients.append(client.cbs_client_id)
                if len(clients)>=2:
                    break
        for index,code in enumerate(clients[:2],1):
            call(f'client-existing-{index}','adh_situation','POST',{'codeAdherent':code})
        if client_only and supplied_client:
            raw = call('loan-client-only','crd_situation','POST',{'codeAdherent':supplied_client})
            if raw:
                for item in normalize_cbs_credit_rows(raw):
                    ref = item.get('ref_demande') or item.get('loan_ref')
                    if ref:
                        loans.append({'refDemande':ref,'codeAdherent':supplied_client})
        for index,payload in enumerate(loans[:2],1):
            call(f'loan-existing-{index}','crd_situation','POST',payload)
        if not clients:
            summary['blocked'].append({'case':'adh_situation-valid','reason':'No non-simulated client fixture available.'})
        if not loans:
            summary['blocked'].append({'case':'crd_situation-valid','reason':'No real loan/client reference pair returned by the portfolio.'})
        if not client_only:
            marker = 'UAT-NOT-FOUND-' + uuid.uuid4().hex[:10]
            call('client-missing-fields','adh_situation','POST',{},expected='rejection')
            call('client-unknown','adh_situation','POST',{'codeAdherent':marker},expected='rejection')
            call('loan-missing-fields','crd_situation','POST',{},expected='rejection')
            call('loan-unknown','crd_situation','POST',{'refDemande':marker,'codeAdherent':marker},expected='rejection')
            call('credit-creation-options','crd_simple','OPTIONS',expected='discovery_only')
        # A preparation artifact only: never send a financial creation request.
        def first_id(key):
            rows = refs.get(key) or []
            return next((str(r['id']) for r in rows if isinstance(r,dict) and r.get('id')),None)
        draft = {'state':'DRAFT_REQUIRES_REVIEW_NOT_SENT','endpoint':endpoints['crd_simple'],
                 'externalId':'UAT-FINFLOW-' + run_id,'callbackUrl':None,
                 'codeAdherent':clients[0] if clients else None,
                 'idPointService':first_id('ref_point_service_list'),
                 'idPeriodicite':None,'taux':None,'nombreEcheance':None,
                 'idObjetFinancement':first_id('ref_object_fin_list'),
                 'idGestionnaire':first_id('ref_gestionnaire_list'),
                 'idProduitCrd':None,'idProduitRemb':None,'montantDemande':None,'codeDevise':None,
                 'review_required':['Confirm the client is an authorized fictitious UAT borrower.',
                                    'Select valid CBS credit/repayment products and compatible financing terms.',
                                    'Validate amount, rate, currency, number of installments and callback URL.',
                                    'Review the completed dossier before any creation call.']}
        save(out / 'draft-credit-for-review.json',draft)
        summary['blocked'].append({'case':'crd_simple-POST','reason':'Financial creation pending review of the fictitious UAT dossier; OPTIONS is not proof of creation.'})
        for key in endpoints:
            if key not in {c['endpoint_key'] for c in summary['cases']}:
                summary['blocked'].append({'case':key,'reason':'Configured endpoint requires a documented method and purpose before invocation.'})
    finally:
        summary['finished_at'] = datetime.now(timezone.utc).isoformat()
        flush()
        session.close()
        manifest = []
        for path in sorted(out.rglob('*.json')):
            manifest.append({'file':str(path.relative_to(out)), 'sha256':hashlib.sha256(path.read_bytes()).hexdigest(), 'bytes':path.stat().st_size})
        save(out / 'manifest.json',manifest)
        print('ARTIFACT_DIRECTORY=' + str(out),flush=True)


main()
