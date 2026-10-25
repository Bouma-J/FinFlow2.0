"""Generate conspicuously synthetic UAT evidence and a contract test template."""
import os
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.utils import simpleSplit
from docx import Document
from docx.shared import Inches, Pt

client_code=os.environ.get('CBS_UAT_CLIENT_CODE','AG0100027')
out=Path(os.environ.get('CBS_UAT_OUTPUT','uat-artifacts/journey-20261020T223709Z'))/'files'
out.mkdir(parents=True,exist_ok=True)
specs={
    'identite':('Identite fictive de recette', ['Client UAT - TEST AG0100027','Ne le 15 janvier 1990 - nationalite ivoirienne fictive',
        'Piece UAT-AG0100027 - emission 01 janvier 2026 - expiration 01 janvier 2030']),
    'domicile':('Justificatif de domicile fictif', ['Adresse UAT 1 rue de la Recette - Abidjan','Telephone fictif +2250000000000',
        'Aucune attestation emise par une autorite reelle']),
    'salaire':('Bulletins de salaire de recette', ['Employeur fictif ENTREPRISE UAT - CDI fictif','Salaire net mensuel fictif 600 000 XOF',
        'Trois mois de test - aout septembre et octobre 2026']),
    'banque':('Releve bancaire de recette', ['Scenario synthetique de trois mois - aucune transaction reelle',
        'Entrees mensuelles 600 000 XOF - charges du menage 200 000 XOF', 'Dette anterieure du scenario 0 XOF']),
    'demande':('Demande de credit UAT', ['Adherent CBS de recette AG0100027', 'Montant de test 200 000 XOF - duree 3 mois - taux annuel 14 pour cent',
        'Objet Recette du parcours de credit - toutes donnees complementaires fictives']),
    'analyse':('Analyse financiere UAT', ['Revenus fictifs 600 000 XOF par mois - charges fictives 200 000 XOF',
        'Capacite avant nouvelle echeance 400 000 XOF - dette existante du scenario 0',
        'Avis de test uniquement - aucune verification economique reelle du client']),
    'visite':('Compte rendu de visite simulee', ['Aucune visite physique realisee',
        'Controle fictif du dossier et de ses justificatifs pour recette informatique',
        'Toutes les validations sont des validations de scenario UAT']),
    'contrat-signe':('Contrat et signature de simulation UAT', ['Credit fictif 200 000 XOF - 3 mois - taux annuel 14 pour cent',
        'Signature de test uniquement - aucune signature manuscrite ou electronique reelle',
        'Aucune valeur contractuelle ni engagement du client']),
}
for name,(title,lines) in specs.items():
    lines=[line.replace('AG0100027',client_code) for line in lines]
    c=Canvas(str(out/(name+'.pdf')),pagesize=A4)
    width,height=A4
    c.setTitle('UAT '+title)
    c.setFillColorRGB(.75,.05,.05);c.setFont('Helvetica-Bold',13)
    c.drawString(42,height-48,'UAT - DOCUMENT SYNTHETIQUE')
    c.setFillColorRGB(0,0,0);c.setFont('Helvetica-Bold',16)
    c.drawString(42,height-92,title)
    c.setFont('Helvetica',11)
    y=height-135
    for line in lines:
        for wrapped in simpleSplit(line,'Helvetica',11,width-84):
            c.drawString(42,y,wrapped);y-=17
        y-=11
    c.setFont('Helvetica',10)
    c.drawString(42,y-15,'Adherent du scenario UAT : '+client_code)
    c.setFillColorRGB(.65,.08,.08);c.setFont('Helvetica-Bold',11)
    c.drawString(42,75,'SANS VALEUR CONTRACTUELLE - NE PAS UTILISER EN PRODUCTION')
    c.setFont('Helvetica',9);c.drawString(42,55,'Scenario autorise de recette informatique - 20 octobre 2026 - page 1/1')
    c.save()
doc=Document()
section=doc.sections[0];section.page_width=Inches(8.5);section.page_height=Inches(11)
style=doc.styles['Normal'];style.font.name='Arial';style.font.size=Pt(11)
doc.add_paragraph('Contrat fictif de recette du credit',style='Title')
doc.add_paragraph('UAT - SANS VALEUR CONTRACTUELLE',style='Heading 1')
doc.add_paragraph('Ce document sert uniquement a verifier la generation et le depot du contrat dans FinFlow. Aucun engagement reel ne doit en etre deduit.')
doc.add_paragraph('Dossier {{ dossier_reference }}')
doc.add_paragraph('Credit fictif 200 000 XOF sur 3 mois au taux annuel de 14 pour cent.')
doc.add_paragraph('Les complements d identite, revenus et justificatifs sont synthetiques et autorises pour ce scenario UAT.')
doc.add_paragraph('Signature de test uniquement. Aucune signature reelle du client.')
section.footer.paragraphs[0].text='UAT - Ne pas utiliser en production'
doc.save(out/'modele-contrat-uat.docx')
print(str(out.resolve()))
