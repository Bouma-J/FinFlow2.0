"""Final access, catalog validation and read-only CBS checks for AG0100053."""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import requests
from rest_framework.test import APIClient
from apps.accounts.models import User
from apps.common.tenancy import tenant_context
from apps.corebanking.services import RestAdapter, resolve_active_connector
from apps.credits.models import CreditApplication
from apps.credits.serializers import CreditApplicationSerializer

out=Path.cwd()/os.environ.get('CBS_UAT_OUTPUT','uat-artifacts/journey-AG0100053-20261020')
state=json.loads((out/'execution-state.json').read_text(encoding='utf-8'))
app=CreditApplication.all_tenants.get(pk=state['application_id'])
connector=resolve_active_connector(app.tenant_id)
os.environ['REQUESTS_CA_BUNDLE']=str(Path.cwd()/'backend/certs/cbs-system-trust.pem')
results={'catalog_validation':[],'role_reads':[],'cbs_reads':[],'remote_calls':[]}
def save():
    (out/'final-controls.json').write_text(json.dumps(results,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
with tenant_context(app.tenant_id):
    serializer=CreditApplicationSerializer()
    for field,value in [('periodicity','UAT-UNKNOWN'),('repayment_mechanism','UAT-UNKNOWN'),('currency','ZZZ')]:
        try:
            serializer._validate_catalog_refs({field:value},app.tenant_id)
            results['catalog_validation'].append({'field':field,'rejected':False})
        except Exception as exc:
            results['catalog_validation'].append({'field':field,'rejected':True,'detail':str(exc)})
routes=['loan-periodicities','currencies','financing-objects','service-points','cbs-managers','financing-sources','decision-motifs','cbs-professions','repayment-methods']
for role in ('charge','lecteur'):
    client=APIClient();client.force_authenticate(User.objects.get(tenant_id=app.tenant_id,username='fil01_'+role))
    for route in routes:
        r=client.get(f'/api/v1/{route}/?is_active=true&page_size=50',HTTP_HOST='localhost',HTTP_X_TENANT_ID=str(app.tenant_id))
        results['role_reads'].append({'role':role,'route':route,'http':r.status_code,'count':getattr(r,'data',{}).get('count')})
    r=client.get(f'/api/v1/credit-applications/{app.pk}/readiness/',HTTP_HOST='localhost',HTTP_X_TENANT_ID=str(app.tenant_id))
    (out/('readiness-final-'+role+'.json')).write_text(json.dumps({'http':r.status_code,'body':getattr(r,'data',{})},ensure_ascii=False,indent=2,default=str),encoding='utf-8')
session=requests.Session();last_end=None
def remote(method,url,**kw):
    global last_end
    if last_end is not None:time.sleep(max(0,3-(time.monotonic()-last_end)))
    start=time.monotonic();gap=None if last_end is None else start-last_end
    kw.update(verify=True,timeout=(8,25),allow_redirects=False)
    response=session.request(method,url,**kw);last_end=time.monotonic()
    body=response.json() if response.content else None
    if isinstance(body,dict):
        body={k:'[REDACTED]' if k.lower() in ('accesstoken','access_token','token','refreshtoken','refresh_token') else v for k,v in body.items()}
    results['remote_calls'].append({'method':method,'url':url,'http':response.status_code,'body':body,'gap_seconds':gap,'time_utc':datetime.now(timezone.utc).isoformat()})
    save()
    print(f'CBS READ {url.split(".pro")[-1]}: {response.status_code}',flush=True)
    if response.status_code==429:raise RuntimeError('Rate limited; stopped')
    return response
adapter=RestAdapter(connector)
with patch('requests.post',lambda url,**kw:remote('POST',url,**kw)),patch('requests.get',lambda url,**kw:remote('GET',url,**kw)):
    bearer=adapter._resolve_bearer_token()
    with patch.object(RestAdapter,'_resolve_bearer_token',return_value=bearer):
        for name,fn,args in [('portfolio',adapter._crd_impayes,{}),('unknown_loan_situation',adapter._crd_situation,{'codeAdherent':'AG0100053','refDemande':'UAT-AG0100053-UNKNOWN'})]:
            try:results['cbs_reads'].append({'case':name,'result':fn(args)})
            except Exception as exc:results['cbs_reads'].append({'case':name,'error':str(exc)})
            save()
session.close();save()
print(json.dumps({'catalog_validation':results['catalog_validation'],'role_read_statuses':sorted(set(r['http'] for r in results['role_reads'])),'cbs_reads':results['cbs_reads']},ensure_ascii=False,indent=2))
