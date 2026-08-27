import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToString } from "react-dom/server";

(globalThis as any).React = React;

import { MarkdownContentViewer } from "../src/workspaces/GraphWorkspace/MarkdownContentViewer.tsx";
import { isSafeUrl } from "../src/workspaces/GraphWorkspace/markdownUrlSafety.ts";

test("isSafeUrl permits safe http, https, and mailto URLs and relative paths", () => {
  assert.equal(isSafeUrl("https://example.com"), true);
  assert.equal(isSafeUrl("http://localhost:8000"), true);
  assert.equal(isSafeUrl("mailto:user@example.com"), true);
  assert.equal(isSafeUrl("#section-1"), true);
  assert.equal(isSafeUrl("/relative/path"), true);
});

test("isSafeUrl rejects protocol-relative URLs and dangerous schemes", () => {
  // Protocol-relative URLs (must be blocked)
  assert.equal(isSafeUrl("//evil.com"), false);
  assert.equal(isSafeUrl("//localhost:8000"), false);
  assert.equal(isSafeUrl("//"), false);

  // Dangerous schemes
  assert.equal(isSafeUrl("javascript:alert('xss')"), false);
  assert.equal(isSafeUrl("JAVASCRIPT:alert(1)"), false);
  assert.equal(isSafeUrl("data:text/html;base64,PHNjcmlwdD4="), false);
  assert.equal(isSafeUrl("vbscript:MsgBox(1)"), false);
  assert.equal(isSafeUrl(""), false);
  assert.equal(isSafeUrl(undefined), false);
});

// ─── C URL contract: whitespace-only strings ────────────────────────────────
// The CommonMark parser normalises whitespace-only link destinations to "" so
// these values are unreachable through normal markdown rendering. However, the
// function is exported and its direct-call contract must be correct.
test("isSafeUrl rejects whitespace-only strings (contract correctness)", () => {
  assert.equal(isSafeUrl(" "), false, "single space must be rejected");
  assert.equal(isSafeUrl("\t"), false, "tab must be rejected");
  assert.equal(isSafeUrl("\n"), false, "newline must be rejected");
  assert.equal(isSafeUrl("   "), false, "multiple spaces must be rejected");
  assert.equal(isSafeUrl(" \t\n "), false, "mixed whitespace must be rejected");
});

test("renders Preview mode with formatted Markdown elements and tabs", () => {
  const markdown = `# Main Title\n\n**Bold Statement**\n\n* Item A\n* Item B`;
  const html = renderToString(React.createElement(MarkdownContentViewer, { content: markdown, defaultMode: "preview" }));

  // Tab buttons are present
  assert.equal(html.includes("Preview"), true);
  assert.equal(html.includes("Source"), true);
  assert.equal(html.includes("Copy"), true);

  // Formatted preview elements
  assert.equal(html.includes("Main Title"), true);
  assert.equal(html.includes("Bold Statement"), true);
  assert.equal(html.includes("<strong>Bold Statement</strong>"), true);
  assert.equal(html.includes("Item A"), true);
  assert.equal(html.includes("Item B"), true);
});

test("renders Source mode with exact unmodified text inside pre/code", () => {
  const markdown = `# Title 🚀\n\n  * Indented item\n\n\`\`\`python\ndef test():\n    return "α + β"\n\`\`\``;
  const html = renderToString(React.createElement(MarkdownContentViewer, { content: markdown, defaultMode: "source" }));

  assert.equal(html.includes("<pre"), true);
  assert.equal(html.includes("<code"), true);
  assert.equal(html.includes("# Title 🚀"), true);
  assert.equal(html.includes("  * Indented item"), true);
  assert.equal(html.includes('return &quot;α + β&quot;'), true);
});

test("renders raw HTML safely as escaped text without executing elements", () => {
  const dangerousHtml = `<script>alert("XSS")</script><iframe src="https://evil.com"></iframe>`;
  const html = renderToString(React.createElement(MarkdownContentViewer, { content: dangerousHtml, defaultMode: "preview" }));

  // Script and iframe tags must NOT be rendered as active DOM tags
  assert.equal(html.includes("<script>"), false);
  assert.equal(html.includes("<iframe"), false);
  // Content is escaped as text
  assert.equal(html.includes("&lt;script&gt;"), true);
});

