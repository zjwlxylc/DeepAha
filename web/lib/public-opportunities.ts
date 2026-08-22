export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

export type SearchParams = Record<string, string | string[] | undefined>;

export interface PublicOpportunityCard {
  public_id: string;
  title: string;
  type: string;
  jurisdiction: string;
  locations: string[];
  issuer_name: string;
  status: string;
  published_at: string;
  deadline: string;
  last_verified_at: string;
  change_markers: string[];
  data_label: "REAL_GOLD" | "LICENSE_SAFE_FIXTURE";
}

export interface PublicOpportunityPage {
  items: PublicOpportunityCard[];
  next_cursor: string | null;
  count: number;
  data_labels: Array<"REAL_GOLD" | "LICENSE_SAFE_FIXTURE">;
  reproduced_at: string | null;
}

export interface PublicEvidence {
  field_path: string;
  evidence_ref_id: string;
  document_id: string;
  locator_kind: string;
  locator_value: string | null;
  locator_payload: Record<string, JsonValue> | null;
  quote_sha256: string | null;
  precedence: number;
  authority: string;
  official_url: string;
}

export interface PublicFieldChange {
  field_path: string;
  before: JsonValue;
  after: JsonValue;
}

export interface PublicHistoryEvent {
  event_id: string;
  from_version: number | null;
  to_version: number;
  event_type: string;
  changed_fields: string[];
  changes: PublicFieldChange[];
  detected_at: string;
  evidence_ref_id: string;
  document_id: string;
  official_url: string;
}

export interface PublicOpportunityDetail extends PublicOpportunityCard {
  current_version: number;
  application_url: string;
  attachment_urls: string[];
  key_evidence: PublicEvidence[];
  history: PublicHistoryEvent[];
  personalization_availability: "AVAILABLE_WITH_PERSONAL_SESSION";
}

export class PublicApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "PublicApiError";
  }
}

const queryKeys = ["q", "type", "status", "region", "sort", "cursor", "limit"] as const;

function firstValue(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export function normalizedSearchParams(searchParams: SearchParams): Record<string, string> {
  const result: Record<string, string> = {};
  for (const key of queryKeys) {
    const value = firstValue(searchParams[key]);
    if (value) {
      result[key] = value;
    }
  }
  return result;
}

export function opportunitiesHref(
  searchParams: Record<string, string>,
  cursor?: string | null,
): string {
  const values = new URLSearchParams(searchParams);
  if (cursor) {
    values.set("cursor", cursor);
  } else {
    values.delete("cursor");
  }
  const query = values.toString();
  return query ? `/opportunities?${query}` : "/opportunities";
}

async function fetchPublicJson<T>(path: string): Promise<T> {
  const baseUrl = process.env.DEEPAHA_API_BASE_URL ?? "http://127.0.0.1:8000";
  const response = await fetch(new URL(path, baseUrl), {
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new PublicApiError(response.status, "Public opportunity request failed");
  }
  return (await response.json()) as T;
}

export async function listPublicOpportunities(
  searchParams: Record<string, string>,
): Promise<PublicOpportunityPage> {
  const query = new URLSearchParams(searchParams).toString();
  return fetchPublicJson<PublicOpportunityPage>(
    `/api/v1/public/opportunities${query ? `?${query}` : ""}`,
  );
}

export async function getPublicOpportunity(publicId: string): Promise<PublicOpportunityDetail> {
  return fetchPublicJson<PublicOpportunityDetail>(
    `/api/v1/public/opportunities/${encodeURIComponent(publicId)}`,
  );
}

export function formatDate(value: string): string {
  return value;
}

export function formatDateTime(value: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Shanghai",
  }).formatToParts(new Date(value));
  const fields = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${fields.year}-${fields.month}-${fields.day} ${fields.hour}:${fields.minute}`;
}
