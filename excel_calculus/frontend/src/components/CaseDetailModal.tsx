import React, { useState, useEffect } from "react";
import type { CaseDetail } from "../types";
import { fetchCaseDetail, updateAssessment } from "../api";
import { X, CheckCircle, AlertTriangle, XCircle, FileText, ShieldCheck } from "lucide-react";

interface Props {
  caseNumber: string;
  concernId: string;
  onClose: () => void;
  onAssessmentUpdated: () => void;
}

export const CaseDetailModal: React.FC<Props> = ({
  caseNumber,
  concernId,
  onClose,
  onAssessmentUpdated
}) => {
  const [caseData, setCaseData] = useState<CaseDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [assessmentStatus, setAssessmentStatus] = useState<string>("CANDIDATE");
  const [exclusionReason, setExclusionReason] = useState<string>("");
  const [reviewerNotes, setReviewerNotes] = useState<string>("");
  const [secondaryResult, setSecondaryResult] = useState<string>("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadCase();
  }, [caseNumber, concernId]);

  const loadCase = async () => {
    try {
      setLoading(true);
      const data = await fetchCaseDetail(caseNumber, concernId);
      setCaseData(data);
      if (data.assessment) {
        setAssessmentStatus(data.assessment.status);
        setExclusionReason(data.assessment.exclusion_reason || "");
        setReviewerNotes(data.assessment.reviewer_notes || "");
        setSecondaryResult(data.assessment.secondary_assessment_result || "");
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleSaveAssessment = async (statusToSet: string) => {
    try {
      setSaving(true);
      await updateAssessment({
        case_number: caseNumber,
        concern_id: concernId,
        status: statusToSet,
        exclusion_reason: statusToSet === "NOT_RELEVANT" ? exclusionReason : null,
        reviewer_notes: reviewerNotes,
        secondary_result: secondaryResult,
        reviewer_id: "medical_reviewer_1"
      });
      setAssessmentStatus(statusToSet);
      onAssessmentUpdated();
    } catch (err) {
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  if (!caseNumber) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-container" onClick={(e) => e.stopPropagation()}>
        {/* Modal Header */}
        <div className="modal-header">
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <FileText size={20} />
            <div>
              <h2 style={{ fontSize: "1.1rem", fontWeight: 700 }}>
                Case Review: <span style={{ fontFamily: "ui-monospace, monospace" }}>{caseNumber}</span>
              </h2>
              <span style={{ fontSize: "0.75rem", color: "#94a3b8" }}>
                Complete Pharmacovigilance Case Inspection & Relevance Assessment
              </span>
            </div>
          </div>
          <button
            onClick={onClose}
            style={{ background: "transparent", border: "none", color: "#cbd5e1", cursor: "pointer" }}
          >
            <X size={22} />
          </button>
        </div>

        {/* Modal Body */}
        <div className="modal-body">
          {loading || !caseData ? (
            <div style={{ padding: "3rem", textAlign: "center", color: "#64748b" }}>
              Loading complete case data from indexed store...
            </div>
          ) : (
            <>
              {/* Evidence Banner: WHY DID THIS CASE MATCH? */}
              {caseData.matches && caseData.matches.length > 0 && (
                <div className="evidence-match-box">
                  <div className="evidence-match-title" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                    <ShieldCheck size={16} /> WHY DID THE SYSTEM RETURN THIS CASE?
                  </div>
                  {caseData.matches.map((m, idx) => (
                    <div key={idx} className="evidence-match-text" style={{ marginTop: "0.25rem" }}>
                      <strong>Rule:</strong> {m.source} &nbsp;|&nbsp; 
                      <strong>Matched:</strong> {m.term} &nbsp;|&nbsp; 
                      <strong>Field:</strong> {m.field}
                      <div style={{ fontStyle: "italic", marginTop: "0.2rem", color: "#065f46" }}>
                        "{m.evidence}"
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* 3-Column Structured Case Inspection */}
              <div className="case-grid-3col">
                {/* Column 1: Overview & Patient Demographics */}
                <div className="case-panel">
                  <div className="panel-title">Case & Patient Overview</div>
                  <div className="info-row">
                    <span className="info-label">Product:</span>
                    <span className="info-value">{caseData.overview.product_name}</span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">Country:</span>
                    <span className="info-value">{caseData.overview.country}</span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">Report Type:</span>
                    <span className="info-value">{caseData.overview.report_type}</span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">Receipt Date:</span>
                    <span className="info-value">{caseData.overview.initial_receipt_date}</span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">Seriousness:</span>
                    <span className="info-value">
                      {caseData.overview.is_serious ? (
                        <span className="badge badge-serious">Serious</span>
                      ) : (
                        "Non-Serious"
                      )}
                    </span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">Listedness:</span>
                    <span className="info-value">{caseData.overview.listedness}</span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">Case Outcome:</span>
                    <span className="info-value">{caseData.overview.case_outcome}</span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">Primary SOC:</span>
                    <span className="info-value" style={{ fontSize: "0.78rem" }}>{caseData.overview.primary_soc}</span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">Patient Demographics:</span>
                    <span className="info-value">{caseData.patient.age || "Unknown"}, {caseData.patient.sex || "Unknown"}</span>
                  </div>

                  <div className="panel-title" style={{ marginTop: "0.5rem" }}>Administered Products ({caseData.products.length})</div>
                  {caseData.products.map((p) => (
                    <div key={p.id} style={{ 
                      padding: "0.4rem 0.6rem", 
                      borderRadius: "4px", 
                      fontSize: "0.8rem", 
                      background: p.is_suspect ? "#fef2f2" : "#f1f5f9",
                      border: p.is_suspect ? "1px solid #fecaca" : "1px solid #e2e8f0",
                      marginBottom: "0.35rem"
                    }}>
                      <div style={{ fontWeight: 600 }}>{p.brand_name || p.active_substance}</div>
                      <div style={{ fontSize: "0.75rem", color: "#64748b" }}>
                        Role: <strong>{p.role}</strong> | Active: {p.active_substance}
                      </div>
                    </div>
                  ))}
                </div>

                {/* Column 2: Exploded Events */}
                <div className="case-panel">
                  <div className="panel-title" style={{ display: "flex", justifyContent: "space-between" }}>
                    <span>Exploded Events ({caseData.events.length})</span>
                    <span style={{ fontSize: "0.7rem", color: "#64748b" }}>1 Row &rarr; N Events</span>
                  </div>
                  <div style={{ maxHeight: "420px", overflowY: "auto", paddingRight: "0.25rem" }}>
                    {caseData.events.map((ev) => (
                      <div
                        key={ev.id}
                        className={`event-item-card ${ev.is_matched ? "matched" : ""}`}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <span style={{ fontWeight: 700, color: ev.is_matched ? "#065f46" : "#0f172a" }}>
                            {ev.position + 1}. {ev.preferred_term}
                          </span>
                          {ev.is_matched && (
                            <span className="badge badge-relevant" style={{ fontSize: "0.68rem" }}>
                              MATCHED RULE
                            </span>
                          )}
                        </div>
                        <div style={{ fontSize: "0.75rem", color: "#64748b", marginTop: "0.25rem" }}>
                          Outcome: <strong>{ev.outcome || "Unknown"}</strong>
                        </div>
                        <div style={{ fontSize: "0.72rem", color: "#94a3b8", marginTop: "0.15rem", fontFamily: "ui-monospace, monospace" }}>
                          Raw: [{ev.raw_verbatim}]
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Column 3: Medical Narrative & Source Lineage */}
                <div className="case-panel">
                  <div className="panel-title">Case Narrative (Complete Medical Summary)</div>
                  <div className="narrative-box">
                    {caseData.narrative || "No narrative text recorded for this report."}
                  </div>

                  <div className="panel-title" style={{ marginTop: "0.5rem" }}>Source Lineage (Audit Trail)</div>
                  <div style={{ fontSize: "0.8rem", color: "#475569", background: "#fff", padding: "0.6rem", borderRadius: "4px", border: "1px solid #e2e8f0" }}>
                    <div><strong>Original File:</strong> {caseData.source_lineage.file}</div>
                    <div><strong>Sheet:</strong> {caseData.source_lineage.sheet}</div>
                    <div><strong>Row Number:</strong> Row {caseData.source_lineage.row}</div>
                  </div>
                </div>
              </div>

              {/* Assessment Section */}
              <div style={{ background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: "8px", padding: "1rem" }}>
                <div style={{ fontSize: "0.9rem", fontWeight: 700, marginBottom: "0.5rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <ShieldCheck size={18} color="#2563eb" /> Safety Relevance Assessment & Reviewer Determination
                </div>
                
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
                  <div>
                    <label style={{ fontSize: "0.8rem", fontWeight: 600, color: "#475569", display: "block", marginBottom: "0.25rem" }}>
                      Exclusion Reason (Mandatory if marking Not Relevant):
                    </label>
                    <select
                      className="select-input"
                      style={{ width: "100%" }}
                      value={exclusionReason}
                      onChange={(e) => setExclusionReason(e.target.value)}
                    >
                      <option value="">-- Select Exclusion Justification --</option>
                      <option value="Alternative medical etiology">Alternative medical etiology</option>
                      <option value="Concomitant drug reaction">Concomitant drug reaction</option>
                      <option value="Disease progression">Disease progression</option>
                      <option value="Lack of temporal association">Lack of temporal association</option>
                      <option value="Pre-existing baseline condition">Pre-existing baseline condition</option>
                      <option value="Unrelated procedural complication">Unrelated procedural complication</option>
                    </select>
                  </div>
                  <div>
                    <label style={{ fontSize: "0.8rem", fontWeight: 600, color: "#475569", display: "block", marginBottom: "0.25rem" }}>
                      Clinical Reviewer Notes & Evidence Appraisal:
                    </label>
                    <input
                      type="text"
                      className="select-input"
                      style={{ width: "100%" }}
                      placeholder="Add medical rationale, latency notes, or dechallenge comments..."
                      value={reviewerNotes}
                      onChange={(e) => setReviewerNotes(e.target.value)}
                    />
                  </div>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Modal Footer / Action Tray */}
        <div className="assessment-tray">
          <div style={{ fontSize: "0.85rem", color: "#64748b" }}>
            Current Status:{" "}
            <span
              className={`badge ${
                assessmentStatus === "RELEVANT"
                  ? "badge-relevant"
                  : assessmentStatus === "NOT_RELEVANT"
                  ? "badge-not-relevant"
                  : assessmentStatus === "NEEDS_REVIEW"
                  ? "badge-needs-review"
                  : "badge-candidate"
              }`}
            >
              {assessmentStatus}
            </span>
          </div>

          <div className="assessment-actions">
            <button
              className="btn-relevant"
              disabled={saving}
              onClick={() => handleSaveAssessment("RELEVANT")}
            >
              <CheckCircle size={16} style={{ marginRight: "0.3rem" }} />
              Mark Relevant
            </button>
            <button
              className="btn-not-relevant"
              disabled={saving}
              onClick={() => handleSaveAssessment("NOT_RELEVANT")}
            >
              <XCircle size={16} style={{ marginRight: "0.3rem" }} />
              Exclude (Not Relevant)
            </button>
            <button
              className="btn-needs-review"
              disabled={saving}
              onClick={() => handleSaveAssessment("NEEDS_REVIEW")}
            >
              <AlertTriangle size={16} style={{ marginRight: "0.3rem" }} />
              Flag for Mentor/Medical Review
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
