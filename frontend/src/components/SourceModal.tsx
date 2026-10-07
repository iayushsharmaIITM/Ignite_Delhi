import { useEffect, useMemo, useRef, useState } from "react"
import { toast } from "sonner"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import {
  Bookmark,
  Code,
  Copy,
  Eye,
  FileCode,
  FileSpreadsheet,
  FileText,
  Maximize2,
  Minimize2,
  X,
} from "lucide-react"
import { t } from "@/lib/i18n"
import { useDialog } from "@/lib/utils"
import { apiFetch } from "@/lib/api"
import type { SourceItem } from "@/components/CitationChip"

type Props = {
  title: string
  excerpt?: string
  // Which exact document version the answer was produced from. Optional: citations
  // made before the server knew cannot supply one, and then the newest is opened.
  version?: string
  sources?: SourceItem[]
  brain: string
  onClose: () => void
}

export type DocType = "pdf" | "docx" | "markdown" | "csv" | "code" | "text"

export function getDocType(filename: string): DocType {
  const ext = filename.split(".").pop()?.toLowerCase() || ""
  if (ext === "pdf") return "pdf"
  if (ext === "docx" || ext === "doc") return "docx"
  if (ext === "md" || ext === "markdown") return "markdown"
  if (ext === "csv" || ext === "tsv") return "csv"
  if (["json", "yaml", "yml", "js", "ts", "tsx", "py", "sh", "sql", "html", "xml", "css"].includes(ext)) {
    return "code"
  }
  return "text"
}

function findMatch(fullText: string, excerpt?: string): { start: number; end: number } | null {
  if (!excerpt || !fullText) return null
  const clean = excerpt.replace(/\s+/g, " ").trim()
  if (!clean) return null

  // 1. Direct case-insensitive search
  const needle = clean.slice(0, 90).toLowerCase()
  const lower = fullText.toLowerCase()
  const pos = lower.indexOf(needle)
  if (pos >= 0) {
    return {
      start: pos,
      end: Math.min(fullText.length, pos + Math.max(needle.length, clean.length)),
    }
  }

  // 2. Whitespace-flattened search
  const flatFull = fullText.replace(/\s+/g, " ")
  const flatNeedle = clean.replace(/\s+/g, " ")
  const flatPos = flatFull.toLowerCase().indexOf(flatNeedle.toLowerCase().slice(0, 70))
  if (flatPos >= 0) {
    const cut = Math.max(0, flatPos - 10)
    const len = Math.min(fullText.length - cut, flatNeedle.length + 30)
    return { start: cut, end: cut + len }
  }

  // 3. Keyword / word sequence search
  const words = clean.split(/\s+/).filter((w) => w.length > 2).slice(0, 6)
  if (words.length >= 2) {
    try {
      const pattern = new RegExp(words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("\\s+"), "i")
      const exec = pattern.exec(fullText)
      if (exec) {
        return { start: exec.index, end: exec.index + exec[0].length }
      }
    } catch {
      // ignore regex failure
    }
  }

  return null
}

function parseCsvRows(text: string): { headers: string[]; rows: string[][] } {
  const isTsv = text.includes("\t") && !text.includes(",")
  const delimiter = isTsv ? "\t" : ","
  const lines = text.trim().split(/\r?\n/)
  if (!lines.length) return { headers: [], rows: [] }

  const splitLine = (line: string): string[] => {
    const row: string[] = []
    let current = ""
    let inQuotes = false
    for (let i = 0; i < line.length; i++) {
      const c = line[i]
      if (c === '"' || c === "'") {
        inQuotes = !inQuotes
      } else if (c === delimiter && !inQuotes) {
        row.push(current.trim())
        current = ""
      } else {
        current += c
      }
    }
    row.push(current.trim())
    return row
  }

  const all = lines.map(splitLine).filter((r) => r.length > 0)
  if (!all.length) return { headers: [], rows: [] }
  return {
    headers: all[0],
    rows: all.slice(1),
  }
}

