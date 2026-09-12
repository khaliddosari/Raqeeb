import type { ReactNode } from "react"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"

type Props = {
  index: number
  id: string
  title: string
  caption: string
  status?: { label: string; tone: "idle" | "active" | "done" | "alert" }
  children: ReactNode
}

// Darker foregrounds than the dark-theme equivalents, so the tinted pills still clear
// contrast requirements against a light surface.
const toneClass: Record<string, string> = {
  idle: "bg-white/50 text-muted-foreground border-white/60",
  active: "bg-amber-100/70 text-amber-900 border-amber-300/70",
  done: "bg-emerald-100/70 text-emerald-900 border-emerald-300/70",
  alert: "bg-red-100/70 text-red-900 border-red-300/70",
}

export function SectionShell({ index, id, title, caption, status, children }: Props) {
  return (
    <section id={id} className="scroll-mt-20">
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-mono text-xs font-semibold text-primary/70 tabular-nums">
          {String(index).padStart(2, "0")}
        </span>
        <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
        {status && (
          <Badge variant="outline" className={`font-mono text-xs uppercase backdrop-blur-sm ${toneClass[status.tone]}`}>
            {status.label}
          </Badge>
        )}
      </div>
      <p className="mt-1 text-sm text-muted-foreground">{caption}</p>
      <Separator className="my-4 bg-primary/15" />
      {children}
    </section>
  )
}
