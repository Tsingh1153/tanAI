"use client";

// Renders assistant/user markdown with GitHub-flavored markdown, syntax
// highlighting, and LaTeX (KaTeX). Isolated in its own component so the heavy
// remark/rehype pipeline is only imported where needed.

import { memo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import remarkBreaks from "remark-breaks";
import rehypeHighlight from "rehype-highlight";
import rehypeKatex from "rehype-katex";
import { MermaidBlock } from "./MermaidBlock";
import { Artifact } from "./Artifact";

const RENDER_LANGS = ["language-mermaid", "language-html", "language-svg"];

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function hasRenderableChild(children: any): boolean {
  const child = Array.isArray(children) ? children[0] : children;
  const cls = child?.props?.className ?? "";
  return RENDER_LANGS.some((l) => cls.includes(l));
}

function MarkdownImpl({ content }: { content: string }) {
  return (
    <div className="prose-content">
      <ReactMarkdown
        // remarkBreaks turns single newlines into hard line breaks so model
        // output that relies on line breaks (lists, worksheets, verse) is not
        // collapsed into one run-on paragraph by CommonMark's default rules.
        remarkPlugins={[remarkGfm, remarkMath, remarkBreaks]}
        rehypePlugins={[rehypeHighlight, rehypeKatex]}
        components={{
          // Open links in a new tab; they point outside the app.
          a: (props) => (
            <a {...props} target="_blank" rel="noopener noreferrer" />
          ),
          // Render special fenced blocks: mermaid diagrams and html/svg
          // artifacts (live preview). Everything else stays a code block.
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          code: ({ className, children, ...props }: any) => {
            const cls = className || "";
            if (/language-mermaid/.test(cls)) {
              return <MermaidBlock code={String(children)} />;
            }
            if (/language-html/.test(cls)) {
              return <Artifact code={String(children)} language="html" />;
            }
            if (/language-svg/.test(cls)) {
              return <Artifact code={String(children)} language="svg" />;
            }
            return (
              <code className={className} {...props}>
                {children}
              </code>
            );
          },
          // Renderable blocks manage their own container, so skip the <pre>.
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          pre: ({ children }: any) =>
            hasRenderableChild(children) ? <>{children}</> : <pre>{children}</pre>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

// Memoized: streaming updates re-render the parent frequently, but a given
// finished bubble's content is stable.
export const Markdown = memo(MarkdownImpl);
