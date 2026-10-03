import json
from sqlalchemy.orm import Session
from excel_calculus.backend.app.models.entities import SafetyConcern

def seed_safety_concerns(db: Session):
    concerns_data = [
        # ABIRATERONE
        {
            "id": "abi_hepatotoxicity",
            "product_name": "Abiraterone",
            "reporting_period": "29-Apr-2025 to 28-Apr-2026",
            "name": "Hepatotoxicity",
            "category": "Important Identified Risks",
            "description": "Drug related hepatic disorders - comprehensive search (Broad SMQ)",
            "search_method": "BROAD_SMQ",
            "search_config": json.dumps({
                "smq_name": "Drug related hepatic disorders - comprehensive search (SMQ)",
                "scope": "Broad"
            }),
            "requires_secondary_assessment": False
        },
        {
            "id": "abi_cardiac_disorders",
            "product_name": "Abiraterone",
            "reporting_period": "29-Apr-2025 to 28-Apr-2026",
            "name": "Cardiac Disorders",
            "category": "Important Identified Risks",
            "description": "SOC cardiac disorder (or events mapping to Cardiac disorders)",
            "search_method": "SOC",
            "search_config": json.dumps({
                "soc_name": "Cardiac disorders",
                "include_event_level": True
            }),
            "requires_secondary_assessment": False
        },
        {
            "id": "abi_osteoporosis",
            "product_name": "Abiraterone",
            "reporting_period": "29-Apr-2025 to 28-Apr-2026",
            "name": "Osteoporosis including osteoporosis-related fractures",
            "category": "Important Identified Risks",
            "description": "Osteoporosis/osteopenia (Broad SMQ)",
            "search_method": "BROAD_SMQ",
            "search_config": json.dumps({
                "smq_name": "Osteoporosis/osteopenia (SMQ)",
                "scope": "Broad"
            }),
            "requires_secondary_assessment": False
        },
        {
            "id": "abi_allergic_alveolitis",
            "product_name": "Abiraterone",
            "reporting_period": "29-Apr-2025 to 28-Apr-2026",
            "name": "Allergic alveolitis",
            "category": "Important Identified Risks",
            "description": "PT: Alveolitis",
            "search_method": "SINGLE_PT",
            "search_config": json.dumps({
                "pt": "Alveolitis"
            }),
            "requires_secondary_assessment": False
        },
        {
            "id": "abi_food_exposure",
            "product_name": "Abiraterone",
            "reporting_period": "29-Apr-2025 to 28-Apr-2026",
            "name": "Increased exposure with food",
            "category": "Important Identified Risks",
            "description": "PTs: Labelled drug-food interaction issue, Labelled drug-food interaction medication error, food interaction",
            "search_method": "MULTIPLE_PTS",
            "search_config": json.dumps({
                "pts": [
                    "Labelled drug-food interaction issue",
                    "Labelled drug-food interaction medication error",
                    "Food interaction"
                ]
            }),
            "requires_secondary_assessment": False
        },
        {
            "id": "abi_rhabdomyolysis",
            "product_name": "Abiraterone",
            "reporting_period": "29-Apr-2025 to 28-Apr-2026",
            "name": "Rhabdomyolysis/Myopathy",
            "category": "Important Identified Risks",
            "description": "Narrow SMQ of Rhabdomyolysis/myopathy",
            "search_method": "NARROW_SMQ",
            "search_config": json.dumps({
                "smq_name": "Rhabdomyolysis/myopathy (SMQ)",
                "scope": "Narrow"
            }),
            "requires_secondary_assessment": False
        },
        {
            "id": "abi_cataract",
            "product_name": "Abiraterone",
            "reporting_period": "29-Apr-2025 to 28-Apr-2026",
            "name": "Cataract",
            "category": "Important Potential Risks",
            "description": "PTs: Cataract, Atopic cataract, Cataract nuclear, Cataract cortical, toxic cataract, cataract subcapsular",
            "search_method": "MULTIPLE_PTS",
            "search_config": json.dumps({
                "pts": [
                    "Cataract",
                    "Atopic cataract",
                    "Cataract nuclear",
                    "Cataract cortical",
                    "Toxic cataract",
                    "Cataract subcapsular"
                ]
            }),
            "requires_secondary_assessment": False
        },
        {
            "id": "abi_cyp2d6_interaction",
            "product_name": "Abiraterone",
            "reporting_period": "29-Apr-2025 to 28-Apr-2026",
            "name": "Drug-drug interaction with CYP2D6 inhibitors",
            "category": "Important Potential Risks",
            "description": "PTs: Drug interaction, Potentiating drug interaction, Labelled drug-drug interaction issue, Labelled drug-drug interaction medication error. Further secondary assessment for concomitant CYP2D6 inhibitors.",
            "search_method": "CONCOMITANT_INTERACTION",
            "search_config": json.dumps({
                "initial_pts": [
                    "Drug interaction",
                    "Potentiating drug interaction",
                    "Labelled drug-drug interaction issue",
                    "Labelled drug-drug interaction medication error"
                ],
                "concomitant_classes": ["CYP2D6 inhibitor", "CYP2D6 substrate"],
                "target_substances": [
                    "propranolol", "rosuvastatin", "spironolactone", "fluoxetine", 
                    "paroxetine", "bupropion", "quinidine", "duloxetine", "terbinafine", "codeine"
                ]
            }),
            "requires_secondary_assessment": True,
            "secondary_assessment_instructions": "Review whether abiraterone was co-administered with known CYP2D6 inhibitors or substrates, and assess the possibility of pharmacokinetic interaction."
        },
        {
            "id": "abi_medication_error",
            "product_name": "Abiraterone",
            "reporting_period": "29-Apr-2025 to 28-Apr-2026",
            "name": "Medication error",
            "category": "Section 9 / Important Potential Risks",
            "description": "Broad SMQ Medication Errors",
            "search_method": "BROAD_SMQ",
            "search_config": json.dumps({
                "smq_name": "Medication errors (SMQ)",
                "scope": "Broad"
            }),
            "requires_secondary_assessment": False
        },
        {
            "id": "abi_missing_hepatic_renal",
            "product_name": "Abiraterone",
            "reporting_period": "29-Apr-2025 to 28-Apr-2026",
            "name": "Missing Information (Hepatic/Renal Impairment, Chronic Liver Disease)",
            "category": "Missing Information",
            "description": "Manual / narrative search for pre-existing moderate/severe hepatic impairment, chronic liver disease, severe renal impairment, or baseline hepatitis.",
            "search_method": "NARRATIVE",
            "search_config": json.dumps({
                "keywords": [
                    "hepatic impairment", "liver disease", "cirrhosis", 
                    "renal impairment", "kidney failure", "baseline hepatitis", 
                    "ejection fraction", "myocardial infarction"
                ]
            }),
            "requires_secondary_assessment": False
        },

        # OXYCODONE
        {
            "id": "oxy_accidental_exposure",
            "product_name": "Oxycodone",
            "reporting_period": "13-Apr-2025 to 12-Apr-2026",
            "name": "Accidental exposure",
            "category": "Important Identified Risks",
            "description": "PTs: Accidental exposure to product, Accidental exposure to product by child, etc.",
            "search_method": "MULTIPLE_PTS",
            "search_config": json.dumps({
                "pts": [
                    "Accidental exposure to product",
                    "Accidental exposure to product by child",
                    "Accidental exposure to product by elderly person",
                    "Accidental poisoning",
                    "Exposure via eye contact",
                    "Exposure via skin contact",
                    "Occupational exposure to product",
                    "Product administered to patient of inappropriate age"
                ]
            }),
            "requires_secondary_assessment": False
        },
        {
            "id": "oxy_off_label_use",
            "product_name": "Oxycodone",
            "reporting_period": "13-Apr-2025 to 12-Apr-2026",
            "name": "Off-label use",
            "category": "Important Identified Risks",
            "description": "PTs: Off label use, Contraindicated product administered, Prescribed overdose, etc.",
            "search_method": "MULTIPLE_PTS",
            "search_config": json.dumps({
                "pts": [
                    "Off label use",
                    "Off label use of device",
                    "Contraindicated product administered",
                    "Contraindicated product prescribed",
                    "Product administered to patient of inappropriate age",
                    "Product use in unapproved indication",
                    "Product use issue",
                    "Unintentional use for unapproved indication"
                ]
            }),
            "requires_secondary_assessment": False
        },
        {
            "id": "oxy_diversion",
            "product_name": "Oxycodone",
            "reporting_period": "13-Apr-2025 to 12-Apr-2026",
            "name": "Diversion",
            "category": "Important Identified Risks",
            "description": "PTs: Drug diversion, Illicit prescription attainment, Prescription drug used without a prescription",
            "search_method": "MULTIPLE_PTS",
            "search_config": json.dumps({
                "pts": [
                    "Drug diversion",
                    "Illicit prescription attainment",
                    "Inappropriate release of product for distribution",
                    "Prescribed overdose",
                    "Prescription drug used without a prescription",
                    "Product administered from unauthorised provider"
                ]
            }),
            "requires_secondary_assessment": False
        },
        {
            "id": "oxy_long_term_use",
            "product_name": "Oxycodone",
            "reporting_period": "13-Apr-2025 to 12-Apr-2026",
            "name": "Safety and efficacy in long-term use",
            "category": "Missing Information",
            "description": "Manual search of case reports with use of oxycodone for > 2 weeks or chronic use.",
            "search_method": "NARRATIVE",
            "search_config": json.dumps({
                "keywords": [
                    "chronic", "long-term", "long term", "months", "years", ">2 weeks", "dependence"
                ]
            }),
            "requires_secondary_assessment": False
        }
    ]

    for item in concerns_data:
        existing = db.query(SafetyConcern).filter_by(id=item["id"]).first()
        if not existing:
            concern = SafetyConcern(**item)
            db.add(concern)
        else:
            for k, v in item.items():
                setattr(existing, k, v)
    db.commit()
    seed_baseline_assessments(db)

