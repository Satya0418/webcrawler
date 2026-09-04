"""
HTML UI and Data Export Generator for Medicine Safety Platform.
Clean, minimalist, white-background design matching the official FDA SrLC format.
Provides CSV and JSON export generators.
"""
import csv
import io
import json
import html
from typing import List, Dict, Any
from collections import defaultdict


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
                        <a href="/drugs/{d_id}" class="btn btn-secondary">View Changes &rarr;</a>
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
    Render drug safety labeling detail page with a clean, simple white background
    matching the exact layout shown in the user's photos, plus CSV and JSON export buttons.
    """
    d_id = drug.get("id") or 1
    display_name = html.escape(drug.get("display_name") or "")
    active_ingredient = html.escape(drug.get("active_ingredient") or "Not specified")
    application_number = html.escape(drug.get("application_number") or "N/A")

    # Group changes by supplement date and ID
    grouped = defaultdict(list)
    pdf_links = {}

    for c in changes:
        s_date = c.get("source_date")
        if s_date:
            date_str = str(s_date)[:10]
            if "-" in date_str and len(date_str) == 10:
                parts = date_str.split("-")
                date_str = f"{parts[1]}/{parts[2]}/{parts[0]}"
        else:
            date_str = "Recent"

        s_id = c.get("source_record_id") or "SUPPL"
        group_key = (date_str, s_id)
        grouped[group_key].append(c)

        # Extract PDF url
        fda_comment = c.get("fda_comment") or ""
        source_url = c.get("source_url") or ""
        if ".pdf" in source_url.lower():
            pdf_links[group_key] = source_url
        elif "Approved Drug Label:" in fda_comment and ".pdf" in fda_comment.lower():
            pdf_links[group_key] = fda_comment.replace("Approved Drug Label:", "").strip()

    # Build supplement blocks
    supplements_html = []

    for (date_str, suppl_id), section_changes in sorted(grouped.items(), key=lambda x: x[0][0], reverse=True):
        pdf_url = pdf_links.get((date_str, suppl_id))
        pdf_link_html = ""
        if pdf_url:
            pdf_link_html = f"""
            <div class="pdf-link-container">
                <a href="{html.escape(pdf_url)}" target="_blank" class="pdf-link">
                    Approved Drug Label (PDF)
                </a>
            </div>
            """

        sections_html = []
        for chg in section_changes:
            sec_title = html.escape(chg.get("section") or "Safety Information")
            up_text = chg.get("updated_text") or ""

            formatted_paragraphs = []
            for block in up_text.split("\n\n"):
                block = block.strip()
                if not block:
                    continue

                if "•" in block:
                    lines = block.split("\n")
                    bullets = []
                    pre = []
                    for line in lines:
                        line = line.strip()
                        if line.startswith("•"):
                            bullets.append(f"<li>{html.escape(line.lstrip('• ').strip())}</li>")
                        elif line:
                            pre.append(f"<p>{html.escape(line)}</p>")
                    if pre:
                        formatted_paragraphs.append("".join(pre))
                    if bullets:
                        formatted_paragraphs.append(f"<ul class='bullet-list'>{''.join(bullets)}</ul>")
                elif block.startswith("…") or block == "...":
                    formatted_paragraphs.append(f"<p class='ellipsis'>{html.escape(block)}</p>")
                elif any(block.startswith(p) for p in ("Newly added", "Additions and/or")):
                    formatted_paragraphs.append(f"<p class='meta-note'><em>{html.escape(block)}</em></p>")
                elif any(block.startswith(p) for p in ("5.", "6.", "8.", "17.", "PATIENT COUNSELING")):
                    formatted_paragraphs.append(f"<p class='subsection-title'><strong>{html.escape(block)}</strong></p>")
                else:
                    formatted_paragraphs.append(f"<p class='text-body'>{html.escape(block)}</p>")

            body_content = "".join(formatted_paragraphs)

            sections_html.append(f"""
            <div class="section-item">
                <h4 class="section-heading">{sec_title}</h4>
                <div class="section-content">
                    {body_content}
                </div>
            </div>
            """)

        supplements_html.append(f"""
        <div class="supplement-panel">
            <div class="supplement-header">
                {date_str} <span class="suppl-id">({html.escape(suppl_id)})</span>
            </div>
            <div class="supplement-body">
                {pdf_link_html}
                {"".join(sections_html)}
            </div>
        </div>
        """)

    if not supplements_html:
        supplements_html.append("""
        <div style="padding: 20px; color: #6b7280;">
            No safety-related labeling changes recorded for this drug.
        </div>
        """)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{display_name} ({application_number}) - FDA Safety Labeling Changes</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
            background-color: #ffffff;
            color: #222222;
            margin: 0;
            padding: 0;
            line-height: 1.55;
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
        .nav-left {{ display: flex; gap: 12px; align-items: center; }}
        .nav-right {{ display: flex; gap: 10px; align-items: center; }}
        .page-container {{
            max-width: 980px;
            margin: 20px auto 60px auto;
            padding: 0 20px;
        }}
        .drug-header {{
            margin-bottom: 24px;
            padding-bottom: 16px;
            border-bottom: 1px solid #dee2e6;
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
            color: #111;
            margin: 0 0 4px 0;
        }}
        .app-number {{
            font-weight: 400;
            color: #555;
        }}
        .ingredient {{
            font-size: 16px;
            font-weight: 600;
            color: #333;
            margin: 0 0 8px 0;
        }}
        .agency-subtitle {{
            color: #555;
            font-size: 13px;
            margin: 0;
        }}
        .export-actions {{
            display: flex;
            gap: 8px;
            align-items: center;
        }}
        .export-label {{
            font-size: 12px;
            font-weight: 600;
            color: #6b7280;
            text-transform: uppercase;
        }}
        .btn-export {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 7px 12px;
            border: 1px solid #d1d5db;
            border-radius: 4px;
            background: #f9fafb;
            color: #1f2937;
            font-size: 13px;
            font-weight: 600;
            text-decoration: none;
            transition: all 0.15s ease-in-out;
        }}
        .btn-export:hover {{
            background: #0284c7;
            color: #ffffff;
            border-color: #0284c7;
        }}
        .btn-export-csv:hover {{
            background: #059669;
            border-color: #059669;
        }}
        .supplement-panel {{
            border: 1px solid #cccccc;
            border-radius: 4px;
            margin-bottom: 20px;
            background: #ffffff;
        }}
        .supplement-header {{
            background: #eef2f5;
            color: #222222;
            padding: 12px 18px;
            font-size: 16px;
            font-weight: 700;
            border-bottom: 1px solid #cccccc;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .suppl-id {{
            color: #555555;
            font-weight: 500;
            font-size: 14px;
        }}
        .supplement-body {{
            padding: 18px 24px 24px 24px;
        }}
        .pdf-link-container {{
            margin-bottom: 18px;
        }}
        .pdf-link {{
            color: #0066cc;
            font-size: 14px;
            text-decoration: underline;
            font-weight: 500;
        }}
        .pdf-link:hover {{ color: #004499; }}
        .section-item {{
            margin-bottom: 24px;
        }}
        .section-heading {{
            font-size: 18px;
            font-weight: 700;
            color: #111111;
            margin: 0 0 10px 0;
            padding-bottom: 4px;
            border-bottom: 1px solid #eeeeee;
        }}
        .section-content {{
            padding-left: 2px;
        }}
        .meta-note {{
            color: #444444;
            font-style: italic;
            margin: 6px 0;
            font-size: 14px;
        }}
        .subsection-title {{
            font-size: 15px;
            margin: 14px 0 6px 0;
            color: #111111;
        }}
        .text-body {{
            margin: 8px 0;
            color: #222222;
            line-height: 1.6;
        }}
        .bullet-list {{
            margin: 8px 0 14px 20px;
            padding: 0;
            list-style-type: disc;
        }}
        .bullet-list li {{
            margin-bottom: 6px;
            color: #222222;
            line-height: 1.55;
        }}
        .ellipsis {{
            color: #888888;
            margin: 4px 0;
        }}
        .footer-note {{
            margin-top: 40px;
            padding-top: 14px;
            border-top: 1px solid #dee2e6;
            font-size: 12px;
            color: #666666;
        }}
    </style>
</head>
<body>
    <div class="top-nav">
        <div class="nav-left">
            <a href="/">&larr; Back to Search</a>
        </div>
    </div>

    <div class="page-container">
        <div class="drug-header">
            <div class="drug-header-main">
                <h1 class="drug-name">
                    {display_name} <span class="app-number">({application_number})</span>
                </h1>
                <div class="ingredient">({active_ingredient})</div>
                <p class="agency-subtitle">Safety-related Labeling Changes Approved by FDA Center for Drug Evaluation and Research (CDER)</p>
            </div>
            <div class="export-actions">
                <span class="export-label">Download Data:</span>
                <a href="/drugs/{d_id}/export?format=csv" class="btn-export btn-export-csv" download>
                    📥 CSV
                </a>
                <a href="/drugs/{d_id}/export?format=json" class="btn-export" download>
                    📥 JSON
                </a>
            </div>
        </div>

        <div class="supplements-container">
            {"".join(supplements_html)}
        </div>

        <div class="footer-note">
            Source: U.S. Food and Drug Administration (FDA) Drug Safety-related Labeling Changes database.
        </div>
    </div>
</body>
</html>
"""
