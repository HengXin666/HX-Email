export function looksLikeHtml(value: string | undefined): boolean {
  if (!value) return false;
  return /<\s*(html|body|div|table|p|a|img|br|span|style|head)\b/i.test(value);
}

export function sanitizeHtml(raw: string): string {
  const parsed: Document = new DOMParser().parseFromString(raw, "text/html");
  const blockedElements: NodeListOf<Element> = parsed.querySelectorAll(
    "script, style, iframe, object, embed, form, base, meta, link",
  );
  blockedElements.forEach((element: Element) => element.remove());

  const elements: NodeListOf<Element> = parsed.body.querySelectorAll("*");
  elements.forEach((element: Element) => {
    const attributes: Attr[] = Array.from(element.attributes);
    attributes.forEach((attribute: Attr) => {
      const name: string = attribute.name.toLowerCase();
      const value: string = attribute.value.trim().toLowerCase();
      const isUrlAttribute: boolean = [
        "href",
        "src",
        "action",
        "formaction",
        "xlink:href",
      ].includes(name);
      if (
        name.startsWith("on") ||
        name === "srcdoc" ||
        (isUrlAttribute && /^(?:javascript|data|vbscript):/.test(value))
      ) {
        element.removeAttribute(attribute.name);
      }
    });
  });

  return parsed.body.innerHTML;
}
