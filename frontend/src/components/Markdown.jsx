import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// size "sm": para texto dentro de listas e cartões (caderno, propostas); por defeito, o tamanho das respostas.
export default function Markdown({ children, size = "base" }) {
  return (
    <div className={`prose prose-stone dark:prose-invert max-w-none ${size === "sm" ? "prose-sm prose-p:my-1 prose-ul:my-1 prose-ol:my-1" : "prose-p:leading-relaxed"} prose-pre:bg-stone-900 prose-table:text-sm prose-th:text-left prose-a:text-accent-600 dark:prose-a:text-accent-400`}>
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
