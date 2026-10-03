import openpyxl
import re
from collections import Counter

def analyze_linelisting(name, path):
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    header = rows[0]
    data = rows[1:]
    
    print(f"\n{'='*25} {name} {'='*25}")
    print(f"Total Rows (excl header): {len(data)}")
    print(f"Total Columns: {len(header)}")
    
    # Check Case Numbers
    case_idx = header.index("Case Number") if "Case Number" in header else 0
    ev_idx = header.index("Event Verbatim") if "Event Verbatim" in header else -1
    soc_idx = header.index("System Organ Class") if "System Organ Class" in header else -1
    pt_outcome_idx = header.index("Outcome of Event") if "Outcome of Event" in header else -1
    
    case_nums = [r[case_idx] for r in data if r[case_idx] is not None]
    distinct_cases = set(case_nums)
    print(f"Non-empty Case Number rows: {len(case_nums)}")
    print(f"Distinct Case Numbers: {len(distinct_cases)}")
    
    # Event Verbatim patterns
    ev_counts = Counter()
    total_events_extracted = 0
    bracket_term_pattern = re.compile(r'\[([^\]]+)\]')
    
    cases_with_events = {}
    for r_idx, r in enumerate(data):
        c_num = r[case_idx]
        ev_val = str(r[ev_idx]) if (ev_idx >= 0 and r[ev_idx] is not None) else ""
        
        # Clean hex escapes like _x0015_, _x0016_, _x000D_
        ev_clean = re.sub(r'_x[0-9a-fA-F]{4}_', '', ev_val)
        
        # Extract terms in brackets
        bracket_terms = bracket_term_pattern.findall(ev_clean)
        clean_terms = []
        for t in bracket_terms:
            t = t.strip()
            # remove trailing underscores or punctuation
            t = re.sub(r'[\r\n\t]+', ' ', t)
            t = re.sub(r'\s+', ' ', t).strip()
            if t:
                clean_terms.append(t)
        
        if c_num not in cases_with_events:
            cases_with_events[c_num] = []
        cases_with_events[c_num].extend(clean_terms)
        total_events_extracted += len(clean_terms)
    
    events_per_case = [len(terms) for terms in cases_with_events.values()]
    print(f"Total Bracket Terms extracted: {total_events_extracted}")
    print(f"Max events in a single case: {max(events_per_case) if events_per_case else 0}")
    print(f"Min events in a single case: {min(events_per_case) if events_per_case else 0}")
    print(f"Avg events per case: {sum(events_per_case)/len(events_per_case) if events_per_case else 0:.2f}")
    
    # Look at top terms
    all_terms = [t for terms in cases_with_events.values() for t in terms]
    top_terms = Counter(all_terms).most_common(10)
    print("Top 10 Extracted Event Terms:")
    for term, cnt in top_terms:
        print(f"  - {term}: {cnt}")

analyze_linelisting("Abiraterone Interval LL", "/Users/satya/Downloads/Required Artifacts for section 16.3 (3)/Abiraterone/Abiraterone_20260428_CAN-KUW-OMAN-UAE PBRER_Interval Linelisting.xlsx")
analyze_linelisting("Oxycodone Interval LL", "/Users/satya/Downloads/Required Artifacts for section 16.3 (3)/Oxycodone/Oxycodone_20260412_CAN PBRER_Interval LL.xlsx")
