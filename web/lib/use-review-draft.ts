"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { clearReviewDraft, readReviewDraft, saveReviewDraft } from "./review-draft-state";

export function useReviewDraft(scope: string | null, initialKey: string, committed: boolean) {
  const ref = useRef<HTMLFormElement>(null);
  const setForm = useCallback((form: HTMLFormElement | null) => { ref.current = form; }, []);
  const [requestKey] = useState(() => scope ? readReviewDraft(scope)?.requestKey ?? initialKey : initialKey);
  useEffect(() => {
    const form = ref.current;
    if (!scope || !form) return;
    if (committed) { clearReviewDraft(scope); return; }
    const controls = () => Array.from(form.querySelectorAll<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>("input[name],select[name],textarea[name]"))
      .filter(control => control.type !== "hidden" && control.type !== "password" && control.type !== "file");
    const saved = readReviewDraft(scope);
    if (saved) for (const control of controls()) {
      const values = saved.values[control.name];
      if (!values) continue;
      if (control instanceof HTMLInputElement && ["checkbox", "radio"].includes(control.type)) control.checked = values.includes(control.value);
      else control.value = values[0] ?? "";
    }
    let dirty = !!saved;
    const capture = () => {
      const values: Record<string, string[]> = {};
      for (const control of controls()) {
        values[control.name] ??= [];
        if (control instanceof HTMLInputElement && ["checkbox", "radio"].includes(control.type) && !control.checked) continue;
        values[control.name].push(control.value);
      }
      dirty = true;
      saveReviewDraft(scope, { requestKey, values });
    };
    const leaving = (event: BeforeUnloadEvent) => { if (dirty) { event.preventDefault(); event.returnValue = ""; } };
    form.addEventListener("input", capture);
    form.addEventListener("change", capture);
    window.addEventListener("beforeunload", leaving);
    return () => {
      form.removeEventListener("input", capture);
      form.removeEventListener("change", capture);
      window.removeEventListener("beforeunload", leaving);
    };
  }, [scope, requestKey, committed]);
  return { ref: setForm, requestKey };
}
