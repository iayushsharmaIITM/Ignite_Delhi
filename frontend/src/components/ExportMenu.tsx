import { toast } from "sonner"
import { FileText, FileType, FileDown, Copy } from "lucide-react"
import { t } from "@/lib/i18n"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Button } from "@/components/ui/button"

type Turn = {
  role: "user" | "bot"
  text: string
  sources?: { source: string; excerpt?: string }[]
}

type Props = {
  turns: Turn[]
}

function turnsToMarkdown(turns: Turn[]): string {
  return turns
    .map((t) => {
      const prefix = t.role === "user" ? "**You:**" : "**Kestrel:**"
      return `${prefix}\n\n${t.text}`
    })
    .join("\n\n---\n\n")
}

function turnsToPlainText(turns: Turn[]): string {
  return turns
    .map((t) => {
      const prefix = t.role === "user" ? "You:" : "Kestrel:"
      return `${prefix}\n\n${t.text}`
    })
    .join("\n\n---\n\n")
}

function turnsToHTML(turns: Turn[]): string {
  const body = turns
    .map((t) => {
      const isUser = t.role === "user"
      const bg = isUser ? "#f3f1ec" : "#ffffff"
      const color = isUser ? "#201d18" : "#201d18"
      const label = isUser ? "You" : "Kestrel"
      return `<div style="margin-bottom:16px;padding:12px 16px;border-radius:8px;background:${bg};color:${color};">
        <div style="font-weight:600;margin-bottom:4px;font-size:12px;text-transform:uppercase;letter-spacing:0.05em;opacity:0.6;">${label}</div>
        <div style="font-size:14px;line-height:1.6;white-space:pre-wrap;">${t.text}</div>
      </div>`
    })
    .join("\n")

  return `<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word" xmlns="http://www.w3.org/TR/REC-html40">
<head><meta charset="utf-8"><title>Kestrel Conversation</title></head>
<body style="font-family:Calibri,Arial,sans-serif;max-width:700px;margin:0 auto;padding:24px;">
<h1 style="font-size:20px;margin-bottom:24px;">Kestrel Conversation</h1>
${body}
</body></html>`
}

function downloadFile(content: string, filename: string, type: string) {
  const blob = new Blob([content], { type })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export function ExportMenu({ turns }: Props) {
  const handleExportMD = () => {
    const md = turnsToMarkdown(turns)
    downloadFile(md, "kestrel-conversation.md", "text/markdown")
    toast.success("Exported as Markdown")
  }

  const handleExportTXT = () => {
    const txt = turnsToPlainText(turns)
    downloadFile(txt, "kestrel-conversation.txt", "text/plain")
    toast.success("Exported as plain text")
  }

  const handleExportDOCX = () => {
    const html = turnsToHTML(turns)
    downloadFile(html, "kestrel-conversation.doc", "application/msword")
    toast.success("Exported as Word document")
  }

  const handleExportPDF = () => {
    const html = turnsToHTML(turns)
    const win = window.open("", "_blank")
    if (win) {
      win.document.write(html)
      win.document.close()
      win.focus()
      setTimeout(() => win.print(), 500)
    }
    toast.success("Opening print dialog — choose 'Save as PDF'")
  }

  const handleCopyTranscript = async () => {
    const txt = turnsToPlainText(turns)
    await navigator.clipboard.writeText(txt)
    toast.success(t("common.copied"))
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="gap-1.5">
          <FileDown className="h-3.5 w-3.5" />
          {t("export.title")}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[200px]">
        <DropdownMenuLabel>{t("export.title")}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={handleExportMD}>
          <FileText className="h-4 w-4" />
          {t("menu.export_md")}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={handleExportTXT}>
          <FileType className="h-4 w-4" />
          {t("menu.export_txt")}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={handleExportDOCX}>
          <FileText className="h-4 w-4" />
          {t("menu.export_docx")}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={handleExportPDF}>
          <FileDown className="h-4 w-4" />
          {t("menu.export_pdf")}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={handleCopyTranscript}>
          <Copy className="h-4 w-4" />
          {t("menu.copy_transcript")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
