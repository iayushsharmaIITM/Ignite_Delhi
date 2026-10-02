import { useEffect, useState } from "react"
import {
  Globe,
  Monitor,
  Moon,
  Sun,
  User,
  LogOut,
  LogIn,
  Zap,
  Crown,
  Building2,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet"
import { Separator } from "@/components/ui/separator"
import { Badge } from "@/components/ui/badge"
import { t, setLang, getLang, getLangs, type LangCode } from "@/lib/i18n"
import { setTheme } from "@/theme"
import { useAuthHeaders } from "@/lib/api"

type ThemeMode = "system" | "dark" | "light"

type UsageRow = {
  feature: string
  brain: string
  model: string
  calls: number
  prompt_tokens: number
  completion_tokens: number
  total_ms: number
}

type Plan = {
  name: string
  price: number
  icon: React.ReactNode
  features: string[]
  current?: boolean
}

const PLANS: Plan[] = [
  {
    name: t("up.free"),
    price: 0,
    icon: <Zap className="h-4 w-4" />,
    features: [t("up.free_f1"), t("up.free_f2"), t("up.free_f3")],
    current: true,
  },
  {
    name: t("up.pro"),
    price: 50,
    icon: <Crown className="h-4 w-4" />,
    features: [t("up.pro_f1"), t("up.pro_f2"), t("up.pro_f3")],
  },
  {
    name: t("up.biz"),
    price: 99,
    icon: <Building2 className="h-4 w-4" />,
    features: [t("up.biz_f1"), t("up.biz_f2"), t("up.biz_f3")],
  },
]

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function SettingsMenu({ open, onOpenChange }: Props) {
  const [lang, setLangState] = useState<LangCode>(getLang())
  const [theme, setThemeState] = useState<ThemeMode>(
    () => (localStorage.getItem("kestrel.theme") as ThemeMode) || "system",
  )
  const [usage, setUsage] = useState<UsageRow[]>([])
  const [usageLoading, setUsageLoading] = useState(false)
  const [usageError, setUsageError] = useState(false)
  const authHeaders = useAuthHeaders()

  // Fetch usage stats when opened
  useEffect(() => {
    if (!open) return
    setUsageLoading(true)
    setUsageError(false)
    fetch("/api/usage", { headers: authHeaders })
      .then((r) => {
        if (!r.ok) throw new Error("Failed")
        return r.json()
      })
      .then((d) => {
        setUsage(d.usage || [])
        setUsageLoading(false)
      })
      .catch(() => {
        setUsageError(true)
        setUsageLoading(false)
      })
  }, [open, authHeaders])

  const handleLangChange = (code: LangCode) => {
    setLang(code)
    setLangState(code)
  }

  const handleThemeChange = (mode: ThemeMode) => {
    setTheme(mode)
    setThemeState(mode)
  }

  const handleSignOut = () => {
    const w = window as unknown as { Clerk?: { signOut?: () => Promise<void> } }
    w.Clerk?.signOut?.()
  }

  const handleSignIn = () => {
    const w = window as unknown as { Clerk?: { openSignIn?: () => void } }
    w.Clerk?.openSignIn?.()
  }

  const handleManageAccount = () => {
    const w = window as unknown as { Clerk?: { openUserProfile?: () => void } }
    w.Clerk?.openUserProfile?.()
  }

  const isSignedIn = !!authHeaders.Authorization

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="w-full overflow-y-auto border-l border-line bg-panel sm:max-w-md"
      >
        <SheetHeader className="px-6 pt-6">
          <SheetTitle className="flex items-center gap-2 text-lg font-semibold text-foreground">
            <Globe className="h-5 w-5 text-accent" />
            {t("set.language")} · {t("set.theme")}
          </SheetTitle>
          <SheetDescription className="text-sm text-muted-foreground">
            {t("upg.sub")}
          </SheetDescription>
        </SheetHeader>

        <div className="flex flex-col gap-6 px-6 pb-8">
          {/* Language */}
          <section>
            <h3 className="mb-3 text-[11px] font-bold uppercase tracking-[0.12em] text-muted-foreground">
              {t("set.language")}
            </h3>
            <div className="grid grid-cols-2 gap-2">
              {getLangs().map((l) => (
                <button
                  key={l.code}
                  type="button"
                  onClick={() => handleLangChange(l.code)}
                  className={cn(
                    "flex items-center gap-2 rounded-lg border px-3 py-2.5 text-left text-[13px] transition-colors duration-150 ease-out",
                    lang === l.code
                      ? "border-accent/60 bg-accent-dim text-accent"
                      : "border-line bg-wash-3 text-muted-foreground hover:border-line-2 hover:text-foreground",
                  )}
                >
                  <span className="text-base">{l.label}</span>
                </button>
              ))}
            </div>
          </section>

          <Separator className="bg-line" />

          {/* Theme */}
          <section>
            <h3 className="mb-3 text-[11px] font-bold uppercase tracking-[0.12em] text-muted-foreground">
              {t("set.theme")}
            </h3>
            <div className="grid grid-cols-3 gap-2">
              {(
                [
                  { mode: "system" as ThemeMode, icon: <Monitor className="h-4 w-4" />, label: t("set.system") },
                  { mode: "dark" as ThemeMode, icon: <Moon className="h-4 w-4" />, label: t("set.dark") },
                  { mode: "light" as ThemeMode, icon: <Sun className="h-4 w-4" />, label: t("set.light") },
                ]
              ).map(({ mode, icon, label }) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => handleThemeChange(mode)}
                  className={cn(
                    "flex flex-col items-center gap-1.5 rounded-lg border px-3 py-3 text-[12px] transition-colors duration-150 ease-out",
                    theme === mode
                      ? "border-accent/60 bg-accent-dim text-accent"
                      : "border-line bg-wash-3 text-muted-foreground hover:border-line-2 hover:text-foreground",
                  )}
                >
                  {icon}
                  <span>{label}</span>
                </button>
              ))}
            </div>
          </section>

          <Separator className="bg-line" />

          {/* Usage Stats */}
          <section>
            <h3 className="mb-3 text-[11px] font-bold uppercase tracking-[0.12em] text-muted-foreground">
              {t("usage.title")}
            </h3>
            <p className="mb-3 text-[12px] text-muted-foreground">{t("usage.sub")}</p>
            {usageLoading ? (
              <div className="flex items-center gap-2 text-[13px] text-muted-foreground">
                <span className="h-2 w-2 animate-pulse rounded-full bg-accent" />
                {t("common.loading")}
              </div>
            ) : usageError ? (
              <div className="rounded-lg border border-line bg-wash-3 px-3 py-2.5 text-[13px] text-muted-foreground">
                {t("common.error")}
              </div>
            ) : usage.length === 0 ? (
              <div className="rounded-lg border border-line bg-wash-3 px-3 py-2.5 text-[13px] text-muted-foreground">
                {isSignedIn ? t("usage.empty") : t("usage.signin")}
              </div>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-line">
                <table className="w-full text-[12px]">
                  <thead>
                    <tr className="border-b border-line bg-wash-3">
                      <th className="px-3 py-2 text-left font-semibold text-muted-foreground">{t("usage.feature")}</th>
                      <th className="px-3 py-2 text-left font-semibold text-muted-foreground">{t("usage.brain")}</th>
                      <th className="px-3 py-2 text-left font-semibold text-muted-foreground">{t("usage.model")}</th>
                      <th className="px-3 py-2 text-right font-semibold text-muted-foreground">{t("usage.calls")}</th>
                      <th className="px-3 py-2 text-right font-semibold text-muted-foreground">{t("usage.tokens")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {usage.map((row, i) => (
                      <tr key={i} className="border-b border-line/50 last:border-0">
                        <td className="px-3 py-2 text-foreground/90">{row.feature}</td>
                        <td className="px-3 py-2 text-muted-foreground">{row.brain}</td>
                        <td className="px-3 py-2 font-mono text-[11px] text-muted-foreground">{row.model}</td>
                        <td className="px-3 py-2 text-right text-foreground/90">{row.calls}</td>
                        <td className="px-3 py-2 text-right text-foreground/90">
                          {row.prompt_tokens + row.completion_tokens}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <Separator className="bg-line" />

          {/* Upgrade Plans */}
          <section>
            <h3 className="mb-3 text-[11px] font-bold uppercase tracking-[0.12em] text-muted-foreground">
              {t("up.title")}
            </h3>
            <div className="flex flex-col gap-3">
              {PLANS.map((plan) => (
                <div
                  key={plan.name}
                  className={cn(
                    "rounded-xl border p-4 transition-colors duration-150 ease-out",
                    plan.current
                      ? "border-accent/40 bg-accent-dim"
                      : "border-line bg-wash-3",
                  )}
                >
                  <div className="mb-2 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-accent">{plan.icon}</span>
                      <span className="text-[14px] font-semibold text-foreground">{plan.name}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      {plan.current && (
                        <Badge variant="secondary" className="text-[10px]">
                          {t("up.current")}
                        </Badge>
                      )}
                      <span className="text-[14px] font-semibold text-foreground">
                        ${plan.price}
                        <span className="text-[11px] font-normal text-muted-foreground">
                          {t("up.per_mo")}
                        </span>
                      </span>
                    </div>
                  </div>
                  <ul className="mb-3 flex flex-col gap-1">
                    {plan.features.map((f, i) => (
                      <li key={i} className="flex items-center gap-2 text-[12px] text-muted-foreground">
                        <span className="h-1 w-1 rounded-full bg-accent/60" />
                        {f}
                      </li>
                    ))}
                  </ul>
                  <Button
                    variant={plan.current ? "secondary" : "default"}
                    size="sm"
                    className="w-full"
                    disabled
                  >
                    {t("up.soon")}
                  </Button>
                </div>
              ))}
            </div>
            <p className="mt-3 text-[11px] leading-relaxed text-muted-foreground">
              {t("up.note")}
            </p>
          </section>

          <Separator className="bg-line" />

          {/* Account */}
          <section className="flex flex-col gap-2">
            {isSignedIn ? (
              <>
                <Button
                  variant="outline"
                  className="w-full justify-start gap-2.5"
                  onClick={handleManageAccount}
                >
                  <User className="h-4 w-4" />
                  {t("set.account")}
                </Button>
                <Button
                  variant="ghost"
                  className="w-full justify-start gap-2.5 text-destructive hover:text-destructive"
                  onClick={handleSignOut}
                >
                  <LogOut className="h-4 w-4" />
                  {t("set.signout")}
                </Button>
              </>
            ) : (
              <Button
                variant="default"
                className="w-full justify-start gap-2.5"
                onClick={handleSignIn}
              >
                <LogIn className="h-4 w-4" />
                {t("set.sign_in")}
              </Button>
            )}
          </section>
        </div>
      </SheetContent>
    </Sheet>
  )
}
