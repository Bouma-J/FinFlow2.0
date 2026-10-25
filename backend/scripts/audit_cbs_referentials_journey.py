"""Sequential live audit of reference imports, UI APIs and a new UAT client.

Runs via manage.py shell. Mutations are restricted to normal reference sync;
all negative validation probes are expected to fail without saving changes.
"""
import json
import os
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import requests
from rest_framework.test import APIClient
from apps.accounts.models import User
from apps.catalog import models as catalog
from apps.catalog.serializers import CreditProductSerializer
from apps.clients.models import Client
from apps.common.tenancy import tenant_context
from apps.corebanking.perfect_defaults import PERFECT_ENDPOINTS
from apps.corebanking.services import RestAdapter, resolve_active_connector
from apps.tenants.models import Tenant, Agency


def main():
    root=Path.cwd()
    code=os.environ.get('CBS_UAT_CLIENT_CODE','AG0100053')
    relative=os.environ.get('CBS_UAT_OUTPUT','uat-artifacts/journey-AG0100053-20261020')
    out=root/relative;out.mkdir(parents=True,exist_ok=True)
    (out/'responses').mkdir(exist_ok=True)
    os.environ['REQUESTS_CA_BUNDLE']=str(root/'backend/certs/cbs-system-trust.pem')
    tenant=Tenant.objects.get(code='FIL01')
    connector=resolve_active_connector(tenant.pk)
    actors={r:User.objects.get(tenant=tenant,username='fil01_'+r) for r in ('admin','charge','lecteur')}
    scopes={
        'currencies':(catalog.Currency,'currencies','ref_devise_list'),
        'periodicities':(catalog.LoanPeriodicity,'loan-periodicities','ref_periodicite_list'),
        'financing_objects':(catalog.FinancingObject,'financing-objects','ref_object_fin_list'),
        'service_points':(catalog.ServicePoint,'service-points','ref_point_service_list'),
        'managers':(catalog.CbsManager,'cbs-managers','ref_gestionnaire_list'),
        'financing_sources':(catalog.FinancingSource,'financing-sources','ref_source_fin_list'),
        'decision_motifs':(catalog.DecisionMotif,'decision-motifs','ref_motif_decision_list'),
        'professions':(catalog.CbsProfession,'cbs-professions','ref_profession_list'),
    }
    def clean(v):
        if isinstance(v,dict):return {k:'[REDACTED]' if k.lower() in {'authorization','password','accesstoken','access_token','token','refreshtoken','refresh_token','callback_secret'} else clean(x) for k,x in v.items()}
        if isinstance(v,(list,tuple)):return [clean(x) for x in v]
        return v
    def save(name,v):
        (out/name).write_text(json.dumps(clean(v),ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    def snapshot():
        return {s:list(m.all_tenants.filter(tenant=tenant).order_by('code').values('id','code','label','cbs_code','is_active',*(['periods_per_year'] if s=='periodicities' else ['purpose_type'] if s=='financing_objects' else []))) for s,(m,_,_) in scopes.items()}
    save('references-before.json',snapshot())
    api_calls=[];remote=[];last_end=None;cached={};raw_refs={};session=requests.Session()
    def local(role,method,path,data=None):
        api=APIClient();api.force_authenticate(actors[role])
        response=getattr(api,method)(path,data or {},format='json',HTTP_HOST='localhost',HTTP_X_TENANT_ID=str(tenant.pk))
        item={'actor':actors[role].username,'method':method,'path':path,'http':response.status_code,'body':getattr(response,'data',None)}
        api_calls.append(item);save('local-audit-calls.json',api_calls)
        print(f'LOCAL {role} {method.upper()} {path}: {response.status_code}',flush=True)
        return item
    def request(method,url,**kw):
        nonlocal last_end
        gap=None if last_end is None else time.monotonic()-last_end
        if gap is not None:time.sleep(max(0,3-gap))
        started=time.monotonic();actual_gap=None if last_end is None else started-last_end
        kw.update(timeout=(8,25),verify=True,allow_redirects=False)
        response=session.request(method,url,**kw);last_end=time.monotonic()
        try:body=response.json()
        except ValueError:body={'non_json_preview':response.text[:1000]}
        filename=f'responses/{len(remote)+1:02d}.json'
        save(filename,body)
        remote.append({'method':method,'url':url,'http':response.status_code,'gap_seconds':actual_gap,'elapsed_seconds':last_end-started,'response_file':filename,'time_utc':datetime.now(timezone.utc).isoformat()})
        save('remote-calls.json',remote)
        for key,path in PERFECT_ENDPOINTS.items():
            if key.startswith('ref_') and url.endswith('/'+path):raw_refs[key]=body
        print(f'CBS {method} {url.split(".pro")[-1]}: {response.status_code}',flush=True)
        if response.status_code==429:raise RuntimeError('HTTP 429; stopped without retry')
        return response
    original_token=RestAdapter._resolve_bearer_token
    def token(adapter):
        if 'value' not in cached:cached['value']=original_token(adapter)
        return cached['value']
    summary={'client_code':code,'started_utc':datetime.now(timezone.utc).isoformat(),'scopes':{},'local_checks':{},'synthetic_complements_authorized_in_session':True}
    try:
        with patch('requests.get',lambda url,**kw:request('GET',url,**kw)),patch('requests.post',lambda url,**kw:request('POST',url,**kw)),patch.object(RestAdapter,'_resolve_bearer_token',token):
            first=local('admin','post',f'/api/v1/cbs-connectors/{connector.pk}/sync-referentials/')
            save('sync-first.json',first)
            after_first=snapshot();save('references-after-first.json',after_first)
            second=local('admin','post',f'/api/v1/cbs-connectors/{connector.pk}/sync-referentials/')
            save('sync-second.json',second)
            after_second=snapshot();save('references-after-second.json',after_second)
            summary['idempotent_reference_rows']=after_first==after_second
            summary['sync_first_http']=first['http'];summary['sync_second_http']=second['http']
            for scope,(model,route,key) in scopes.items():
                original=raw_refs.get(key,{})
                rows=original.get('datas') or []
                active=[r for r in after_second[scope] if r['is_active']]
                expected=[str(r.get('code') if scope=='currencies' else r.get('id')) for r in rows]
                local_ids=[r['cbs_code'] for r in active]
                seen=Counter(str(r.get('id')) for r in rows)
                fields=sorted(set().union(*(set(r) for r in rows))) if rows else []
                list_api=local('admin','get',f'/api/v1/{route}/?is_active=true&page_size=50')
                body=list_api['body'] or {};api_rows=list(body.get('results',[]));page=2
                while body.get('next'):
                    page_result=local('admin','get',f'/api/v1/{route}/?is_active=true&page_size=50&page={page}')
                    body=page_result['body'] or {};api_rows+=body.get('results',[]);page+=1
                    if page>10:raise RuntimeError('Unexpected pagination size')
                neg=None
                if active:neg=local('admin','patch',f'/api/v1/{route}/{active[0]["id"]}/',{'label':active[0]['label']})['http']
                summary['scopes'][scope]={'source_rows':len(rows),'business_code':original.get('responseCode'),'source_fields':fields,'source_null':original.get('datas') is None,'duplicates':[v for v,n in seen.items() if n>1],'missing_id_code_label':[i for i,r in enumerate(rows) if any(r.get(k) in (None,'') for k in ('id','code','libelle'))],'local_active_rows':len(active),'source_ids_not_local':sorted(set(expected)-set(local_ids)),'local_ids_not_source':sorted(set(local_ids)-set(expected)),'api_rows_all_pages':len(api_rows),'api_count':list_api['body'].get('count') if isinstance(list_api['body'],dict) else None,'api_first_page_http':list_api['http'],'patch_readonly_http':neg}
            methods=local('admin','get','/api/v1/repayment-methods/?page_size=100')
            save('repayment-methods-manual.json',methods)
            summary['manual_repayment_methods']=methods['body']
            summary['local_checks']['charge_sync_http']=local('charge','post',f'/api/v1/cbs-connectors/{connector.pk}/sync-referentials/')['http']
            adapter=RestAdapter(connector)
            identity=adapter.fetch_ref_list('ref_type_piece_identite_list',default_path=PERFECT_ENDPOINTS['ref_type_piece_identite_list'])
            save('identity-types-not-imported.json',identity)
            summary['identity_type_count_without_sync_scope']=len(identity)
            params={'client_type':'INDIVIDUAL','code_adherent':code}
            preview=local('charge','post','/api/v1/clients/cbs-preview/',params)
            save('client-preview-api.json',preview)
            summary['preview_http']=preview['http']
            summary['client_can_import']=(preview['body'] or {}).get('can_import')
            summary['client_missing_required']=(preview['body'] or {}).get('missing_required')
            if preview['http']==200 and not summary['client_can_import']:
                imported=local('charge','post','/api/v1/clients/cbs-import/',params)
                save('client-strict-import.json',imported)
                summary['strict_import_http']=imported['http']
            elif preview['http']==200:
                summary['strict_import_pending_journey']=True
            summary['existing_client_ids']=list(Client.all_tenants.filter(tenant=tenant,cbs_client_id=code).values_list('id',flat=True))
            charge=actors['charge']
            if charge.agency_id:
                summary['local_checks']['unknown_service_point_http']=local('admin','patch',f'/api/v1/agencies/{charge.agency_id}/',{'cbs_point_of_service_id':'UAT-NONEXISTENT-SERVICE-POINT'})['http']
            summary['local_checks']['unknown_manager_http']=local('admin','patch',f'/api/v1/users/{charge.pk}/',{'cbs_id':'UAT-NONEXISTENT-MANAGER'})['http']
            with tenant_context(tenant.pk):
                product=catalog.CreditProduct.objects.get(code='CONSO-STD')
                probe=CreditProductSerializer(product,data={'cbs_product_code':'UAT-NONEXISTENT-PRODUCT'},partial=True)
                summary['local_checks']['unknown_product_serializer_accepts']=probe.is_valid()
                summary['local_checks']['unknown_product_serializer_errors']=probe.errors
            save('products-for-setup.json',list(catalog.CreditProduct.all_tenants.filter(tenant=tenant).values('id','code','label','cbs_product_code','cbs_repayment_product_code','amount_min','amount_max','interest_rate','duration_min_months','duration_max_months','is_active')))
            save('agency-manager-mapping.json',{'agencies':list(Agency.objects.filter(tenant=tenant).values('id','code','cbs_point_of_service_id')),'users':list(User.objects.filter(tenant=tenant).values('username','agency_id','cbs_id'))})
            summary['financing_objects_without_purpose_type']=sum(not r.get('purpose_type') for r in after_second['financing_objects'] if r['is_active'])
            connector.refresh_from_db()
            save('connector-mapping.json',connector.mapping_rules)
    finally:
        summary['completed_utc']=datetime.now(timezone.utc).isoformat();summary['remote_call_count']=len(remote)
        summary['min_gap_seconds']=min((r['gap_seconds'] for r in remote if r['gap_seconds'] is not None),default=None)
        save('audit-summary.json',summary);session.close()
        print('ARTIFACT_DIRECTORY='+str(out.resolve()),flush=True)


main()
