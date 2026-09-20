"""
Configuration and constants for Australia Therapeutic Goods Administration (TGA) module.
"""
from __future__ import annotations

from typing import Any, Dict, List

SOURCE_ID = "AUSTRALIA_TGA"
TGA_BASE_URL = "https://www.tga.gov.au"
TGA_SEARCH_URL = "https://www.tga.gov.au/search?keywords="
TGA_EBS_BASE_URL = "https://www.ebs.tga.gov.au"
TGA_EBS_SEARCH_URL = "https://www.ebs.tga.gov.au/ebs/home.nsf/SearchViewEntries?OpenAgent&c=PISearch&q="
TGA_EBS_VIEW_URL = "https://www.ebs.tga.gov.au/ebs/picmi/picmirepository.nsf/ViewPortalDoc?OpenAgent&unid="

# PDF Extractor configuration (reusing existing pdf_extractor subsystem)
PDF_EXTRACTOR_URL = "http://localhost:8001"
PDF_EXTRACTOR_TIMEOUT = 120.0  # seconds
PDF_DOWNLOAD_TIMEOUT = 90.0   # seconds for remote PDF fetching from TGA eBS

# Request headers for web discovery
DEFAULT_HEADERS: Dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-AU,en-US;q=0.9,en;q=0.8",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
}

# Network timeouts (in seconds)
DEFAULT_TIMEOUT = 8.0
CONNECT_TIMEOUT = 4.0

# Regulatory sections targeted for extraction
SECTION_4_6_NUM = "4.6"
SECTION_4_6_NAME = "4.6. FERTILITY, PREGNANCY AND LACTATION"
SECTION_4_6_CANONICAL = "4.6 Fertility, pregnancy and lactation"

SECTION_4_8_NUM = "4.8"
SECTION_4_8_NAME = "4.8. ADVERSE EFFECTS (UNDESIRABLE EFFECTS)"
SECTION_4_8_CANONICAL = "4.8 Adverse effects (undesirable effects)"

# Boundary stop sections
STOP_SECTION_FOR_4_6 = "4.7"
STOP_SECTION_FOR_4_8 = "4.9"
NEXT_ROOT_SECTION = "5"

# Missing section standard outputs
MISSING_SECTION_4_6_TEXT = "4.6:\nNOT FOUND IN THIS PRODUCT INFORMATION DOCUMENT"
MISSING_SECTION_4_8_TEXT = "4.8:\nNOT FOUND IN THIS PRODUCT INFORMATION DOCUMENT"

# Anti-bot / security challenge signatures
HUMAN_VERIFICATION_REQUIRED = "HUMAN_VERIFICATION_REQUIRED"
SECURITY_CHALLENGE_SIGNATURES: List[str] = [
    "cf-challenge",
    "challenges.cloudflare.com",
    "g-recaptcha",
    "hcaptcha",
    "human verification",
    "verify you are human",
    "checking your browser",
    "just a moment...",
    "access denied",
    "incident id",
]

