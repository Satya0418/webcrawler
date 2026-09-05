"""
HTML UI and Data Export Generator for Medicine Safety Platform.
Clean, minimalist, white-background design matching the official FDA SrLC format.
Provides CSV and JSON export generators.
"""
import csv
import io
import json
import html
import re
from datetime import datetime
from typing import List, Dict, Any
from collections import defaultdict

from app.scrapers.fda_srlc_scraper import (
    clean_adverse_reaction_text,
    format_fda_date_to_report,
    parse_fda_date,
)


def _get_val(obj: Any, attr: str, default: Any = "") -> Any:
    if isinstance(obj, dict):
        val = obj.get(attr)
    else:
        val = getattr(obj, attr, default)
    return default if val is None else val


def export_drug_csv(drug: Any, changes: List[Any]) -> str:
    """Generate RFC 4180 compliant CSV of all safety labeling changes for a drug."""
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

    # Header
    writer.writerow([
        "Drug Name",
        "Active Ingredient",
        "Application Number",
        "Supplement Date",
        "Supplement ID",
        "Labeling Section",
        "Change Type",
        "Updated Text",
        "Original Text",
        "FDA Comment / PDF URL",
        "Content Hash (SHA-256)",
        "Last Verified Date",
    ])

    d_name = _get_val(drug, "display_name", "")
    active_ingr = _get_val(drug, "active_ingredient", "")
    app_num = _get_val(drug, "application_number", "")

    for c in changes:
        s_date = _get_val(c, "source_date", "")
        s_date_str = str(s_date)[:10] if s_date else ""
        s_id = _get_val(c, "source_record_id", "")
        sec = _get_val(c, "section", "")
        chg_type = _get_val(c, "change_type", "Labeling Revision")
        up_text = _get_val(c, "updated_text", "")
        orig_text = _get_val(c, "original_text", "")
        fda_cmt = _get_val(c, "fda_comment", "") or _get_val(c, "source_url", "")
        c_hash = _get_val(c, "content_hash", "")
        verified = _get_val(c, "last_verified_at", "")
        verified_str = str(verified)[:19] if verified else ""

        writer.writerow([
            d_name,
            active_ingr,
            app_num,
            s_date_str,
            s_id,
            sec,
            chg_type,
            up_text,
            orig_text,
            fda_cmt,
            c_hash,
            verified_str,
        ])

    return output.getvalue()


def export_drug_json(drug: Any, changes: List[Any]) -> str:
    """Generate structured JSON of all safety labeling changes for a drug."""
    d_id = _get_val(drug, "id", None)
    d_name = _get_val(drug, "display_name", "")
    norm_name = _get_val(drug, "normalized_name", "")
    active_ingr = _get_val(drug, "active_ingredient", "")
    app_num = _get_val(drug, "application_number", "")
    source = _get_val(drug, "source", "FDA_SRLC")
    created = _get_val(drug, "created_at", "")
    updated = _get_val(drug, "updated_at", "")

    items = []
    for c in changes:
        s_date = _get_val(c, "source_date", None)
        app_date = _get_val(c, "approval_date", None)
        eff_date = _get_val(c, "effective_date", None)
        ver_date = _get_val(c, "last_verified_at", None)

        items.append({
            "id": _get_val(c, "id", None),
            "section": _get_val(c, "section", None),
            "source_record_id": _get_val(c, "source_record_id", None),
            "source_date": str(s_date)[:10] if s_date else None,
            "approval_date": str(app_date)[:10] if app_date else None,
            "effective_date": str(eff_date)[:10] if eff_date else None,
            "change_type": _get_val(c, "change_type", "Labeling Revision"),
            "updated_text": _get_val(c, "updated_text", None),
            "original_text": _get_val(c, "original_text", None),
            "fda_comment": _get_val(c, "fda_comment", None),
            "source_url": _get_val(c, "source_url", None),
            "content_hash": _get_val(c, "content_hash", None),
            "last_verified_at": str(ver_date) if ver_date else None,
        })

    data = {
        "drug": {
            "id": d_id,
            "display_name": d_name,
            "normalized_name": norm_name,
            "active_ingredient": active_ingr,
            "application_number": app_num,
            "source": source,
            "created_at": str(created) if created else None,
            "updated_at": str(updated) if updated else None,
        },
        "total_safety_changes": len(items),
        "safety_changes": items,
    }
    return json.dumps(data, indent=2)