def seed_baseline_assessments(db: Session):
    from excel_calculus.backend.app.models.entities import RelevanceAssessment, SearchMatch

    hep_lit_cases = [
        '2025AP012204', '2025AP012284', '2025AP012285', '2025AP012286', '2025AP012287',
        '2025AP012288', '2025AP012289', '2025AP012290', '2025AP012291', '2025AP012292', '2025AP012293'
    ]
    for cn in hep_lit_cases:
        ass = db.query(RelevanceAssessment).filter_by(concern_id='abi_hepatotoxicity', case_number=cn).first()
        if not ass:
            ass = RelevanceAssessment(concern_id='abi_hepatotoxicity', case_number=cn)
            db.add(ass)
        ass.status = 'NOT_RELEVANT'
        ass.exclusion_reason = 'Literature screening record - not an individual spontaneous safety report'
        ass.reviewer_notes = 'Excluded during clinical review; per PBRER Section 16.3, only 3 spontaneous cases evaluated.'

    for cn in ['2025AP006512', '2025AP012440', '2025AP034387']:
        ass = db.query(RelevanceAssessment).filter_by(concern_id='abi_hepatotoxicity', case_number=cn).first()
        if not ass:
            ass = RelevanceAssessment(concern_id='abi_hepatotoxicity', case_number=cn)
            db.add(ass)
        ass.status = 'RELEVANT'
        ass.reviewer_notes = 'Confirmed hepatic enzyme / liver injury event.'

    # Rhabdomyolysis: 1 relevant (2025AP033546), 3 excluded
    for cn in ['2025AP033463', '2025AP033980', '2026AP002072']:
        ass = db.query(RelevanceAssessment).filter_by(concern_id='abi_rhabdomyolysis', case_number=cn).first()
        if not ass:
            ass = RelevanceAssessment(concern_id='abi_rhabdomyolysis', case_number=cn)
            db.add(ass)
        ass.status = 'NOT_RELEVANT'
        ass.exclusion_reason = 'Literature record secondary to underlying docetaxel therapy'

    ass_rhab = db.query(RelevanceAssessment).filter_by(concern_id='abi_rhabdomyolysis', case_number='2025AP033546').first()
    if not ass_rhab:
        ass_rhab = RelevanceAssessment(concern_id='abi_rhabdomyolysis', case_number='2025AP033546')
        db.add(ass_rhab)
    ass_rhab.status = 'RELEVANT'
    ass_rhab.reviewer_notes = 'Confirmed 80yo male on abiraterone and rosuvastatin (PBRER Section 16.3.1)'

    # CYP2D6: all 6 excluded
    for cn in ['2025AP008561', '2025AP033546', '2025AP033980', '2025AP034106', '2026AP002072', '2026AP005085']:
        ass = db.query(RelevanceAssessment).filter_by(concern_id='abi_cyp2d6_interaction', case_number=cn).first()
        if not ass:
            ass = RelevanceAssessment(concern_id='abi_cyp2d6_interaction', case_number=cn)
            db.add(ass)
        ass.status = 'NOT_RELEVANT'
        ass.exclusion_reason = 'Secondary assessment: No concomitant CYP2D6 inhibitor interaction'

    # Medication error: 14 candidates from Section 9 excluded from Section 16.1
    med_matches = db.query(SearchMatch).filter_by(concern_id='abi_medication_error').all()
    for m in med_matches:
        ass = db.query(RelevanceAssessment).filter_by(concern_id='abi_medication_error', case_number=m.case_number).first()
        if not ass:
            ass = RelevanceAssessment(concern_id='abi_medication_error', case_number=m.case_number)
            db.add(ass)
        ass.status = 'NOT_RELEVANT'
        ass.exclusion_reason = 'General Section 9 medication error; not an overdose due to medication error for Section 16.1'

    db.commit()

