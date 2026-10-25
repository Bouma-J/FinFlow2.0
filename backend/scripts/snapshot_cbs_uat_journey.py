"""Save read-only end-state evidence for the in-progress UAT dossier."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import requests
from rest_framework.test import APIClient
from apps.accounts.models import User
from apps.corebanking.models import IntegrationLog
from apps.credits.models import CreditApplication, Loan
from apps.tenants.models import Tenant

out = Path.cwd() / os.environ.get('CBS_UAT_OUTPUT','uat-artifacts/journey-20261020T223709Z')
state = json.loads((out / 'execution-state.json').read_text(encoding='utf-8'))
tenant = Tenant.objects.get(code='FIL01')
app = CreditApplication.all_tenants.get(pk=state['application_id'])
api = APIClient()
api.force_authenticate(User.objects.get(username='fil01_operations', tenant=tenant))
detail = api.get(f'/api/v1/credit-applications/{app.pk}/', HTTP_HOST='localhost', HTTP_X_TENANT_ID=str(tenant.pk))
def save(name, data):
    (out / name).write_text(json.dumps(data,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
save('final-dossier-api.json', {'http':detail.status_code,'body':getattr(detail,'data',None)})
logs = list(IntegrationLog.all_tenants.filter(tenant=tenant,idempotency_key=f'disburse:{app.pk}').values(
    'id','operation','status','attempts','external_reference','error_message','request_payload','response_payload','updated_at'))
save('final-disbursement-journal.json',logs)
health=[]
for url in ('http://127.0.0.1:8000/api/v1/health/', 'http://127.0.0.1:5173/'):
    try:
        response=requests.get(url,timeout=8)
        health.append({'url':url,'http':response.status_code,'content_type':response.headers.get('Content-Type'),'bytes':len(response.content)})
    except requests.RequestException as exc:
        health.append({'url':url,'error':str(exc)})
summary={'checked_at':datetime.now(timezone.utc).isoformat(),'application_reference':app.reference,
    'application_id':str(app.pk),'status':app.status,'local_loan_count':Loan.all_tenants.filter(application=app).count(),
    'detail_http':detail.status_code,'journal':[ {k:v for k,v in row.items() if k not in ('request_payload','response_payload')} for row in logs],
    'health':health}
save('final-state.json',summary)
print(json.dumps(summary,ensure_ascii=False,indent=2,default=str))
