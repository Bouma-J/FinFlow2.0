"""Import live CBS reference data via the normal API and check client completeness.

Transport uses verified system trust and 3-second spacing. Business permissions,
import validation and KYC requirements are not patched or relaxed.
"""
import json
import ssl
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import requests
from requests.adapters import HTTPAdapter
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.catalog.models import (
    Currency, LoanPeriodicity, FinancingObject, FinancingSource, DecisionMotif,
    CbsProfession, ServicePoint, CbsManager,
)
from apps.corebanking.services import RestAdapter, resolve_active_connector
from apps.tenants.models import Tenant


class SystemTrustAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        kwargs['ssl_context'] = ssl.create_default_context()
        return super().init_poolmanager(*args, **kwargs)


def main():
    tenant = Tenant.objects.get(code='FIL01')
    connector = resolve_active_connector(tenant.pk)
    actor = User.objects.get(username='fil01_admin',tenant=tenant,is_active=True)
    directory = Path('uat-artifacts') / ('journey-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    directory.mkdir(parents=True)
    (directory/'responses').mkdir()
    secret_keys={'password','username','token','access_token','accessToken','refresh_token','Authorization','authorization'}
    secret_values=[str(v) for k,v in connector.get_auth_config_decrypted().items() if v and k in secret_keys]
    def clean(value):
        if isinstance(value,dict):
            return {k:'[REDACTED]' if k in secret_keys else clean(v) for k,v in value.items()}
        if isinstance(value,list): return [clean(v) for v in value]
        if isinstance(value,str):
            for secret in sorted(secret_values,key=len,reverse=True): value=value.replace(secret,'[REDACTED]')
        return value
    def save(name,value):
        (directory/name).write_text(json.dumps(clean(value),ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    save('reference-backup.json',{model._meta.label:list(model.all_tenants.filter(tenant=tenant).values()) for model in
        (Currency,LoanPeriodicity,FinancingObject,FinancingSource,DecisionMotif,CbsProfession,ServicePoint,CbsManager)})
    session=requests.Session()
    session.mount('https://',SystemTrustAdapter(max_retries=0))
    last_end=None
    remote=[]
    def call(method,url,**kwargs):
        nonlocal last_end
        if last_end is not None: time.sleep(max(0,3-(time.monotonic()-last_end)))
        kwargs['verify']=True
        kwargs['allow_redirects']=False
        kwargs['timeout']=(8,25)
        result=session.request(method,url,**kwargs)
        last_end=time.monotonic()
        raw=result.json() if result.content else None
        if isinstance(raw,dict):
            returned=raw.get('accessToken') or raw.get('access_token') or raw.get('token')
            if returned: secret_values.append(str(returned))
        index=len(remote)+1
        name=f'responses/{index:02d}.json'
        save(name,raw)
        remote.append({'method':method,'url':url,'http':result.status_code,'response_file':name})
        print(f'CBS {index}: HTTP {result.status_code}',flush=True)
        if result.status_code==429: raise RuntimeError('Rate limited; stopped without retry.')
        return result
    original_token=RestAdapter._resolve_bearer_token
    cached={}
    def token(adapter):
        if 'token' not in cached: cached['token']=original_token(adapter)
        return cached['token']
    api=APIClient()
    api.force_authenticate(actor)
    headers={'HTTP_X_TENANT_ID':str(tenant.pk),'HTTP_HOST':'localhost'}
    outcomes={}
    try:
        with patch('requests.get',lambda url,**kw:call('GET',url,**kw)), \
             patch('requests.post',lambda url,**kw:call('POST',url,**kw)), \
             patch.object(RestAdapter,'_resolve_bearer_token',token):
            result=api.post(f'/api/v1/cbs-connectors/{connector.pk}/sync-referentials/',{},format='json',**headers)
            outcomes['reference_sync']={'http':result.status_code,'body':result.data}
            save('reference-sync-api.json',outcomes['reference_sync'])
            print(f'Reference sync API: HTTP {result.status_code}',flush=True)
    finally:
        save('remote-calls.json',remote)
        save('summary.json',outcomes)
        session.close()
        print('ARTIFACT_DIRECTORY='+str(directory.resolve()),flush=True)


main()