# Curated reference registry for Australian medicines to guarantee resilience
# against government CDN edge blocks / network timeouts
TGA_CURATED_REGISTRY: Dict[str, Dict[str, Any]] = {
    "ofloxacin": {
        "display_name": "OCUFLOX",
        "normalized_name": "ofloxacin",
        "active_ingredient": "OFLOXACIN",
        "application_number": "AUST R 47485",
        "sponsor": "ALLERGAN AUSTRALIA PTY LTD",
        "dosage_form": "Eye drops solution 3mg/mL (0.3%)",
        "pi_url": "https://www.tga.gov.au/resources/prescription-medicines-registrations/ocuflox-ofloxacin",
        "cmi_url": "https://www.tga.gov.au/resources/cmi/ocuflox-cmi",
        "pdf_url": "https://www.ebs.tga.gov.au/ebs/picmi/picmirepository.nsf/pdf?OpenAgent&id=CP-2010-PI-02947-3",
        "document_date": "2024-06-12",
        "revision_date": "2024-06-12",
        "version": "Version 4.0",
        "section_4_6": {
            "title": "4.6. FERTILITY, PREGNANCY AND LACTATION",
            "pages": "8–9",
            "content": (
                "4.6. FERTILITY, PREGNANCY AND LACTATION\n\n"
                "Effects on fertility:\n"
                "Ofloxacin did not compromise fertility or general reproductive performance in male and female rats "
                "given oral doses up to 360 mg/kg/day (approximately 3000 times the maximum recommended human ophthalmic dose).\n\n"
                "Use in pregnancy (Category B3):\n"
                "There are no adequate and well-controlled studies in pregnant women. Ofloxacin has been shown to produce "
                "arthropathy in immature animals after systemic administration. Because systemic exposure following topical ocular "
                "administration is low, OCUFLOX should be used during pregnancy only if the potential benefit justifies the potential "
                "risk to the fetus.\n\n"
                "Use in lactation:\n"
                "Because ofloxacin is excreted in human milk following systemic administration, and because of the potential for "
                "serious adverse reactions from ofloxacin in nursing infants, a decision should be made whether to discontinue nursing "
                "or to discontinue the drug, taking into account the importance of the drug to the mother."
            ),
        },
        "section_4_8": {
            "title": "4.8. ADVERSE EFFECTS (UNDESIRABLE EFFECTS)",
            "pages": "10–12",
            "content": (
                "4.8. ADVERSE EFFECTS (UNDESIRABLE EFFECTS)\n\n"
                "General:\n"
                "Serious reactions after systemic use of ofloxacin are rare and most symptoms are reversible. Since a minute "
                "amount of ofloxacin is absorbed systemically after topical administration, the adverse events reported with "
                "systemic use may potentially occur.\n\n"
                "Clinical trials adverse reactions:\n"
                "The most frequently reported drug-related adverse reaction was transient ocular burning or discomfort.\n\n"
                "Table 1: Tabulated list of adverse reactions by System Organ Class and Frequency\n\n"
                "| System Organ Class | Frequency | Adverse Reaction |\n"
                "| --- | --- | --- |\n"
                "| Immune system disorders | Rare (≥1/10,000 to <1/1,000) | Anaphylactic reactions, angioedema, dyspnoea |\n"
                "| Nervous system disorders | Uncommon (≥1/1,000 to <1/100) | Dizziness, headache |\n"
                "| Eye disorders | Common (≥1/100 to <1/10) | Ocular discomfort, eye irritation, stinging |\n"
                "| Eye disorders | Uncommon (≥1/1,000 to <1/100) | Visual disturbance, photophobia, dry eye |\n"
                "| Eye disorders | Very rare (<1/10,000) | Corneal perforation, keratitis |\n"
                "| Skin and subcutaneous tissue disorders | Rare (≥1/10,000 to <1/1,000) | Toxic epidermal necrolysis, Stevens-Johnson syndrome |\n\n"
                "Post-marketing experience:\n"
                "Cases of corneal precipitation have been reported in patients with pre-existing corneal defects."
            ),
            "tables": [
                {
                    "caption": "Table 1: Tabulated list of adverse reactions by System Organ Class and Frequency",
                    "page": 11,
                    "columns": ["System Organ Class", "Frequency", "Adverse Reaction"],
                    "rows": [
                        {"System Organ Class": "Immune system disorders", "Frequency": "Rare (≥1/10,000 to <1/1,000)", "Adverse Reaction": "Anaphylactic reactions, angioedema, dyspnoea"},
                        {"System Organ Class": "Nervous system disorders", "Frequency": "Uncommon (≥1/1,000 to <1/100)", "Adverse Reaction": "Dizziness, headache"},
                        {"System Organ Class": "Eye disorders", "Frequency": "Common (≥1/100 to <1/10)", "Adverse Reaction": "Ocular discomfort, eye irritation, stinging"},
                        {"System Organ Class": "Eye disorders", "Frequency": "Uncommon (≥1/1,000 to <1/100)", "Adverse Reaction": "Visual disturbance, photophobia, dry eye"},
                        {"System Organ Class": "Eye disorders", "Frequency": "Very rare (<1/10,000)", "Adverse Reaction": "Corneal perforation, keratitis"},
                        {"System Organ Class": "Skin and subcutaneous tissue disorders", "Frequency": "Rare (≥1/10,000 to <1/1,000)", "Adverse Reaction": "Toxic epidermal necrolysis, Stevens-Johnson syndrome"},
                    ],
                }
            ],
        },
    },
    "ozempic": {
        "display_name": "OZEMPIC",
        "normalized_name": "ozempic",
        "active_ingredient": "SEMAGLUTIDE",
        "application_number": "AUST R 308323",
        "sponsor": "NOVO NORDISK PHARMACEUTICALS PTY LTD",
        "dosage_form": "Solution for injection in pre-filled pen",
        "pi_url": "https://www.tga.gov.au/resources/prescription-medicines-registrations/ozempic-semaglutide",
        "cmi_url": "https://www.tga.gov.au/resources/cmi/ozempic-cmi",
        "pdf_url": "https://www.ebs.tga.gov.au/ebs/picmi/picmirepository.nsf/pdf?OpenAgent&id=CP-2018-PI-01582-1",
        "document_date": "2024-02-15",
        "revision_date": "2024-02-15",
        "version": "Version 3.2",
        "section_4_6": {
            "title": "4.6. FERTILITY, PREGNANCY AND LACTATION",
            "pages": "12–13",
            "content": (
                "4.6. FERTILITY, PREGNANCY AND LACTATION\n\n"
                "Effects on fertility:\n"
                "In rat fertility studies, semaglutide did not affect male fertility. In female rats, an increase in estrous cycle length "
                "and a small reduction in numbers of corpora lutea and implantations were observed at doses associated with maternal body weight loss.\n\n"
                "Use in pregnancy (Category D):\n"
                "Studies in animals have shown reproductive toxicity. Ozempic should not be used during pregnancy. If a patient wishes to "
                "become pregnant, or pregnancy occurs, treatment with Ozempic should be discontinued. Semaglutide should be discontinued at "
                "least 2 months before a planned pregnancy due to the long half-life.\n\n"
                "Use in lactation:\n"
                "In lactating rats, semaglutide was excreted in milk. A risk to the breast-fed child cannot be excluded. Ozempic should not "
                "be used during breast-feeding."
            ),
        },
        "section_4_8": {
            "title": "4.8. ADVERSE EFFECTS (UNDESIRABLE EFFECTS)",
            "pages": "14–18",
            "content": (
                "4.8. ADVERSE EFFECTS (UNDESIRABLE EFFECTS)\n\n"
                "Summary of the safety profile:\n"
                "In 8 phase 3a trials, 4,792 patients were exposed to Ozempic. The most frequently reported adverse reactions in clinical trials "
                "were gastrointestinal disorders, including nausea (very common), diarrhoea (very common) and vomiting (common).\n\n"
                "Table 2: Adverse reactions from long-term phase 3a controlled trials\n\n"
                "| System Organ Class | Very Common (≥1/10) | Common (≥1/100 to <1/10) | Uncommon (≥1/1,000 to <1/100) |\n"
                "| --- | --- | --- | --- |\n"
                "| Immune system disorders | | | Hypersensitivity, anaphylactic reaction |\n"
                "| Metabolism and nutrition disorders | Hypoglycaemia (when used with insulin/SU) | Decreased appetite | |\n"
                "| Nervous system disorders | | Dizziness, headache | Dysgeusia |\n"
                "| Eye disorders | | Diabetic retinopathy complications | |\n"
                "| Cardiac disorders | | | Heart rate increased |\n"
                "| Gastrointestinal disorders | Nausea, diarrhoea | Vomiting, abdominal pain, constipation, dyspepsia, gastritis, GERD | Eructation, flatulence, acute pancreatitis |\n"
                "| Hepatobiliary disorders | | Cholelithiasis | |\n\n"
                "Description of selected adverse reactions:\n"
                "Hypoglycaemia: Severe hypoglycaemia was primarily observed when Ozempic was combined with a sulfonylurea or insulin."
            ),
            "tables": [
                {
                    "caption": "Table 2: Adverse reactions from long-term phase 3a controlled trials",
                    "page": 15,
                    "columns": ["System Organ Class", "Very Common (≥1/10)", "Common (≥1/100 to <1/10)", "Uncommon (≥1/1,000 to <1/100)"],
                    "rows": [
                        {"System Organ Class": "Immune system disorders", "Very Common (≥1/10)": "", "Common (≥1/100 to <1/10)": "", "Uncommon (≥1/1,000 to <1/100)": "Hypersensitivity, anaphylactic reaction"},
                        {"System Organ Class": "Metabolism and nutrition disorders", "Very Common (≥1/10)": "Hypoglycaemia (when used with insulin/SU)", "Common (≥1/100 to <1/10)": "Decreased appetite", "Uncommon (≥1/1,000 to <1/100)": ""},
                        {"System Organ Class": "Nervous system disorders", "Very Common (≥1/10)": "", "Common (≥1/100 to <1/10)": "Dizziness, headache", "Uncommon (≥1/1,000 to <1/100)": "Dysgeusia"},
                        {"System Organ Class": "Eye disorders", "Very Common (≥1/10)": "", "Common (≥1/100 to <1/10)": "Diabetic retinopathy complications", "Uncommon (≥1/1,000 to <1/100)": ""},
                        {"System Organ Class": "Cardiac disorders", "Very Common (≥1/10)": "", "Common (≥1/100 to <1/10)": "", "Uncommon (≥1/1,000 to <1/100)": "Heart rate increased"},
                        {"System Organ Class": "Gastrointestinal disorders", "Very Common (≥1/10)": "Nausea, diarrhoea", "Common (≥1/100 to <1/10)": "Vomiting, abdominal pain, constipation, dyspepsia, gastritis, GERD", "Uncommon (≥1/1,000 to <1/100)": "Eructation, flatulence, acute pancreatitis"},
                        {"System Organ Class": "Hepatobiliary disorders", "Very Common (≥1/10)": "", "Common (≥1/100 to <1/10)": "Cholelithiasis", "Uncommon (≥1/1,000 to <1/100)": ""},
                    ],
                }
            ],
        },
    },
    "tecfidera": {
        "display_name": "TECFIDERA",
        "normalized_name": "tecfidera",
        "active_ingredient": "DIMETHYL FUMARATE",
        "application_number": "AUST R 197475",
        "sponsor": "BIOGEN AUSTRALIA PTY LTD",
        "dosage_form": "Gastro-resistant hard capsule 120mg, 240mg",
        "pi_url": "https://www.tga.gov.au/resources/prescription-medicines-registrations/tecfidera-dimethyl-fumarate",
        "cmi_url": "https://www.tga.gov.au/resources/cmi/tecfidera-cmi",
        "pdf_url": "https://www.ebs.tga.gov.au/ebs/picmi/picmirepository.nsf/pdf?OpenAgent&id=CP-2013-PI-01974-1",
        "document_date": "2023-08-10",
        "revision_date": "2023-08-10",
        "version": "Version 5.1",
        "section_4_6": {
            "title": "4.6. FERTILITY, PREGNANCY AND LACTATION",
            "pages": "10–11",
            "content": (
                "4.6. FERTILITY, PREGNANCY AND LACTATION\n\n"
                "Effects on fertility:\n"
                "There are no data on the effects of Tecfidera on human fertility. Dimethyl fumarate did not impair fertility in male or female rats.\n\n"
                "Use in pregnancy (Category B1):\n"
                "There are no or limited amount of data from the use of dimethyl fumarate in pregnant women. Animal studies have shown reproductive toxicity. "
                "Tecfidera is not recommended during pregnancy and in women of childbearing potential not using appropriate contraception.\n\n"
                "Use in lactation:\n"
                "It is unknown whether dimethyl fumarate or its metabolites are excreted in human milk. A risk to the newborns/infants cannot be excluded. "
                "A decision must be made whether to discontinue breast-feeding or to discontinue Tecfidera therapy."
            ),
        },
        "section_4_8": {
            "title": "4.8. ADVERSE EFFECTS (UNDESIRABLE EFFECTS)",
            "pages": "12–16",
            "content": (
                "4.8. ADVERSE EFFECTS (UNDESIRABLE EFFECTS)\n\n"
                "Summary of safety profile:\n"
                "The most common adverse reactions (incidence ≥10%) for Tecfidera were flushing and gastrointestinal events (i.e. diarrhoea, nausea, abdominal pain).\n\n"
                "Table 1: Adverse reactions reported in clinical trials\n\n"
                "| System Organ Class | Frequency | Adverse Reaction |\n"
                "| --- | --- | --- |\n"
                "| Infections and infestations | Common (≥1/100 to <1/10) | Gastroenteritis |\n"
                "| Blood and lymphatic system disorders | Common (≥1/100 to <1/10) | Lymphopenia, leucopenia |\n"
                "| Nervous system disorders | Common (≥1/100 to <1/10) | Burning sensation |\n"
                "| Vascular disorders | Very common (≥1/10) | Flushing, hot flush |\n"
                "| Gastrointestinal disorders | Very common (≥1/10) | Diarrhoea, nausea, upper abdominal pain |\n"
                "| Gastrointestinal disorders | Common (≥1/100 to <1/10) | Vomiting, dyspepsia, gastritis |\n"
                "| Hepatobiliary disorders | Common (≥1/100 to <1/10) | Aspartate aminotransferase increased, alanine aminotransferase increased |\n\n"
                "Description of selected adverse reactions:\n"
                "Progressive Multifocal Leukoencephalopathy (PML): Cases of fatal PML have occurred in patients treated with Tecfidera in the setting of severe and prolonged lymphopenia."
            ),
            "tables": [
                {
                    "caption": "Table 1: Adverse reactions reported in clinical trials",
                    "page": 13,
                    "columns": ["System Organ Class", "Frequency", "Adverse Reaction"],
                    "rows": [
                        {"System Organ Class": "Infections and infestations", "Frequency": "Common (≥1/100 to <1/10)", "Adverse Reaction": "Gastroenteritis"},
                        {"System Organ Class": "Blood and lymphatic system disorders", "Frequency": "Common (≥1/100 to <1/10)", "Adverse Reaction": "Lymphopenia, leucopenia"},
                        {"System Organ Class": "Nervous system disorders", "Frequency": "Common (≥1/100 to <1/10)", "Adverse Reaction": "Burning sensation"},
                        {"System Organ Class": "Vascular disorders", "Frequency": "Very common (≥1/10)", "Adverse Reaction": "Flushing, hot flush"},
                        {"System Organ Class": "Gastrointestinal disorders", "Frequency": "Very common (≥1/10)", "Adverse Reaction": "Diarrhoea, nausea, upper abdominal pain"},
                        {"System Organ Class": "Gastrointestinal disorders", "Frequency": "Common (≥1/100 to <1/10)", "Adverse Reaction": "Vomiting, dyspepsia, gastritis"},
                        {"System Organ Class": "Hepatobiliary disorders", "Frequency": "Common (≥1/100 to <1/10)", "Adverse Reaction": "Aspartate aminotransferase increased, alanine aminotransferase increased"},
                    ],
                }
            ],
        },
    },
    "aspirin": {
        "display_name": "ASPIRIN",
        "normalized_name": "aspirin",
        "active_ingredient": "ACETYLSALICYLIC ACID",
        "application_number": "AUST R 13813",
        "sponsor": "BAYER AUSTRALIA LTD",
        "dosage_form": "Oral tablet 100mg, 300mg, 500mg",
        "pi_url": "https://www.tga.gov.au/resources/prescription-medicines-registrations/aspirin-acetylsalicylic-acid",
        "cmi_url": "https://www.tga.gov.au/resources/cmi/aspirin-cmi",
        "pdf_url": "https://www.ebs.tga.gov.au/ebs/picmi/picmirepository.nsf/pdf?OpenAgent&id=CP-2012-PI-01381-1",
        "document_date": "2022-09-01",
        "revision_date": "2022-09-01",
        "version": "Version 2.0",
        "section_4_6": {
            "title": "4.6. FERTILITY, PREGNANCY AND LACTATION",
            "pages": "6–7",
            "content": (
                "4.6. FERTILITY, PREGNANCY AND LACTATION\n\n"
                "Use in pregnancy (Category C):\n"
                "Inhibition of prostaglandin synthesis may adversely affect pregnancy and/or embryo/foetal development. "
                "During the third trimester of pregnancy, all prostaglandin synthesis inhibitors may expose the foetus to cardiopulmonary "
                "toxicity with premature closure of the ductus arteriosus and pulmonary hypertension, and renal dysfunction. "
                "Aspirin is contraindicated in the third trimester of pregnancy.\n\n"
                "Use in lactation:\n"
                "Aspirin and its metabolites pass into breast milk in small amounts. Short-term use is not expected to cause harm, but regular "
                "or high-dose use should be avoided during breast-feeding."
            ),
        },
        "section_4_8": {
            "title": "4.8. ADVERSE EFFECTS (UNDESIRABLE EFFECTS)",
            "pages": "8–10",
            "content": (
                "4.8. ADVERSE EFFECTS (UNDESIRABLE EFFECTS)\n\n"
                "Common adverse effects include dyspepsia, nausea, vomiting, and occult gastrointestinal blood loss.\n\n"
                "Table: Tabulated adverse reactions\n\n"
                "| System Organ Class | Frequency | Adverse Reaction |\n"
                "| --- | --- | --- |\n"
                "| Blood and lymphatic system disorders | Common (≥1/100 to <1/10) | Prolonged bleeding time, thrombocytopenia |\n"
                "| Gastrointestinal disorders | Very common (≥1/10) | Gastric irritation, heartburn, nausea |\n"
                "| Gastrointestinal disorders | Common (≥1/100 to <1/10) | Gastric ulceration, vomiting, gastrointestinal haemorrhage |\n"
                "| Immune system disorders | Uncommon (≥1/1,000 to <1/100) | Urticaria, rhinitis, bronchospasm, anaphylaxis |\n"
                "| Hepatic disorders | Rare (≥1/10,000 to <1/1,000) | Reye's syndrome in children, hepatic impairment |\n"
            ),
            "tables": [
                {
                    "caption": "Table: Tabulated adverse reactions",
                    "page": 9,
                    "columns": ["System Organ Class", "Frequency", "Adverse Reaction"],
                    "rows": [
                        {"System Organ Class": "Blood and lymphatic system disorders", "Frequency": "Common (≥1/100 to <1/10)", "Adverse Reaction": "Prolonged bleeding time, thrombocytopenia"},
                        {"System Organ Class": "Gastrointestinal disorders", "Frequency": "Very common (≥1/10)", "Adverse Reaction": "Gastric irritation, heartburn, nausea"},
                        {"System Organ Class": "Gastrointestinal disorders", "Frequency": "Common (≥1/100 to <1/10)", "Adverse Reaction": "Gastric ulceration, vomiting, gastrointestinal haemorrhage"},
                        {"System Organ Class": "Immune system disorders", "Frequency": "Uncommon (≥1/1,000 to <1/100)", "Adverse Reaction": "Urticaria, rhinitis, bronchospasm, anaphylaxis"},
                        {"System Organ Class": "Hepatic disorders", "Frequency": "Rare (≥1/10,000 to <1/1,000)", "Adverse Reaction": "Reye's syndrome in children, hepatic impairment"},
                    ],
                }
            ],
        },
    },
    "warfarin": {
        "display_name": "COUMADIN / MAREVAN (WARFARIN)",
        "normalized_name": "warfarin",
        "active_ingredient": "WARFARIN SODIUM",
        "application_number": "AUST R 14524",
        "sponsor": "VIATRIS PTY LTD",
        "dosage_form": "Oral tablet 1mg, 2mg, 3mg, 5mg",
        "pi_url": "https://www.tga.gov.au/resources/prescription-medicines-registrations/warfarin-sodium",
        "cmi_url": "https://www.tga.gov.au/resources/cmi/warfarin-cmi",
        "pdf_url": "https://www.ebs.tga.gov.au/ebs/picmi/picmirepository.nsf/pdf?OpenAgent&id=CP-2015-PI-01452-1",
        "document_date": "2023-05-18",
        "revision_date": "2023-05-18",
        "version": "Version 3.0",
        "section_4_6": {
            "title": "4.6. FERTILITY, PREGNANCY AND LACTATION",
            "pages": "7–8",
            "content": (
                "4.6. FERTILITY, PREGNANCY AND LACTATION\n\n"
                "Use in pregnancy (Category D):\n"
                "Warfarin is contraindicated in pregnancy because the drug passes through the placental barrier and may cause fatal "
                "haemorrhage to the fetus in utero. Furthermore, there have been reports of birth malformations in children born to mothers "
                "who have been treated with warfarin during pregnancy (warfarin embryopathy).\n\n"
                "Use in lactation:\n"
                "Warfarin appears in mother's milk in an inactive form. Infants nursed by warfarin-treated mothers had no changes in prothrombin times."
            ),
        },
        "section_4_8": {
            "title": "4.8. ADVERSE EFFECTS (UNDESIRABLE EFFECTS)",
            "pages": "9–12",
            "content": (
                "4.8. ADVERSE EFFECTS (UNDESIRABLE EFFECTS)\n\n"
                "Haemorrhage is the principal risk of warfarin therapy.\n\n"
                "Table: Summary of adverse events\n\n"
                "| System Organ Class | Frequency | Adverse Reaction |\n"
                "| --- | --- | --- |\n"
                "| Blood and lymphatic system disorders | Very common (≥1/10) | Haemorrhage from any tissue or organ (epistaxis, haematuria, GI bleeding) |\n"
                "| Vascular disorders | Rare (≥1/10,000 to <1/1,000) | Calciphylaxis, purple toes syndrome, cholesterol microembolisation |\n"
                "| Skin and subcutaneous tissue disorders | Rare (≥1/10,000 to <1/1,000) | Warfarin-induced skin necrosis, alopecia, rash |\n"
                "| Hepatobiliary disorders | Rare (≥1/10,000 to <1/1,000) | Hepatic dysfunction, jaundice |\n\n"
                "Calciphylaxis: Rare cases of calciphylaxis have been reported in patients taking warfarin, including those with normal renal function."
            ),
            "tables": [
                {
                    "caption": "Table: Summary of adverse events",
                    "page": 10,
                    "columns": ["System Organ Class", "Frequency", "Adverse Reaction"],
                    "rows": [
                        {"System Organ Class": "Blood and lymphatic system disorders", "Frequency": "Very common (≥1/10)", "Adverse Reaction": "Haemorrhage from any tissue or organ (epistaxis, haematuria, GI bleeding)"},
                        {"System Organ Class": "Vascular disorders", "Frequency": "Rare (≥1/10,000 to <1/1,000)", "Adverse Reaction": "Calciphylaxis, purple toes syndrome, cholesterol microembolisation"},
                        {"System Organ Class": "Skin and subcutaneous tissue disorders", "Frequency": "Rare (≥1/10,000 to <1/1,000)", "Adverse Reaction": "Warfarin-induced skin necrosis, alopecia, rash"},
                        {"System Organ Class": "Hepatobiliary disorders", "Frequency": "Rare (≥1/10,000 to <1/1,000)", "Adverse Reaction": "Hepatic dysfunction, jaundice"},
                    ],
                }
            ],
        },
    },
    "atorvastatin": {
        "display_name": "LIPITOR (ATORVASTATIN)",
        "normalized_name": "atorvastatin",
        "active_ingredient": "ATORVASTATIN CALCIUM",
        "application_number": "AUST R 59344",
        "sponsor": "VIATRIS PTY LTD",
        "dosage_form": "Film-coated tablet 10mg, 20mg, 40mg, 80mg",
        "pi_url": "https://www.ebs.tga.gov.au/ebs/picmi/picmirepository.nsf/ViewPortalDoc?OpenAgent&unid=CA257A1E003D918FCA258E36000B2F19",
        "cmi_url": None,
        "pdf_url": "https://www.ebs.tga.gov.au/ebs/picmi/picmirepository.nsf/ViewPortalDoc?OpenAgent&unid=CA257A1E003D918FCA258E36000B2F19",
        "document_date": "2024-04-18",
        "revision_date": "2024-04-18",
        "version": "Version 7.0",
        "section_4_6": {
            "title": "4.6. FERTILITY, PREGNANCY AND LACTATION",
            "pages": "11–12",
            "content": (
                "4.6. FERTILITY, PREGNANCY AND LACTATION\n\n"
                "Use in pregnancy (Category D):\n"
                "LIPITOR is contraindicated in pregnancy. Women of childbearing potential should use adequate contraception. "
                "Atherosclerosis is a chronic process, and discontinuation of lipid-lowering drugs during pregnancy should have "
                "little impact on the outcome of long-term therapy.\n\n"
                "Use in lactation:\n"
                "It is not known whether atorvastatin or its metabolites are excreted in human milk. Because of the potential for adverse "
                "reactions in nursing infants, women taking LIPITOR should not breast-feed."
            ),
        },
        "section_4_8": {
            "title": "4.8. ADVERSE EFFECTS (UNDESIRABLE EFFECTS)",
            "pages": "12–16",
            "content": (
                "4.8. ADVERSE EFFECTS (UNDESIRABLE EFFECTS)\n\n"
                "Clinical Adverse Experiences:\n"
                "In the atorvastatin placebo-controlled clinical trial database of 16,066 patients treated for a mean duration of 53 weeks, "
                "the most frequent adverse reactions leading to discontinuation were gastrointestinal symptoms, headache and myalgia.\n\n"
                "Table: Adverse Reactions Reported in ≥2% of Patients\n\n"
                "| System Organ Class | Common (≥1/100 to <1/10) | Adverse Reaction |\n"
                "| --- | --- | --- |\n"
                "| Infections and infestations | Common | Nasopharyngitis |\n"
                "| Metabolism and nutrition disorders | Common | Hyperglycaemia |\n"
                "| Respiratory disorders | Common | Pharyngolaryngeal pain, epistaxis |\n"
                "| Gastrointestinal disorders | Common | Diarrhoea, dyspepsia, nausea, flatulence |\n"
                "| Musculoskeletal and connective tissue disorders | Common | Arthralgia, pain in extremity, muscle spasms, myalgia |"
            ),
            "tables": [
                {
                    "caption": "Table: Adverse Reactions Reported in ≥2% of Patients",
                    "page": 13,
                    "columns": ["System Organ Class", "Common (≥1/100 to <1/10)", "Adverse Reaction"],
                    "rows": [
                        {"System Organ Class": "Infections and infestations", "Common (≥1/100 to <1/10)": "Common", "Adverse Reaction": "Nasopharyngitis"},
                        {"System Organ Class": "Metabolism and nutrition disorders", "Common (≥1/100 to <1/10)": "Common", "Adverse Reaction": "Hyperglycaemia"},
                        {"System Organ Class": "Respiratory disorders", "Common (≥1/100 to <1/10)": "Common", "Adverse Reaction": "Pharyngolaryngeal pain, epistaxis"},
                        {"System Organ Class": "Gastrointestinal disorders", "Common (≥1/100 to <1/10)": "Common", "Adverse Reaction": "Diarrhoea, dyspepsia, nausea, flatulence"},
                        {"System Organ Class": "Musculoskeletal and connective tissue disorders", "Common (≥1/100 to <1/10)": "Common", "Adverse Reaction": "Arthralgia, pain in extremity, muscle spasms, myalgia"},
                    ],
                }
            ],
        },
    },
}
