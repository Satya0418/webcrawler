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
from urllib.parse import quote_plus
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


def render_homepage_html(
    query: str = "",
    results: list = None,
    error: str = None,
    source: str = "ALL",
) -> str:
    """Render a clean search homepage with source selection and multi-authority results."""
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
                d_source = r.get("source") or "FDA_SRLC"
                is_mw = "MEDWATCH" in str(d_source).upper()
                is_mhra = "UK_MHRA" in str(d_source).upper() or "MHRA" in str(d_source).upper()
                is_hc = "HEALTH_CANADA" in str(d_source).upper() or "CANADA" in str(d_source).upper()
                is_tga = "AUSTRALIA_TGA" in str(d_source).upper() or "TGA" in str(d_source).upper()

                if is_mw:
                    source_badge = '<span class="badge badge-medwatch">🚨 FDA MedWatch</span>'
                    action_label = "View MedWatch Alerts &rarr;"
                    id_label = "Report / Event ID"
                elif is_mhra:
                    source_badge = '<span class="badge badge-mhra">🇬🇧 UK MHRA</span>'
                    action_label = "View MHRA Safety Update &rarr;"
                    id_label = "UK PL / Reference"
                elif is_tga:
                    source_badge = '<span class="badge badge-tga">🇦🇺 Australia TGA</span>'
                    action_label = "View TGA Product Info &rarr;"
                    id_label = "ARTG ID"
                elif is_hc:
                    source_badge = '<span class="badge badge-hc">🍁 Health Canada</span>'
                    action_label = "View Safety Information &rarr;"
                    id_label = "DIN"
                else:
                    source_badge = '<span class="badge badge-fda">🇺🇸 FDA SrLC</span>'
                    action_label = "View Adverse Reactions &rarr;"
                    id_label = "Application"

                cards.append(f"""
                <div class="result-row">
                    <div class="result-main">
                        <a href="/drugs/{d_id}" class="result-drug-name">{d_name}</a>
                        <div class="result-details">
                            Active Ingredient: <strong>{ingr}</strong> &bull; {id_label}: <strong>{app_num}</strong>
                        </div>
                        <div class="result-meta">
                            {source_badge}
                            <span class="badge">{cnt} Safety Updates</span>
                            <span class="meta-item">Updated: {verified}</span>
                        </div>
                    </div>
                    <div class="result-action">
                        <a href="/drugs/{d_id}" class="btn btn-secondary">{action_label}</a>
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

    selected_all = "selected" if source in ("ALL", "", None) else ""
    selected_mw = "selected" if source in ("FDA_MEDWATCH", "MEDWATCH") else ""
    selected_mhra = "selected" if source in ("UK_MHRA", "MHRA") else ""
    selected_tga = "selected" if source in ("AUSTRALIA_TGA", "TGA") else ""
    selected_hc = "selected" if source in ("HEALTH_CANADA_INFOWATCH", "HEALTH_CANADA") else ""
    selected_fda = "selected" if source in ("FDA_SRLC", "FDA") else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Medicine Safety Information - Health Canada & FDA</title>
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
            flex-wrap: wrap;
            gap: 12px;
        }}
        .header-title {{
            font-size: 18px;
            font-weight: 700;
            color: #111827;
            text-decoration: none;
        }}
        .header-sources {{
            display: flex;
            gap: 8px;
            align-items: center;
        }}
        .source-tag {{
            font-size: 12px;
            font-weight: 600;
            padding: 3px 10px;
            border-radius: 20px;
        }}
        .hc-tag {{
            background: #fef2f2;
            color: #b91c1c;
            border: 1px solid #fecaca;
        }}
        .fda-tag {{
            background: #eff6ff;
            color: #1d4ed8;
            border: 1px solid #bfdbfe;
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
            max-width: 720px;
            margin: 25px auto 40px auto;
            flex-wrap: wrap;
        }}
        .source-select {{
            padding: 12px 14px;
            border: 1px solid #d1d5db;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 600;
            background: #f9fafb;
            color: #374151;
            outline: none;
            cursor: pointer;
            min-width: 190px;
        }}
        .source-select:focus {{
            border-color: #0284c7;
            box-shadow: 0 0 0 3px rgba(2, 132, 199, 0.15);
        }}
        .search-input {{
            flex: 1;
            min-width: 240px;
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
            flex-wrap: wrap;
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
        .badge-hc {{
            background: #fef2f2;
            color: #b91c1c;
            border: 1px solid #fecaca;
        }}
        .badge-fda {{
            background: #eff6ff;
            color: #1d4ed8;
            border: 1px solid #bfdbfe;
        }}
        .badge-tga {{
            background: #f0fdf4;
            color: #15803d;
            border: 1px solid #bbf7d0;
        }}
        .badge-medwatch {{
            background: #fff1f2;
            color: #be123c;
            border: 1px solid #fecdd3;
        }}
        .badge-mhra {{
            background: #eef4f8;
            color: #003078;
            border: 1px solid #b6d5ee;
        }}
        .tga-tag {{
            background: #f0fdf4;
            color: #15803d;
            border: 1px solid #bbf7d0;
        }}
        .mw-tag {{
            background: #fff1f2;
            color: #be123c;
            border: 1px solid #fecdd3;
        }}
        .mhra-tag {{
            background: #eef4f8;
            color: #003078;
            border: 1px solid #b6d5ee;
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
        <a href="/" class="header-title">Medicine Safety Platform</a>
        <div class="header-sources">
            <span class="source-tag hc-tag">🍁 Health Canada</span>
            <span class="source-tag fda-tag">🇺🇸 US FDA SrLC</span>
            <span class="source-tag tga-tag">🇦🇺 Australia TGA</span>
            <span class="source-tag mw-tag">🚨 FDA MedWatch</span>
            <span class="source-tag mhra-tag">🇬🇧 UK MHRA</span>
        </div>
    </header>

    <main class="main">
        <div class="hero">
            <h1>Search Medicine Safety Information</h1>
            <p>Retrieve authoritative safety information, warnings, and revisions from <strong>U.S. FDA (SrLC & MedWatch)</strong>, <strong>Health Canada (MedEffect)</strong>, <strong>Australia TGA (Therapeutic Goods Administration)</strong>, and <strong>UK MHRA (Medicines and Healthcare products Regulatory Agency)</strong>.</p>
        </div>

        <form action="/" method="get" class="search-box">
            <select name="source" class="source-select" id="source-select" aria-label="Select Source">
                <option value="ALL" {selected_all}>🌐 All Sources (US + Canada + Australia + UK)</option>
                <option value="UK_MHRA" {selected_mhra}>🇬🇧 UK MHRA (Drug Safety Update)</option>
                <option value="FDA_MEDWATCH" {selected_mw}>🚨 FDA MedWatch (Safety Alerts & Adverse Events)</option>
                <option value="AUSTRALIA_TGA" {selected_tga}>🇦🇺 Australia TGA</option>
                <option value="HEALTH_CANADA_INFOWATCH" {selected_hc}>🍁 Health Canada InfoWatch</option>
                <option value="FDA_SRLC" {selected_fda}>🇺🇸 US FDA SrLC</option>
            </select>
            <input type="text" name="q" class="search-input" placeholder="Enter medicine or active ingredient (e.g. Ozempic, Tecfidera, Warfarin, Aspirin)..." required value="{html.escape(query)}">
            <button type="submit" class="btn btn-primary" id="search-submit">Search</button>
        </form>

        {results_html}

        <div class="disclaimer">
            <strong>Disclaimer:</strong> Regulatory drug safety information provided for informational purposes only. Sourced from the U.S. FDA Center for Drug Evaluation and Research (CDER), FDA MedWatch Safety Information and Adverse Event Reporting Program, Health Canada Marketed Health Products Directorate (MedEffect Canada), Australia Therapeutic Goods Administration (TGA), and the UK Medicines and Healthcare products Regulatory Agency (MHRA). Not intended as medical advice.
        </div>
    </main>
</body>
</html>
"""


def _render_health_canada_drug_detail(drug: dict, changes: list) -> str:
    """
    Render Health Canada InfoWatch drug detail page showing all safety updates,
    monographs, reviews, and advisories with complete source traceability.
    """
    d_id = drug.get("id") or 1
    display_name = drug.get("display_name") or ""
    display_clean = display_name.title() if display_name.isupper() else display_name
    active_ingredient = drug.get("active_ingredient") or "Not specified"
    application_number = drug.get("application_number") or ""

    plain_reports = []
    cards_html = []

    for c in changes:
        sec = _get_val(c, "section") or "Safety Information"
        chg_type = _get_val(c, "change_type") or "Labeling Revision"
        s_date = _get_val(c, "source_date")
        date_str = str(s_date)[:10] if s_date else "Recent Notice"
        s_url = _get_val(c, "source_url") or ""
        rec_id = _get_val(c, "source_record_id") or ""
        verified = _get_val(c, "last_verified_at")
        verified_str = str(verified)[:10] if verified else ""
        text = _get_val(c, "updated_text") or _get_val(c, "original_text") or ""
        clean_text = text.strip()

        plain_report = (
            f"Health Canada — Health Product InfoWatch\n"
            f"Medicine: {display_clean} ({active_ingredient})\n"
            f"Section: {sec} | Topic: {chg_type}\n"
            f"Date: {date_str}\n"
            f"Source URL: {s_url}\n\n"
            f"{clean_text}"
        )
        plain_reports.append(plain_report)

        paragraphs = clean_text.split("\n\n")
        para_html = "".join(f"<p>{html.escape(p.strip())}</p>" for p in paragraphs if p.strip())

        source_link_html = ""
        if s_url:
            source_link_html = f"""
            <div class="hc-source-link">
                <a href="{html.escape(s_url)}" target="_blank" rel="noopener noreferrer" class="btn-hc-source">
                    🔗 View Official Notice on Canada.ca &rarr;
                </a>
            </div>
            """

        meta_bits = []
        if rec_id:
            meta_bits.append(f"Record: <code>{html.escape(rec_id)}</code>")
        if verified_str:
            meta_bits.append(f"Verified: {html.escape(verified_str)}")
        meta_html = " &bull; ".join(meta_bits)

        cards_html.append(f"""
        <div class="hc-card">
            <div class="hc-card-header">
                <div class="hc-card-title-group">
                    <span class="badge badge-hc">🍁 Health Canada</span>
                    <span class="badge badge-sec">{html.escape(sec)}</span>
                    <span class="hc-date">{html.escape(date_str)}</span>
                </div>
                <button type="button" class="btn-copy-card" onclick="copyText(this)" data-copy="{html.escape(plain_report)}">
                    📋 Copy Text
                </button>
            </div>
            <div class="hc-card-body">
                <h3 class="hc-article-title">{html.escape(chg_type)}</h3>
                <div class="hc-prose">
                    {para_html}
                </div>
                {source_link_html}
                <div class="hc-card-meta">
                    {meta_html}
                </div>
            </div>
        </div>
        """)

    top_copy_text = "\n\n---\n\n".join(plain_reports) if plain_reports else ""
    top_copy_btn = ""
    if top_copy_text:
        top_copy_btn = f"""
        <button type="button" class="btn-export btn-copy-primary" onclick="copyText(this)" data-copy="{html.escape(top_copy_text)}">
            📋 Copy All Notices
        </button>
        """

    if not cards_html:
        content_html = """
        <div class="no-data-box">
            <div class="no-data-icon">🍁</div>
            <h2 class="no-data-title">No safety notices found</h2>
            <p class="no-data-desc">No Health Product InfoWatch safety notices were found for this medicine in the database.</p>
        </div>
        """
    else:
        content_html = "".join(cards_html)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(display_clean)} - Health Canada InfoWatch Safety Information</title>
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
        .drug-header-main {{ flex: 1; }}
        .drug-name {{
            font-size: 26px;
            font-weight: 700;
            color: #111827;
            margin: 0 0 4px 0;
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
        .badge-hc {{
            background: #fef2f2;
            color: #b91c1c;
            border: 1px solid #fecaca;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
        }}
        .badge-sec {{
            background: #f3f4f6;
            color: #374151;
            border: 1px solid #d1d5db;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
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
            background: #b91c1c;
            color: #ffffff;
            border-color: #b91c1c;
        }}
        .btn-copy-primary {{
            background: #b91c1c;
            color: #ffffff;
            border-color: #b91c1c;
        }}
        .btn-copy-primary:hover {{
            background: #991b1b;
            border-color: #991b1b;
        }}
        .hc-card {{
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            margin-bottom: 24px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04);
            overflow: hidden;
        }}
        .hc-card-header {{
            background: #fdf2f2;
            border-bottom: 1px solid #fee2e2;
            padding: 12px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 8px;
        }}
        .hc-card-title-group {{
            display: flex;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
        }}
        .hc-date {{
            font-size: 13px;
            font-weight: 600;
            color: #4b5563;
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
        .btn-copy-card:hover {{ background: #f9fafb; border-color: #9ca3af; }}
        .hc-card-body {{
            padding: 20px 24px;
        }}
        .hc-article-title {{
            font-size: 18px;
            font-weight: 700;
            color: #111827;
            margin: 0 0 14px 0;
        }}
        .hc-prose p {{
            margin: 0 0 12px 0;
            line-height: 1.6;
            color: #1f2937;
        }}
        .hc-source-link {{
            margin: 16px 0 12px 0;
        }}
        .btn-hc-source {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 8px 14px;
            background: #fef2f2;
            color: #b91c1c;
            border: 1px solid #fecaca;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 600;
            text-decoration: none;
            transition: all 0.15s;
        }}
        .btn-hc-source:hover {{
            background: #b91c1c;
            color: #ffffff;
        }}
        .hc-card-meta {{
            font-size: 12px;
            color: #6b7280;
            border-top: 1px solid #f3f4f6;
            padding-top: 10px;
            margin-top: 12px;
        }}
        .no-data-box {{
            background: #f9fafb;
            border: 1px solid #e5e7eb;
            border-radius: 6px;
            padding: 40px 20px;
            text-align: center;
            margin: 30px 0;
        }}
        .no-data-icon {{ font-size: 32px; margin-bottom: 12px; }}
        .no-data-title {{ font-size: 18px; font-weight: 700; color: #374151; margin: 0 0 8px 0; }}
        .no-data-desc {{ color: #6b7280; font-size: 14px; margin: 0; }}
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
                <h1 class="drug-name">{html.escape(display_clean)}</h1>
                <div class="ingredient">Active Ingredient: <strong>{html.escape(active_ingredient)}</strong>{f" &bull; DIN: <strong>{html.escape(application_number)}</strong>" if application_number and application_number != 'N/A' else ""}</div>
                <p class="agency-subtitle">Source: Health Canada &bull; Drug Product Database &bull; MedEffect Canada</p>
            </div>
            <div class="export-actions">
                {top_copy_btn}
                <a href="/drugs/{d_id}/export?format=csv" class="btn-export" download>📥 CSV</a>
                <a href="/drugs/{d_id}/export?format=json" class="btn-export" download>📥 JSON</a>
            </div>
        </div>

        <div class="reports-container">
            {content_html}
        </div>

        <div class="footer-note">
            Source: Health Canada Marketed Health Products Directorate &bull; MedEffect Canada &bull; Health Product InfoWatch.
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


def _render_australia_tga_drug_detail(drug: dict, changes: list) -> str:
    """
    Render Australian Therapeutic Goods Administration (TGA) drug detail page.
    Displays ARTG identification, Product Information (PI), Consumer Medicines
    Information (CMI), safety alerts, recalls, and warnings.
    """
    d_id = drug.get("id") or 1
    display_name = drug.get("display_name") or ""
    display_clean = display_name.title() if display_name.isupper() else display_name
    active_ingredient = drug.get("active_ingredient") or "Not specified"
    application_number = drug.get("application_number") or ""
    artg_display = application_number if application_number else "AUST R / Listed"

    plain_reports = []
    cards_html = []

    for c in changes:
        sec = _get_val(c, "section") or "TGA Safety Alert & Advisory"
        chg_type = _get_val(c, "change_type") or "Regulatory Action"
        s_date = _get_val(c, "source_date")
        date_str = str(s_date)[:10] if s_date else "Recent Notice"
        s_url = _get_val(c, "source_url") or ""
        rec_id = _get_val(c, "source_record_id") or ""
        verified = _get_val(c, "last_verified_at")
        verified_str = str(verified)[:10] if verified else ""
        text = _get_val(c, "updated_text") or _get_val(c, "original_text") or ""
        clean_text = text.strip()

        plain_report = (
            f"Australia Therapeutic Goods Administration (TGA)\n"
            f"Medicine: {display_clean} ({active_ingredient})\n"
            f"ARTG: {artg_display}\n"
            f"Section: {sec} | Type: {chg_type}\n"
            f"Date: {date_str}\n"
            f"Source URL: {s_url}\n\n"
            f"{clean_text}"
        )
        plain_reports.append(plain_report)

        paragraphs = clean_text.split("\n\n")
        para_html = "".join(f"<p>{html.escape(p.strip())}</p>" for p in paragraphs if p.strip())

        source_link_html = ""
        if s_url:
            source_link_html = f"""
            <div class="tga-source-link">
                <a href="{html.escape(s_url)}" target="_blank" rel="noopener noreferrer" class="btn-tga-source">
                    🔗 View Official Notice on TGA.gov.au &rarr;
                </a>
            </div>
            """

        meta_bits = []
        if rec_id:
            meta_bits.append(f"Record: <code>{html.escape(rec_id)}</code>")
        if verified_str:
            meta_bits.append(f"Verified: {html.escape(verified_str)}")
        meta_html = " &bull; ".join(meta_bits)

        cards_html.append(f"""
        <div class="tga-card">
            <div class="tga-card-header">
                <div class="tga-card-title-group">
                    <span class="badge badge-tga">🇦🇺 Australia TGA</span>
                    <span class="badge badge-sec">{html.escape(sec)}</span>
                    <span class="tga-date">{html.escape(date_str)}</span>
                </div>
                <button type="button" class="btn-copy-card" onclick="copyText(this)" data-copy="{html.escape(plain_report)}">
                    📋 Copy Text
                </button>
            </div>
            <div class="tga-card-body">
                <h3 class="tga-article-title">{html.escape(chg_type)}</h3>
                <div class="tga-prose">
                    {para_html}
                </div>
                {source_link_html}
                <div class="tga-card-meta">
                    {meta_html}
                </div>
            </div>
        </div>
        """)

    top_copy_text = "\n\n---\n\n".join(plain_reports) if plain_reports else ""
    top_copy_btn = ""
    if top_copy_text:
        top_copy_btn = f"""
        <button type="button" class="btn-export btn-copy-primary" onclick="copyText(this)" data-copy="{html.escape(top_copy_text)}">
            📋 Copy All Notices
        </button>
        """

    if not cards_html:
        content_html = """
        <div class="no-data-box">
            <div class="no-data-icon">🇦🇺</div>
            <h2 class="no-data-title">No Australian TGA safety notices found</h2>
            <p class="no-data-desc">No Therapeutic Goods Administration notices were found for this medicine in the database.</p>
        </div>
        """
    else:
        content_html = "".join(cards_html)

    tga_official_search_url = f"https://www.tga.gov.au/search?keywords={quote_plus(display_name)}"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(display_clean)} - Australia TGA Safety & Product Information</title>
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
        .drug-header-main {{ flex: 1; }}
        .drug-name {{
            font-size: 26px;
            font-weight: 700;
            color: #111827;
            margin: 0 0 4px 0;
        }}
        .ingredient {{
            font-size: 16px;
            font-weight: 600;
            color: #374151;
            margin: 0 0 6px 0;
        }}
        .din-tag {{
            font-size: 13px;
            color: #15803d;
            font-weight: 600;
            background: #f0fdf4;
            padding: 2px 8px;
            border-radius: 4px;
            border: 1px solid #bbf7d0;
            display: inline-block;
            margin-bottom: 8px;
        }}
        .source-badge-wrap {{
            display: flex;
            gap: 8px;
            align-items: center;
            margin-top: 6px;
            flex-wrap: wrap;
        }}
        .badge {{
            display: inline-flex;
            align-items: center;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
        }}
        .badge-tga {{
            background: #f0fdf4;
            color: #15803d;
            border: 1px solid #bbf7d0;
        }}
        .badge-sec {{
            background: #f3f4f6;
            color: #374151;
            border: 1px solid #e5e7eb;
        }}
        .drug-header-actions {{
            display: flex;
            gap: 8px;
            align-items: center;
            flex-wrap: wrap;
        }}
        .btn-export {{
            padding: 6px 12px;
            font-size: 13px;
            font-weight: 500;
            color: #374151;
            background: #f9fafb;
            border: 1px solid #d1d5db;
            border-radius: 4px;
            text-decoration: none;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            transition: all 0.15s ease;
        }}
        .btn-export:hover {{
            background: #f3f4f6;
            border-color: #9ca3af;
            color: #111827;
        }}
        .btn-copy-primary {{
            background: #15803d;
            color: #ffffff;
            border-color: #15803d;
            font-weight: 600;
        }}
        .btn-copy-primary:hover {{
            background: #166534;
            border-color: #166534;
            color: #ffffff;
        }}
        .tga-official-box {{
            background: #f0fdf4;
            border: 1px solid #bbf7d0;
            border-radius: 8px;
            padding: 14px 18px;
            margin-bottom: 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 12px;
        }}
        .tga-official-title {{
            font-size: 14px;
            font-weight: 600;
            color: #166534;
            margin: 0 0 2px 0;
        }}
        .tga-official-sub {{
            font-size: 13px;
            color: #15803d;
            margin: 0;
        }}
        .btn-tga-official {{
            background: #15803d;
            color: #ffffff;
            font-size: 13px;
            font-weight: 600;
            padding: 8px 14px;
            border-radius: 6px;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            transition: background 0.15s;
        }}
        .btn-tga-official:hover {{
            background: #166534;
            color: #ffffff;
        }}
        .tga-card {{
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            margin-bottom: 20px;
            background: #ffffff;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
            overflow: hidden;
            transition: border-color 0.15s ease;
        }}
        .tga-card:hover {{
            border-color: #bbf7d0;
        }}
        .tga-card-header {{
            background: #f9fafb;
            border-bottom: 1px solid #e5e7eb;
            padding: 12px 18px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 10px;
        }}
        .tga-card-title-group {{
            display: flex;
            gap: 8px;
            align-items: center;
            flex-wrap: wrap;
        }}
        .tga-date {{
            font-size: 13px;
            color: #6b7280;
            font-weight: 500;
        }}
        .btn-copy-card {{
            padding: 4px 10px;
            font-size: 12px;
            font-weight: 500;
            color: #374151;
            background: #ffffff;
            border: 1px solid #d1d5db;
            border-radius: 4px;
            cursor: pointer;
            transition: all 0.15s ease;
        }}
        .btn-copy-card:hover {{
            background: #f3f4f6;
            color: #111827;
        }}
        .tga-card-body {{
            padding: 20px 22px;
        }}
        .tga-article-title {{
            font-size: 18px;
            font-weight: 700;
            color: #111827;
            margin: 0 0 14px 0;
            line-height: 1.4;
        }}
        .tga-prose p {{
            margin: 0 0 12px 0;
            color: #374151;
            line-height: 1.65;
        }}
        .tga-prose p:last-child {{
            margin-bottom: 0;
        }}
        .tga-source-link {{
            margin-top: 16px;
            padding-top: 14px;
            border-top: 1px solid #f3f4f6;
        }}
        .btn-tga-source {{
            display: inline-flex;
            align-items: center;
            font-size: 13px;
            font-weight: 600;
            color: #15803d;
            text-decoration: none;
        }}
        .btn-tga-source:hover {{
            text-decoration: underline;
        }}
        .tga-card-meta {{
            margin-top: 14px;
            font-size: 12px;
            color: #9ca3af;
        }}
        .tga-card-meta code {{
            background: #f3f4f6;
            padding: 1px 4px;
            border-radius: 3px;
            color: #6b7280;
            font-size: 11px;
        }}
        .no-data-box {{
            text-align: center;
            padding: 60px 20px;
            background: #f9fafb;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
        }}
        .no-data-icon {{ font-size: 40px; margin-bottom: 12px; }}
        .no-data-title {{ font-size: 18px; font-weight: 600; color: #111827; margin: 0 0 6px 0; }}
        .no-data-desc {{ color: #6b7280; font-size: 14px; margin: 0; }}
        .footer-note {{
            margin-top: 40px;
            padding-top: 16px;
            border-top: 1px solid #e5e7eb;
            font-size: 12px;
            color: #6b7280;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="top-nav">
        <div>
            <a href="/">&larr; Back to Unified Medicine Safety Search</a>
        </div>
        <div>
            <a href="https://www.tga.gov.au" target="_blank" rel="noopener noreferrer">Official Australian TGA Portal &rarr;</a>
        </div>
    </div>

    <div class="page-container">
        <div class="drug-header">
            <div class="drug-header-main">
                <h1 class="drug-name">{html.escape(display_clean)}</h1>
                <div class="ingredient">Active Ingredient: {html.escape(active_ingredient)}</div>
                <div class="din-tag">ARTG: {html.escape(artg_display)}</div>
                <div class="source-badge-wrap">
                    <span class="badge badge-tga">🇦🇺 Australia TGA</span>
                    <span class="badge badge-sec">{len(cards_html)} Safety Record(s)</span>
                </div>
            </div>
            <div class="drug-header-actions">
                {top_copy_btn}
                <a href="/drugs/{d_id}/export?format=csv" class="btn-export">Download CSV</a>
                <a href="/drugs/{d_id}/export?format=json" class="btn-export">Download JSON</a>
            </div>
        </div>

        <div class="tga-official-box">
            <div>
                <div class="tga-official-title">Official Australian Therapeutic Goods Administration Record</div>
                <div class="tga-official-sub">Search entries, Product Information (PI) & Consumer Medicines Information (CMI)</div>
            </div>
            <a href="{html.escape(tga_official_search_url)}" target="_blank" rel="noopener noreferrer" class="btn-tga-official">
                🔗 View on TGA.gov.au &rarr;
            </a>
        </div>

        <div class="notices-list">
            {content_html}
        </div>

        <div class="footer-note">
            Source: Australian Government Department of Health and Aged Care &bull; Therapeutic Goods Administration (TGA).
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


def _render_fda_medwatch_drug_detail(drug: dict, changes: list) -> str:
    """Render FDA MedWatch Safety Information and Adverse Event Reporting Program detail page."""
    d_id = drug.get("id") or 1
    display_name = drug.get("display_name") or ""
    display_clean = display_name.title() if display_name.isupper() else display_name
    active_ingredient = drug.get("active_ingredient") or "Not specified"
    application_number = drug.get("application_number") or ""
    app_display = application_number if application_number else "MW-FAERS-Surveillance"
    sponsor = drug.get("sponsor") or "Regulated Sponsor"
    dosage_form = drug.get("dosage_form") or "Pharmaceutical Product"
    detail_url = drug.get("detail_url") or "https://www.fda.gov/safety/medwatch-fda-safety-information-and-adverse-event-reporting-program"

    plain_reports = []
    cards_html = []

    for c in changes:
        sec = _get_val(c, "section") or "MedWatch Safety Alert"
        chg_type = _get_val(c, "change_type") or "Adverse Event Surveillance"
        s_date = _get_val(c, "source_date")
        date_str = str(s_date)[:10] if s_date else "Recent Communication"
        s_url = _get_val(c, "source_url") or "https://www.fda.gov/safety/medwatch-fda-safety-information-and-adverse-event-reporting-program"
        rec_id = _get_val(c, "source_record_id") or ""
        verified = _get_val(c, "last_verified_at")
        verified_str = str(verified)[:10] if verified else ""
        text = _get_val(c, "updated_text") or _get_val(c, "original_text") or ""
        clean_text = text.strip()
        fda_comment = _get_val(c, "fda_comment") or ""

        plain_report = (
            f"FDA MedWatch Safety Information & Adverse Event Reporting Program\n"
            f"Medicine: {display_clean} ({active_ingredient})\n"
            f"Report / Event ID: {app_display}\n"
            f"Section: {sec} | Type: {chg_type}\n"
            f"Date: {date_str}\n"
            f"Source URL: {s_url}\n\n"
            f"{clean_text}"
        )
        plain_reports.append(plain_report)

        paragraphs = clean_text.split("\n\n")
        para_html = "".join(f"<p>{html.escape(p.strip())}</p>" for p in paragraphs if p.strip())

        source_link_html = ""
        if s_url:
            source_link_html = f"""
            <div class="mw-source-link">
                <a href="{html.escape(s_url)}" target="_blank" rel="noopener noreferrer" class="btn-mw-source">
                    🔗 View Notice on FDA.gov &rarr;
                </a>
            </div>
            """

        comment_html = ""
        if fda_comment:
            comment_html = f"""
            <div class="mw-comment-box">
                <strong>FDA MedWatch Note:</strong> {html.escape(fda_comment)}
            </div>
            """

        meta_bits = []
        if rec_id:
            meta_bits.append(f"Identifier: <code>{html.escape(rec_id)}</code>")
        if verified_str:
            meta_bits.append(f"Verified: {html.escape(verified_str)}")
        meta_html = " &bull; ".join(meta_bits)

        cards_html.append(f"""
        <div class="mw-card">
            <div class="mw-card-header">
                <div class="mw-card-title-group">
                    <span class="badge badge-medwatch">🚨 FDA MedWatch</span>
                    <span class="badge badge-sec">{html.escape(sec)}</span>
                    <span class="mw-date">{html.escape(date_str)}</span>
                </div>
                <button type="button" class="btn-copy-card" onclick="copyText(this)" data-copy="{html.escape(plain_report)}">
                    📋 Copy Alert
                </button>
            </div>
            <div class="mw-card-body">
                <h3 class="mw-article-title">{html.escape(chg_type)}</h3>
                <div class="mw-prose">
                    {para_html}
                </div>
                {comment_html}
                {source_link_html}
                <div class="mw-card-meta">
                    {meta_html}
                </div>
            </div>
        </div>
        """)

    all_plain_text = "\n\n" + ("=" * 60) + "\n\n".join(plain_reports)
    empty_html = """
    <div class="empty-state">
        <div class="empty-state-title">No safety alerts or adverse reaction reports recorded</div>
        <div class="empty-state-desc">No formal post-marketing warnings or Class I/II recalls currently indexed for this product in FDA MedWatch.</div>
    </div>
    """
    body_content = "".join(cards_html) if cards_html else empty_html

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(display_clean)} - FDA MedWatch Safety Information & Adverse Events</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
            background-color: #f8fafc;
            color: #1e293b;
            margin: 0;
            padding: 0;
            line-height: 1.5;
        }}
        .header {{
            background: #ffffff;
            border-bottom: 1px solid #e2e8f0;
            padding: 14px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        .header-title {{
            font-size: 18px;
            font-weight: 700;
            color: #0f172a;
            text-decoration: none;
        }}
        .header-sources {{
            display: flex;
            gap: 8px;
            align-items: center;
        }}
        .source-tag {{
            font-size: 12px;
            font-weight: 600;
            padding: 3px 8px;
            border-radius: 4px;
        }}
        .mw-tag {{
            background: #fff1f2;
            color: #be123c;
            border: 1px solid #fecdd3;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
            padding: 24px 16px;
        }}
        .breadcrumb {{
            font-size: 13px;
            color: #64748b;
            margin-bottom: 16px;
        }}
        .breadcrumb a {{
            color: #0284c7;
            text-decoration: none;
        }}
        .breadcrumb a:hover {{
            text-decoration: underline;
        }}
        .drug-header-card {{
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 24px;
            margin-bottom: 20px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }}
        .drug-header-top {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            flex-wrap: wrap;
            gap: 12px;
            margin-bottom: 16px;
        }}
        .drug-title {{
            font-size: 26px;
            font-weight: 800;
            color: #0f172a;
            margin: 0 0 4px 0;
        }}
        .drug-subtitle {{
            font-size: 15px;
            color: #475569;
            margin: 0 0 8px 0;
        }}
        .mw-report-tag {{
            font-size: 13px;
            color: #be123c;
            font-weight: 600;
            background: #fff1f2;
            padding: 2px 8px;
            border-radius: 4px;
            border: 1px solid #fecdd3;
            display: inline-block;
            margin-bottom: 8px;
        }}
        .source-badge-wrap {{
            display: flex;
            gap: 8px;
            align-items: center;
            margin-top: 6px;
            flex-wrap: wrap;
        }}
        .badge {{
            display: inline-flex;
            align-items: center;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
        }}
        .badge-medwatch {{
            background: #fff1f2;
            color: #be123c;
            border: 1px solid #fecdd3;
        }}
        .badge-sec {{
            background: #f1f5f9;
            color: #475569;
            border: 1px solid #cbd5e1;
        }}
        .drug-header-actions {{
            display: flex;
            gap: 8px;
            align-items: center;
            flex-wrap: wrap;
        }}
        .btn-export {{
            padding: 6px 12px;
            font-size: 13px;
            font-weight: 500;
            color: #334155;
            background: #f8fafc;
            border: 1px solid #cbd5e1;
            border-radius: 4px;
            text-decoration: none;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            transition: all 0.15s ease;
        }}
        .btn-export:hover {{
            background: #f1f5f9;
            border-color: #94a3b8;
            color: #0f172a;
        }}
        .btn-copy-primary {{
            background: #be123c;
            color: #ffffff;
            border-color: #be123c;
            font-weight: 600;
        }}
        .btn-copy-primary:hover {{
            background: #9f1239;
            border-color: #9f1239;
            color: #ffffff;
        }}
        .mw-official-box {{
            background: #fff1f2;
            border: 1px solid #fecdd3;
            border-radius: 8px;
            padding: 16px 20px;
            margin-bottom: 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 12px;
        }}
        .mw-official-title {{
            font-size: 15px;
            font-weight: 700;
            color: #9f1239;
            margin: 0 0 4px 0;
        }}
        .mw-official-sub {{
            font-size: 13px;
            color: #be123c;
            margin: 0;
        }}
        .mw-official-links {{
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }}
        .btn-mw-official {{
            padding: 7px 14px;
            font-size: 13px;
            font-weight: 600;
            color: #ffffff;
            background: #be123c;
            border: 1px solid #9f1239;
            border-radius: 5px;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }}
        .btn-mw-official:hover {{
            background: #9f1239;
        }}
        .btn-mw-report {{
            padding: 7px 14px;
            font-size: 13px;
            font-weight: 600;
            color: #9f1239;
            background: #ffffff;
            border: 1px solid #fecdd3;
            border-radius: 5px;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }}
        .btn-mw-report:hover {{
            background: #ffe4e6;
        }}
        .section-heading {{
            font-size: 18px;
            font-weight: 700;
            color: #0f172a;
            margin: 0 0 16px 0;
        }}
        .mw-card {{
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            margin-bottom: 16px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        }}
        .mw-card-header {{
            background: #f8fafc;
            border-bottom: 1px solid #e2e8f0;
            padding: 12px 18px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 8px;
        }}
        .mw-card-title-group {{
            display: flex;
            align-items: center;
            gap: 8px;
            flex-wrap: wrap;
        }}
        .mw-date {{
            font-size: 12px;
            color: #64748b;
        }}
        .btn-copy-card {{
            padding: 4px 8px;
            font-size: 12px;
            font-weight: 500;
            color: #475569;
            background: #ffffff;
            border: 1px solid #cbd5e1;
            border-radius: 4px;
            cursor: pointer;
        }}
        .btn-copy-card:hover {{
            background: #f1f5f9;
            color: #0f172a;
        }}
        .mw-card-body {{
            padding: 18px;
        }}
        .mw-article-title {{
            font-size: 16px;
            font-weight: 700;
            color: #0f172a;
            margin: 0 0 12px 0;
        }}
        .mw-prose p {{
            font-size: 14px;
            line-height: 1.6;
            color: #334155;
            margin: 0 0 10px 0;
        }}
        .mw-prose p:last-child {{
            margin-bottom: 0;
        }}
        .mw-comment-box {{
            background: #fff1f2;
            border-left: 3px solid #be123c;
            padding: 10px 14px;
            margin: 12px 0;
            font-size: 13px;
            color: #881337;
            border-radius: 0 4px 4px 0;
        }}
        .mw-source-link {{
            margin-top: 14px;
            padding-top: 12px;
            border-top: 1px dashed #e2e8f0;
        }}
        .btn-mw-source {{
            font-size: 13px;
            font-weight: 600;
            color: #be123c;
            text-decoration: none;
        }}
        .btn-mw-source:hover {{
            text-decoration: underline;
        }}
        .mw-card-meta {{
            margin-top: 12px;
            font-size: 12px;
            color: #64748b;
        }}
        .mw-card-meta code {{
            background: #f1f5f9;
            padding: 1px 4px;
            border-radius: 3px;
            font-size: 11px;
        }}
        .empty-state {{
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 40px 24px;
            text-align: center;
        }}
        .empty-state-title {{
            font-size: 16px;
            font-weight: 600;
            color: #475569;
            margin-bottom: 6px;
        }}
        .empty-state-desc {{
            font-size: 13px;
            color: #94a3b8;
        }}
        .disclaimer-box {{
            margin-top: 30px;
            padding: 14px 18px;
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            font-size: 12px;
            color: #64748b;
            line-height: 1.5;
        }}
    </style>
</head>
<body>
    <header class="header">
        <a href="/" class="header-title">Medicine Safety Platform</a>
        <div class="header-sources">
            <span class="source-tag mw-tag">🚨 FDA MedWatch</span>
        </div>
    </header>

    <div class="container">
        <div class="breadcrumb">
            <a href="/">&larr; Back to Search</a> / <span>FDA MedWatch Safety Reports</span>
        </div>

        <div class="drug-header-card">
            <div class="drug-header-top">
                <div>
                    <div class="mw-report-tag">{html.escape(app_display)}</div>
                    <h1 class="drug-title">{html.escape(display_clean)}</h1>
                    <div class="drug-subtitle">Active Ingredient: <strong>{html.escape(active_ingredient)}</strong> &bull; Sponsor: <strong>{html.escape(sponsor)}</strong></div>
                    <div class="source-badge-wrap">
                        <span class="badge badge-medwatch">🚨 FDA MedWatch Surveillance</span>
                        <span class="badge badge-sec">{len(changes)} Safety Signals & Recalls</span>
                        <span class="badge badge-sec">{html.escape(dosage_form)}</span>
                    </div>
                </div>
                <div class="drug-header-actions">
                    <button type="button" class="btn-export btn-copy-primary" onclick="copyText(this)" data-copy="{html.escape(all_plain_text)}">
                        📋 Copy Full Report
                    </button>
                    <a href="/drugs/{d_id}/export?format=csv" class="btn-export">Export CSV</a>
                    <a href="/drugs/{d_id}/export?format=json" class="btn-export">Export JSON</a>
                </div>
            </div>
        </div>

        <div class="mw-official-box">
            <div>
                <div class="mw-official-title">Official FDA MedWatch Program Hub</div>
                <div class="mw-official-sub">Post-marketing safety surveillance, adverse reaction reports (FAERS), and safety communications.</div>
            </div>
            <div class="mw-official-links">
                <a href="https://www.accessdata.fda.gov/scripts/medwatch/index.cfm?action=reporting.home" target="_blank" rel="noopener noreferrer" class="btn-mw-report">
                    📝 Report a Problem (Form 3500)
                </a>
                <a href="{html.escape(detail_url)}" target="_blank" rel="noopener noreferrer" class="btn-mw-official">
                    🏛️ FDA MedWatch Portal &rarr;
                </a>
            </div>
        </div>

        <h2 class="section-heading">FDA MedWatch Safety Alerts, Recalls & FAERS Signals</h2>

        {body_content}

        <div class="disclaimer-box">
            <strong>MedWatch Disclaimer:</strong> Adverse reaction signals and safety reports are compiled from the U.S. FDA MedWatch Safety Information and Adverse Event Reporting Program, the FDA Adverse Event Reporting System (FAERS), and CDER enforcement notices. Voluntary reports submitted by healthcare professionals and consumers do not by themselves establish a causal relationship. Consult healthcare professionals before altering any treatment regimen.
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


def _render_uk_mhra_drug_detail(drug: dict, changes: list) -> str:
    """Render UK MHRA Drug Safety Update detail page."""
    d_id = drug.get("id") or 1
    display_name = drug.get("display_name") or ""
    display_clean = display_name.title() if display_name.isupper() else display_name
    active_ingredient = drug.get("active_ingredient") or "Not specified"
    application_number = drug.get("application_number") or ""
    pl_display = application_number if application_number else "PLGB / UK Licensed"
    sponsor = drug.get("sponsor") or "UK Marketing Authorisation Holder"
    dosage_form = drug.get("dosage_form") or "Licensed Medicinal Product"
    detail_url = drug.get("detail_url") or "https://www.gov.uk/drug-safety-update"

    plain_reports = []
    cards_html = []

    for c in changes:
        sec = _get_val(c, "section") or "MHRA Drug Safety Update"
        chg_type = _get_val(c, "change_type") or "Clinical Safety Advice"
        s_date = _get_val(c, "source_date")
        date_str = str(s_date)[:10] if s_date else "Recent Update"
        s_url = _get_val(c, "source_url") or "https://www.gov.uk/drug-safety-update"
        rec_id = _get_val(c, "source_record_id") or ""
        verified = _get_val(c, "last_verified_at")
        verified_str = str(verified)[:10] if verified else ""
        text = _get_val(c, "updated_text") or _get_val(c, "original_text") or ""
        clean_text = text.strip()
        fda_comment = _get_val(c, "fda_comment") or ""

        plain_report = (
            f"UK Medicines and Healthcare products Regulatory Agency (MHRA)\n"
            f"Drug Safety Update | Medicine: {display_clean} ({active_ingredient})\n"
            f"UK Licence / Reference: {pl_display}\n"
            f"Section: {sec} | Update: {chg_type}\n"
            f"Date: {date_str}\n"
            f"Source URL: {s_url}\n\n"
            f"{clean_text}"
        )
        plain_reports.append(plain_report)

        paragraphs = clean_text.split("\n\n")
        para_html = "".join(f"<p>{html.escape(p.strip())}</p>" for p in paragraphs if p.strip())

        source_link_html = ""
        if s_url:
            source_link_html = f"""
            <div class="mhra-source-link">
                <a href="{html.escape(s_url)}" target="_blank" rel="noopener noreferrer" class="btn-mhra-source">
                    🔗 Read Full Drug Safety Update on GOV.UK &rarr;
                </a>
            </div>
            """

        comment_html = ""
        if fda_comment:
            comment_html = f"""
            <div class="mhra-comment-box">
                <strong>MHRA Clinical Note:</strong> {html.escape(fda_comment)}
            </div>
            """

        meta_bits = []
        if rec_id:
            meta_bits.append(f"Reference: <code>{html.escape(rec_id)}</code>")
        if verified_str:
            meta_bits.append(f"Verified: {html.escape(verified_str)}")
        meta_html = " &bull; ".join(meta_bits)

        cards_html.append(f"""
        <div class="mhra-card">
            <div class="mhra-card-header">
                <div class="mhra-card-title-group">
                    <span class="badge badge-mhra">🇬🇧 UK MHRA</span>
                    <span class="badge badge-sec">{html.escape(sec)}</span>
                    <span class="mhra-date">{html.escape(date_str)}</span>
                </div>
                <button type="button" class="btn-copy-card" onclick="copyText(this)" data-copy="{html.escape(plain_report)}">
                    📋 Copy Update
                </button>
            </div>
            <div class="mhra-card-body">
                <h3 class="mhra-article-title">{html.escape(chg_type)}</h3>
                <div class="mhra-prose">
                    {para_html}
                </div>
                {comment_html}
                {source_link_html}
                <div class="mhra-card-meta">
                    {meta_html}
                </div>
            </div>
        </div>
        """)

    all_plain_text = "\n\n" + ("=" * 60) + "\n\n".join(plain_reports)
    empty_html = """
    <div class="empty-state">
        <div class="empty-state-title">No Drug Safety Updates currently recorded</div>
        <div class="empty-state-desc">No specific MHRA or CHM safety bulletins currently indexed for this medicine.</div>
    </div>
    """
    body_content = "".join(cards_html) if cards_html else empty_html

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(display_clean)} - UK MHRA Drug Safety Update</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
            background-color: #f3f4f6;
            color: #111827;
            margin: 0;
            padding: 0;
            line-height: 1.5;
        }}
        .header {{
            background: #003078;
            border-bottom: 2px solid #1d70b8;
            padding: 14px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        .header-title {{
            font-size: 18px;
            font-weight: 700;
            color: #ffffff;
            text-decoration: none;
        }}
        .header-sources {{
            display: flex;
            gap: 8px;
            align-items: center;
        }}
        .source-tag {{
            font-size: 12px;
            font-weight: 600;
            padding: 3px 8px;
            border-radius: 4px;
        }}
        .mhra-tag {{
            background: #eef4f8;
            color: #003078;
            border: 1px solid #b6d5ee;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
            padding: 24px 16px;
        }}
        .breadcrumb {{
            font-size: 13px;
            color: #6b7280;
            margin-bottom: 16px;
        }}
        .breadcrumb a {{
            color: #1d70b8;
            text-decoration: none;
        }}
        .breadcrumb a:hover {{
            text-decoration: underline;
        }}
        .drug-header-card {{
            background: #ffffff;
            border: 1px solid #d1d5db;
            border-radius: 8px;
            padding: 24px;
            margin-bottom: 20px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }}
        .drug-header-top {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            flex-wrap: wrap;
            gap: 12px;
            margin-bottom: 16px;
        }}
        .drug-title {{
            font-size: 26px;
            font-weight: 800;
            color: #003078;
            margin: 0 0 4px 0;
        }}
        .drug-subtitle {{
            font-size: 15px;
            color: #4b5563;
            margin: 0 0 8px 0;
        }}
        .pl-tag {{
            font-size: 13px;
            color: #003078;
            font-weight: 600;
            background: #eef4f8;
            padding: 2px 8px;
            border-radius: 4px;
            border: 1px solid #b6d5ee;
            display: inline-block;
            margin-bottom: 8px;
        }}
        .source-badge-wrap {{
            display: flex;
            gap: 8px;
            align-items: center;
            margin-top: 6px;
            flex-wrap: wrap;
        }}
        .badge {{
            display: inline-flex;
            align-items: center;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
        }}
        .badge-mhra {{
            background: #eef4f8;
            color: #003078;
            border: 1px solid #b6d5ee;
        }}
        .badge-sec {{
            background: #f3f4f6;
            color: #374151;
            border: 1px solid #e5e7eb;
        }}
        .drug-header-actions {{
            display: flex;
            gap: 8px;
            align-items: center;
            flex-wrap: wrap;
        }}
        .btn-export {{
            padding: 6px 12px;
            font-size: 13px;
            font-weight: 500;
            color: #374151;
            background: #f9fafb;
            border: 1px solid #d1d5db;
            border-radius: 4px;
            text-decoration: none;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            transition: all 0.15s ease;
        }}
        .btn-export:hover {{
            background: #f3f4f6;
            border-color: #9ca3af;
            color: #111827;
        }}
        .btn-copy-primary {{
            background: #003078;
            color: #ffffff;
            border-color: #003078;
            font-weight: 600;
        }}
        .btn-copy-primary:hover {{
            background: #002255;
            color: #ffffff;
        }}
        .mhra-official-box {{
            background: #eef4f8;
            border: 1px solid #b6d5ee;
            border-radius: 8px;
            padding: 16px 20px;
            margin-bottom: 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 12px;
        }}
        .mhra-official-title {{
            font-size: 15px;
            font-weight: 700;
            color: #003078;
            margin: 0 0 4px 0;
        }}
        .mhra-official-sub {{
            font-size: 13px;
            color: #1d70b8;
            margin: 0;
        }}
        .mhra-official-links {{
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }}
        .btn-mhra-official {{
            padding: 7px 14px;
            font-size: 13px;
            font-weight: 600;
            color: #ffffff;
            background: #003078;
            border: 1px solid #002255;
            border-radius: 5px;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }}
        .btn-mhra-official:hover {{
            background: #002255;
        }}
        .btn-mhra-yellowcard {{
            padding: 7px 14px;
            font-size: 13px;
            font-weight: 600;
            color: #003078;
            background: #ffdd00;
            border: 1px solid #e0be00;
            border-radius: 5px;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }}
        .btn-mhra-yellowcard:hover {{
            background: #f0ce00;
        }}
        .section-heading {{
            font-size: 18px;
            font-weight: 700;
            color: #111827;
            margin: 0 0 16px 0;
        }}
        .mhra-card {{
            background: #ffffff;
            border: 1px solid #d1d5db;
            border-radius: 8px;
            margin-bottom: 16px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        }}
        .mhra-card-header {{
            background: #f9fafb;
            border-bottom: 1px solid #e5e7eb;
            padding: 12px 18px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 8px;
        }}
        .mhra-card-title-group {{
            display: flex;
            align-items: center;
            gap: 8px;
            flex-wrap: wrap;
        }}
        .mhra-date {{
            font-size: 12px;
            color: #6b7280;
        }}
        .btn-copy-card {{
            padding: 4px 8px;
            font-size: 12px;
            font-weight: 500;
            color: #4b5563;
            background: #ffffff;
            border: 1px solid #d1d5db;
            border-radius: 4px;
            cursor: pointer;
        }}
        .btn-copy-card:hover {{
            background: #f3f4f6;
            color: #111827;
        }}
        .mhra-card-body {{
            padding: 18px;
        }}
        .mhra-article-title {{
            font-size: 16px;
            font-weight: 700;
            color: #003078;
            margin: 0 0 12px 0;
        }}
        .mhra-prose p {{
            font-size: 14px;
            line-height: 1.6;
            color: #374151;
            margin: 0 0 10px 0;
        }}
        .mhra-prose p:last-child {{
            margin-bottom: 0;
        }}
        .mhra-comment-box {{
            background: #eef4f8;
            border-left: 3px solid #003078;
            padding: 10px 14px;
            margin: 12px 0;
            font-size: 13px;
            color: #003078;
            border-radius: 0 4px 4px 0;
        }}
        .mhra-source-link {{
            margin-top: 14px;
            padding-top: 12px;
            border-top: 1px dashed #e5e7eb;
        }}
        .btn-mhra-source {{
            font-size: 13px;
            font-weight: 600;
            color: #1d70b8;
            text-decoration: none;
        }}
        .btn-mhra-source:hover {{
            text-decoration: underline;
        }}
        .mhra-card-meta {{
            margin-top: 12px;
            font-size: 12px;
            color: #6b7280;
        }}
        .mhra-card-meta code {{
            background: #f3f4f6;
            padding: 1px 4px;
            border-radius: 3px;
            font-size: 11px;
        }}
        .empty-state {{
            background: #ffffff;
            border: 1px solid #d1d5db;
            border-radius: 8px;
            padding: 40px 24px;
            text-align: center;
        }}
        .empty-state-title {{
            font-size: 16px;
            font-weight: 600;
            color: #4b5563;
            margin-bottom: 6px;
        }}
        .empty-state-desc {{
            font-size: 13px;
            color: #9ca3af;
        }}
        .disclaimer-box {{
            margin-top: 30px;
            padding: 14px 18px;
            background: #ffffff;
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
        <a href="/" class="header-title">Medicine Safety Platform</a>
        <div class="header-sources">
            <span class="source-tag mhra-tag">🇬🇧 UK MHRA</span>
        </div>
    </header>

    <div class="container">
        <div class="breadcrumb">
            <a href="/">&larr; Back to Search</a> / <span>UK MHRA Drug Safety Updates</span>
        </div>

        <div class="drug-header-card">
            <div class="drug-header-top">
                <div>
                    <div class="pl-tag">{html.escape(pl_display)}</div>
                    <h1 class="drug-title">{html.escape(display_clean)}</h1>
                    <div class="drug-subtitle">Active Ingredient: <strong>{html.escape(active_ingredient)}</strong> &bull; Licence Holder: <strong>{html.escape(sponsor)}</strong></div>
                    <div class="source-badge-wrap">
                        <span class="badge badge-mhra">🇬🇧 UK MHRA Drug Safety Update</span>
                        <span class="badge badge-sec">{len(changes)} Safety Bulletins</span>
                        <span class="badge badge-sec">{html.escape(dosage_form)}</span>
                    </div>
                </div>
                <div class="drug-header-actions">
                    <button type="button" class="btn-export btn-copy-primary" onclick="copyText(this)" data-copy="{html.escape(all_plain_text)}">
                        📋 Copy Full Report
                    </button>
                    <a href="/drugs/{d_id}/export?format=csv" class="btn-export">Export CSV</a>
                    <a href="/drugs/{d_id}/export?format=json" class="btn-export">Export JSON</a>
                </div>
            </div>
        </div>

        <div class="mhra-official-box">
            <div>
                <div class="mhra-official-title">Official UK MHRA Drug Safety Update Portal</div>
                <div class="mhra-official-sub">Monthly newsletter and safety reviews from the MHRA and the Commission on Human Medicines.</div>
            </div>
            <div class="mhra-official-links">
                <a href="https://yellowcard.mhra.gov.uk/" target="_blank" rel="noopener noreferrer" class="btn-mhra-yellowcard">
                    ⚠️ Report ADR (Yellow Card)
                </a>
                <a href="{html.escape(detail_url)}" target="_blank" rel="noopener noreferrer" class="btn-mhra-official">
                    🏛️ GOV.UK Drug Safety Update &rarr;
                </a>
            </div>
        </div>

        <h2 class="section-heading">MHRA Safety Bulletins, Clinical Warnings & Advisory Notices</h2>

        {body_content}

        <div class="disclaimer-box">
            <strong>MHRA Disclaimer:</strong> Information derived from the UK Medicines and Healthcare products Regulatory Agency (MHRA) Drug Safety Update and the Commission on Human Medicines (CHM). Healthcare professionals are reminded to report suspected adverse drug reactions via the Yellow Card scheme at https://yellowcard.mhra.gov.uk/ or using the Yellow Card app.
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


def render_drug_detail_html(drug: dict, changes: list) -> str:
    """
    Render drug safety labeling detail page.
    - If UK MHRA: displays MHRA Drug Safety Update articles, clinical advice, and Yellow Card info.
    - If FDA MedWatch: displays MedWatch safety communications, FAERS reports, and recalls.
    - If Australia TGA: displays Australian TGA safety alerts, advisories, PI, and CMI.
    - If Health Canada: displays Health Canada InfoWatch safety reviews, monograph updates, and advisories.
    - If FDA: displays Adverse Reactions regulatory report formatted to FDA 3.1 specifications.
    """
    drug_source = str(drug.get("source") or "").upper()
    is_mhra = (
        "UK_MHRA" in drug_source
        or "MHRA" in drug_source
        or any("MHRA" in str(_get_val(c, "source", "")).upper() for c in changes)
    )
    if is_mhra:
        return _render_uk_mhra_drug_detail(drug, changes)

    is_mw = (
        "FDA_MEDWATCH" in drug_source
        or "MEDWATCH" in drug_source
        or any("MEDWATCH" in str(_get_val(c, "source", "")).upper() for c in changes)
    )
    if is_mw:
        return _render_fda_medwatch_drug_detail(drug, changes)

    is_tga = (
        "AUSTRALIA_TGA" in drug_source
        or "TGA" in drug_source
        or any("AUSTRALIA_TGA" in str(_get_val(c, "source", "")).upper() for c in changes)
    )
    if is_tga:
        return _render_australia_tga_drug_detail(drug, changes)

    is_hc = (
        "HEALTH_CANADA" in drug_source
        or "CANADA" in drug_source
        or any("HEALTH_CANADA" in str(_get_val(c, "source", "")).upper() for c in changes)
    )
    if is_hc:
        return _render_health_canada_drug_detail(drug, changes)

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
