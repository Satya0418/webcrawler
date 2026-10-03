import { useState, useEffect } from "react";
import type { SafetyConcern, SearchSummary } from "./types";
import { fetchSafetyConcerns, runConcernSearch, fetchSearchSummary, fetchIngestionStatus } from "./api";
import { CaseDetailModal } from "./components/CaseDetailModal";
import { Section161Table } from "./components/Section161Table";
import { IngestionManager } from "./components/IngestionManager";
import { Activity, Search, FileText, ChevronRight, ChevronLeft, Filter, UploadCloud } from "lucide-react";

export function App() {
  const [activeTab, setActiveTab] = useState<"section161" | "review" | "pipeline">("section161");
  const [selectedProduct, setSelectedProduct] = useState<string>("Abiraterone");
  const [availableProducts, setAvailableProducts] = useState<string[]>(["Abiraterone", "Oxycodone"]);
  const [concerns, setConcerns] = useState<SafetyConcern[]>([]);
  const [selectedConcernId, setSelectedConcernId] = useState<string>("");
  const [searchSummary, setSearchSummary] = useState<SearchSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [filterText, setFilterText] = useState("");
  const [selectedCaseForReview, setSelectedCaseForReview] = useState<string | null>(null);

  // Load available products on initial load
  useEffect(() => {
    fetchIngestionStatus().then((status) => {
      if (status.products && status.products.length > 0) {
        setAvailableProducts(status.products);
      }
    }).catch(console.error);
  }, []);

  // Load concerns when product changes
  useEffect(() => {
    loadConcerns(selectedProduct);
  }, [selectedProduct]);

  const loadConcerns = async (product: string) => {
    try {
      const data = await fetchSafetyConcerns(product);
      setConcerns(data);
      if (data.length > 0) {
        setSelectedConcernId(data[0].id);
      }
    } catch (err) {
      console.error(err);
    }
  };

  // Run or fetch search when concern changes
  useEffect(() => {
    if (selectedConcernId) {
      executeSearch(selectedConcernId);
    }
  }, [selectedConcernId]);

  const executeSearch = async (concernId: string) => {
    try {
      setLoading(true);
      const res = await runConcernSearch(concernId);
      setSearchSummary(res);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleAssessmentUpdated = async () => {
    if (selectedConcernId) {
      const res = await fetchSearchSummary(selectedConcernId);
      setSearchSummary(res);
    }
  };

  const currentConcern = concerns.find((c) => c.id === selectedConcernId);

  // Filter cases in table
  const filteredCases = (searchSummary?.cases || []).filter((c) => {
    if (!filterText) return true;
    const q = filterText.toLowerCase();
    return (
      c.case_number.toLowerCase().includes(q) ||
      c.country.toLowerCase().includes(q) ||
      c.outcome.toLowerCase().includes(q) ||
      c.matches.some((m) => m.matched_term.toLowerCase().includes(q))
    );
  });

  return (
    <div className="app-container">
      {/* Top Header */}
      <header className="app-header">
        <div className="brand-section">
          <div className="brand-logo">
            <Activity size={22} />
          </div>
          <div className="brand-text">
            <h1>Excel Calculus &bull; PBRER Section 16.1 Platform</h1>
            <span>Deterministic Summary of Safety Concerns Table & Multi-Event Line Listing Calculus</span>
          </div>
        </div>

        <nav className="header-nav">
          <button
            className={`nav-tab ${activeTab === "section161" ? "active" : ""}`}
            onClick={() => setActiveTab("section161")}
          >
            <FileText size={16} /> Section 16.1 Summary Table
          </button>
          <button
            className={`nav-tab ${activeTab === "review" ? "active" : ""}`}
            onClick={() => setActiveTab("review")}
          >
            <Search size={16} /> Case Review & Assessment
          </button>
          <button
            className={`nav-tab ${activeTab === "pipeline" ? "active" : ""}`}
            onClick={() => setActiveTab("pipeline")}
          >
            <UploadCloud size={16} /> Add Files & Pipeline
          </button>
        </nav>

        <div className="system-badge">
          <div className="status-dot"></div>
          <span>Indexed Store Active</span>
        </div>
      </header>

      {/* Main Container */}
      <main className="main-content">
        {activeTab === "pipeline" ? (
          <IngestionManager
            onFileIngested={async () => {
              try {
                const s = await fetchIngestionStatus();
                if (s.products && s.products.length > 0) {
                  setAvailableProducts(s.products);
                }
                loadConcerns(selectedProduct);
              } catch (err) {
                console.error(err);
              }
            }}
          />
        ) : activeTab === "section161" ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
            <div className="control-bar" style={{ marginBottom: "0.25rem" }}>
              <div className="control-group">
                <span className="control-label">Product:</span>
                <select
                  className="select-input"
                  value={selectedProduct}
                  onChange={(e) => setSelectedProduct(e.target.value)}
                >
                  {availableProducts.map((p) => (
                    <option key={p} value={p}>
                      {p} (Interval 2025-2026)
                    </option>
                  ))}
                </select>
                <button
                  className="btn-secondary"
                  onClick={() => setActiveTab("pipeline")}
                  title="Upload a new line listing or reference file"
                  style={{ display: "flex", alignItems: "center", gap: "0.35rem", padding: "0.45rem 0.75rem", fontSize: "0.85rem" }}
                >
                  <UploadCloud size={15} color="#2563eb" /> Add File
                </button>
              </div>
            </div>

            <Section161Table
              product={selectedProduct}
              onSelectConcern={(concernId) => {
                setSelectedConcernId(concernId);
                setActiveTab("review");
              }}
            />
          </div>
        ) : (
          <>
            <div style={{ marginBottom: "0.75rem" }}>
              <button
                className="btn-secondary"
                onClick={() => setActiveTab("section161")}
                style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem", padding: "0.4rem 0.8rem", fontSize: "0.85rem" }}
              >
                <ChevronLeft size={16} /> Back to Section 16.1 Summary Table
              </button>
            </div>

            {/* Control Bar: Product & Safety Concern Selectors */}
            <div className="control-bar">
              <div className="control-group">
                <span className="control-label">Product:</span>
                <select
                  className="select-input"
                  value={selectedProduct}
                  onChange={(e) => setSelectedProduct(e.target.value)}
                >
                  {availableProducts.map((p) => (
                    <option key={p} value={p}>
                      {p} (Interval 2025-2026)
                    </option>
                  ))}
                </select>
                <button
                  className="btn-secondary"
                  onClick={() => setActiveTab("pipeline")}
                  title="Upload a new line listing or reference file"
                  style={{ display: "flex", alignItems: "center", gap: "0.35rem", padding: "0.45rem 0.75rem", fontSize: "0.85rem" }}
                >
                  <UploadCloud size={15} color="#2563eb" /> Add File
                </button>
              </div>

              <div className="control-group" style={{ flex: 1 }}>
                <span className="control-label">Safety Concern:</span>
                <select
                  className="select-input"
                  style={{ flex: 1 }}
                  value={selectedConcernId}
                  onChange={(e) => setSelectedConcernId(e.target.value)}
                >
                  {concerns.map((c) => (
                    <option key={c.id} value={c.id}>
                      [{c.category}] {c.name}
                    </option>
                  ))}
                </select>
              </div>

              <button
                className="btn-primary"
                onClick={() => selectedConcernId && executeSearch(selectedConcernId)}
              >
                <Search size={16} /> Re-Run Match
              </button>
            </div>

            {/* Criteria Banner */}
            {currentConcern && (
              <div className="criteria-banner">
                <div>
                  <div className="criteria-title">
                    {currentConcern.name} &bull; {currentConcern.reporting_period}
                  </div>
                  <div className="criteria-desc">
                    <strong>Search Criteria:</strong> {currentConcern.description}
                  </div>
                </div>
                <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                  <span className="criteria-badge">{currentConcern.search_method}</span>
                  {currentConcern.requires_secondary_assessment && (
                    <span className="badge badge-needs-review">2-Level Assessment</span>
                  )}
                </div>
              </div>
            )}

            {/* Metrics Cards */}
            <div className="metrics-grid">
              <div className="metric-card">
                <div className="metric-card-title">Candidate Events</div>
                <div className="metric-card-value" style={{ color: "#2563eb" }}>
                  {searchSummary?.total_event_matches || 0}
                </div>
                <div className="metric-card-sub">Exploded line-listing matches</div>
              </div>
              <div className="metric-card">
                <div className="metric-card-title">Distinct Candidate Cases</div>
                <div className="metric-card-value" style={{ color: "#0f172a" }}>
                  {searchSummary?.distinct_candidate_cases || 0}
                </div>
                <div className="metric-card-sub">De-duplicated Case Numbers</div>
              </div>
              <div className="metric-card">
                <div className="metric-card-title">Confirmed Relevant</div>
                <div className="metric-card-value" style={{ color: "#059669" }}>
                  {searchSummary?.relevant_cases_count || 0}
                </div>
                <div className="metric-card-sub">Included in Section 16.3</div>
              </div>
              <div className="metric-card">
                <div className="metric-card-title">Excluded (Not Relevant)</div>
                <div className="metric-card-value" style={{ color: "#64748b" }}>
                  {searchSummary?.not_relevant_cases_count || 0}
                </div>
                <div className="metric-card-sub">With clinical justification</div>
              </div>
              <div className="metric-card">
                <div className="metric-card-title">Needs Review / Pending</div>
                <div className="metric-card-value" style={{ color: "#d97706" }}>
                  {(searchSummary?.needs_review_cases_count || 0) + (searchSummary?.candidate_pending_count || 0)}
                </div>
                <div className="metric-card-sub">Awaiting assessment</div>
              </div>
            </div>

            {/* Candidate Cases Data Table */}
            <div className="table-card">
              <div className="table-header-bar">
                <div className="table-title">
                  Candidate Cases ({filteredCases.length} of {searchSummary?.distinct_candidate_cases || 0})
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <Filter size={16} color="#64748b" />
                  <input
                    type="text"
                    className="table-filter-input"
                    placeholder="Filter cases, country, terms..."
                    value={filterText}
                    onChange={(e) => setFilterText(e.target.value)}
                  />
                </div>
              </div>

              {loading ? (
                <div style={{ padding: "3rem", textAlign: "center", color: "#64748b" }}>
                  Executing deterministic lookup against normalized store...
                </div>
              ) : filteredCases.length === 0 ? (
                <div style={{ padding: "3rem", textAlign: "center", color: "#64748b" }}>
                  No candidate cases matched the configured criteria for this reporting period.
                </div>
              ) : (
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Case Number</th>
                      <th>Country</th>
                      <th>Report Type</th>
                      <th>Seriousness</th>
                      <th>Outcome</th>
                      <th>Matched Event(s)</th>
                      <th>Match Reason & Evidence</th>
                      <th>Assessment</th>
                      <th style={{ textAlign: "right" }}>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredCases.map((c) => (
                      <tr key={c.case_number}>
                        <td>
                          <span
                            className="case-link"
                            onClick={() => setSelectedCaseForReview(c.case_number)}
                          >
                            {c.case_number}
                          </span>
                        </td>
                        <td>{c.country}</td>
                        <td>{c.report_type}</td>
                        <td>
                          {c.is_serious ? (
                            <span className="badge badge-serious">Serious</span>
                          ) : (
                            <span style={{ color: "#64748b" }}>Non-Serious</span>
                          )}
                        </td>
                        <td>{c.outcome || "Unknown"}</td>
                        <td>
                          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.25rem" }}>
                            {c.matches.map((m, idx) => (
                              <span key={idx} className="evidence-tag">
                                {m.matched_term}
                              </span>
                            ))}
                          </div>
                        </td>
                        <td>
                          <span style={{ fontSize: "0.78rem", color: "#475569" }}>
                            {c.matches[0]?.reference_source}
                          </span>
                        </td>
                        <td>
                          <span
                            className={`badge ${
                              c.assessment_status === "RELEVANT"
                                ? "badge-relevant"
                                : c.assessment_status === "NOT_RELEVANT"
                                ? "badge-not-relevant"
                                : c.assessment_status === "NEEDS_REVIEW"
                                ? "badge-needs-review"
                                : "badge-candidate"
                            }`}
                          >
                            {c.assessment_status}
                          </span>
                        </td>
                        <td style={{ textAlign: "right" }}>
                          <button
                            className="btn-secondary"
                            style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem" }}
                            onClick={() => setSelectedCaseForReview(c.case_number)}
                          >
                            Review <ChevronRight size={14} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </>
        )}
      </main>

      {/* Case Review Modal */}
      {selectedCaseForReview && (
        <CaseDetailModal
          caseNumber={selectedCaseForReview}
          concernId={selectedConcernId}
          onClose={() => setSelectedCaseForReview(null)}
          onAssessmentUpdated={handleAssessmentUpdated}
        />
      )}
    </div>
  );
}
export default App;
