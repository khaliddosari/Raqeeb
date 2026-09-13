import type { ReactNode } from "react"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

export type Tone = "idle" | "running" | "done" | "malfunction"

type Props = {
  index: number
  id: string
  title: string
  caption: string
  status?: { label: string; tone: Tone }
  className?: string
  children: ReactNode
}

// The conventional status colours operators already read without a legend: grey idle, blue
// running, green done, red malfunction. The dot repeats the state so colour is never the only cue.
const toneClass: Record<Tone, string> = {
  idle: "bg-slate-100 text-slate-700 border-slate-300",
  running: "bg-blue-100 text-blue-900 border-blue-300",
  done: "bg-green-100 text-green-900 border-green-300",
  malfunction: "bg-red-100 text-red-900 border-red-300",
}

const dotClass: Record<Tone, string> = {
  idle: "bg-slate-400",
  running: "bg-blue-600",
  done: "bg-green-600",
  malfunction: "bg-red-600",
}

export function StatusPill({ label, tone, className }: { label: string; tone: Tone; className?: string }) {
  return (
    <Badge
      variant="outline"
      className={cn("shrink-0 gap-1.5 font-mono text-xs uppercase rtl:font-sans", toneClass[tone], className)}
    >
      <span aria-hidden="true" className="relative flex size-1.5">
        {tone === "running" && (
          <span className={cn("absolute inline-flex size-full rounded-full opacity-60 motion-safe:animate-ping", dotClass[tone])} />
        )}
        <span className={cn("relative inline-flex size-1.5 rounded-full", dotClass[tone])} />
      </span>
      {label}
    </Badge>
  )
}

// One glass panel per section. On the desk layout the panel is sized by its grid cell,
// so the body is a shrinkable flex column and anything long scrolls inside it.
export function SectionShell({ index, id, title, caption, status, className, children }: Props) {
  return (
    <section
      id={id}
      className={cn(
        "flex min-h-0 scroll-mt-20 flex-col rounded-2xl bg-card text-card-foreground shadow-(--glass-shadow) ring-1 ring-(--glass-edge) backdrop-blur-xl backdrop-saturate-150 desk:overflow-hidden",
        className,
      )}
    >
      <div className="shrink-0 border-b border-primary/15 px-4 pt-3 pb-2.5 desk:pt-2.5 desk:pb-2">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xl leading-none font-bold text-primary tabular-nums">{index}</span>
          <h2 className="truncate text-base font-semibold tracking-tight">{title}</h2>
          {status && <StatusPill label={status.label} tone={status.tone} className="ms-auto" />}
        </div>
        <p className="mt-0.5 text-xs text-muted-foreground desk:truncate">{caption}</p>
      </div>
      <div className="flex min-h-0 flex-1 flex-col gap-3 p-4 desk:p-3">{children}</div>
    </section>
  )
}
