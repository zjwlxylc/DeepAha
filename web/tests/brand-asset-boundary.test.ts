import { describe, expect, it } from "vitest";

import { GET } from "../app/favicon.ico/route";


describe("favicon brand-asset boundary", () => {
  it("does not ship the watermarked raster or an invented replacement", () => {
    const response = GET();

    expect(response.status).toBe(204);
    expect(response.headers.get("X-DeepAha-Brand-Asset")).toBe("pending-clean-approved-icon");
  });
});
