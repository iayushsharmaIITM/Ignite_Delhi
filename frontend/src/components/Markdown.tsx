import { useMemo } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { CitationChip, type SourceItem } from "@/components/CitationChip"

type Props = {
  children: string
  sources?: SourceItem[]
  onOpenSource?: (item: SourceItem) => void
}

// Split into its own module so the ~150 kB markdown pipeline loads only
// when the first bot answer actually renders.
export default function Markdown({ children, sources, onOpenSource }: Props) {
  // Pre-process inline [N] citations to [^N] if N corresponds to a known source
  const processedText = useMemo(() => {
    if (!children || !sources || sources.length === 0) return children || ""
    const count = sources.length
    // Convert [N] into [^N] only if 1 <= N <= count and not already preceded by ^
    return children.replace(/(?<!\^)(?:\[([0-9]+)\])/g, (match, digits) => {
      const n = parseInt(digits, 10)
      if (n >= 1 && n <= count) {
        return `[^${n}]`
      }
      return match
    })
  }, [children, sources])

  const components = useMemo(() => {
    return {
      a: ({ href, children: linkChildren, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { children?: React.ReactNode }) => {
        if (href && (href.startsWith("#user-content-fn-") || href.startsWith("#fn-"))) {
          const num = parseInt(String(linkChildren), 10)
          if (!isNaN(num) && num >= 1 && sources && num <= sources.length) {
            const src = sources[num - 1]
            if (src && onOpenSource) {
              return (
                <CitationChip
                  index={num}
                  source={src}
                  inline
                  onOpenSource={onOpenSource}
                />
              )
            }
          }
        }
        return <a href={href} {...props}>{linkChildren}</a>
      },
      section: ({ className, children: secChildren, ...props }: React.HTMLAttributes<HTMLElement> & { children?: React.ReactNode }) => {
        // Suppress trailing GFM footnotes list in favor of Kestrel's Perplexity source strip
        if (className === "footnotes" || (props as Record<string, unknown>)["data-footnotes"]) {
          return null
        }
        return <section className={className} {...props}>{secChildren}</section>
      },
    }
  }, [sources, onOpenSource])

  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {processedText}
    </ReactMarkdown>
  )
}
