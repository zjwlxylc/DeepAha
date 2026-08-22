"use server";

import { randomUUID } from "node:crypto";

import { revalidatePath } from "next/cache";

import { setDeadlineReminderPreference } from "../lib/reminders";

export async function toggleDeadlineReminderAction(formData: FormData): Promise<void> {
  const keys = [...formData.keys()].filter((key) => !key.startsWith("$ACTION_"));
  if (keys.some((key) => key !== "enabled") || keys.filter((key) => key === "enabled").length > 1) {
    throw new Error("Invalid reminder preference form");
  }
  const rawEnabled = formData.get("enabled");
  const enabled = rawEnabled === "true" || rawEnabled === "on";
  await setDeadlineReminderPreference(enabled, randomUUID());
  revalidatePath("/me/reminders");
}
