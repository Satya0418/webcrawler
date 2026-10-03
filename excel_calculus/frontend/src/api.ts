import type { SafetyConcern, SearchSummary, CaseDetail, IngestionStatus, UploadResult, Section161ReportData } from "./types";

const API_BASE = "http://localhost:8000/api";

export async function fetchSection161Report(product: string = "Abiraterone"): Promise<Section161ReportData> {
  const res = await fetch(`${API_BASE}/reports/section-16-1?product=${encodeURIComponent(product)}`);
  if (!res.ok) throw new Error("Failed to fetch Section 16.1 report");
  return res.json();
}

export async function fetchIngestionStatus(): Promise<IngestionStatus> {
  const res = await fetch(`${API_BASE}/ingestion/status`);
  if (!res.ok) throw new Error("Failed to fetch ingestion status");
  return res.json();
}

export async function uploadWorkbookFile(
  file: File,
  productName?: string,
  fileType: string = "auto"
): Promise<UploadResult> {
  const formData = new FormData();
  formData.append("file", file);
  if (productName && productName.trim()) {
    formData.append("product_name", productName.trim());
  }
  formData.append("file_type", fileType);

  const res = await fetch(`${API_BASE}/ingestion/upload`, {
    method: "POST",
    body: formData
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Upload failed" }));
    throw new Error(err.detail || "Failed to upload and ingest workbook");
  }
  return res.json();
}

export async function fetchSafetyConcerns(product?: string): Promise<SafetyConcern[]> {
  const url = product ? `${API_BASE}/concerns?product=${encodeURIComponent(product)}` : `${API_BASE}/concerns`;
  const res = await fetch(url);
  if (!res.ok) throw new Error("Failed to fetch safety concerns");
  return res.json();
}

export async function runConcernSearch(concernId: string, reviewer = "reviewer"): Promise<SearchSummary> {
  const res = await fetch(`${API_BASE}/search/${concernId}?reviewer=${encodeURIComponent(reviewer)}`, {
    method: "POST"
  });
  if (!res.ok) throw new Error("Failed to run concern search");
  return res.json();
}

export async function fetchSearchSummary(concernId: string): Promise<SearchSummary> {
  const res = await fetch(`${API_BASE}/search/${concernId}`);
  if (!res.ok) throw new Error("Failed to fetch search summary");
  return res.json();
}

export async function fetchCaseDetail(caseNumber: string, concernId?: string): Promise<CaseDetail> {
  const url = concernId 
    ? `${API_BASE}/cases/${encodeURIComponent(caseNumber)}?concern_id=${encodeURIComponent(concernId)}`
    : `${API_BASE}/cases/${encodeURIComponent(caseNumber)}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch case ${caseNumber}`);
  return res.json();
}

export async function updateAssessment(data: {
  case_number: string;
  concern_id: string;
  status: string;
  exclusion_reason?: string | null;
  reviewer_notes?: string | null;
  secondary_result?: string | null;
  reviewer_id?: string;
}) {
  const res = await fetch(`${API_BASE}/assessment`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data)
  });
  if (!res.ok) throw new Error("Failed to update assessment");
  return res.json();
}

export function getSection161PdfUrl(product: string = "Abiraterone", preview: boolean = false): string {
  return `${API_BASE}/reports/section-16-1/pdf?product=${encodeURIComponent(product)}&preview=${preview}`;
}

