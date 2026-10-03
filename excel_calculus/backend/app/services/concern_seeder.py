import json
from sqlalchemy.orm import Session
from excel_calculus.backend.app.models.entities import SafetyConcern

def seed_safety_concerns(db: Session):
    concerns_data = [
        # ABIRATERONE - Section 16.1 Important Identified Risks
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
            "name": "Cardiac disorders",
            "category": "Important Identified Risks",
            "description": "SOC cardiac disorder",
            "search_method": "SOC",
            "search_config": json.dumps({
                "soc_name": "Cardiac disorders",
                "include_event_level": False
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
            "description": "PTs: Labelled drug-food interaction issue, Labelled drug-food interaction medication error and food interaction",
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

        # ABIRATERONE - Section 16.1 Important Potential Risks
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
            "name": "Drug drug interaction with CYP2D6 inhibitors",
            "category": "Important Potential Risks",
            "description": "PTs: Drug interaction, Potentiating drug interaction, Labelled drug-drug interaction issue, Labelled drug-drug interaction medication error. Further assessment for concomitant CYP2D6 inhibitors.",
            "search_method": "CONCOMITANT_INTERACTION",
            "search_config": json.dumps({
                "initial_pts": [
                    "Drug interaction",
                    "Potentiating drug interaction",
                    "Labelled drug-drug interaction issue",
                    "Labelled drug-drug interaction medication error"
                ],
                "target_substances": [
                    "propranolol", "rosuvastatin", "spironolactone", "fluoxetine", 
                    "paroxetine", "bupropion", "quinidine", "duloxetine", "terbinafine", "codeine"
                ]
            }),
            "requires_secondary_assessment": True,
            "secondary_assessment_instructions": "Review whether abiraterone was co-administered with known CYP2D6 inhibitors or substrates, and assess clinical possibility of pharmacokinetic interaction."
        },
        {
            "id": "abi_overdose_med_error",
            "product_name": "Abiraterone",
            "reporting_period": "29-Apr-2025 to 28-Apr-2026",
            "name": "Overdose due to medication error",
            "category": "Important Potential Risks",
            "description": "Broad SMQ of Medication Error further assessed with PTs of Overdose and accidental overdose",
            "search_method": "SMQ_SUBFILTER",
            "search_config": json.dumps({
                "smq_name": "Medication errors (SMQ)",
                "scope": "Broad",
                "sub_filter_pts": [
                    "Overdose",
                    "Accidental overdose"
                ]
            }),
            "requires_secondary_assessment": False
        },

        # ABIRATERONE - Section 16.1 Missing Information
        {
            "id": "abi_missing_hepatic_impairment",
            "product_name": "Abiraterone",
            "reporting_period": "29-Apr-2025 to 28-Apr-2026",
            "name": "Use in patients with moderate/severe hepatic impairment and chronic liver disease",
            "category": "Missing Information",
            "description": "Manual search for case report with abiraterone use in patients with pre-existing moderate/severe hepatic impairment and chronic liver disease",
            "search_method": "NARRATIVE",
            "search_config": json.dumps({
                "keywords": [
                    "moderate hepatic impairment", "severe hepatic impairment", 
                    "chronic liver disease", "cirrhosis", "child-pugh"
                ]
            }),
            "requires_secondary_assessment": False
        },
        {
            "id": "abi_missing_severe_renal",
            "product_name": "Abiraterone",
            "reporting_period": "29-Apr-2025 to 28-Apr-2026",
            "name": "Use in patients with severe renal impairment",
            "category": "Missing Information",
            "description": "Manual search for case reports with abiraterone use in patients with pre-existing severe renal impairment",
            "search_method": "NARRATIVE",
            "search_config": json.dumps({
                "keywords": [
                    "severe renal impairment", "end stage renal", "dialysis", 
                    "creatinine clearance < 30", "crcl < 30"
                ]
            }),
            "requires_secondary_assessment": False
        },
        {
            "id": "abi_missing_heart_disease",
            "product_name": "Abiraterone",
            "reporting_period": "29-Apr-2025 to 28-Apr-2026",
            "name": "Use in patients with heart disease as specified in the safety criteria",
            "category": "Missing Information",
            "description": "Manual search for abiraterone use in patients with pre-existing heart disease (myocardial infarction, arterial thrombotic events, severe/unstable angina, NYHA Class III/IV, or LVEF < 50%)",
            "search_method": "NARRATIVE",
            "search_config": json.dumps({
                "keywords": [
                    "myocardial infarction", "arterial thrombotic", "unstable angina", 
                    "class iii heart", "class iv heart", "ejection fraction < 50%", "ejection fraction <50%"
                ]
            }),
            "requires_secondary_assessment": False
        },
        {
            "id": "abi_missing_baseline_hepatitis",
            "product_name": "Abiraterone",
            "reporting_period": "29-Apr-2025 to 28-Apr-2026",
            "name": "Use in patients with baseline hepatitis or significant abnormalities of liver function tests",
            "category": "Missing Information",
            "description": "Manual search for abiraterone use in patients with pre-existing baseline hepatitis or significant abnormalities of liver function tests",
            "search_method": "NARRATIVE",
            "search_config": json.dumps({
                "keywords": [
                    "baseline hepatitis", "pre-existing hepatitis", "chronic hepatitis b", 
                    "chronic hepatitis c", "baseline lft", "baseline transaminases"
                ]
            }),
            "requires_secondary_assessment": False
        },

        # ABIRATERONE - Section 9 Medication Errors
        {
            "id": "abi_medication_error",
            "product_name": "Abiraterone",
            "reporting_period": "29-Apr-2025 to 28-Apr-2026",
            "name": "Medication error",
            "category": "Section 9 Adverse Reactions & Medication Errors",
            "description": "Broad SMQ Search: Medication errors (SMQ)",
            "search_method": "BROAD_SMQ",
            "search_config": json.dumps({
                "smq_name": "Medication errors (SMQ)",
                "scope": "Broad"
            }),
            "requires_secondary_assessment": False
        },

        # OXYCODONE - Safety Concerns
        {
            "id": "oxy_accidental_exposure",
            "product_name": "Oxycodone",
            "reporting_period": "13-Apr-2025 to 12-Apr-2026",
            "name": "Accidental exposure",
            "category": "Important Identified Risks",
            "description": "Configured Accidental Exposure PT collection",
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
            "description": "Configured Off-Label Use PT collection",
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
            "description": "Configured Drug Diversion PT collection",
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