// ─── C-1: HAST node prop must not reach the DOM ─────────────────────────────
// react-markdown passes a HAST `node` (Element) object to custom component
// overrides. Before this fix, ...props spread caused React 19 to serialise it
// as node="[object Object]" on every <a> and <code> element.
test("rendered links do not expose the HAST node object as a DOM attribute", () => {
  const content = `[Example](https://example.com)\n\nInline \`code\` here.`;
  const html = renderToString(React.createElement(MarkdownContentViewer, { content, defaultMode: "preview" }));

  // The rendered HTML must not contain the serialised HAST object
  assert.equal(html.includes("node="), false, "node= attribute must not appear in rendered HTML");
  assert.equal(html.includes("[object Object]"), false, "serialised HAST object must not appear in rendered HTML");

  // The link must still render correctly with the right href
  assert.equal(html.includes('href="https://example.com"'), true, "href must be present");
});

// ─── C-2: Fragment links must not open in a new tab ─────────────────────────
// Links to in-document anchors such as #section or GFM footnote backlinks like
// #user-content-fn-1 must stay in the current document. Only external links
// use target="_blank".
test("fragment links render in the current document without target blank", () => {
  const content = `[Jump to section](#introduction)\n\n[External](https://example.com)`;
  const html = renderToString(React.createElement(MarkdownContentViewer, { content, defaultMode: "preview" }));

  // Fragment link must have the href
  assert.equal(html.includes('href="#introduction"'), true, "fragment href must be present");

  // Confirm no target=_blank attribute appears anywhere near the fragment link.
  // We check that the output contains a fragment href WITHOUT target="_blank"
  // by verifying the two strings are not both present (the external link has
  // target blank; the fragment link must not).
  const fragmentLinkIdx = html.indexOf('href="#introduction"');
  assert.notEqual(fragmentLinkIdx, -1, "fragment link must be rendered");
  // Inspect the 80 chars around the fragment href — should not contain target
  const fragmentContext = html.slice(Math.max(0, fragmentLinkIdx - 10), fragmentLinkIdx + 90);
  assert.equal(fragmentContext.includes('target="_blank"'), false, "fragment link must not have target=_blank");

  // External link must still have target blank
  assert.equal(html.includes('href="https://example.com"'), true, "external href must be present");
  assert.equal(html.includes('target="_blank"'), true, "external link must have target=_blank");
  assert.equal(html.includes('rel="noopener noreferrer"'), true, "external link must have rel");
});

