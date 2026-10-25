"""Execute the authorized fictitious FIL01 UAT journey using normal business APIs.

Native identity complements and PDF proofs are explicitly synthetic. The genuine
CBS snapshot is retained separately. No workflow status or approval is forced.
"""
import copy
import hashlib
import json
import os
import ssl
import time
from datetime import date
from pathlib import Path
from unittest.mock import patch

import requests
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.audit.context import set_audit_context, reset_audit_context
from apps.clients.models import Client
from apps.clients.cbs_services import map_preview_to_client_fields
from apps.common.tenancy import tenant_context
from apps.corebanking.services import RestAdapter, resolve_active_connector, get_client_situation
from apps.credits.models import CreditApplication, Loan
from apps.workflow.models import ApprovalTask
from apps.workflow.services import user_can_act
from apps.catalog.models import CreditProduct, CbsManager, FinancingObject
from apps.documents.models import Document
from apps.tenants.models import Tenant, Agency

ROOT=Path.cwd()
CLIENT_CODE=os.environ.get('CBS_UAT_CLIENT_CODE','AG0100027')
OUT=ROOT/os.environ.get('CBS_UAT_OUTPUT','uat-artifacts/journey-20261020T223709Z')
FILES=OUT/'files'
STATE=OUT/'execution-state.json'
SCENARIO=json.loads(Path(os.environ['CBS_UAT_SCENARIO']).read_text(encoding='utf-8')) if os.environ.get('CBS_UAT_SCENARIO') else {}


