import { useMemo, useRef, useState } from "react"
import {
  ChevronLeft,
  MessageSquare,
  MoreHorizontal,
  Pencil,
  Pin,
  Plug,
  Plus,
  Search,
  Trash2,
  Upload,
  Waypoints,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

type ChatSummary = { id: string; title: string; brain: string; at: number }
type Props = {
  collapsed: boolean
  onToggle: () => void
  currentBrain: string
  currentChat: string | null
  view: "chat" | "connectors" | "graph"
  onViewChange: (v: "chat" | "connectors" | "graph") => void
  onBrainChange: (brain: string) => void
  onNewChat: () => void
  onOpenChat: (chatId: string, brain: string) => void
  chats: ChatSummary[]
  onRefreshChats?: () => void
}

const CHAT_CAP = 16

export function Sidebar({
  collapsed,
  onToggle,
  currentBrain,
  currentChat,
  view,
  onViewChange,
  onBrainChange,
  onNewChat,
  onOpenChat,
  chats,
}: Props) {
  const [search, setSearch] = useState("")
  const [foldersOpen] = useState<Record<string, boolean>>({})
  const armedRef = useRef<string | null>(null)
  const [, force] = useState(0)

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return chats.filter((c) => !q || c.title.toLowerCase().includes(q) || (c.brain || "").toLowerCase().includes(q))
  }, [chats, search])

  const groups = useMemo(() => {
    const m = new Map<string, typeof filtered>()
    filtered.forEach((c) => {
      const k = c.brain || currentBrain
      if (!m.has(k)) m.set(k, [])
      m.get(k)!.push(c)
    })
    return [...m.entries()]
  }, [filtered, currentBrain])

  const qs = (brain: string) => (brain && brain !== "demo" ? `?brain=${encodeURIComponent(brain)}` : "")

  return (
    <aside
      aria-label="Kestrel navigation"
      className={cn(
        "flex h-full flex-col border-r border-sidebar-border bg-sidebar transition-[width] duration-200 ease-out",
        "max-md:fixed max-md:inset-y-0 max-md:left-0 max-md:z-40 max-md:shadow-2xl",
        collapsed ? "w-0 overflow-hidden opacity-0" : "w-[268px] opacity-100",
      )}
    >
      <div className="flex items-center gap-3 border-b border-sidebar-border px-4 py-4">
        <div className="grid h-9 w-9 flex-none place-items-center rounded-lg bg-primary text-lg text-primary-foreground shadow">
          ◆
        </div>
        <div className="min-w-0">
          <div className="truncate text-[15px] font-semibold tracking-tight text-foreground">Kestrel</div>
          <div className="text-[9.5px] font-bold uppercase tracking-[0.16em] text-muted-foreground">
            Company Brain
          </div>
        </div>
        <TooltipProvider delayDuration={200}>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                aria-label="Collapse sidebar"
                onClick={onToggle}
                className="ml-auto h-7 w-7 text-muted-foreground"
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right">Collapse</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>

      <nav aria-label="Workspace" className="px-3 pt-3">
        <div className="px-2 pb-1 text-[9.5px] font-bold uppercase tracking-[0.15em] text-muted-foreground/70">
          Workspace
        </div>
        <Button variant="ghost" className="w-full justify-start gap-2.5 text-[13.5px] text-muted-foreground" onClick={onNewChat}>
          <MessageSquare className="h-4 w-4 opacity-75" /> New chat
        </Button>
        <Button variant="ghost" className="w-full justify-start gap-2.5 text-[13.5px] text-muted-foreground" onClick={() => onBrainChange("__upload__")}>
          <Upload className="h-4 w-4 opacity-75" /> New brain
        </Button>
        <Button
          variant="ghost"
          aria-pressed={view === "graph"}
          className={cn(
            "w-full justify-start gap-2.5 text-[13.5px]",
            view === "graph" ? "bg-sidebar-accent text-foreground" : "text-muted-foreground",
          )}
          onClick={() => onBrainChange("__graph__")}
        >
          <Waypoints className="h-4 w-4 opacity-75" /> Graph
        </Button>
        <Button
          variant="ghost"
          aria-pressed={view === "connectors"}
          className={cn(
            "w-full justify-start gap-2.5 text-[13.5px]",
            view === "connectors"
              ? "bg-sidebar-accent text-foreground"
              : "text-muted-foreground",
          )}
          onClick={() => onViewChange("connectors")}
        >
          <Plug className="h-4 w-4 opacity-75" /> Connectors
        </Button>
      </nav>

      <div className="px-3 pt-4">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search chats…"
            aria-label="Search chats"
            className="h-8 border-none bg-wash-3 pl-8 text-[13px] focus-visible:ring-1"
          />
        </div>
      </div>

      <div className="px-3 pt-3">
        <div className="flex items-center justify-between px-2 pb-1">
          <span className="text-[9.5px] font-bold uppercase tracking-[0.15em] text-muted-foreground/70">Chats</span>
          <Button variant="ghost" size="icon" aria-label="New chat" onClick={onNewChat} className="h-6 w-6">
            <Plus className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-3 pb-4">
        {groups.length === 0 && (
          <div className="rounded-lg border border-line px-3 py-2.5 text-xs text-muted-foreground">
            {search ? "No chats match your search." : "No saved chats yet — start one and it's saved here, per brain."}
          </div>
        )}
        <div role="list">
        {groups.map(([brain, list]) => {
          const open = foldersOpen[brain] !== false
          return (
            <div key={brain} role="listitem">
              <button
                type="button"
                aria-expanded={open}
                onClick={() => {
                  foldersOpen[brain] = !open
                  force((n) => n + 1)
                }}
                className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-[12.5px] font-semibold text-foreground/90 hover:bg-sidebar-accent"
              >
                <span className={cn("text-[9px] text-muted-foreground transition-transform", open && "rotate-90")}>▶</span>
                <span className="truncate">{brain === "demo" ? "Demo brain" : brain}</span>
                <span className="ml-auto text-[10px] text-muted-foreground">{list.length}</span>
              </button>
              {open &&
                list.slice(0, CHAT_CAP).map((c) => {
                  const active = c.id === currentChat && brain === (currentBrain || "demo")
                  return (
                    <TooltipProvider key={c.id} delayDuration={300}>
                      <div
                        className={cn(
                          "group flex items-center rounded-lg pl-6 pr-1",
                          active ? "bg-sidebar-accent" : "hover:bg-wash",
                        )}
                      >
                        <button
                          type="button"
                          onClick={() => onOpenChat(c.id, brain)}
                          className={cn(
                            "group/item flex min-w-0 flex-1 items-center gap-2 py-2 text-left text-[13px] transition-colors duration-150 ease-out",
                            active ? "text-foreground" : "text-muted-foreground hover:text-foreground",
                          )}
                        >
                          <span className={cn(
                            "h-1 w-1 flex-none rounded-full transition-colors duration-150 ease-out",
                            active ? "bg-accent" : "bg-muted-foreground/50 group-hover/item:bg-accent/60",
                          )} />
                          <span className="truncate">{c.title}</span>
                        </button>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              aria-label={`Actions for ${c.title}`}
                              className="h-6 w-6 opacity-0 group-hover:opacity-100"
                            >
                              <MoreHorizontal className="h-3.5 w-3.5" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="start">
                            <DropdownMenuItem onClick={() => alert("Rename: " + c.title)}>
                              <Pencil className="h-3.5 w-3.5" /> Rename
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => alert("Pinned: " + c.title)}>
                              <Pin className="h-3.5 w-3.5" /> Pin
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              className="text-destructive"
                              onClick={() => {
                                if (armedRef.current === c.id) {
                                  localStorage.setItem(
                                    "kestrel.chats." + brain,
                                    JSON.stringify(
                                      JSON.parse(localStorage.getItem("kestrel.chats." + brain) || "[]").filter(
                                        (x: { id: string }) => x.id !== c.id,
                                      ),
                                    ),
                                  )
                                  armedRef.current = null
                                  force((n) => n + 1)
                                } else {
                                  armedRef.current = c.id
                                  force((n) => n + 1)
                                }
                              }}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                              {armedRef.current === c.id ? "Click again to delete" : "Delete"}
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    </TooltipProvider>
                  )
                })}
            </div>
          )
        })}
        </div>
      </div>

      <div className="border-t border-sidebar-border px-3 py-3 text-[11px] text-muted-foreground">
        {qs(currentBrain) && `?brain=${currentBrain}`}
      </div>
    </aside>
  )
}