export function SourceModal({ title, excerpt, version, sources, brain, onClose }: Props) {
  const [activeSource, setActiveSource] = useState<SourceItem>({
    source: title,
    excerpt,
    version,
  })

  useEffect(() => {
    setActiveSource({ source: title, excerpt, version })
  }, [title, excerpt, version])

  const currentTitle = activeSource.source || title
  const currentExcerpt = activeSource.excerpt !== undefined ? activeSource.excerpt : excerpt
  const currentVersion = activeSource.version !== undefined ? activeSource.version : version

  const [where, setWhere] = useState("loading…")
  const [plainText, setPlainText] = useState("")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<"live" | "raw">("live")
  const [isExpanded, setIsExpanded] = useState(false)

  const markRef = useRef<HTMLElement | null>(null)
  const panelRef = useDialog<HTMLDivElement>(true, onClose)

  const docType = useMemo(() => getDocType(currentTitle), [currentTitle])
  const match = useMemo(() => findMatch(plainText, currentExcerpt), [plainText, currentExcerpt])

  useEffect(() => {
    let alive = true
    const ac = new AbortController()
    setLoading(true)
    setError(null)

    const params = new URLSearchParams({ name: currentTitle })
    if (brain) params.set("dataset", brain)
    if (currentVersion) params.set("document_version_id", currentVersion)

    apiFetch(`/api/source?${params.toString()}`, { signal: ac.signal })
      .then((r) => r.json().catch(() => ({})).then((d) => ({ ok: r.ok, d })))
      .then(({ ok, d }) => {
        if (!alive) return
        setLoading(false)
        if (!ok) throw new Error(d.detail || "unavailable")
        const text = d.text || ""
        setPlainText(text)
        setWhere(
          (d.source === "corpus" ? "from the corpus" : "from this brain") +
            " · " + text.length.toLocaleString() + " chars",
        )
      })
      .catch((e) => {
        if (!alive) return
        setLoading(false)
        setWhere("unavailable")
        setError(String(e?.message || e).slice(0, 120))
      })

    return () => {
      alive = false
      ac.abort()
    }
  }, [currentTitle, brain, currentVersion])

  // Automatically scroll the cited highlight into view when loaded
  useEffect(() => {
    if (markRef.current) {
      const timer = setTimeout(() => {
        markRef.current?.scrollIntoView({ behavior: "smooth", block: "center" })
      }, 150)
      return () => clearTimeout(timer)
    }
  }, [plainText, tab, match])

  const jumpToCitation = () => {
    if (markRef.current) {
      markRef.current.scrollIntoView({ behavior: "smooth", block: "center" })
      markRef.current.classList.add("pulse-focus")
      setTimeout(() => {
        markRef.current?.classList.remove("pulse-focus")
      }, 1200)
    }
  }

  const copy = () => {
    navigator.clipboard.writeText(plainText).then(
      () => toast.success(t("common.copied", "Copied!")),
      () => {},
    )
  }

  const renderBadge = () => {
    switch (docType) {
      case "pdf":
        return <span className="src-type-badge badge-pdf"><FileText className="h-3 w-3" /> PDF</span>
      case "docx":
        return <span className="src-type-badge badge-docx"><FileText className="h-3 w-3" /> DOCX</span>
      case "markdown":
        return <span className="src-type-badge badge-md"><FileText className="h-3 w-3" /> Markdown</span>
      case "csv":
        return <span className="src-type-badge badge-csv"><FileSpreadsheet className="h-3 w-3" /> Table</span>
      case "code":
        return <span className="src-type-badge badge-code"><FileCode className="h-3 w-3" /> Code</span>
      default:
        return <span className="src-type-badge badge-txt"><FileText className="h-3 w-3" /> Text</span>
    }
  }

  const renderMarkdown = () => {
    let content = plainText
    if (match) {
      const before = plainText.slice(0, match.start)
      const matched = plainText.slice(match.start, match.end)
      const after = plainText.slice(match.end)
      content = `${before}[${matched.replace(/[\r\n]+/g, " ")}](#kestrel-cite-highlight)${after}`
    }

    return (
      <div className="live-doc-page live-doc-md">
        <div className="live-doc-meta-bar">
          <span className="font-semibold text-fg">Markdown Document</span>
          <span>{title}</span>
        </div>
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            a: ({ href, children, ...props }) => {
              if (href === "#kestrel-cite-highlight") {
                return (
                  <mark ref={markRef} className="src-mark-live">
                    {children}
                  </mark>
                )
              }
              return <a href={href} {...props}>{children}</a>
            },
          }}
        >
          {content}
        </ReactMarkdown>
      </div>
    )
  }

  const renderDocPages = (kind: "pdf" | "docx") => {
    const paragraphs = plainText.split(/\n\n+/)
    const isPdf = kind === "pdf"
    const excerptNeedle = (excerpt || "").slice(0, 60).toLowerCase().trim()
    let markMounted = false

    return (
      <div className={`live-doc-page ${isPdf ? "live-doc-pdf" : "live-doc-docx"}`}>
        <div className="live-doc-meta-bar">
          <span className="font-semibold text-fg">
            {isPdf ? "PDF Document · Text Layer" : "Word Document (.docx) · Document View"}
          </span>
          <span>{isPdf ? "Page 1 of 1 · 100% Zoom" : "Print Layout"}</span>
        </div>
        <h1 className="live-doc-title text-xl font-bold mb-4">{title}</h1>
        <div className="live-doc-body-text">
          {paragraphs.map((p, idx) => {
            const pLower = p.toLowerCase()
            if (!markMounted && excerptNeedle && pLower.includes(excerptNeedle)) {
              markMounted = true
              const at = pLower.indexOf(excerptNeedle)
              const pBefore = p.slice(0, at)
              const pMark = p.slice(at, at + Math.min(p.length - at, (excerpt || "").length || excerptNeedle.length))
              const pAfter = p.slice(at + pMark.length)
              return (
                <p key={idx} className="mb-4 text-sm leading-relaxed">
                  <span>{pBefore}</span>
                  <mark ref={markRef} className="src-mark-live">{pMark}</mark>
                  <span>{pAfter}</span>
                </p>
              )
            }
            return (
              <p key={idx} className="mb-4 text-sm leading-relaxed text-fg-2">
                {p}
              </p>
            )
          })}
          {!markMounted && match && (
            <p className="mt-4 border-t border-line pt-2 text-xs text-muted">
              Cited section: <mark ref={markRef} className="src-mark-live">{plainText.slice(match.start, match.end)}</mark>
            </p>
          )}
        </div>
      </div>
    )
  }

  const renderCsv = () => {
    const { headers, rows } = parseCsvRows(plainText)
    const needle = (excerpt || "").slice(0, 40).toLowerCase().trim()
    let markMounted = false

    return (
      <div className="live-doc-table-wrap">
        <div className="live-doc-meta-bar px-4 pt-3 pb-2 border-b border-line-2 bg-panel-2">
          <span className="font-semibold text-fg">Spreadsheet Data Table ({rows.length} rows, {headers.length} columns)</span>
          <span>{title}</span>
        </div>
        <div className="overflow-x-auto">
          <table className="live-doc-table">
            <thead>
              <tr>
                <th className="col-idx">#</th>
                {headers.map((h, i) => (
                  <th key={i}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rIdx) => {
                const rowText = row.join(" ").toLowerCase()
                const isMatchRow = needle && rowText.includes(needle)
                return (
                  <tr key={rIdx} className={isMatchRow ? "row-highlighted" : ""}>
                    <td className="col-idx">{rIdx + 1}</td>
                    {row.map((cell, cIdx) => {
                      const isCellMatch = !markMounted && needle && cell.toLowerCase().includes(needle)
                      if (isCellMatch) {
                        markMounted = true
                        return (
                          <td key={cIdx} className="cell-matched">
                            <mark ref={markRef} className="src-mark-live">{cell}</mark>
                          </td>
                        )
                      }
                      return <td key={cIdx}>{cell}</td>
                    })}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        {!markMounted && match && (
          <div className="p-3 border-t border-line text-xs text-muted">
            Cited section: <mark ref={markRef} className="src-mark-live">{plainText.slice(match.start, match.end)}</mark>
          </div>
        )}
      </div>
    )
  }

  const renderCode = () => {
    const lines = plainText.split(/\r?\n/)
    const needle = (excerpt || "").slice(0, 50).toLowerCase().trim()
    let markMounted = false

    return (
      <div className="live-doc-code-wrap">
        <div className="live-doc-meta-bar px-4 pt-3 pb-2 border-b border-line-2 bg-panel-2">
          <span className="font-semibold text-fg">Source Code / Structured Data ({lines.length} lines)</span>
          <span>{title}</span>
        </div>
        <div className="py-2 overflow-x-auto">
          {lines.map((line, lIdx) => {
            const isMatchLine = !markMounted && needle && line.toLowerCase().includes(needle)
            if (isMatchLine) {
              markMounted = true
              return (
                <div key={lIdx} className="code-line code-line-highlighted">
                  <span className="code-line-num">{lIdx + 1}</span>
                  <span className="code-line-text">
                    <mark ref={markRef} className="src-mark-live">{line}</mark>
                  </span>
                </div>
              )
            }
            return (
              <div key={lIdx} className="code-line">
                <span className="code-line-num">{lIdx + 1}</span>
                <span className="code-line-text">{line}</span>
              </div>
            )
          })}
        </div>
        {!markMounted && match && (
          <div className="p-3 border-t border-line text-xs text-muted">
            Cited section: <mark ref={markRef} className="src-mark-live">{plainText.slice(match.start, match.end)}</mark>
          </div>
        )}
      </div>
    )
  }

  const renderText = () => {
    const paragraphs = plainText.split(/\n\n+/)
    const needle = (excerpt || "").slice(0, 60).toLowerCase().trim()
    let markMounted = false

    return (
      <div className="live-doc-page live-doc-txt">
        <div className="live-doc-meta-bar">
          <span className="font-semibold text-fg">Text Document</span>
          <span>{title}</span>
        </div>
        <h1 className="live-doc-title text-xl font-bold mb-4">{title}</h1>
        <div className="live-doc-body-text">
          {paragraphs.map((p, idx) => {
            const pLower = p.toLowerCase()
            if (!markMounted && needle && pLower.includes(needle)) {
              markMounted = true
              const at = pLower.indexOf(needle)
              const pBefore = p.slice(0, at)
              const pMark = p.slice(at, at + Math.min(p.length - at, (excerpt || "").length || needle.length))
              const pAfter = p.slice(at + pMark.length)
              return (
                <p key={idx} className="mb-4 text-sm leading-relaxed">
                  <span>{pBefore}</span>
                  <mark ref={markRef} className="src-mark-live">{pMark}</mark>
                  <span>{pAfter}</span>
                </p>
              )
            }
            return (
              <p key={idx} className="mb-4 text-sm leading-relaxed text-fg-2">
                {p}
              </p>
            )
          })}
          {!markMounted && match && (
            <p className="mt-4 border-t border-line pt-2 text-xs text-muted">
              Cited section: <mark ref={markRef} className="src-mark-live">{plainText.slice(match.start, match.end)}</mark>
            </p>
          )}
        </div>
      </div>
    )
  }

  const renderLiveContent = () => {
    if (loading) {
      return (
        <div className="state flex items-center justify-center gap-2 p-12 text-muted">
          <span className="spin" /> Loading source document…
        </div>
      )
    }
    if (error) {
      return (
        <div className="state error p-12 text-red-500">
          Could not open this source: {error}
        </div>
      )
    }

    switch (docType) {
      case "markdown":
        return renderMarkdown()
      case "pdf":
        return renderDocPages("pdf")
      case "docx":
        return renderDocPages("docx")
      case "csv":
        return renderCsv()
      case "code":
        return renderCode()
      default:
        return renderText()
    }
  }

  const renderRawContent = () => {
    if (loading) {
      return <div className="state">Loading…</div>
    }
    if (error) {
      return <div className="state">Could not open this source: {error}</div>
    }

    if (match) {
      return (
        <>
          <span>{plainText.slice(0, match.start)}</span>
          <mark ref={markRef}>{plainText.slice(match.start, match.end)}</mark>
          <span>{plainText.slice(match.end)}</span>
        </>
      )
    }
    return plainText
  }

  return (
    <div
      id="source-modal"
      className="km-scrim"
      style={{ zIndex: 95 }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        tabIndex={-1}
        aria-label="Cited source document"
        className={`km-sheet sheet max-w-[860px] w-full max-h-[88vh] p-0 overflow-hidden rounded-2xl shadow-2xl border border-line-2 bg-panel animate-in fade-in-0 zoom-in-95 relative flex flex-col ${
          isExpanded ? "expanded !max-w-[96vw] !h-[92vh] !max-h-[92vh]" : ""
        }`}
      >
        <div className="head flex items-center justify-between gap-3 px-5 py-3.5 border-b border-line bg-panel-2">
          <div className="flex items-center gap-2.5 min-w-0">
            <span className="nm font-mono text-xs font-semibold text-fg truncate" id="src-name" title={currentTitle}>
              {currentTitle}
            </span>
            {renderBadge()}
            <span className="where text-[11px] text-muted hidden sm:inline" id="src-where">
              {where}
            </span>
          </div>

          <div className="flex items-center gap-2 ml-auto">
            <div className="src-view-tabs">
              <button
                type="button"
                className={tab === "live" ? "active" : ""}
                onClick={() => setTab("live")}
                title="Formatted Live Document View"
              >
                <Eye className="h-3.5 w-3.5" />
                <span>Live Doc</span>
              </button>
              <button
                type="button"
                className={tab === "raw" ? "active" : ""}
                onClick={() => setTab("raw")}
                title="Raw Source Text View"
              >
                <Code className="h-3.5 w-3.5" />
                <span>Raw</span>
              </button>
            </div>

            {currentExcerpt && (
              <button
                type="button"
                className="src-jump-btn"
                onClick={jumpToCitation}
                title="Jump to cited section"
              >
                <Bookmark className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">Jump to citation</span>
              </button>
            )}

            <button
              type="button"
              id="src-expand"
              className="p-1.5 hover:bg-wash-2 rounded-lg text-muted hover:text-fg transition-colors"
              title={isExpanded ? t("src.restore", "Restore size") : t("src.expand", "Expand")}
              aria-label={isExpanded ? "Restore size" : "Expand"}
              onClick={() => setIsExpanded((e) => !e)}
            >
              {isExpanded ? (
                <Minimize2 className="h-3.5 w-3.5" />
              ) : (
                <Maximize2 className="h-3.5 w-3.5" />
              )}
            </button>
            <button
              type="button"
              id="src-copy"
              className="p-1.5 hover:bg-wash-2 rounded-lg text-muted hover:text-fg transition-colors"
              title={t("src.copy", "Copy source text")}
              aria-label={t("src.copy", "Copy source text")}
              onClick={copy}
            >
              <Copy className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              id="src-close"
              className="km-x p-1 hover:bg-wash-2 rounded-lg transition-colors"
              title={t("src.close", "Close")}
              aria-label={t("src.close", "Close")}
              onClick={onClose}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {sources && sources.length > 1 && (
          <div className="flex items-center gap-1.5 px-5 py-2 border-b border-line bg-panel overflow-x-auto">
            <span className="text-[11px] font-semibold text-muted uppercase tracking-wider whitespace-nowrap mr-1">
              Sources ({sources.length}):
            </span>
            {sources.map((s, idx) => {
              const isActive = s.source === currentTitle
              return (
                <button
                  key={idx}
                  type="button"
                  className={`text-xs px-2.5 py-1 rounded-full font-mono flex items-center gap-1.5 transition-all whitespace-nowrap ${
                    isActive
                      ? "bg-primary text-primary-foreground font-semibold shadow-sm"
                      : "bg-panel-2 text-fg-2 hover:bg-wash-2 hover:text-fg border border-line"
                  }`}
                  onClick={() => setActiveSource(s)}
                  title={s.source}
                >
                  <span className="text-[10px] font-bold">[{idx + 1}]</span>
                  <span className="truncate max-w-[160px]">{s.source}</span>
                </button>
              )
            })}
          </div>
        )}

        {tab === "live" ? (
          <div id="src-body" className="live-doc-canvas flex-1 overflow-y-auto min-h-0">
            {renderLiveContent()}
          </div>
        ) : (
          <pre id="src-body" className="flex-1 overflow-y-auto min-h-0">{renderRawContent()}</pre>
        )}
      </div>
    </div>
  )
}
