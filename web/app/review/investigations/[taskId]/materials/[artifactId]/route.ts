import { cookies } from "next/headers";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function unavailable(status: number): Response {
  return new Response("原件暂不可下载，请确认审核权限和材料状态。", {
    status, headers: { "Cache-Control": "private, no-store", "Content-Type": "text/plain; charset=utf-8" },
  });
}

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ taskId: string; artifactId: string }> },
): Promise<Response> {
  const token = (await cookies()).get("deepaha_phase7_reviewer_session")?.value;
  if (!token) return unavailable(401);
  const { taskId, artifactId } = await params;
  if (!UUID.test(taskId) || !artifactId || artifactId.length > 256 || /[/\\\x00-\x1f]/.test(artifactId) || [".", ".."].includes(artifactId)) return unavailable(400);
  const baseUrl = process.env.DEEPAHA_API_BASE_URL ?? "http://127.0.0.1:8000";
  try {
    const response = await fetch(new URL(`/api/v1/local-human-test/investigations/${encodeURIComponent(taskId)}/materials/${encodeURIComponent(artifactId)}`, baseUrl), {
      headers: { Authorization: `Bearer ${token}`, Accept: "application/octet-stream" },
      cache: "no-store", redirect: "error",
    });
    if (!response.ok) return unavailable([401, 403, 404].includes(response.status) ? response.status : 502);
    const filename = /^attachment; filename="(original-[0-9a-f]{16}\.(?:pdf|doc|docx|xls|xlsx|html|txt|png|jpg|bin))"$/.exec(
      response.headers.get("Content-Disposition") ?? "",
    )?.[1] ?? "original.bin";
    return new Response(response.body, { headers: {
      "Content-Type": "application/octet-stream",
      "Content-Disposition": `attachment; filename="${filename}"`,
      "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
      "Content-Security-Policy": "sandbox; default-src 'none'",
    } });
  } catch { return unavailable(502); }
}
