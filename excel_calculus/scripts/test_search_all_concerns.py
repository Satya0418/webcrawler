import openpyxl
import re
from test_smq_hierarchy_parser import smq_terms

# Load Abiraterone Interval LL
ll_path = "/Users/satya/Downloads/Required Artifacts for section 16.3 (3)/Abiraterone/Abiraterone_20260428_CAN-KUW-OMAN-UAE PBRER_Interval Linelisting.xlsx"
wb_ll = openpyxl.load_workbook(ll_path, data_only=True)
ws_ll = wb_ll.active

rows = list(ws_ll.iter_rows(values_only=True))
headers = rows[0]
data = rows[1:]

idx_case = headers.index("Case Number")
idx_ev = headers.index("Event Verbatim")
idx_soc = headers.index("System Organ Class")
idx_prod = headers.index("Product Name")
idx_outcome = headers.index("Outcome of Event")
idx_narrative = headers.index("Case Narrative")

# Extract all case events
bracket_pattern = re.compile(r"\[([^\]]+)\]")
case_events = []
cases_data = {}

for r_idx, r in enumerate(data):
    c_num = r[idx_case]
    cases_data[c_num] = {
        "soc": r[idx_soc],
        "prod": r[idx_prod],
        "outcome": r[idx_outcome],
        "narrative": r[idx_narrative]
    }
    ev_raw = str(r[idx_ev]) if r[idx_ev] else ""
    ev_clean = re.sub(r"_x[0-9a-fA-F]{4}_", "", ev_raw)
    bracket_terms = bracket_pattern.findall(ev_clean)
    for pos, t in enumerate(bracket_terms):
        clean = re.sub(r"[\r\n\t]+", " ", t)
        clean = re.sub(r"\s+", " ", clean).strip()
        case_events.append({
            "case_number": c_num,
            "event": clean,
            "event_lower": clean.lower(),
            "pos": pos
        })

print(f"Loaded {len(cases_data)} cases, {len(case_events)} events.")

# 1. Hepatotoxicity: Drug related hepatic disorders - comprehensive search (Broad SMQ)
hep_terms = {t.lower(): t for t in smq_terms["Drug related hepatic disorders - comprehensive search (SMQ)"]["Broad"]}
hep_matches = [e for e in case_events if e["event_lower"] in hep_terms]
hep_cases = sorted(set(e["case_number"] for e in hep_matches))
print(f"\n1. HEPATOTOXICITY (Broad SMQ): {len(hep_matches)} events, {len(hep_cases)} distinct cases")
for c in hep_cases:
    m = [e["event"] for e in hep_matches if e["case_number"] == c]
    print(f"   Case {c}: {m}")

# 2. Cardiac Disorders: SOC cardiac disorder
cardiac_cases = sorted(set(c for c, d in cases_data.items() if d["soc"] and "cardiac" in str(d["soc"]).lower()))
# Also check if any individual events match cardiac terms
print(f"\n2. CARDIAC DISORDERS (SOC): {len(cardiac_cases)} distinct cases (SOC match)")
# Let's check event level for cardiac
cardiac_events = [e for e in case_events if any(k in e["event_lower"] for k in ["cardiac", "arrhythmia", "infarction", "tachycardia", "atrial fibrillation", "angina"])]
cardiac_ev_cases = sorted(set(e["case_number"] for e in cardiac_events))
print(f"   Event-level cardiac mentions: {len(cardiac_events)} events across {len(cardiac_ev_cases)} cases:")
for c in cardiac_ev_cases:
    m = [e["event"] for e in cardiac_events if e["case_number"] == c]
    print(f"   Case {c}: {m}")

# 3. Osteoporosis: Osteoporosis/osteopenia (Broad SMQ)
osteo_terms = {t.lower(): t for t in smq_terms["Osteoporosis/osteopenia (SMQ)"]["Broad"]}
osteo_matches = [e for e in case_events if e["event_lower"] in osteo_terms]
osteo_cases = sorted(set(e["case_number"] for e in osteo_matches))
print(f"\n3. OSTEOPOROSIS (Broad SMQ): {len(osteo_matches)} events, {len(osteo_cases)} distinct cases")
for c in osteo_cases:
    m = [e["event"] for e in osteo_matches if e["case_number"] == c]
    print(f"   Case {c}: {m}")

# 4. Allergic alveolitis: PT: Alveolitis
alveo_matches = [e for e in case_events if e["event_lower"] == "alveolitis"]
print(f"\n4. ALLERGIC ALVEOLITIS (PT: Alveolitis): {len(alveo_matches)} events")

# 5. Increased exposure with food: PTs: Labelled drug-food interaction issue, Labelled drug-food interaction medication error, food interaction
food_pts = {"labelled drug-food interaction issue", "labelled drug-food interaction medication error", "food interaction"}
food_matches = [e for e in case_events if e["event_lower"] in food_pts]
print(f"\n5. INCREASED EXPOSURE WITH FOOD: {len(food_matches)} events")

# 6. Rhabdomyolysis/Myopathy: Narrow SMQ of Rhabdomyolysis/myopathy
rhabdo_narrow = {t.lower(): t for t in smq_terms["Rhabdomyolysis/myopathy (SMQ)"]["Narrow"]}
rhabdo_matches = [e for e in case_events if e["event_lower"] in rhabdo_narrow]
rhabdo_cases = sorted(set(e["case_number"] for e in rhabdo_matches))
print(f"\n6. RHABDOMYOLYSIS/MYOPATHY (Narrow SMQ): {len(rhabdo_matches)} events, {len(rhabdo_cases)} distinct cases")
for c in rhabdo_cases:
    m = [e["event"] for e in rhabdo_matches if e["case_number"] == c]
    print(f"   Case {c}: {m}")

# 7. Cataract: PTs
cat_pts = {"cataract", "atopic cataract", "cataract nuclear", "cataract cortical", "toxic cataract", "cataract subcapsular"}
cat_matches = [e for e in case_events if e["event_lower"] in cat_pts]
print(f"\n7. CATARACT: {len(cat_matches)} events")

# 8. Drug-drug interaction with CYP2D6 inhibitors
cyp_pts = {"drug interaction", "potentiating drug interaction", "labelled drug-drug interaction issue", "labelled drug-drug interaction medication error"}
cyp_matches = [e for e in case_events if e["event_lower"] in cyp_pts]
cyp_cases = sorted(set(e["case_number"] for e in cyp_matches))
print(f"\n8. CYP2D6 INITIAL MATCHES (PT list): {len(cyp_matches)} events, {len(cyp_cases)} distinct cases")
for c in cyp_cases:
    m = [e["event"] for e in cyp_matches if e["case_number"] == c]
    prod = cases_data[c]["prod"]
    print(f"   Case {c}: {m} | Concomitant Products: {prod}")

# 9. Medication Error (Broad SMQ)
med_err_terms = {t.lower(): t for t in smq_terms["Medication errors (SMQ)"]["Broad"]}
med_err_matches = [e for e in case_events if e["event_lower"] in med_err_terms]
med_err_cases = sorted(set(e["case_number"] for e in med_err_matches))
print(f"\n9. MEDICATION ERROR (Broad SMQ): {len(med_err_matches)} events, {len(med_err_cases)} distinct cases")
for c in med_err_cases:
    m = [e["event"] for e in med_err_matches if e["case_number"] == c]
    print(f"   Case {c}: {m}")
