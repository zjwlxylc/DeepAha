import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import RootLayout from "../app/layout";


describe("root layout browser contract", () => {
  it("declares intentional smooth scrolling for Next route transitions", () => {
    const markup = renderToStaticMarkup(
      <RootLayout>
        <main id="main-content">content</main>
      </RootLayout>,
    );

    expect(markup).toContain('data-scroll-behavior="smooth"');
  });
});
