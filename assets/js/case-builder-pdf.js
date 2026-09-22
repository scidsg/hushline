import { PDF, layoutText } from "@libpdf/core";
import fontUrl from "../fonts/sans/AtkinsonHyperlegible-Regular.ttf";

export async function createProtectedCasePdf(text, password) {
  if (
    [...password].length < 12 ||
    new TextEncoder().encode(password).length > 127
  ) {
    throw new Error(
      "Use at least 12 characters and no more than 127 UTF-8 bytes for your password.",
    );
  }
  const response = await fetch(fontUrl, { credentials: "omit" });
  if (!response.ok)
    throw new Error("The PDF font could not be loaded. Please try again.");
  const pdf = PDF.create();
  const font = pdf.embedFont(new Uint8Array(await response.arrayBuffer()));
  if (!font.canEncode(text.replace(/\s/g, ""))) {
    throw new Error(
      "Some characters cannot be represented in this PDF font. Your outline is unchanged; use Send as a tip instead.",
    );
  }
  // A generic filename and metadata avoid exposing the case title before unlock.
  pdf.setTitle("Case outline");
  pdf.setAuthor("");
  pdf.setProtection({
    userPassword: password,
    ownerPassword: password,
    algorithm: "AES-256",
    encryptMetadata: true,
  });
  let page;
  let y;
  let pageNumber = 0;
  function addPage() {
    page = pdf.addPage({ size: "letter" });
    pageNumber += 1;
    page.drawText("Case outline", { x: 48, y: 744, size: 18, font });
    page.drawText(String(pageNumber), { x: 550, y: 30, size: 10, font });
    y = 706;
  }
  addPage();
  for (const paragraph of text.split("\n")) {
    if (!paragraph) {
      y -= 10;
      continue;
    }
    for (const line of layoutText(paragraph, font, 11, 516, 16).lines) {
      // Long unbroken references must wrap instead of disappearing off the page.
      let remaining = "";
      for (const character of line.text) {
        if (font.getTextWidth(remaining + character, 11) > 516) {
          if (y < 54) addPage();
          page.drawText(remaining, { x: 48, y, size: 11, font });
          y -= 16;
          remaining = "";
        }
        remaining += character;
      }
      if (remaining) {
        if (y < 54) addPage();
        page.drawText(remaining, { x: 48, y, size: 11, font });
        y -= 16;
      }
    }
    y -= 5;
  }
  return pdf.save();
}
