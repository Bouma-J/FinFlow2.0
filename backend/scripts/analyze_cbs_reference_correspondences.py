"""Offline field checks against the saved live audit and actual UAT dossier."""
import json
import os
import re
from pathlib import Path
from unittest.mock import patch
from requests import Response
from apps.common.tenancy import tenant_context
from apps.corebanking.services import RestAdapter, resolve_active_connector, OP_GET_CLIENT_OUTSTANDING
from apps.catalog.cbs_resolve import application_cbs_refs
from apps.catalog.models import FinancingObject
from apps.credits.models import CreditApplication
from apps.clients.models import Client

out=Path.cwd()/os.environ.get('CBS_UAT_OUTPUT','uat-artifacts/journey-AG0100053-20261020')
state=json.loads((out/'execution-state.json').read_text(encoding='utf-8'))
app=CreditApplication.all_tenants.get(pk=state['application_id'])
connector=resolve_active_connector(app.tenant_id)
source=json.loads((out/'genuine-CBS-client.json').read_text(encoding='utf-8'))
payload=json.loads((out/'setup-payload-preview.json').read_text(encoding='utf-8'))
def save(name,v):
    (out/name).write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
ui_source=(Path.cwd()/'frontend/src/components/CreditApplicationForm.tsx').read_text(encoding='utf-8')
mapping_block=re.search(r'const PURPOSE_FROM_CBS_CODE[^=]*=\s*\{(.*?)\};',ui_source,re.S).group(1)
mapping=dict(re.findall(r'(\w+):\s*"([A-Z_]+)"',mapping_block))
objects=list(FinancingObject.all_tenants.filter(tenant_id=app.tenant_id,is_active=True).order_by('sort_order','label').values('id','code','label','cbs_code','purpose_type'))
inferred=[{'source_id':r['cbs_code'],'label':r['label'],'form_value':(r['purpose_type'] or '').strip().upper() or mapping.get(r['code'].strip().upper(),'OTHER')} for r in objects]
seen=set();options=[]
for row in inferred:
    if row['form_value'] not in seen:options.append(row);seen.add(row['form_value'])
ui={'source_count':len(objects),'option_count_after_form_dedup':len(options),'options':options,'all_rows':inferred,
    'connector_consumption_mapping':connector.mapping_rules.get('disbursement',{}).get('purpose_map',{}).get('CONSUMPTION')}
save('ui-purpose-options-offline.json',ui)
with tenant_context(app.tenant_id):refs=application_cbs_refs(app)
save('application-cbs-refs.json',refs)
cases=[]
for name,body in [('business_409',{'responseCode':409,'message':'UAT reference denied','datas':None}),('malformed_envelope',{'unexpected':'UAT'}),('empty_valid',{'responseCode':200,'datas':[]})]:
    response=Response();response.status_code=200;response._content=json.dumps(body).encode('utf-8')
    with patch.object(RestAdapter,'_resolve_bearer_token',return_value='OFFLINE-NO-NETWORK'),patch.object(RestAdapter,'_http_get',return_value=response):
        try:cases.append({'case':name,'returned':RestAdapter(connector).fetch_ref_list('ref_devise_list'),'raised':False})
        except Exception as exc:cases.append({'case':name,'raised':True,'error':str(exc)})
save('reference-parser-negative-offline.json',cases)
with patch('requests.get') as blocked_get,patch('requests.post') as blocked_post:
    encours=RestAdapter(connector).send(OP_GET_CLIENT_OUTSTANDING,{'cbs_client_id':'AG0100053','currency':'XOF'})
    save('outstanding-rest-fallback-offline.json',{'response':encours,'http_get_calls':blocked_get.call_count,'http_post_calls':blocked_post.call_count})
client=Client.all_tenants.get(pk=state['client_id'])
field_rows=[]
for key,value in source.items():
    if key=='raw':continue
    empty=value is None or value==''
    field_rows.append({'normalized_field':key,'value':value,'present':not empty})
save('client-source-all-fields.json',field_rows)
agreements={
    'codeAdherent_matches_source':payload['codeAdherent']==source['code_adherent'],
    'numManuel_matches_source':payload['numManuel']==source['num_manuel'],
    'point_service_matches_source':payload['idPointService']==source['id_point_service'],
    'account_is_not_adherent_code':payload['numManuel']!=payload['codeAdherent'],
    'registration_date_retained':str(client.cbs_registration_date)==source['date_inscription'],
    'native_identity_is_marked_synthetic':client.national_id.startswith('UAT-'),
    'credit_limit_not_coerced_to_zero':source['limit_credit'] is None and client.cbs_credit_limit is None,
    'expected_monthly_periodicity':payload['idPeriodicite']=='M',
    'expected_installment_count':payload['nombreEcheance']==3,
    'expected_currency':payload['codeDevise']=='FCFA',
    'no_numeric_product_identifiers':not str(payload['idProduitCrd']).isdigit() and not str(payload['idProduitRemb']).isdigit(),
}
save('correspondence-checks.json',agreements)
print(json.dumps({'ui_options':options,'cbs_ready':refs.get('ready_for_cbs'),'cbs_warnings':refs.get('warnings'),'offline_parser':cases,'field_checks':agreements},ensure_ascii=False,indent=2))
