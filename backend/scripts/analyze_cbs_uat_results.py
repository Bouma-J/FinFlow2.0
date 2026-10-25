"""Offline analysis of captured CBS responses. No network or business writes."""
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import requests

from apps.catalog.models import (
    Currency, LoanPeriodicity, FinancingObject, FinancingSource,
    DecisionMotif, CbsProfession, ServicePoint, CbsManager, CreditProduct,
)
from apps.accounts.models import User
from apps.clients.cbs_services import collect_cbs_import_issues
from apps.corebanking.services import (
    CoreBankingError, RestAdapter, _is_paid_schedule_status,
    OP_GET_CLIENT_OUTSTANDING, resolve_active_connector,
)
from apps.tenants.models import Tenant, Agency

root = Path.cwd() / 'uat-artifacts'
runs = []
for path in sorted(root.glob('cbs-*')):
    if (path / 'results.json').exists():
        runs.append((path, json.loads((path/'results.json').read_text(encoding='utf-8'))))
base_path, base = next((p,r) for p,r in reversed(runs) if r.get('scope','full_read_only')=='full_read_only')
client_path, client_run = next((p,r) for p,r in reversed(runs) if r.get('scope')=='client_supplement')
tenant = Tenant.objects.get(code=base['tenant'])
connector = resolve_active_connector(tenant.pk)
adapter = RestAdapter(connector)

def read_case(run_path, run, name, field='response_file'):
    case = next(c for c in run['cases'] if c['case']==name)
    return json.loads((run_path / case[field]).read_text(encoding='utf-8'))

def save(name, value):
    (base_path/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str),encoding='utf-8')

catalogs = {}
catalog_checks = []
for key, model, id_field in (
    ('ref_devise_list',Currency,'code'),('ref_periodicite_list',LoanPeriodicity,'id'),
    ('ref_object_fin_list',FinancingObject,'id'),('ref_source_fin_list',FinancingSource,'id'),
    ('ref_motif_decision_list',DecisionMotif,'id'),('ref_profession_list',CbsProfession,'id'),
    ('ref_point_service_list',ServicePoint,'id'),('ref_gestionnaire_list',CbsManager,'id'),
):
    rows = read_case(base_path,base,key.replace('_','-'),'normalized_file')
    catalogs[key] = rows
    remote_ids = {str(r[id_field]) for r in rows}
    local_ids = list(model.all_tenants.filter(tenant=tenant,is_active=True).values_list('cbs_code',flat=True))
    catalog_checks.append({'catalog':key,'remote_rows':len(rows),'local_active_rows':len(local_ids),
        'local_codes_matching_remote':sum(bool(v) and v in remote_ids for v in local_ids),
        'local_codes_missing':sum(not v for v in local_ids),
        'local_codes_not_in_response':sum(bool(v) and v not in remote_ids for v in local_ids)})
raw_client = read_case(client_path,client_run,'client-existing-1')
mapped_client = read_case(client_path,client_run,'client-existing-1','normalized_file')['client_mapping']
client_quality = {
    'raw_fields':list(raw_client), 'normalized_fields':list(mapped_client),
    'name_present':bool(mapped_client['full_name']),
    'CBS_validation_flag':mapped_client['est_valide'],
    'credit_limit_available':mapped_client['limit_credit'] is not None,
    'service_point_known':mapped_client['id_point_service'] in {r['id'] for r in catalogs['ref_point_service_list']},
    'individual_import_issues':collect_cbs_import_issues(mapped_client,'INDIVIDUAL'),
    'corporate_import_issues':collect_cbs_import_issues(mapped_client,'CORPORATE'),
    'note':'Client type not inferred from the aggregate name. Import requirements depend on the selected legal profile.',
}
checks=[]
for status in ('Impayé','Non payé','unpaid','Partiellement payé','Payé','En attente'):
    expected = status == 'Payé'
    actual = _is_paid_schedule_status(status)
    checks.append({'check':'paid_status_'+status,'expected_paid':expected,'actual_paid':actual,
                   'result':'PASS' if expected==actual else 'FAIL'})

def response(body):
    value = requests.Response()
    value.status_code=200
    value._content=json.dumps(body).encode()
    value.headers['Content-Type']='application/json'
    value.url=connector.base_url+'/offline-replay'
    return value

