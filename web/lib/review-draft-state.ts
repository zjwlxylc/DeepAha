// Window memory only: never localStorage, cookies, or cross-session persistence.
export interface ReviewDraft { requestKey: string; values: Record<string, string[]> }
const drafts = new Map<string, ReviewDraft>();
export function readReviewDraft(scope: string): ReviewDraft | undefined { return drafts.get(scope); }
export function saveReviewDraft(scope: string, draft: ReviewDraft): void {
  drafts.delete(scope);
  drafts.set(scope, draft);
  if (drafts.size > 100) drafts.delete(drafts.keys().next().value!);
}
export function clearReviewDraft(scope: string): void { drafts.delete(scope); }