def render_homepage_html(query: str = "", results: list = None, error: str = None) -> str:
    """Render a clean, white-background search homepage with optional results."""
    results_html = ""
    if error:
        results_html = f"""
        <div class="alert alert-error">
            {html.escape(error)}
        </div>
        """
    elif results is not None:
        if not results:
            results_html = f"""
            <div class="alert alert-info">
                No safety labeling changes found for "<strong>{html.escape(query)}</strong>".
            </div>
            """
        else:
            cards = []
            for r in results:
                d_id = r.get("drug_id") or r.get("id")
                d_name = html.escape(r.get("drug_name") or r.get("display_name") or "")
                ingr = html.escape(r.get("active_ingredient") or "Not specified")
                app_num = html.escape(r.get("application_number") or "N/A")
                cnt = r.get("safety_change_count", 0)
                verified = str(r.get("last_verified_at", ""))[:10] if r.get("last_verified_at") else "Recent"

                cards.append(f"""
                <div class="result-row">
                    <div class="result-main">
                        <a href="/drugs/{d_id}" class="result-drug-name">{d_name}</a>
                        <div class="result-details">
                            Active Ingredient: <strong>{ingr}</strong> &bull; Application: <strong>{app_num}</strong>
                        </div>
                        <div class="result-meta">
                            <span class="badge">{cnt} Labeling Updates</span>
                            <span class="meta-item">Source: FDA SrLC</span>
                            <span class="meta-item">Updated: {verified}</span>
                        </div>
                    </div>
                    <div class="result-action">
                        <a href="/drugs/{d_id}" class="btn btn-secondary">View Adverse Reactions &rarr;</a>
                        <a href="/drugs/{d_id}/export?format=csv" class="btn btn-outline" title="Download CSV">CSV</a>
                        <a href="/drugs/{d_id}/export?format=json" class="btn btn-outline" title="Download JSON">JSON</a>
                    </div>
                </div>
                """)

            results_html = f"""
            <div class="results-container">
                <div class="results-header">
                    Results for "<strong>{html.escape(query)}</strong>" ({len(results)} found)
                </div>
                <div class="results-list">
                    {"".join(cards)}
                </div>
            </div>
            """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Medicine Safety Information - FDA SrLC</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
            background-color: #ffffff;
            color: #212529;
            margin: 0;
            padding: 0;
            line-height: 1.5;
        }}
        .header {{
            background: #f8f9fa;
            border-bottom: 1px solid #e5e7eb;
            padding: 16px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        .header-title {{
            font-size: 18px;
            font-weight: 700;
            color: #111827;
            text-decoration: none;
        }}
        .header-links a {{
            color: #4b5563;
            text-decoration: none;
            margin-left: 20px;
            font-size: 14px;
        }}
        .header-links a:hover {{ color: #0284c7; text-decoration: underline; }}
        .main {{
            max-width: 900px;
            margin: 40px auto;
            padding: 0 20px;
        }}
        .hero {{
            text-align: center;
            margin-bottom: 30px;
        }}
        .hero h1 {{
            font-size: 28px;
            color: #111827;
            margin-bottom: 8px;
            font-weight: 700;
        }}
        .hero p {{
            color: #6b7280;
            font-size: 15px;
            margin: 0;
        }}
        .search-box {{
            display: flex;
            gap: 8px;
            max-width: 650px;
            margin: 25px auto 40px auto;
        }}
        .search-input {{
            flex: 1;
            padding: 12px 16px;
            border: 1px solid #d1d5db;
            border-radius: 6px;
            font-size: 16px;
            outline: none;
            background: #fff;
            color: #111827;
        }}
        .search-input:focus {{
            border-color: #0284c7;
            box-shadow: 0 0 0 3px rgba(2, 132, 199, 0.15);
        }}
        .btn {{
            padding: 12px 20px;
            border-radius: 6px;
            font-size: 15px;
            font-weight: 600;
            cursor: pointer;
            text-decoration: none;
            border: 1px solid transparent;
            display: inline-flex;
            align-items: center;
        }}
        .btn-primary {{
            background: #0284c7;
            color: #fff;
        }}
        .btn-primary:hover {{ background: #0369a1; }}
        .btn-secondary {{
            background: #f3f4f6;
            color: #1f2937;
            border: 1px solid #d1d5db;
            font-size: 13px;
            padding: 8px 14px;
        }}
        .btn-secondary:hover {{ background: #e5e7eb; }}
        .btn-outline {{
            background: #fff;
            color: #4b5563;
            border: 1px solid #d1d5db;
            font-size: 12px;
            padding: 8px 12px;
            font-weight: 600;
        }}
        .btn-outline:hover {{
            background: #f9fafb;
            color: #111827;
            border-color: #9ca3af;
        }}
        .results-container {{
            margin-top: 20px;
        }}
        .results-header {{
            font-size: 16px;
            font-weight: 600;
            color: #374151;
            margin-bottom: 16px;
            border-bottom: 2px solid #e5e7eb;
            padding-bottom: 8px;
        }}
        .result-row {{
            border: 1px solid #e5e7eb;
            border-radius: 6px;
            padding: 18px 20px;
            margin-bottom: 12px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: #fff;
            flex-wrap: wrap;
            gap: 12px;
        }}
        .result-row:hover {{
            border-color: #cbd5e1;
            background: #fafafa;
        }}
        .result-drug-name {{
            font-size: 20px;
            font-weight: 700;
            color: #0369a1;
            text-decoration: none;
        }}
        .result-drug-name:hover {{ text-decoration: underline; }}
        .result-details {{
            color: #4b5563;
            font-size: 14px;
            margin: 4px 0 8px 0;
        }}
        .result-meta {{
            display: flex;
            gap: 12px;
            align-items: center;
        }}
        .result-action {{
            display: flex;
            gap: 8px;
            align-items: center;
        }}
        .badge {{
            background: #e0f2fe;
            color: #0369a1;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
        }}
        .meta-item {{
            color: #6b7280;
            font-size: 13px;
        }}
        .alert {{
            padding: 14px 18px;
            border-radius: 6px;
            font-size: 14px;
            margin-bottom: 20px;
        }}
        .alert-info {{ background: #f0fdf4; border: 1px solid #bbf7d0; color: #166534; }}
        .alert-error {{ background: #fef2f2; border: 1px solid #fecaca; color: #991b1b; }}
        .disclaimer {{
            margin-top: 50px;
            padding: 14px;
            background: #f9fafb;
            border: 1px solid #e5e7eb;
            border-radius: 6px;
            font-size: 12px;
            color: #6b7280;
            line-height: 1.5;
        }}
    </style>
</head>
<body>
    <header class="header">
        <a href="/" class="header-title">FDA Drug Safety-related Labeling Changes (SrLC)</a>
    </header>

    <main class="main">
        <div class="hero">
            <h1>Search Medicine Safety Labeling Changes</h1>
            <p>Retrieve authoritative safety information, warnings, and revisions directly from the FDA SrLC database.</p>
        </div>

        <form action="/" method="get" class="search-box">
            <input type="text" name="q" class="search-input" placeholder="Enter medicine or active ingredient (e.g. ZYVOX, Warfarin)..." required value="{html.escape(query)}">
            <button type="submit" class="btn btn-primary">Search</button>
        </form>

        {results_html}

        <div class="disclaimer">
            <strong>Disclaimer:</strong> Regulatory drug safety-related labeling changes provided for informational purposes only. Sourced from the U.S. FDA Center for Drug Evaluation and Research (CDER). Not intended as medical advice.
        </div>
    </main>
</body>
</html>
"""


def render_drug_detail_html(drug: dict, changes: list) -> str:
    """
    Render drug safety labeling detail page showing ONLY Adverse Reactions.
    Formats the report exactly as specified in regulatory reporting style:
    - Displays 3.1 The United States Food and Drug Administration header
    - Introductory approval sentence with DD-Mon-YYYY date
    - Adverse Reactions header
    - Subsection headers (e.g. Postmarketing Experience)
    - Clean disorder paragraphs
    - Removes all Section 17 PCI/PI/MG, Medication Guides, Warnings, and noise.
    - If no adverse reaction data exists, displays 'No data is present on adverse reaction'.
    """
    d_id = drug.get("id") or 1
    display_name = drug.get("display_name") or ""
    display_clean = display_name.title() if display_name.isupper() else display_name
    active_ingredient = drug.get("active_ingredient") or "Not specified"
    ingr_clean = re.sub(r"\b(sulfate|hydrochloride|sodium|potassium|acetate)\b", "", active_ingredient.lower(), flags=re.I).strip()
    if not ingr_clean:
        ingr_clean = active_ingredient.lower()

    application_number = drug.get("application_number") or "N/A"

    # Filter changes for ONLY Adverse Reactions
    ar_changes = []
    for c in changes:
        sec = _get_val(c, "section", "")
        if re.search(r"(?i)\badverse\s+reactions?\b", sec):
            ar_changes.append(c)

    # Group Adverse Reactions by distinct parsed supplement date
    grouped = defaultdict(list)
    for c in ar_changes:
        s_date = _get_val(c, "source_date")
        dt_obj = parse_fda_date(s_date)
        date_str = dt_obj.strftime("%m/%d/%Y") if dt_obj else (str(s_date)[:10] if s_date else "Recent")
        group_key = (date_str, dt_obj or datetime.min)
        grouped[group_key].append(c)

    # Sort dates chronologically descending (newest date first)
    sorted_groups = sorted(grouped.items(), key=lambda item: item[0][1], reverse=True)

    report_sheets_html = []
    plain_reports = []

    for (date_str, dt_obj), section_changes in sorted_groups:
        formatted_date = format_fda_date_to_report(dt_obj) if dt_obj else format_fda_date_to_report(date_str)
        suppl_ids = list(dict.fromkeys([_get_val(c, "source_record_id") for c in section_changes if _get_val(c, "source_record_id")]))
        suppl_id = ", ".join(suppl_ids) if suppl_ids else None

        seen_texts = set()
        raw_texts = []
        for chg in section_changes:
            txt = (_get_val(chg, "updated_text") or "").strip()
            if txt and txt not in seen_texts:
                seen_texts.add(txt)
                raw_texts.append(txt)

        cleaned_text = clean_adverse_reaction_text("\n\n".join(raw_texts))
        if not cleaned_text:
            continue

        intro_sentence = (
            f"On {formatted_date}, the United States Food and Drug Administration "
            f"Center for Drug Evaluation and Research approved the following safety labeling "
            f"changes for {display_clean} ({ingr_clean}; Additions underlined):"
        )

        body_html_parts = []
        plain_text_lines = [
            "3.1 The United States Food and Drug Administration",
            "",
            intro_sentence,
            "",
            "Adverse Reactions",
            "",
        ]

        blocks = cleaned_text.split("\n\n")
        for block in blocks:
            block = block.strip()
            if not block:
                continue

            plain_text_lines.append(block)
            plain_text_lines.append("")

            # If block is a subsection title (e.g. "Postmarketing Experience")
            if len(block) < 60 and ("Experience" in block or "Reactions" in block or not ":" in block):
                body_html_parts.append(f'<h4 class="report-subheading">{html.escape(block)}</h4>')
            elif ":" in block:
                # Format disorders line with bold prefix
                label, desc = block.split(":", 1)
                body_html_parts.append(
                    f'<p class="report-disorder"><strong>{html.escape(label.strip())}:</strong> {html.escape(desc.strip())}</p>'
                )
            else:
                body_html_parts.append(f'<p class="report-disorder">{html.escape(block)}</p>')

        single_plain_report = "\n".join(plain_text_lines).strip()
        plain_reports.append(single_plain_report)

        suppl_label = f"({html.escape(suppl_id)})" if suppl_id else ""
        report_sheets_html.append(f"""
        <div class="report-sheet">
            <div class="report-sheet-top">
                <span class="suppl-badge">Supplement Date: {html.escape(date_str)} {suppl_label}</span>
                <button type="button" class="btn-copy-card" onclick="copyText(this)" data-copy="{html.escape(single_plain_report)}">
                    📋 Copy Text
                </button>
            </div>

            <div class="report-sheet-content">
                <div class="report-sec-num">3.1 The United States Food and Drug Administration</div>
                <p class="report-intro-p">
                    On {html.escape(formatted_date)}, the United States Food and Drug Administration Center for Drug Evaluation and Research approved the following safety labeling changes for {html.escape(display_clean)} ({html.escape(ingr_clean)}; <em>Additions underlined</em>):
                </p>

                <h3 class="report-main-heading">Adverse Reactions</h3>

                <div class="report-body-container">
                    {"".join(body_html_parts)}
                </div>
            </div>
        </div>
        """)

    if not report_sheets_html:
        main_content_html = """
        <div class="no-data-box">
            <div class="no-data-icon">⚠️</div>
            <h2 class="no-data-title">No data is present on adverse reaction</h2>
            <p class="no-data-desc">No Adverse Reactions safety-related labeling changes were approved or recorded for this medicine in the FDA SrLC database.</p>
        </div>
        """
        top_copy_btn = ""
    else:
        latest_sheet = report_sheets_html[0]
        older_sheets = report_sheets_html[1:]
        older_html = ""
        if older_sheets:
            older_html = f"""
            <details class="older-revisions-details">
                <summary class="older-revisions-summary">
                    📁 Previous Adverse Reactions Labeling Updates ({len(older_sheets)} prior)
                </summary>
                <div class="older-revisions-content">
                    {"".join(older_sheets)}
                </div>
            </details>
            """
        main_content_html = f"{latest_sheet}\n{older_html}"
        top_copy_btn = f"""
        <button type="button" class="btn-export btn-copy-primary" onclick="copyText(this)" data-copy="{html.escape(plain_reports[0])}">
            📋 Copy Report
        </button>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{display_clean} ({application_number}) - Adverse Reactions</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
            background-color: #ffffff;
            color: #111827;
            margin: 0;
            padding: 0;
            line-height: 1.6;
            font-size: 15px;
        }}
        .top-nav {{
            background: #f8f9fa;
            border-bottom: 1px solid #dee2e6;
            padding: 10px 24px;
            font-size: 13px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .top-nav a {{
            color: #0066cc;
            text-decoration: none;
            font-weight: 500;
        }}
        .top-nav a:hover {{ text-decoration: underline; }}
        .page-container {{
            max-width: 900px;
            margin: 24px auto 60px auto;
            padding: 0 20px;
        }}
        .drug-header {{
            margin-bottom: 24px;
            padding-bottom: 16px;
            border-bottom: 1px solid #e5e7eb;
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            flex-wrap: wrap;
            gap: 16px;
        }}
        .drug-header-main {{
            flex: 1;
        }}
        .drug-name {{
            font-size: 26px;
            font-weight: 700;
            color: #111827;
            margin: 0 0 4px 0;
        }}
        .app-number {{
            font-weight: 400;
            color: #4b5563;
        }}
        .ingredient {{
            font-size: 16px;
            font-weight: 600;
            color: #374151;
            margin: 0 0 6px 0;
        }}
        .agency-subtitle {{
            color: #6b7280;
            font-size: 13px;
            margin: 0;
        }}
        .export-actions {{
            display: flex;
            gap: 8px;
            align-items: center;
        }}
        .btn-export {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 7px 14px;
            border: 1px solid #d1d5db;
            border-radius: 4px;
            background: #ffffff;
            color: #1f2937;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            text-decoration: none;
            transition: all 0.15s ease-in-out;
        }}
        .btn-export:hover {{
            background: #0284c7;
            color: #ffffff;
            border-color: #0284c7;
        }}
        .btn-copy-primary {{
            background: #0284c7;
            color: #ffffff;
            border-color: #0284c7;
        }}
        .btn-copy-primary:hover {{
            background: #0369a1;
            border-color: #0369a1;
        }}
        .report-sheet {{
            background: #ffffff;
            border: 1px solid #d1d5db;
            border-radius: 6px;
            margin-bottom: 28px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }}
        .report-sheet-top {{
            background: #f3f4f6;
            padding: 10px 20px;
            border-bottom: 1px solid #e5e7eb;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .suppl-badge {{
            font-size: 13px;
            font-weight: 600;
            color: #374151;
        }}
        .btn-copy-card {{
            background: #ffffff;
            border: 1px solid #d1d5db;
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            color: #374151;
            transition: all 0.15s;
        }}
        .btn-copy-card:hover {{
            background: #f9fafb;
            border-color: #9ca3af;
        }}
        .report-sheet-content {{
            padding: 24px 28px 30px 28px;
        }}
        .report-sec-num {{
            font-size: 16px;
            font-weight: 700;
            color: #111827;
            margin-bottom: 16px;
        }}
        .report-intro-p {{
            font-size: 15px;
            color: #1f2937;
            margin-bottom: 20px;
            line-height: 1.6;
        }}
        .report-main-heading {{
            font-size: 18px;
            font-weight: 700;
            color: #111827;
            margin: 0 0 12px 0;
            padding-bottom: 4px;
            border-bottom: 1px solid #f3f4f6;
        }}
        .report-subheading {{
            font-size: 16px;
            font-weight: 700;
            color: #111827;
            margin: 16px 0 10px 0;
        }}
        .report-disorder {{
            font-size: 15px;
            color: #1f2937;
            margin: 10px 0;
            line-height: 1.6;
        }}
        .no-data-box {{
            background: #f9fafb;
            border: 1px solid #e5e7eb;
            border-radius: 6px;
            padding: 40px 20px;
            text-align: center;
            margin: 30px 0;
        }}
        .no-data-icon {{
            font-size: 32px;
            margin-bottom: 12px;
        }}
        .no-data-heading, .no-data-title {{
            font-size: 18px;
            font-weight: 700;
            color: #374151;
            margin: 0 0 8px 0;
        }}
        .no-data-desc {{
            color: #6b7280;
            font-size: 14px;
            margin: 0;
        }}
        .older-revisions-details {{
            margin-top: 24px;
            border: 1px solid #d1d5db;
            border-radius: 6px;
            background: #f9fafb;
            overflow: hidden;
        }}
        .older-revisions-summary {{
            padding: 12px 18px;
            font-size: 14px;
            font-weight: 600;
            color: #4b5563;
            cursor: pointer;
            outline: none;
            user-select: none;
        }}
        .older-revisions-summary:hover {{
            color: #0284c7;
            background: #f3f4f6;
        }}
        .older-revisions-content {{
            padding: 18px;
            background: #ffffff;
            border-top: 1px solid #e5e7eb;
        }}
        .footer-note {{
            margin-top: 40px;
            padding-top: 14px;
            border-top: 1px solid #e5e7eb;
            font-size: 12px;
            color: #6b7280;
        }}
    </style>
</head>
<body>
    <div class="top-nav">
        <div>
            <a href="/">&larr; Back to Search</a>
        </div>
    </div>

    <div class="page-container">
        <div class="drug-header">
            <div class="drug-header-main">
                <h1 class="drug-name">
                    {html.escape(display_clean)} <span class="app-number">({html.escape(application_number)})</span>
                </h1>
                <div class="ingredient">({html.escape(active_ingredient)})</div>
                <p class="agency-subtitle">Safety-related Labeling Changes Approved by FDA Center for Drug Evaluation and Research (CDER)</p>
            </div>
            <div class="export-actions">
                {top_copy_btn}
                <a href="/drugs/{d_id}/export?format=csv" class="btn-export" download>
                    📥 CSV
                </a>
                <a href="/drugs/{d_id}/export?format=json" class="btn-export" download>
                    📥 JSON
                </a>
            </div>
        </div>

        <div class="reports-container">
            {main_content_html}
        </div>

        <div class="footer-note">
            Source: U.S. Food and Drug Administration (FDA) Drug Safety-related Labeling Changes database.
        </div>
    </div>

    <script>
        function copyText(btn) {{
            var text = btn.getAttribute('data-copy');
            if (!text) return;
            navigator.clipboard.writeText(text).then(function() {{
                var orig = btn.innerHTML;
                btn.innerHTML = '✓ Copied!';
                btn.style.backgroundColor = '#16a34a';
                btn.style.borderColor = '#16a34a';
                btn.style.color = '#ffffff';
                setTimeout(function() {{
                    btn.innerHTML = orig;
                    btn.style.backgroundColor = '';
                    btn.style.borderColor = '';
                    btn.style.color = '';
                }}, 2000);
            }});
        }}
    </script>
</body>
</html>
"""
