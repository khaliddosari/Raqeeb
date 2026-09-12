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
  idle: "bg-muted text-muted-foreground",
  active: "bg-amber-100 text-amber-800 border-amber-300",
  done: "bg-emerald-100 text-emerald-800 border-emerald-300",
  alert: "bg-red-100 text-red-800 border-red-300",
}

export function SectionShell({ index, id, title, caption, status, children }: Props) {
  return (
    <section id={id} className="scroll-mt-20">
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-mono text-xs text-muted-foreground tabular-nums">
          {String(index).padStart(2, "0")}
        </span>
        <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
        {status && (
          <Badge variant="outline" className={`font-mono text-xs uppercase ${toneClass[status.tone]}`}>
            {status.label}
          </Badge>
        )}
      </div>
      <p className="mt-1 text-sm text-muted-foreground">{caption}</p>
      <Separator className="my-4" />
      {children}
    </section>
  )
}