for name, body, key, payload in (
    ('reference_business_error_HTTP200',{'responseCode':409,'message':'UAT business error','datas':None},'ref_devise_list',{}),
    ('client_nonnumeric_business_code',{'responseCode':'INVALID','message':'UAT invalid code'},'adh_situation',{'codeAdherent':'OFFLINE'}),
    ('loan_unknown_schema_zero_balance',{'responseCode':200,'datas':[{'unrecognized':True}]},'crd_situation',{'refDemande':'OFFLINE','codeAdherent':'OFFLINE'}),
):
    with patch.object(adapter,'_resolve_bearer_token',return_value='OFFLINE'), \
         patch.object(adapter,'_http_get',return_value=response(body)), \
         patch.object(adapter,'_http_post',return_value=response(body)):
        try:
            if key.startswith('ref_'):
                value=adapter.fetch_ref_list(key)
            elif key=='adh_situation':
                value=adapter._adh_situation(payload)
            else:
                value=adapter._crd_situation(payload)
            checks.append({'check':name,'result':'FAIL','expected':'CoreBankingError',
                           'actual':'accepted','accepted_empty_rows':value==[],
                           'settled':value.get('settled') if isinstance(value,dict) else None})
        except Exception as exc:
            checks.append({'check':name,'result':'PASS' if isinstance(exc,CoreBankingError) else 'FAIL',
                           'exception_type':type(exc).__name__})
value=adapter.send(OP_GET_CLIENT_OUTSTANDING,{'cbs_client_id':'OFFLINE','currency':'XOF'})
checks.append({'check':'unimplemented_outstanding_operation','result':'FAIL' if value.get('raw',{}).get('simulated') else 'PASS',
               'simulated':value.get('raw',{}).get('simulated'),'amount':value.get('total_outstanding'),
               'note':'Offline adapter dispatch only; not a live CBS endpoint call.'})

product=CreditProduct.all_tenants.filter(tenant=tenant,is_active=True).exclude(cbs_product_code='').first()
monthly=next((r for r in catalogs['ref_periodicite_list'] if r['code'].upper()=='M' or 'MENS' in r['code'].upper()),None)
currency=next((r for r in catalogs['ref_devise_list'] if r['code'].upper() in ('XOF','FCFA')),None)
draft={
    'state':'DRAFT_FOR_REVIEW_NOT_EXECUTABLE_AS_IS',
    'payload':{
        'externalId':'UAT-FINFLOW-'+base['run_id'], 'callbackUrl':None,
        'codeAdherent':mapped_client['code_adherent'],
        'idPointService':mapped_client['id_point_service'],
        'idPeriodicite':monthly['id'] if monthly else None,
        'taux':str(product.interest_rate) if product else None,
        'nombreEcheance':max(1,product.duration_min_months) if product and monthly else None,
        'idObjetFinancement':None,
        'idGestionnaire':None,
        'idProduitCrd':product.cbs_product_code if product else None,
        'idProduitRemb':product.cbs_repayment_product_code if product else None,
        'montantDemande':str(product.amount_min) if product else None,
        'codeDevise':currency['code'] if currency else None,
    },
    'sources':{'client_and_service_point':'live client response','periodicity_and_currency':'live reference responses',
               'amount_rate_duration_products':'local active credit product, not yet validated against live CBS products'},
    'review_required':['Validate the fictitious borrower dossier and missing KYC data.',
        'Provide a CBS-reachable callback URL and its security configuration.',
        'Select the financing purpose and authorized manager; validate CBS product identifiers.',
        'Approve the amount, rate, installments and currency before a financial creation call.'],
}
save('draft-credit-for-review.json',draft)
analysis={'source_runs':[base['run_id'],client_run['run_id']],
    'live_call_count':sum(len(r['cases']) for p,r in [(base_path,base),(client_path,client_run)]),
    'minimum_recorded_pause_seconds':min(c['gap_since_previous_end_seconds'] for p,r in [(base_path,base),(client_path,client_run)] for c in r['cases'] if c.get('gap_since_previous_end_seconds') is not None),
    'reference_count':9,'reference_rows_total':sum(c.get('normalized_rows',0) for c in base['cases'] if c['endpoint_key'].startswith('ref_') and c.get('bearer_present')),
    'catalog_consistency':catalog_checks,'client_quality':client_quality,'offline_checks':checks}
save('offline-analysis.json',analysis)
for directory in (base_path,client_path):
    manifest=[{'file':str(p.relative_to(directory)), 'sha256':hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes':p.stat().st_size}
              for p in sorted(directory.rglob('*.json')) if p.name!='manifest.json']
    (directory/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(json.dumps({'live_calls':analysis['live_call_count'],'reference_rows':analysis['reference_rows_total'],
    'individual_import_missing_count':len(client_quality['individual_import_issues']),
    'corporate_import_missing_count':len(client_quality['corporate_import_issues']),
    'catalog_consistency':catalog_checks,'offline_checks':checks},ensure_ascii=True))
