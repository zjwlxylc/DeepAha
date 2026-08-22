"use server";

import { randomBytes, randomUUID } from "node:crypto";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import {
  personalFetch,
  type OfficialLinkResult,
  type PersonalActionSnapshot,
  type PersonalOpportunityDetail,
  type UserStateSnapshot,
} from "../lib/personal-opportunities";

function text(formData: FormData, key: string): string {
  return String(formData.get(key) ?? "").trim();
}

function optionalText(formData: FormData, key: string): string | null {
  return text(formData, key) || null;
}

function todayInShanghai(): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
  }).format(new Date());
}

function safeReturnTo(value: string): string {
  return value.startsWith("/") && !value.startsWith("//") ? value : "/me/opportunities";
}

function uuid7(): string {
  const bytes = randomBytes(16);
  const timestamp = Date.now();
  for (let index = 5; index >= 0; index -= 1) {
    bytes[index] = Math.floor(timestamp / 2 ** ((5 - index) * 8)) & 0xff;
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x70;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = bytes.toString("hex");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export async function saveProfileAction(formData: FormData): Promise<never> {
  const majorName = optionalText(formData, "major_name");
  const majorCode = optionalText(formData, "major_code");
  const educationLevel = optionalText(formData, "education_level");
  const graduationYear = optionalText(formData, "graduation_year");
  const studentStatus = optionalText(formData, "student_status");
  const residenceRegion = optionalText(formData, "residence_region");
  const skipped = ["birth_date", "certificates", "hukou_region", "target_regions"];
  if (formData.get("skip_major") || (!majorName && !majorCode)) {
    skipped.push("major_name", "major_code");
  }
  if (!educationLevel) skipped.push("education_level");
  if (!graduationYear) skipped.push("graduation_year");
  if (!studentStatus) skipped.push("student_status");
  if (!residenceRegion) skipped.push("residence_region");
  const preferenceRegion = optionalText(formData, "preference_region");
  const preferenceType = optionalText(formData, "preference_type");
  const body = {
    life_stage: optionalText(formData, "life_stage"),
    goal_types: text(formData, "goal_type") ? [text(formData, "goal_type")] : [],
    attributes: {
      education_level: educationLevel,
      major_name: skipped.includes("major_name") ? null : majorName,
      major_code: skipped.includes("major_code") ? null : majorCode,
      graduation_year: graduationYear ? Number(graduationYear) : null,
      student_status: studentStatus,
      birth_date: null,
      hukou_region: null,
      residence_region: residenceRegion,
      target_regions: null,
      certificates: null,
    },
    preference_regions: preferenceRegion ? [preferenceRegion] : [],
    preference_types: preferenceType ? [preferenceType] : [],
    skipped_fields: skipped,
    personalization_enabled: formData.get("personalization_enabled") === "on",
    consent_version: "phase6-consent-v1",
    allowed_purposes: ["ACTION_TRACKING", "ELIGIBILITY", "PERSONAL_RANKING"],
    scenario_clock: todayInShanghai(),
  };
  await personalFetch<UserStateSnapshot>("/api/v1/me/profile", {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": randomUUID(),
    },
    body: JSON.stringify(body),
  });
  await personalFetch("/api/v1/me/matches", { method: "POST" });
  revalidatePath("/me/opportunities");
  redirect(safeReturnTo(text(formData, "return_to")));
}

export async function toggleSavedAction(formData: FormData): Promise<void> {
  const publicId = text(formData, "public_id");
  await personalFetch<PersonalActionSnapshot>(
    `/api/v1/me/opportunities/${encodeURIComponent(publicId)}/saved`,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": randomUUID(),
      },
      body: JSON.stringify({ saved: text(formData, "saved") === "true" }),
    },
  );
  revalidatePath(`/me/opportunities/${publicId}`);
}

export async function setActionStatusAction(formData: FormData): Promise<void> {
  const publicId = text(formData, "public_id");
  await personalFetch<PersonalActionSnapshot>(
    `/api/v1/me/opportunities/${encodeURIComponent(publicId)}/status`,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": randomUUID(),
      },
      body: JSON.stringify({ state: text(formData, "state") }),
    },
  );
  revalidatePath(`/me/opportunities/${publicId}`);
}

export async function addMaterialAction(formData: FormData): Promise<void> {
  const publicId = text(formData, "public_id");
  const label = text(formData, "material_label");
  if (!label) return;
  const current = await personalFetch<PersonalOpportunityDetail>(
    `/api/v1/me/opportunities/${encodeURIComponent(publicId)}`,
  );
  await personalFetch<PersonalActionSnapshot>(
    `/api/v1/me/opportunities/${encodeURIComponent(publicId)}/materials`,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": randomUUID(),
      },
      body: JSON.stringify({
        items: [
          ...(current.action?.material_items ?? []),
          {
            material_item_id: uuid7(),
            label,
            completed: false,
            due_on: optionalText(formData, "material_due_on"),
          },
        ],
      }),
    },
  );
  revalidatePath(`/me/opportunities/${publicId}`);
}

export async function openOfficialLinkAction(formData: FormData): Promise<never> {
  const publicId = text(formData, "public_id");
  const result = await personalFetch<OfficialLinkResult>(
    `/api/v1/me/opportunities/${encodeURIComponent(publicId)}/official-link`,
    { method: "POST", headers: { "Idempotency-Key": randomUUID() } },
  );
  redirect(result.official_url);
}