test("GFM footnote backlinks render without target blank", () => {
  // GFM footnote syntax: footnote ref in text + definition below
  const content = `See the note[^1] for more.\n\n[^1]: This is the footnote text.`;
  const html = renderToString(React.createElement(MarkdownContentViewer, { content, defaultMode: "preview" }));

  // The footnote reference link (#user-content-fn-1) and backlink
  // (#user-content-fnref-1) are fragment links and must not open in a new tab.
  // We verify no fragment href is paired with target=_blank.
  // Extract all href="#..." occurrences and confirm none is adjacent to target=_blank.
  const anchorMatches = [...html.matchAll(/href="#[^"]*"/g)];
  assert.ok(anchorMatches.length > 0, "GFM footnotes must produce fragment links");
  for (const match of anchorMatches) {
    const start = match.index ?? 0;
    const context = html.slice(Math.max(0, start - 10), start + 120);
    assert.equal(
      context.includes('target="_blank"'),
      false,
      `fragment link ${match[0]} must not have target=_blank`,
    );
  }
});

// ─── C-1-R: GFM footnote attributes must be preserved (regression test) ─────
// The C-1 fix (removing the HAST `node` prop) must NOT silently drop other
// legitimate HAST attributes. remark-gfm generates the following on footnote
// links that are required for correct in-page navigation and accessibility:
//
//   Footnote reference anchor:
//     id="user-content-fnref-1"           ← backlink target
//     data-footnote-ref="true"
//     aria-describedby="footnote-label"
//
//   Footnote back-link anchor:
//     data-footnote-backref=""
//     aria-label="Back to reference 1"    ← screen-reader label
//     class="data-footnote-backref"
//
// If these are absent, clicking the ↩ back-link cannot scroll back to the
// in-text reference, and screen readers cannot announce the backlink purpose.
test("GFM footnote links preserve generated id, aria, and class attributes", () => {
  const content = `See the note[^1] for more.\n\n[^1]: This is the footnote text.`;
  const html = renderToString(React.createElement(MarkdownContentViewer, { content, defaultMode: "preview" }));

  // The HAST `node` object must not appear serialised as a DOM attribute.
  assert.equal(html.includes("node="), false, "node= attribute must not appear in HTML");
  assert.equal(html.includes("[object Object]"), false, "serialised HAST object must not appear in HTML");

  // Footnote reference anchor must retain its id so the backlink can navigate to it.
  assert.equal(
    html.includes('id="user-content-fnref-1"'),
    true,
    "footnote reference anchor must retain id for back-navigation",
  );

  // Footnote backlink must retain its aria-label for screen-reader accessibility.
  assert.equal(
    html.includes('aria-label="Back to reference 1"'),
    true,
    "footnote backlink must retain aria-label for accessibility",
  );

  // Footnote backlink must retain its class attribute.
  assert.equal(
    html.includes('class="data-footnote-backref"'),
    true,
    "footnote backlink must retain class attribute",
  );
});

test("renders safe links as <a> with target blank and unclickable span for unsafe links", () => {
  const content = `[Safe Link](https://getsemantica.ai)\n\n[Unsafe Scheme](javascript:alert(1))\n\n[Protocol Relative](//evil.com)`;
  const html = renderToString(React.createElement(MarkdownContentViewer, { content, defaultMode: "preview" }));

  // Safe link renders as <a> with security attributes
  assert.equal(html.includes('href="https://getsemantica.ai"'), true);
  assert.equal(html.includes('target="_blank"'), true);
  assert.equal(html.includes('rel="noopener noreferrer"'), true);

  // Unsafe links do NOT render as <a> tags
  assert.equal(html.includes('href="javascript:alert(1)"'), false);
  assert.equal(html.includes('href="//evil.com"'), false);
  assert.equal(html.includes("Unsafe Scheme"), true);
  assert.equal(html.includes("Protocol Relative"), true);
});

test("renders remote images as safe placeholder badges instead of <img> tags", () => {
  const content = `![System Diagram](https://example.com/diagram.png)`;
  const html = renderToString(React.createElement(MarkdownContentViewer, { content, defaultMode: "preview" }));

  // No <img> tag rendered
  assert.equal(html.includes("<img"), false);
  // Image placeholder badge rendered
  assert.equal(html.includes("Image:"), true);
  assert.equal(html.includes("System Diagram"), true);
});

test("renders clear empty-state message when content is empty or null", () => {
  const emptyHtml = renderToString(React.createElement(MarkdownContentViewer, { content: "" }));
  assert.equal(emptyHtml.includes("No content available for this node."), true);

  const nullHtml = renderToString(React.createElement(MarkdownContentViewer, { content: null }));
  assert.equal(nullHtml.includes("No content available for this node."), true);
});

test("renders plain text cleanly without requiring Markdown formatting", () => {
  const plainText = "Plain entity summary text without markdown formatting.";
  const html = renderToString(React.createElement(MarkdownContentViewer, { content: plainText, defaultMode: "preview" }));

  assert.equal(html.includes(plainText), true);
});

test("handles very large Markdown content without failure", () => {
  const largeContent = `# Large Knowledge Node\n\n` + "Structured observation paragraph. ".repeat(400);
  assert.equal(largeContent.length > 10000, true);

  const html = renderToString(React.createElement(MarkdownContentViewer, { content: largeContent, defaultMode: "preview" }));
  assert.equal(html.includes("Large Knowledge Node"), true);
});

// ─── H-2: Stale copied state lifecycle (SSR-compatible portion) ─────────────
// Full state-transition testing (Node A → copy → Node B) requires an interactive
// framework. The lifecycle correctness is guaranteed by the render-phase
// previous-prop synchronisation pattern: a `copiedForContent` state value tracks
// the content for which the copied indicator was set; when `content` changes, the
// mismatch is detected during render and `copied` is reset to false in the same
// React batch, before the new node's UI is painted. What we CAN verify in SSR
// is that the initial render for any content value shows the Copy button (not the
// Copied indicator), which confirms the initial state is always clean.
test("copy button always starts in un-copied state on initial render", () => {
  const html = renderToString(React.createElement(MarkdownContentViewer, {
    content: "# Some Node\n\nDescription text.",
    defaultMode: "preview",
  }));

  // Initial render must show 'Copy', never 'Copied'
  assert.equal(html.includes("Copy"), true, "Copy button must be present on initial render");
  assert.equal(html.includes("Copied"), false, "Copied indicator must NOT be present on initial render");
});
