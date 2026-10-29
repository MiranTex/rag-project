import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export default function Markdown({ children }) {
  return (
    <div className="prose prose-stone max-w-none prose-p:leading-relaxed prose-pre:bg-stone-900 prose-table:text-sm prose-th:text-left prose-a:text-accent-600">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // Tabelas largas fazem scroll dentro da resposta em vez de alargar a página.
          table: ({ node, ...props }) => (
            <div className="overflow-x-auto">
              <table {...props} />
            </div>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
