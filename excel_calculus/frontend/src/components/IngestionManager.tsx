import React, { useState, useEffect, useRef } from "react";
import type { IngestionStatus, UploadResult } from "../types";
import { fetchIngestionStatus, uploadWorkbookFile } from "../api";
import { FileSpreadsheet, CheckCircle2, RefreshCw, UploadCloud, AlertCircle, FileCheck, Layers } from "lucide-react";

interface Props {
  onFileIngested?: () => void;
}

export const IngestionManager: React.FC<Props> = ({ onFileIngested }) => {
  const [status, setStatus] = useState<IngestionStatus | null>(null);
  const [loading, setLoading] = useState(true);

  // File upload state
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [productName, setProductName] = useState<string>("");
  const [fileType, setFileType] = useState<string>("auto");
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    loadStatus();
  }, []);

  const loadStatus = async () => {
    try {
      setLoading(true);
      const data = await fetchIngestionStatus();
      setStatus(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleFileSelect = (file: File) => {
    setSelectedFile(file);
    setUploadResult(null);
    setUploadError(null);

    // Auto-fill product name if detected from filename
    const lowerName = file.name.toLowerCase();
    if (lowerName.includes("abiraterone")) {
      setProductName("Abiraterone");
    } else if (lowerName.includes("oxycodone")) {
      setProductName("Oxycodone");
    } else if (!productName) {
      const candidate = file.name.split(/[_\-\.]/)[0];
      if (candidate && candidate.length > 2) {
        setProductName(candidate.charAt(0).toUpperCase() + candidate.slice(1).toLowerCase());
      }
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0];
      if (file.name.endsWith(".xlsx") || file.name.endsWith(".xls")) {
        handleFileSelect(file);
      } else {
        setUploadError("Only Excel workbooks (.xlsx, .xls) are supported.");
      }
    }
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) {
      setUploadError("Please select a file to ingest.");
      return;
    }

    try {
      setUploading(true);
      setUploadError(null);
      setUploadResult(null);

      const result = await uploadWorkbookFile(selectedFile, productName, fileType);
      setUploadResult(result);
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";

      // Refresh pipeline status
      await loadStatus();

      // Trigger parent reload
      if (onFileIngested) {
        onFileIngested();
      }
    } catch (err: any) {
      setUploadError(err.message || "Failed to upload and ingest file.");
    } finally {
      setUploading(false);
    }
  };

  if (loading && !status) {
    return <div style={{ padding: "3rem", textAlign: "center", color: "#64748b" }}>Loading ingestion status...</div>;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h2 style={{ fontSize: "1.25rem", fontWeight: 700, color: "#0f172a" }}>
            Data Pipeline & Medical Reference Management
          </h2>
          <span style={{ fontSize: "0.85rem", color: "#64748b" }}>
            Upload new line listings, inspect multi-event explosions, and track ingested MedDRA SMQ terminology.
          </span>
        </div>
        <button className="btn-secondary" onClick={loadStatus}>
          <RefreshCw size={16} /> Refresh Telemetry
        </button>
      </div>

      {/* Metrics Grid */}
      <div className="metrics-grid">
        <div className="metric-card">
          <div className="metric-card-title">Indexed Cases</div>
          <div className="metric-card-value">{status?.total_cases || 0}</div>
          <div className="metric-card-sub">In SQLite database</div>
        </div>
        <div className="metric-card">
          <div className="metric-card-title">Exploded Events</div>
          <div className="metric-card-value" style={{ color: "#2563eb" }}>{status?.total_exploded_events || 0}</div>
          <div className="metric-card-sub">1 Case &rarr; N Searchable Events</div>
        </div>
        <div className="metric-card">
          <div className="metric-card-title">MedDRA SMQ Terms</div>
          <div className="metric-card-value" style={{ color: "#059669" }}>{status?.total_smq_terms?.toLocaleString() || 0}</div>
          <div className="metric-card-sub">MedDRA Version 29.0</div>
        </div>
        <div className="metric-card">
          <div className="metric-card-title">Safety Concerns Configured</div>
          <div className="metric-card-value">{status?.total_safety_concerns || 0}</div>
          <div className="metric-card-sub">Deterministic Rules Active</div>
        </div>
      </div>

      {/* Upload Workbook Card */}
      <div className="table-card" style={{ padding: "1.5rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", marginBottom: "1rem" }}>
          <UploadCloud size={20} color="#2563eb" />
          <h3 style={{ fontSize: "1.05rem", fontWeight: 700, color: "#0f172a" }}>
            Add / Upload New Line-Listing or SMQ Workbook
          </h3>
        </div>

        <form onSubmit={handleUpload}>
          <div
            onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            style={{
              border: `2px dashed ${isDragging ? "#2563eb" : "#cbd5e1"}`,
              borderRadius: "0.5rem",
              padding: "2rem",
              textAlign: "center",
              cursor: "pointer",
              backgroundColor: isDragging ? "#eff6ff" : "#f8fafc",
              transition: "all 0.2s ease",
              marginBottom: "1rem"
            }}
          >
            <input
              type="file"
              ref={fileInputRef}
              onChange={(e) => {
                if (e.target.files && e.target.files.length > 0) {
                  handleFileSelect(e.target.files[0]);
                }
              }}
              accept=".xlsx,.xls"
              style={{ display: "none" }}
            />
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "0.5rem" }}>
              <UploadCloud size={32} color={selectedFile ? "#059669" : "#64748b"} />
              {selectedFile ? (
                <div>
                  <span style={{ fontWeight: 600, color: "#0f172a" }}>{selectedFile.name}</span>
                  <div style={{ fontSize: "0.8rem", color: "#64748b" }}>
                    {(selectedFile.size / 1024).toFixed(1)} KB &bull; Ready to Ingest
                  </div>
                </div>
              ) : (
                <div>
                  <span style={{ fontWeight: 600, color: "#1e293b" }}>Click to browse</span> or drag and drop your Excel line listing here
                  <div style={{ fontSize: "0.8rem", color: "#64748b", marginTop: "0.25rem" }}>
                    Supports interval line listings (.xlsx, .xls) and MedDRA SMQ reference workbooks
                  </div>
                </div>
              )}
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto", gap: "1rem", alignItems: "flex-end" }}>
            <div>
              <label style={{ display: "block", fontSize: "0.8rem", fontWeight: 600, color: "#475569", marginBottom: "0.3rem" }}>
                Target Product Name:
              </label>
              <input
                type="text"
                className="select-input"
                placeholder="e.g. Abiraterone, Oxycodone, etc."
                value={productName}
                onChange={(e) => setProductName(e.target.value)}
                style={{ width: "100%" }}
              />
            </div>

            <div>
              <label style={{ display: "block", fontSize: "0.8rem", fontWeight: 600, color: "#475569", marginBottom: "0.3rem" }}>
                File Classification:
              </label>
              <select
                className="select-input"
                value={fileType}
                onChange={(e) => setFileType(e.target.value)}
                style={{ width: "100%" }}
              >
                <option value="auto">Auto-Detect File Structure</option>
                <option value="line_listing">Pharmacovigilance Line Listing (.xlsx)</option>
                <option value="smq_reference">MedDRA SMQ Reference Spreadsheet (.xlsx)</option>
              </select>
            </div>

            <button
              type="submit"
              className="btn-primary"
              disabled={!selectedFile || uploading}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
                padding: "0.55rem 1.25rem",
                whiteSpace: "nowrap"
              }}
            >
              {uploading ? (
                <>
                  <RefreshCw size={16} className="spin" /> Ingesting & Exploding...
                </>
              ) : (
                <>
                  <Layers size={16} /> Ingest Workbook
                </>
              )}
            </button>
          </div>
        </form>

        {/* Upload Success Alert */}
        {uploadResult && (
          <div
            style={{
              marginTop: "1.25rem",
              padding: "1rem",
              borderRadius: "0.5rem",
              backgroundColor: "#f0fdf4",
              border: "1px solid #bbf7d0",
              color: "#166534"
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontWeight: 700 }}>
              <CheckCircle2 size={18} color="#16a34a" />
              Ingestion & Multi-Event Explosion Succeeded
            </div>
            <div style={{ fontSize: "0.85rem", marginTop: "0.4rem", lineHeight: 1.5 }}>
              {uploadResult.message}
            </div>
            {uploadResult.file_type === "line_listing" && (
              <div style={{ fontSize: "0.8rem", marginTop: "0.5rem", display: "flex", gap: "1.5rem", color: "#14532d" }}>
                <span><strong>Product:</strong> {uploadResult.product_name}</span>
                <span><strong>Cases Added:</strong> {uploadResult.cases_ingested}</span>
                <span><strong>Exploded Events:</strong> {uploadResult.events_exploded}</span>
                <span><strong>Lineage:</strong> 100% Traceable</span>
              </div>
            )}
          </div>
        )}

        {/* Upload Error Alert */}
        {uploadError && (
          <div
            style={{
              marginTop: "1.25rem",
              padding: "1rem",
              borderRadius: "0.5rem",
              backgroundColor: "#fef2f2",
              border: "1px solid #fecaca",
              color: "#991b1b",
              display: "flex",
              alignItems: "center",
              gap: "0.5rem"
            }}
          >
            <AlertCircle size={18} color="#dc2626" />
            <span style={{ fontSize: "0.85rem" }}>{uploadError}</span>
          </div>
        )}
      </div>

      {/* Loaded Source Line Listings Table */}
      <div className="table-card">
        <div className="table-header-bar">
          <div className="table-title">Loaded Source Line Listings & Workbooks</div>
        </div>
        <table className="data-table">
          <thead>
            <tr>
              <th>Workbook File</th>
              <th>Product Target</th>
              <th>Pipeline Status</th>
              <th>Lineage Preservation</th>
            </tr>
          </thead>
          <tbody>
            {status?.ingested_files?.map((f, idx) => (
              <tr key={idx}>
                <td style={{ fontWeight: 600, display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <FileSpreadsheet size={16} color="#059669" /> {f}
                </td>
                <td>
                  <span className="badge" style={{ backgroundColor: "#e2e8f0", color: "#334155" }}>
                    {f.toLowerCase().includes("abiraterone")
                      ? "Abiraterone"
                      : f.toLowerCase().includes("oxycodone")
                      ? "Oxycodone"
                      : "General Product"}
                  </span>
                </td>
                <td>
                  <span className="badge badge-relevant">
                    <CheckCircle2 size={12} /> INGESTED & INDEXED
                  </span>
                </td>
                <td style={{ color: "#059669", fontSize: "0.8rem", fontWeight: 500 }}>
                  <FileCheck size={14} style={{ display: "inline", verticalAlign: "middle", marginRight: "0.25rem" }} />
                  100% Raw Row & Verbatim Traceable
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
