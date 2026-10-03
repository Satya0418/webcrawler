import React, { useState, useEffect } from "react";
import type { Section161ReportData } from "../types";
import { fetchSection161Report } from "../api";
import { Printer, Copy, Check, FileSpreadsheet, RefreshCw, ChevronRight, ShieldCheck, AlertCircle } from "lucide-react";

interface Props {
  product: string;
  onSelectConcern: (concernId: string) => void;
}

export const Section161Table: React.FC<Props> = ({ product, onSelectConcern }) => {
  const [reportData, setReportData] = useState<Section161ReportData | null>(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

    let text = `16.1 Summary of Safety Concerns\nProduct: ${reportData.product_name}\nReporting Period: ${reportData.reporting_period}\n\n${reportData.intro_text}\n\n`;
    text += `Risk Category | Risk Term | Search Method | Number of Relevant Case Reports\n`;
    text += `---|---|---|---\n`;

    for (const sec of reportData.table_sections) {
      text += `**${sec.category_name}** | | |\n`;
      for (const risk of sec.risks) {
        text += `${sec.category_name} | ${risk.risk_term} | ${risk.search_method} | ${risk.number_of_relevant_cases}\n`;
      }
    }

    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
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
      {/* Top Header Card */}
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
          <button className="btn-secondary" onClick={loadTableData} title="Recalculate counts from indexed line listings">
            <RefreshCw size={15} /> Recalculate
          </button>
          <button className="btn-secondary" onClick={copyTableToClipboard} title="Copy table for pasting directly into PBRER Word document">
            {copied ? <Check size={15} color="#16a34a" /> : <Copy size={15} />}
            {copied ? "Copied to Clipboard!" : "Copy Table for Word"}
          </button>
          <button className="btn-secondary" onClick={() => window.print()} title="Print Section 16.1 Table">
            <Printer size={15} /> Print / Export
          </button>
        </div>
      </div>

      {/* Summary KPI Cards */}
      <div className="metrics-grid">
        <div className="metric-card">
          <div className="metric-card-title">Total Relevant Case Reports</div>
          <div className="metric-card-value" style={{ color: "#2563eb" }}>
            {reportData.total_relevant_cases}
          </div>
          <div className="metric-card-sub">Included in Section 16.1</div>
        </div>
        <div className="metric-card">
          <div className="metric-card-title">Total Candidate Matches</div>
          <div className="metric-card-value">{reportData.total_candidate_cases}</div>
          <div className="metric-card-sub">From line-listing calculus</div>
        </div>
        <div className="metric-card">
          <div className="metric-card-title">Important Identified Risks</div>
          <div className="metric-card-value" style={{ color: "#059669" }}>
            {reportData.table_sections.find((s) => s.category_name === "Important Identified Risks")?.risks.length || 0}
          </div>
          <div className="metric-card-sub">Monitored Safety Concerns</div>
        </div>
        <div className="metric-card">
          <div className="metric-card-title">Important Potential / Missing</div>
          <div className="metric-card-value" style={{ color: "#d97706" }}>
            {(reportData.table_sections.find((s) => s.category_name === "Important Potential Risks")?.risks.length || 0) +
             (reportData.table_sections.find((s) => s.category_name === "Missing Information")?.risks.length || 0)}
          </div>
          <div className="metric-card-sub">Potential & Missing Concerns</div>
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
            Click &ldquo;Review Cases&rdquo; to inspect candidate line-listing records
          </span>
        </div>

        <table className="data-table">
          <thead>
            <tr>
              <th style={{ width: "35%" }}>Risk Term / Safety Concern</th>
              <th style={{ width: "30%" }}>Search Method & Criteria</th>
              <th style={{ width: "15%", textAlign: "center" }}>
                Number of Relevant Case Reports
              </th>
              <th style={{ width: "10%", textAlign: "center" }}>Candidate Cases</th>
              <th style={{ width: "10%", textAlign: "center" }}>Action</th>
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
                    <td style={{ textAlign: "center", color: "#64748b", fontSize: "0.85rem", fontWeight: 500 }}>
                      {risk.candidate_case_count}
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
              <td style={{ textAlign: "center", color: "#334155" }}>
                {reportData.total_candidate_cases}
              </td>
              <td></td>
            </tr>
          </tbody>
        </table>
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
    </div>
  );
};
