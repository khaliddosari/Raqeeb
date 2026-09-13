import { useId } from "react"
import { cn } from "@/lib/utils"

// Placeholder artwork for panels that are waiting on the pipeline. Line drawings in the navy
// palette, restrained enough for an operations console. Every drawing is decorative and hidden
// from assistive technology; the text beside it carries the meaning.

type Props = { className?: string }

// An empty scanner: viewfinder corners around a bag, with a sweeping scan line.
export function ScanIllustration({ className }: Props) {
  const glow = useId()
  return (
    <svg viewBox="0 0 160 110" fill="none" aria-hidden="true" className={cn("overflow-visible", className)}>
      <defs>
        <linearGradient id={glow} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="currentColor" stopOpacity="0" />
          <stop offset="1" stopColor="currentColor" stopOpacity="0.16" />
        </linearGradient>
      </defs>
      <g strokeWidth="2.25" strokeLinecap="round" className="stroke-primary/45">
        <path d="M12 30V16a6 6 0 0 1 6-6h14" />
        <path d="M128 10h14a6 6 0 0 1 6 6v14" />
        <path d="M148 80v14a6 6 0 0 1-6 6h-14" />
        <path d="M32 100H18a6 6 0 0 1-6-6V80" />
      </g>
      <path d="M68 38v-6a4 4 0 0 1 4-4h16a4 4 0 0 1 4 4v6" strokeWidth="2" className="stroke-primary/35" />
      <rect x="42" y="38" width="76" height="50" rx="8" strokeWidth="2" className="fill-white/70 stroke-primary/35" />
      <rect x="52" y="48" width="18" height="30" rx="3" className="fill-primary/10" />
      <rect x="76" y="50" width="32" height="10" rx="3" className="fill-primary/10" />
      <rect x="76" y="66" width="20" height="12" rx="3" className="fill-primary/15" />
      <circle cx="102" cy="72" r="5" className="fill-primary/10" />
      <g className="text-primary motion-safe:animate-[raqeeb-scan_3.2s_ease-in-out_infinite]">
        <rect x="22" y="44" width="116" height="14" fill={`url(#${glow})`} />
        <path d="M22 58h116" strokeWidth="1.5" strokeLinecap="round" className="stroke-primary/60" />
      </g>
    </svg>
  )
}

// A filed report: a stacked sheet with a title bar, text lines, a record table and a seal.
export function ReportIllustration({ className }: Props) {
  return (
    <svg viewBox="0 0 160 110" fill="none" aria-hidden="true" className={className}>
      <rect x="58" y="6" width="62" height="84" rx="7" strokeWidth="1.5" className="fill-white/40 stroke-primary/15" />
      <rect x="46" y="14" width="62" height="88" rx="7" strokeWidth="2" className="fill-white/80 stroke-primary/30" />
      <rect x="55" y="24" width="28" height="6" rx="3" className="fill-primary/40" />
      <rect x="55" y="36" width="44" height="4" rx="2" className="fill-primary/12" />
      <rect x="55" y="45" width="36" height="4" rx="2" className="fill-primary/12" />
      <g strokeWidth="1.5" className="stroke-primary/15">
        <rect x="55" y="56" width="44" height="30" rx="3" />
        <path d="M55 66h44M55 76h44M71 56v30" />
      </g>
      <circle cx="106" cy="88" r="12" className="fill-primary" />
      <path d="m100.5 88 4 4 7-8" strokeWidth="2.25" strokeLinecap="round" strokeLinejoin="round" className="stroke-primary-foreground" />
    </svg>
  )
}

// A line waiting to connect: a handset between two quiet waveforms.
export function CallIllustration({ className }: Props) {
  const bars = [8, 14, 22, 12, 28, 16, 10]
  return (
    <svg viewBox="0 0 160 110" fill="none" aria-hidden="true" className={className}>
      {[...bars].reverse().map((h, i) => (
        <rect key={`l${i}`} x={14 + i * 7} y={55 - h / 2} width="3.5" height={h} rx="1.75" className="fill-primary/20" />
      ))}
      {bars.map((h, i) => (
        <rect key={`r${i}`} x={118 + i * 7} y={55 - h / 2} width="3.5" height={h} rx="1.75" className="fill-primary/20" />
      ))}
      <circle cx="80" cy="55" r="30" strokeWidth="1.5" strokeDasharray="3 5" className="stroke-primary/25" />
      <circle cx="80" cy="55" r="21" strokeWidth="2" className="fill-white/80 stroke-primary/30" />
      {/* Lucide's phone glyph, 24 units square, centred on the dial */}
      <path
        d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="stroke-primary"
        transform="translate(68 43)"
      />
    </svg>
  )
}

// A reasoning trail: three steps on a timeline, the last one still open, and a shield.
export function JudgmentIllustration({ className }: Props) {
  return (
    <svg viewBox="0 0 160 110" fill="none" aria-hidden="true" className={className}>
      <path d="M40 24v60" strokeWidth="2" strokeDasharray="2 4" strokeLinecap="round" className="stroke-primary/25" />
      {[24, 54].map((y) => (
        <g key={y}>
          <circle cx="40" cy={y} r="7" className="fill-primary/80" />
          <path d={`m36.8 ${y} 2.2 2.2 4.2-4.4`} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" className="stroke-primary-foreground" />
          <rect x="54" y={y - 6} width="34" height="5" rx="2.5" className="fill-primary/30" />
          <rect x="54" y={y + 3} width="24" height="4" rx="2" className="fill-primary/12" />
        </g>
      ))}
      <circle cx="40" cy="84" r="7" strokeWidth="2" strokeDasharray="3 3" className="fill-white/80 stroke-primary/40" />
      <rect x="54" y="78" width="30" height="5" rx="2.5" className="fill-primary/15" />
      <rect x="54" y="87" width="20" height="4" rx="2" className="fill-primary/10" />
      <path
        d="M122 26 140 33v14c0 11.5-7.6 20.8-18 25.5-10.4-4.7-18-14-18-25.5V33z"
        strokeWidth="2"
        className="fill-white/80 stroke-primary/35"
      />
      <path d="M122 34 133 38.2v9c0 7.2-4.6 13-11 16.2-6.4-3.2-11-9-11-16.2v-9z" className="fill-primary/10" />
      <path d="m116.5 48 4 4 7.5-8" strokeWidth="2.25" strokeLinecap="round" strokeLinejoin="round" className="stroke-primary/70" />
    </svg>
  )
}
