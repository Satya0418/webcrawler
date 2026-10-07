import React, { useState, useEffect } from "react";
import type { Section161ReportData } from "../types";
import { fetchSection161Report, getSection161PdfUrl } from "../api";
import { 
  Printer, 
  Copy, 
  Check, 
  FileSpreadsheet, 
  RefreshCw, 
  ChevronRight, 
  ShieldCheck, 
  AlertCircle, 
  LayoutList, 
  Table, 
  FileDown, 
  Eye, 
  X 
} from "lucide-react";

interface Props {
  product: string;
  onSelectConcern: (concernId: string) => void;
}

export const Section161Table: React.FC<Props> = ({ product, onSelectConcern }) => {
  const [reportData, setReportData] = useState<Section161ReportData | null>(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<"official" | "reviewer">("official");
  const [showPdfPreview, setShowPdfPreview] = useState(false);

  useEffect(() => {
    loadTableData();
  }, [product]);

  const loadTableData = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await fetchSection161Report(product);
      setReportData(data);
    } catch (err: any) {
      console.error(err);
      setError(err.message || "Failed to load Section 16.1 summary data");
    } finally {
      setLoading(false);
    }
  };

  const copyTableToClipboard = () => {
    if (!reportData) return;

    // Per Requirement 18: No Total row in official regulatory table (cases may belong to multiple concerns)
    let tsv = `Risk Term\tNumber of Relevant Case Reports\n`;
    let html = `<table border="1" cellpadding="6" cellspacing="0" style="border-collapse: collapse; font-family: 'Times New Roman', Times, serif; width: 100%; font-size: 10pt;">
      <thead>
        <tr style="background-color: #f1f5f9; font-weight: bold;">
          <th align="left" style="border: 1px solid #000000; padding: 6px 8px;">Risk Term</th>
          <th align="center" style="border: 1px solid #000000; padding: 6px 8px; width: 180px;">Number of Relevant Case Reports</th>
        </tr>
      </thead>
      <tbody>`;

    for (const sec of reportData.table_sections) {
      tsv += `${sec.category_name.toUpperCase()}\t\n`;
      html += `<tr style="font-weight: bold; background-color: #fafafa;">
        <td colspan="2" style="border: 1px solid #000000; padding: 6px 8px; text-transform: uppercase;">${sec.category_name}</td>
      </tr>`;
      for (const risk of sec.risks) {
        tsv += `${risk.risk_term}\t${risk.number_of_relevant_cases}\n`;
        html += `<tr>
          <td style="border: 1px solid #000000; padding: 5px 8px; padding-left: 16px;">${risk.risk_term}</td>
          <td align="center" style="border: 1px solid #000000; padding: 5px 8px;">${risk.number_of_relevant_cases}</td>
        </tr>`;
      }
    }

    html += `</tbody></table>`;

    if (navigator.clipboard && window.ClipboardItem) {
      const textBlob = new Blob([tsv], { type: "text/plain" });
      const htmlBlob = new Blob([html], { type: "text/html" });
      navigator.clipboard.write([new ClipboardItem({ "text/plain": textBlob, "text/html": htmlBlob })]).then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2500);
      }).catch(() => {
        navigator.clipboard.writeText(tsv);
        setCopied(true);
        setTimeout(() => setCopied(false), 2500);
      });
    } else {
      navigator.clipboard.writeText(tsv);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    }
  };

  if (loading && !reportData) {
    return <div style={{ padding: "3rem", textAlign: "center", color: "#64748b" }}>Calculating PBRER Section 16.1 table...</div>;
  }

  if (error) {
    return (
      <div style={{ padding: "2rem", textAlign: "center", color: "#dc2626" }}>
        <AlertCircle size={24} style={{ marginBottom: "0.5rem" }} />
        <div>{error}</div>
        <button className="btn-secondary" onClick={loadTableData} style={{ marginTop: "1rem" }}>
          Retry
        </button>
      </div>
    );
  }

  if (!reportData) return null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      {/* Top Header Bar */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "1rem" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <span className="badge" style={{ backgroundColor: "#2563eb", color: "#ffffff", fontWeight: 700 }}>
              PBRER SECTION 16.1
            </span>
            <span style={{ fontSize: "0.85rem", color: "#64748b", fontWeight: 500 }}>
              {reportData.product_name} &bull; Interval {reportData.reporting_period}
            </span>
          </div>
          <h2 style={{ fontSize: "1.35rem", fontWeight: 800, color: "#0f172a", marginTop: "0.35rem" }}>
            16.1 Summary of Safety Concerns
          </h2>
          <p style={{ fontSize: "0.9rem", color: "#475569", marginTop: "0.25rem", fontStyle: "italic", maxWidth: "800px" }}>
            &ldquo;{reportData.intro_text}&rdquo;
          </p>
        </div>

        <div style={{ display: "flex", gap: "0.5rem" }}>
          {/* View Mode Toggle */}
          <div style={{ display: "flex", backgroundColor: "#f1f5f9", borderRadius: "0.375rem", padding: "2px", border: "1px solid #e2e8f0" }}>
            <button
              onClick={() => setViewMode("official")}
              style={{
                padding: "0.35rem 0.65rem",
                fontSize: "0.8rem",
                fontWeight: 600,
                border: "none",
                borderRadius: "0.25rem",
                cursor: "pointer",
                display: "inline-flex",
                alignItems: "center",
                gap: "0.3rem",
                backgroundColor: viewMode === "official" ? "#ffffff" : "transparent",
                color: viewMode === "official" ? "#1e293b" : "#64748b",
                boxShadow: viewMode === "official" ? "0 1px 2px rgba(0,0,0,0.06)" : "none"
              }}
              title="Official PBRER 2-column regulatory submission format"
            >
              <Table size={14} /> Official PBRER View
            </button>
            <button
              onClick={() => setViewMode("reviewer")}
              style={{
                padding: "0.35rem 0.65rem",
                fontSize: "0.8rem",
                fontWeight: 600,
                border: "none",
                borderRadius: "0.25rem",
                cursor: "pointer",
                display: "inline-flex",
                alignItems: "center",
                gap: "0.3rem",
                backgroundColor: viewMode === "reviewer" ? "#ffffff" : "transparent",
                color: viewMode === "reviewer" ? "#1e293b" : "#64748b",
                boxShadow: viewMode === "reviewer" ? "0 1px 2px rgba(0,0,0,0.06)" : "none"
              }}
              title="Reviewer working table with criteria, candidate cases, and review actions"
            >
              <LayoutList size={14} /> Reviewer & Audit View
            </button>
          </div>

          <button className="btn-secondary" onClick={loadTableData} title="Recalculate counts from indexed line listings">
            <RefreshCw size={15} /> Recalculate
          </button>
          <button className="btn-secondary" onClick={copyTableToClipboard} title="Copy official 2-column table ready to paste into Word or Excel">
            {copied ? <Check size={15} color="#16a34a" /> : <Copy size={15} />}
            {copied ? "Copied Table!" : "Copy Table for Word"}
          </button>
          <button className="btn-secondary" onClick={() => window.print()} title="Print Section 16.1 Table">
            <Printer size={15} /> Print
          </button>
          <button 
            className="btn-secondary" 
            onClick={() => setShowPdfPreview(true)}
            title="Preview Section 16.1 PBRER PDF matching official regulatory submission format"
            style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}
          >
            <Eye size={15} color="#2563eb" /> Preview PDF
          </button>
          <a
            href={getSection161PdfUrl(product, false)}
            download={`${product}_Section_16.1_PBRER_Report.pdf`}
            className="btn-primary"
            style={{ textDecoration: "none", display: "inline-flex", alignItems: "center", gap: "0.35rem" }}
            title="Download formal A4 PBRER PDF Report"
          >
            <FileDown size={15} /> Download PBRER PDF
          </a>
        </div>
      </div>

      {/* Summary KPI Cards */}
      <div className="metrics-grid">
        <div className="metric-card">
          <div className="metric-card-title">Total Relevant Case Reports</div>
          <div className="metric-card-value" style={{ color: "#2563eb" }}>
            {reportData.total_relevant_cases}
          </div>
          <div className="metric-card-sub">Retrieved by predefined safety searches</div>
        </div>
        <div className="metric-card">
          <div className="metric-card-title">Total Candidate Matches</div>
          <div className="metric-card-value">{reportData.total_candidate_cases}</div>
          <div className="metric-card-sub">Distinct retrieved case reports</div>
        </div>
        <div className="metric-card">
          <div className="metric-card-title">Important Identified Risks</div>
          <div className="metric-card-value" style={{ color: "#059669" }}>
            {reportData.table_sections.find((s) => s.category_name === "Important Identified Risks")?.risks.length || 0}
          </div>
          <div className="metric-card-sub">Safety Concerns</div>
        </div>
        <div className="metric-card">
          <div className="metric-card-title">Important Potential / Missing</div>
          <div className="metric-card-value" style={{ color: "#d97706" }}>
            {(reportData.table_sections.find((s) => s.category_name === "Important Potential Risks")?.risks.length || 0) +
             (reportData.table_sections.find((s) => s.category_name === "Missing Information")?.risks.length || 0)}
          </div>
          <div className="metric-card-sub">Safety Concerns</div>
        </div>
      </div>

      {/* The Master PBRER Section 16.1 Table */}
      <div className="table-card">
        <div className="table-header-bar" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div className="table-title" style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <FileSpreadsheet size={18} color="#2563eb" />
            Table: Number of Case Reports Pertaining to Safety Concerns (PBRER Section 16.1)
          </div>
          <span style={{ fontSize: "0.8rem", color: "#64748b" }}>
            {viewMode === "official"
              ? "Official 2-column regulatory submission format. Click any risk row to inspect cases."
              : "Reviewer view with criteria and direct case review actions."}
          </span>
        </div>

        {viewMode === "official" ? (
          /* OFFICIAL PBRER 2-COLUMN TABLE */
          <table className="data-table">
            <thead>
              <tr>
                <th style={{ width: "70%", padding: "0.75rem 1rem", fontSize: "0.85rem", textTransform: "uppercase" }}>
                  Risk Term
                </th>
                <th style={{ width: "30%", textAlign: "center", padding: "0.75rem 1rem", fontSize: "0.85rem", textTransform: "uppercase" }}>
                  Number of Relevant Case Reports
                </th>
              </tr>
            </thead>
            <tbody>
              {reportData.table_sections.map((section) => (
                <React.Fragment key={section.category_name}>
                  {/* Category Header Row */}
                  <tr style={{ backgroundColor: "#f8fafc" }}>
                    <td
                      colSpan={2}
                      style={{
                        fontWeight: 800,
                        fontSize: "0.85rem",
                        letterSpacing: "0.03em",
                        color: "#0f172a",
                        padding: "0.75rem 1rem",
                        borderTop: "2px solid #cbd5e1",
                        borderBottom: "1px solid #cbd5e1",
                        textTransform: "uppercase"
                      }}
                    >
                      {section.category_name}
                    </td>
                  </tr>

                  {/* Individual Safety Concern Rows */}
                  {section.risks.map((risk) => (
                    <tr
                      key={risk.concern_id}
                      onClick={() => onSelectConcern(risk.concern_id)}
                      style={{ cursor: "pointer", transition: "background-color 0.15s ease" }}
                      title={`Click to review ${risk.candidate_case_count} candidate case(s)`}
                    >
                      <td style={{ padding: "0.65rem 1.25rem" }}>
                        <div style={{ fontWeight: 600, color: "#1e293b" }}>{risk.risk_term}</div>
                      </td>
                      <td style={{ textAlign: "center", padding: "0.65rem 1rem" }}>
                        <span
                          className="badge"
                          style={{
                            fontSize: "0.95rem",
                            fontWeight: 700,
                            padding: "0.25rem 0.75rem",
                            backgroundColor: risk.number_of_relevant_cases > 0 ? "#eff6ff" : "#f8fafc",
                            color: risk.number_of_relevant_cases > 0 ? "#1d4ed8" : "#475569",
                            border: `1px solid ${risk.number_of_relevant_cases > 0 ? "#bfdbfe" : "#e2e8f0"}`
                          }}
                        >
                          {risk.number_of_relevant_cases}
                        </span>
                      </td>
                    </tr>
                  ))}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        ) : (
          /* REVIEWER & AUDIT TABLE */
          <table className="data-table">
            <thead>
              <tr>
                <th style={{ width: "35%" }}>Risk Term / Safety Concern</th>
                <th style={{ width: "30%" }}>Search Method & Criteria</th>
                <th style={{ width: "15%", textAlign: "center" }}>
                  Number of Relevant Case Reports
                </th>
                <th style={{ width: "12%", textAlign: "center" }}>Reviewer Status</th>
                <th style={{ width: "8%", textAlign: "center" }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {reportData.table_sections.map((section) => (
                <React.Fragment key={section.category_name}>
                  {/* Category Header Row */}
                  <tr style={{ backgroundColor: "#f8fafc" }}>
                    <td
                      colSpan={5}
                      style={{
                        fontWeight: 800,
                        fontSize: "0.85rem",
                        letterSpacing: "0.03em",
                        color: "#1e293b",
                        paddingTop: "0.85rem",
                        paddingBottom: "0.85rem",
                        borderTop: "2px solid #e2e8f0",
                        borderBottom: "1px solid #cbd5e1",
                        textTransform: "uppercase"
                      }}
                    >
                      <span style={{ display: "inline-block", width: "8px", height: "8px", backgroundColor: "#2563eb", borderRadius: "50%", marginRight: "0.5rem" }}></span>
                      {section.category_name}
                    </td>
                  </tr>

                  {/* Individual Safety Concern Rows */}
                  {section.risks.map((risk) => (
                    <tr key={risk.concern_id} style={{ transition: "background-color 0.15s ease" }}>
                      <td style={{ paddingLeft: "1.5rem" }}>
                        <div style={{ fontWeight: 600, color: "#0f172a" }}>{risk.risk_term}</div>
                        {risk.requires_secondary_assessment && (
                          <span style={{ fontSize: "0.75rem", color: "#d97706", fontWeight: 500 }}>
                            &bull; Requires Concomitant Assessment
                          </span>
                        )}
                      </td>
                      <td>
                        <span className="badge" style={{ backgroundColor: "#f1f5f9", color: "#334155", marginRight: "0.4rem", fontSize: "0.7rem" }}>
                          {risk.search_method}
                        </span>
                        <span style={{ fontSize: "0.8rem", color: "#64748b" }}>
                          {risk.search_criteria}
                        </span>
                      </td>
                      <td style={{ textAlign: "center" }}>
                        <span
                          className="badge"
                          style={{
                            fontSize: "0.95rem",
                            fontWeight: 700,
                            padding: "0.35rem 0.75rem",
                            backgroundColor: risk.number_of_relevant_cases > 0 ? "#eff6ff" : "#f1f5f9",
                            color: risk.number_of_relevant_cases > 0 ? "#1d4ed8" : "#64748b",
                            border: `1px solid ${risk.number_of_relevant_cases > 0 ? "#bfdbfe" : "#e2e8f0"}`
                          }}
                        >
                          {risk.number_of_relevant_cases}
                        </span>
                      </td>
                      <td style={{ textAlign: "center", color: "#64748b", fontSize: "0.8rem", fontWeight: 500 }}>
                        <span style={{ color: "#16a34a", fontWeight: 600 }}>{risk.confirmed_relevant_count || 0} Confirmed</span>
                        <br />
                        <span style={{ color: "#64748b", fontSize: "0.75rem" }}>{risk.pending_count || 0} Pending</span>
                      </td>
                      <td style={{ textAlign: "center" }}>
                        <button
                          className="btn-secondary"
                          onClick={() => onSelectConcern(risk.concern_id)}
                          style={{
                            padding: "0.3rem 0.65rem",
                            fontSize: "0.8rem",
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "0.25rem"
                          }}
                        >
                          Review Cases <ChevronRight size={14} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </React.Fragment>
              ))}

              {/* Total Row */}
              <tr style={{ backgroundColor: "#f1f5f9", fontWeight: 700, borderTop: "2px solid #cbd5e1" }}>
                <td colSpan={2} style={{ paddingLeft: "1.5rem", fontSize: "0.9rem", color: "#0f172a" }}>
                  Total Relevant Case Reports across all Safety Concerns:
                </td>
                <td style={{ textAlign: "center" }}>
                  <span
                    className="badge badge-relevant"
                    style={{ fontSize: "1rem", fontWeight: 800, padding: "0.4rem 0.85rem" }}
                  >
                    {reportData.total_relevant_cases}
                  </span>
                </td>
                <td style={{ textAlign: "center", color: "#334155", fontSize: "0.85rem" }}>
                  {reportData.total_candidate_cases} Retrieved
                </td>
                <td></td>
              </tr>
            </tbody>
          </table>
        )}
      </div>

      {/* Regulatory Context Box */}
      <div
        style={{
          padding: "1rem 1.25rem",
          backgroundColor: "#f8fafc",
          border: "1px solid #e2e8f0",
          borderRadius: "0.5rem",
          fontSize: "0.85rem",
          color: "#475569",
          lineHeight: 1.6
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontWeight: 700, color: "#1e293b", marginBottom: "0.25rem" }}>
          <ShieldCheck size={16} color="#2563eb" />
          PBRER Section 16.1 Regulatory Compliance
        </div>
        The case counts above represent the deterministic calculation for <strong>PBRER Section 16.1</strong>.
        Each number is derived from the interval line listing, exploding multi-event verbatim terms, evaluating against MedDRA SMQs / PT lists, and applying reviewer relevance assessments.
        Click <strong>Review Cases</strong> on any risk term to inspect patient demographics, suspect products, exploded events, and raw row lineage.
      </div>

      {/* PDF Preview Modal */}
      {showPdfPreview && (
        <div 
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: "rgba(15, 23, 42, 0.75)",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 9999,
            padding: "1.5rem"
          }}
        >
          <div 
            style={{
              backgroundColor: "#ffffff",
              borderRadius: "0.5rem",
              width: "100%",
              maxWidth: "1050px",
              height: "92vh",
              display: "flex",
              flexDirection: "column",
              overflow: "hidden",
              boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.25)"
            }}
          >
            {/* Modal Header */}
            <div 
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "0.85rem 1.25rem",
                borderBottom: "1px solid #e2e8f0",
                backgroundColor: "#f8fafc"
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <FileSpreadsheet size={18} color="#2563eb" />
                <span style={{ fontWeight: 700, color: "#0f172a", fontSize: "0.95rem" }}>
                  PBRER Section 16.1 PDF Preview — {reportData.product_name}
                </span>
                <span style={{ fontSize: "0.8rem", color: "#64748b" }}>
                  (Formal A4 Regulatory Submission Format)
                </span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                <a
                  href={getSection161PdfUrl(product, false)}
                  download={`${product}_Section_16.1_PBRER_Report.pdf`}
                  className="btn-primary"
                  style={{ textDecoration: "none", fontSize: "0.8rem", padding: "0.35rem 0.75rem", display: "inline-flex", alignItems: "center", gap: "0.3rem" }}
                >
                  <FileDown size={14} /> Download PDF
                </a>
                <button
                  onClick={() => setShowPdfPreview(false)}
                  style={{
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    padding: "0.25rem",
                    color: "#64748b"
                  }}
                  title="Close Preview"
                >
                  <X size={20} />
                </button>
              </div>
            </div>

            {/* Modal PDF iframe */}
            <div style={{ flex: 1, backgroundColor: "#525659", padding: "0" }}>
              <iframe
                src={getSection161PdfUrl(product, true)}
                title="PBRER PDF Preview"
                style={{ width: "100%", height: "100%", border: "none" }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

