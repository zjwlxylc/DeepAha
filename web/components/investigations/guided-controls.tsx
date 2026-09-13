"use client";

import { useEffect, useState } from "react";
import { clearReviewDraft, readReviewDraft, saveReviewDraft } from "../../lib/review-draft-state";

export function useGuidedAnswers(scope: string | null, initialKey: string, committed: boolean) {
  const [key] = useState(() => scope ? readReviewDraft(scope)?.requestKey ?? initialKey : initialKey);
  const [answers, setAnswers] = useState<Record<string, string>>(() => {
    const values = scope ? readReviewDraft(scope)?.values : undefined;
    return values ? Object.fromEntries(Object.entries(values).map(([k, v]) => [k, v[0] ?? ""])) : {};
  });
  const change = (name: string, value: string) => {
    const next = { ...answers, [name]: value };
    setAnswers(next);
    if (scope) saveReviewDraft(scope, { requestKey: key, values: Object.fromEntries(Object.entries(next).map(([k, v]) => [k, [v]])) });
  };
  useEffect(() => {
    if (committed) { if (scope) clearReviewDraft(scope); return; }
    const leave = (event: BeforeUnloadEvent) => { if (Object.keys(answers).length) { event.preventDefault(); event.returnValue = ""; } };
    window.addEventListener("beforeunload", leave);
    return () => window.removeEventListener("beforeunload", leave);
  }, [scope, answers, committed]);
  const reset = () => { setAnswers({}); if (scope) clearReviewDraft(scope); };
  return { answers, change, reset, requestKey: key };
}

export function Question({ title, name, value, choices, onChange }: { title: string; name: string; value?: string; choices: [string, string][]; onChange: (name: string, value: string) => void }) {
  return <fieldset className="guided-question"><legend tabIndex={-1} data-guided-question>{title}</legend><p className="field-help">选择后显示下一步；保存前可以重新回答。</p>{choices.map(([id, label]) => <label className="guided-choice" key={id}><input type="radio" name={name} value={id} checked={value === id} onChange={event => {
    const form = event.currentTarget.form;
    onChange(name, id);
    requestAnimationFrame(() => form?.querySelector<HTMLElement>("[data-guided-question], button[type=submit]")?.focus());
  }} /><span>{label}</span></label>)}</fieldset>;
}

export function Hidden({ values }: { values: Record<string, string | undefined | null> }) {
  return <>{Object.entries(values).map(([name, value]) => <input key={name} type="hidden" name={name} value={value ?? ""} />)}</>;
}
