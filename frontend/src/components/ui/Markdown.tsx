import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";

interface MarkdownProps {
  content: string;
  className?: string;
}

export function Markdown({ content, className }: MarkdownProps) {
  return (
    <div className={cn(
      "prose prose-sm dark:prose-invert max-w-none prose-p:leading-relaxed prose-pre:bg-muted/50 prose-pre:border prose-pre:border-border/40 prose-pre:rounded-lg prose-headings:font-black prose-headings:tracking-tighter prose-strong:font-black prose-a:text-primary hover:prose-a:underline",
      className
    )}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
        h1: ({ children }) => <h1 className="text-2xl mb-4">{children}</h1>,
        h2: ({ children }) => <h2 className="text-xl mb-3">{children}</h2>,
        h3: ({ children }) => <h3 className="text-lg mb-2">{children}</h3>,
        ul: ({ children }) => <ul className="list-disc pl-5 space-y-1 mb-4">{children}</ul>,
        ol: ({ children }) => <ol className="list-decimal pl-5 space-y-1 mb-4">{children}</ol>,
        li: ({ children }) => <li className="text-foreground/90">{children}</li>,
        p: ({ children }) => <p className="mb-4 last:mb-0">{children}</p>,
        strong: ({ children }) => <strong className="font-black text-foreground">{children}</strong>,
        code: ({ children }) => (
          <code className="bg-muted px-1.5 py-0.5 rounded text-sm font-mono text-primary">
            {children}
          </code>
        ),
      }}
    >
      {content}
      </ReactMarkdown>
    </div>
  );
}
