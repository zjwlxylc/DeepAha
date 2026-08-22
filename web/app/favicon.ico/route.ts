export function GET(): Response {
  return new Response(null, {
    status: 204,
    headers: {
      "Cache-Control": "public, max-age=86400",
      "X-DeepAha-Brand-Asset": "pending-clean-approved-icon",
    },
  });
}