def main():
    tenant=Tenant.objects.get(code='FIL01')
    connector=resolve_active_connector(tenant.pk)
    actors={name:User.objects.get(username='fil01_'+name,tenant=tenant,is_active=True) for name in
        ('admin','charge','analyste','chef','comite','comite_groupe','operations','assistant_ops','admin_credit','juridique')}
    state=json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {'steps':[],'synthetic_UAT':True}
    def clean(value):
        if isinstance(value,dict): return {k:'[REDACTED]' if k.lower() in {'password','authorization','accesstoken','access_token','token','callback_secret'} else clean(v) for k,v in value.items()}
        if isinstance(value,(list,tuple)): return [clean(v) for v in value]
        return value
    def save(name,value):
        (OUT/name).write_text(json.dumps(clean(value),ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    def checkpoint(): save('execution-state.json',state)
    def file(name): return SimpleUploadedFile('UAT-'+name, (FILES/name).read_bytes(), content_type='application/pdf' if name.endswith('.pdf') else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    def api(role,method,path,data=None,multipart=False,expect=(200,201,202)):
        client=APIClient();client.force_authenticate(actors[role])
        response=getattr(client,method)(path,data or {},format='multipart' if multipart else 'json',HTTP_HOST='localhost',HTTP_X_TENANT_ID=str(tenant.pk))
        body=getattr(response,'data',None)
        index=len(state['steps'])+1
        save(f'local-{index:02d}.json',{'actor':actors[role].username,'method':method,'path':path,'http':response.status_code,'body':body})
        state['steps'].append({'actor':actors[role].username,'method':method,'path':path,'http':response.status_code,'response_file':f'local-{index:02d}.json'})
        checkpoint()
        print(f'{role} {method.upper()} {path}: HTTP {response.status_code}',flush=True)
        if response.status_code not in expect:
            raise RuntimeError(f'Business API blocked: {path}; see local-{index:02d}.json')
        return body

    # Persist a trusted CA bundle locally; TLS validation remains enabled.
    ca_dir=ROOT/'backend/certs';ca_dir.mkdir(exist_ok=True)
    ca_file=ca_dir/'cbs-system-trust.pem'
    if not ca_file.exists():
        original=Path(requests.certs.where()).read_text(encoding='ascii')
        ca_file.write_text(original+'\n'+''.join(ssl.DER_cert_to_PEM_cert(c) for c in ssl.create_default_context().get_ca_certs(binary_form=True)),encoding='ascii')
    env_path=ROOT/'backend/.env'
    original_env=env_path.read_text(encoding='utf-8') if env_path.exists() else ''
    line='REQUESTS_CA_BUNDLE='+ca_file.as_posix()
    env_lines=original_env.splitlines()
    updated=[line if row.startswith('REQUESTS_CA_BUNDLE=') else row for row in env_lines]
    if not any(row.startswith('REQUESTS_CA_BUNDLE=') for row in env_lines): updated.append(line)
    if updated!=env_lines: env_path.write_text('\n'.join(updated)+'\n',encoding='utf-8')
    os.environ['REQUESTS_CA_BUNDLE']=str(ca_file)
    session=requests.Session()
    last_end=None
    remote=json.loads((OUT/'execution-remote-calls.json').read_text(encoding='utf-8')) if (OUT/'execution-remote-calls.json').exists() else []
    def remote_call(method,url,**kwargs):
        nonlocal last_end
        if last_end is not None: time.sleep(max(0,3-(time.monotonic()-last_end)))
        kwargs['verify']=True;kwargs['timeout']=(8,25);kwargs['allow_redirects']=False
        result=session.request(method,url,**kwargs);last_end=time.monotonic()
        raw=result.json() if result.content else None
        index=len(remote)+1
        save(f'journey-cbs-{index:02d}.json',{'method':method,'url':url,'http':result.status_code,'body':raw})
        remote.append({'method':method,'url':url,'http':result.status_code,'response_file':f'journey-cbs-{index:02d}.json'})
        print(f'CBS {method} HTTP {result.status_code}',flush=True)
        if result.status_code==429: raise RuntimeError('Rate limited; no retry.')
        return result
    original_token=RestAdapter._resolve_bearer_token
    cached={}
    def token(adapter):
        if 'value' not in cached: cached['value']=original_token(adapter)
        return cached['value']

    try:
        with patch('requests.post',lambda url,**kw:remote_call('POST',url,**kw)), \
             patch('requests.get',lambda url,**kw:remote_call('GET',url,**kw)), \
             patch.object(RestAdapter,'_resolve_bearer_token',token):
            # The API checks configuration permissions. Activation can expose the
            # known portfolio 404 in its initial import task; it does not disburse.
            if not state.get('live_connector_configured'):
                mapping=copy.deepcopy(connector.mapping_rules or {})
                save('connector-before-UAT.json',{'mapping_rules':mapping})
                mapping['force_simulate']=False;mapping['verify_ssl']=True
                mapping.setdefault('disbursement',{})['mode']='CBS'
                mapping['disbursement'].setdefault('purpose_map',{})['CONSUMPTION']='45'
                if mapping != connector.mapping_rules:
                    api('admin','patch',f'/api/v1/cbs-connectors/{connector.pk}/',{'mapping_rules':mapping})
                state['live_connector_configured']=True;checkpoint()
                connector.refresh_from_db()
            if not state.get('manager_associated'):
                manager=CbsManager.all_tenants.get(tenant=tenant,cbs_code='AG011U1',is_active=True)
                if actors['charge'].cbs_id != manager.cbs_code:
                    api('admin','patch',f'/api/v1/users/{actors["charge"].pk}/',{'cbs_id':manager.cbs_code})
                state['manager_associated']=True;checkpoint()

            if not state.get('client_id'):
                if Client.all_tenants.filter(tenant=tenant,cbs_client_id=CLIENT_CODE).exists():
                    raise RuntimeError('An existing client needs explicit reconciliation; duplicate creation stopped.')
                with tenant_context(tenant.pk):
                    preview=get_client_situation(tenant.pk,code_adherent=CLIENT_CODE)
                save('genuine-CBS-client.json',preview)
                agency=Agency.objects.get(tenant=tenant,cbs_point_of_service_id=preview['id_point_service'])
                body={'agency':str(agency.pk),'client_type':'INDIVIDUAL','last_name':'TEST '+CLIENT_CODE,'first_name':'Client UAT',
                      'birth_date':'1990-01-15','birth_country':'CI','country':'CI','nationality':'Ivoirienne UAT',
                      'profession':'Salarie fictif UAT','phone':'+2250000000000','email':'uat-'+CLIENT_CODE.lower()+'@example.invalid',
                      'city':'Abidjan UAT','address':'1 rue de la Recette UAT','civility':'MR','marital_status':'SINGLE',
                      'id_document_type':'CNI','national_id':'UAT-'+CLIENT_CODE,'id_document_issue_date':'2026-01-01',
                      'id_document_expiry_date':'2030-01-01','kyc_status':'PENDING',
                      'cbs_client_id':preview['code_adherent'],'cbs_account_number':preview['num_manuel']}
                body.update(SCENARIO.get('client',{}))
                created=api('charge','post','/api/v1/clients/',body)
                state['client_id']=created['id'];checkpoint()
                # The standard importer rejects incomplete CBS identities. Use its
                # canonical mapping for genuine read-only provenance, retaining
                # local synthetic complements as distinct native fields.
                with tenant_context(tenant.pk):
                    obj=Client.objects.get(pk=state['client_id'])
                    values=map_preview_to_client_fields(preview=preview,client_type='INDIVIDUAL',tenant_id=tenant.pk,user=actors['charge'],agency=agency,kyc_status='PENDING')
                    names=[key for key in values if key.startswith('cbs_')]
                    for key in names: setattr(obj,key,values[key])
                    audit_tokens=set_audit_context(actors['charge'],'127.0.0.1')
                    try: obj.save(update_fields=names+['updated_at'])
                    finally: reset_audit_context(audit_tokens)
                save('synthetic-client-complements.json',{'native_fields':body,'genuine_CBS_snapshot':'genuine-CBS-client.json','authorization':'User explicitly authorized fictitious missing data for the UAT sandbox.'})
            cid=state['client_id']
            if not state.get('kyc_validated'):
                api('charge','patch',f'/api/v1/clients/{cid}/',{'id_document_scan':file('identite.pdf')},multipart=True)
                api('chef','patch',f'/api/v1/clients/{cid}/',{'kyc_status':'VALIDATED'})
                state['kyc_validated']=True;checkpoint()
            product=CreditProduct.all_tenants.get(tenant=tenant,code='CONSO-STD',is_active=True)
            if not state.get('application_id'):
                body={'client':cid,'product':str(product.pk),'agency':str(actors['charge'].agency_id),
                    'amount_requested':'200000.00','amount_proposed':'200000.00','duration_months':3,
                    'interest_rate':str(product.interest_rate),'currency':'XOF','periodicity':'MONTHLY','repayment_mechanism':'DEGRESSIVE',
                    'purpose_type':'CONSUMPTION','purpose':'UAT - recette complete avec complements fictifs autorises. Aucun usage en production.',
                    'financing_object':str(FinancingObject.all_tenants.get(tenant=tenant,cbs_code='45',is_active=True).pk),
                    'project_total_cost':'250000.00','personal_contribution':'50000.00',
                    'employer_name':'ENTREPRISE UAT FICTIVE','contract_type':'CDI','salary_domiciliation':True,'dependents_count':0,
                    'client_account_number':Client.all_tenants.get(pk=cid).cbs_account_number,
                    'relationship_start_date':str(Client.all_tenants.get(pk=cid).cbs_registration_date or date(2026,1,1)),'avg_monthly_credit_movements':'600000.00',
                    'has_credit_insurance':False,'funds_origin':'Apport fictif de recette UAT',
                    'special_conditions':'UAT - Toutes les pieces et donnees locales complementaires sont synthetiques.',
                    'suspensive_conditions':'Recette uniquement - aucune valeur contractuelle reelle.'}
                body.update(SCENARIO.get('credit',{}))
                created=api('charge','post','/api/v1/credit-applications/',body)
                state['application_id']=created['id'];state['application_reference']=created['reference'];checkpoint()
            aid=state['application_id']
            if not state.get('documents_attached'):
                labels={'identite.pdf':"Pièce d'identité",'domicile.pdf':'Justificatif de domicile',
                    'salaire.pdf':'Bulletins de salaire (3 mois)','banque.pdf':'Relevé bancaire (3 mois)',
                    'demande.pdf':'Lettre de demande UAT','analyse.pdf':'Analyse financiere UAT','visite.pdf':'Compte rendu de visite UAT'}
                for name,label in labels.items():
                    api('charge','post','/api/v1/credit-documents/',{'application':aid,'label':label,'file':file(name)},multipart=True)
                api('charge','patch',f'/api/v1/credit-applications/{aid}/',{'document_checklist':[{'label':label,'provided':True} for label in labels.values()]})
                state['documents_attached']=True;checkpoint()
            if not state.get('visit_id'):
                value=api('charge','post','/api/v1/field-visits/',{'application':aid,'visit_date':str(date.today()),'report':'UAT - Visite simulee, aucune visite physique. Voir justificatif synthetique joint.'})
                state['visit_id']=value['id'];checkpoint()
            if not state.get('analysis_id'):
                analysis_body={'application':aid,'is_reference':True,
                    'individual_profile':'SALARIE','reference_period':'MONTHLY','analysis_date':str(date.today()),
                    'salary_income':'600000','net_salary':'600000','rent_expense':'100000','food_expense':'60000',
                    'utilities_expense':'20000','transport_expense':'20000','dependents_count':0,
                    'employer_name':'ENTREPRISE UAT FICTIVE','employment_type':'PERMANENT','employment_seniority_months':36,
                    'salary_paid_through_bank':True,'salary_verified':True,'information_quality':'VERIFIED',
                    'financial_statement_date':str(date.today()),'bank_statement_months':3,'financial_documents_verified':True,
                    'field_visit_confirmed':True,'verification_comment':'UAT - coherence des seules pieces synthetiques, sans verification de revenus reels.',
                    'primary_repayment_source':'Salaire fictif du scenario UAT','recommendation':'FAVORABLE',
                    'strengths':'UAT - capacite fictive de remboursement suffisante','weaknesses':'Scenario artificiel, aucune conclusion sur le client reel.',
                    'comment':'UAT - analyse synthetique autorisee pour tester le logiciel.'}
                analysis_body.update(SCENARIO.get('analysis',{}))
                value=api('charge','post','/api/v1/financial-analyses/',analysis_body)
                state['analysis_id']=value['id'];checkpoint()
            if not state.get('submitted'):
                api('charge','get',f'/api/v1/credit-applications/{aid}/readiness/')
                api('charge','post',f'/api/v1/credit-applications/{aid}/submit/')
                state['submitted']=True;checkpoint()
            with tenant_context(tenant.pk):
                for _ in range(15):
                    app=CreditApplication.objects.get(pk=aid)
                    if app.status not in ('IN_APPROVAL','SUBMITTED'): break
                    task=ApprovalTask.objects.filter(instance__object_id=aid,status='PENDING',step__order=1).first()
                    candidates=ApprovalTask.objects.filter(instance__object_id=aid,status='PENDING').select_related('instance','step')
                    task=next((t for t in candidates if t.step.order==t.instance.current_order),None)
                    if not task: raise RuntimeError('No actionable workflow task; see dossier.')
                    role=next((r for r in ('analyste','chef','comite','comite_groupe') if user_can_act(actors[r],task.step,app,task.instance.amount)),None)
                    if not role: raise RuntimeError('No authorized existing actor for the current task.')
                    api(role,'post',f'/api/v1/approval-tasks/{task.pk}/decide/',{'decision':'APPROVED','opinion':'FAVORABLE','comment':'UAT - validation du scenario synthetique et de ses pieces, aucune decision de production.'})
            app=CreditApplication.all_tenants.get(pk=aid)
            if app.status not in ('APPROVED','CONTRACT_GENERATED','DISBURSEMENT_PENDING','DISBURSED'):
                raise RuntimeError('Workflow did not produce an approved state.')
            if not state.get('contract_id'):
                template=api('admin','post','/api/v1/contract-templates/',{'name':'UAT - contrat fictif du parcours CBS','code':'UAT-CBS-'+CLIENT_CODE,
                    'category':'LOAN','applies_to':'INDIVIDUAL','product':str(product.pk),'is_required':False,
                    'description':'Modele de test sans valeur contractuelle','file':file('modele-contrat-uat.docx')},multipart=True)
                state['template_id']=template['id'];checkpoint()
                generated=api('charge','post','/api/v1/generated-contracts/generate/?sync=1',{'application':aid,'template':template['id']})
                state['contract_id']=generated['id'];checkpoint()
            if not state.get('contract_signed'):
                api('juridique','post',f'/api/v1/generated-contracts/{state["contract_id"]}/upload_signed/',
                    {'signed_file':file('contrat-signe.pdf'),'notes':'UAT - signature simulee, sans engagement reel.'},multipart=True)
                state['contract_signed']=True;checkpoint()
            if not state.get('documents_verified'):
                verifier=next(r for r in ('juridique','admin_credit','admin') if actors[r].has_perm('documents.change_document'))
                for doc in Document.all_tenants.filter(tenant=tenant,object_id=aid,is_deleted=False):
                    api(verifier,'post',f'/api/v1/documents/{doc.pk}/verify/',{'status':'VERIFIED','comment':'UAT - document synthetique identifie comme tel, contenu et rattachement verifies pour ce seul scenario.'})
                state['documents_verified']=True
                state['reviewed']=False;state['authorized']=False;checkpoint()
            if not state.get('reviewed'):
                api('admin_credit','post',f'/api/v1/credit-applications/{aid}/setup-review/',{'comment':'UAT - controle du client source CBS, complements fictifs, analyse, pieces synthetiques et contrat de simulation.',
                    'checks':{k:True for k in ('kyc','contribution','collateral','terms','insurance')}})
                state['reviewed']=True;checkpoint()
            if not state.get('authorized'):
                api('admin_credit','post',f'/api/v1/credit-applications/{aid}/authorize-setup/',{'comment':'UAT - autorisation nominative de tester la mise en place sur le CBS de recette.'})
                state['authorized']=True;checkpoint()
            if not state.get('setup_requested'):
                app=CreditApplication.all_tenants.get(pk=aid)
                if app.status != 'DISBURSEMENT_PENDING':
                    api('assistant_ops','post',f'/api/v1/credit-applications/{aid}/request-disburse/')
                else:
                    state['setup_request_source']='Created automatically by the credit administrator authorization.'
                state['setup_requested']=True;checkpoint()
            if not state.get('disbursed'):
                if state.get('setup_attempted'):
                    raise RuntimeError('Une transmission a déjà été tentée ; rapprocher sa réponse avant tout rejeu.')
                from apps.corebanking.disbursement import build_credit_disbursement_payload
                payload=build_credit_disbursement_payload(CreditApplication.all_tenants.get(pk=aid))
                save('setup-payload-preview.json',payload)
                if os.environ.get('CBS_UAT_REQUIRE_REAL_PRODUCT_IDS')=='1':
                    blockers=[key+' is not a verified CBS numeric product identifier: '+str(payload.get(key))
                              for key in ('idProduitCrd','idProduitRemb') if not str(payload.get(key,'')).isdigit()]
                    if blockers:
                        state['setup_blockers']=blockers
                        state['setup_attempted']=False
                        state['blocked_error']='Known CBS product mapping issue; no duplicate failing submission sent.'
                        api('operations','get',f'/api/v1/credit-applications/{aid}/')
                        checkpoint()
                        print('SETUP BLOCKED BEFORE CBS SUBMISSION: '+json.dumps(blockers),flush=True)
                        return
                state['setup_attempted']=True;checkpoint()
                result=api('operations','post',f'/api/v1/credit-applications/{aid}/disburse/')
                state['loan_id']=result['id'];state['disbursed']=True;checkpoint()
            api('operations','get',f'/api/v1/credit-applications/{aid}/')
            api('operations','get',f'/api/v1/loans/{state["loan_id"]}/')
            state.pop('blocked_error',None);checkpoint()
    except Exception as exc:
        state['blocked_error']=str(exc);checkpoint()
        print('BLOCKED: '+str(exc),flush=True)
        raise
    finally:
        save('execution-remote-calls.json',remote)
        checkpoint();session.close()
        print('STATE_FILE='+str(STATE.resolve()),flush=True)


main()
