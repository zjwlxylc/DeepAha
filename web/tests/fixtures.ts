import type { PublicOpportunityDetail, PublicOpportunityPage } from "../lib/public-opportunities";

export const publicId = "opp_0123456789abcdef0123456789abcdef";

export const publicPage: PublicOpportunityPage = {
  items: [
    {
      public_id: publicId,
      title: "合成青年人才补贴计划",
      type: "YOUTH_POLICY_BENEFIT",
      jurisdiction: "合成浙江省",
      locations: ["合成杭州市"],
      issuer_name: "合成浙江公共服务机构",
      status: "OPEN",
      published_at: "2026-08-20T01:00:00Z",
      deadline: "2026-09-20",
      last_verified_at: "2026-08-22T01:00:00Z",
      change_markers: ["DEADLINE_CHANGED"],
      data_label: "LICENSE_SAFE_FIXTURE",
    },
  ],
  next_cursor: "next-cursor",
  count: 1,
  data_labels: ["LICENSE_SAFE_FIXTURE"],
  reproduced_at: "2026-08-22T01:00:00Z",
};

export const publicDetail: PublicOpportunityDetail = {
  ...publicPage.items[0],
  current_version: 2,
  application_url: "https://phase5-fixture.example.test/alpha/apply",
  attachment_urls: ["https://phase5-fixture.example.test/alpha/conditions.pdf"],
  key_evidence: [
    {
      field_path: "application_url",
      evidence_ref_id: "019d0000-0000-7000-8000-000000000001",
      document_id: "019d0000-0000-7000-8000-000000000002",
      locator_kind: "html_selector",
      locator_value: null,
      locator_payload: {
        schema_version: "0.2.0",
        kind: "html_selector",
        selector: "main article",
        text_sha256: "1".repeat(64),
      },
      quote_sha256: "1".repeat(64),
      precedence: 400,
      authority: "ORIGINAL_OFFICIAL_NOTICE",
      official_url: "https://phase5-fixture.example.test/alpha/notice-v2",
    },
  ],
  history: [
    {
      event_id: "019d0000-0000-7000-8000-000000000003",
      from_version: 1,
      to_version: 2,
      event_type: "DEADLINE_CHANGED",
      changed_fields: ["application_window.closes_on"],
      changes: [
        {
          field_path: "application_window.closes_on",
          before: "2026-09-10",
          after: "2026-09-20",
        },
      ],
      detected_at: "2026-08-21T03:00:00Z",
      evidence_ref_id: "019d0000-0000-7000-8000-000000000001",
      document_id: "019d0000-0000-7000-8000-000000000002",
      official_url: "https://phase5-fixture.example.test/alpha/notice-v2",
    },
  ],
  personalization_availability: "AVAILABLE_WITH_PERSONAL_SESSION",
};
