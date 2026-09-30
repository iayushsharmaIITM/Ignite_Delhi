import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

// Split into its own module so the ~150 kB markdown pipeline loads only
// when the first bot answer actually renders.
export default function Markdown({ children }: { children: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
  )
}
