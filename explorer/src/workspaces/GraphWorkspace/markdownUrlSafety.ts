/**
 * URL-safety predicate for the Markdown content viewer.
 *
 * Extracted into a pure module so the check can be unit-tested without
 * importing the MarkdownContentViewer React component, and so the component
 * module exports only components (react-refresh/only-export-components,
 * issue #1119). The behaviour is unchanged from the original in-component
 * implementation: only http, https, mailto, in-document fragments, and
 * root-relative paths are permitted.
 */

export function isSafeUrl(url?: string): boolean {
  if (!url) return false;
  const trimmed = url.trim();
  // Reject whitespace-only strings — new URL("", base) would resolve to the base
  // protocol and produce a false positive. This guards direct callers of the exported
  // function; markdown parsers normalise whitespace-only destinations to "" which
  // already fails the !url check above.
  if (!trimmed) return false;
  if (trimmed.startsWith("//")) return false;
  if (trimmed.startsWith("#")) return true;
  if (trimmed.startsWith("/")) return true;
  try {
    const parsed = new URL(trimmed, "http://localhost");
    return ["http:", "https:", "mailto:"].includes(parsed.protocol);
  } catch {
    return false;
  }
}
