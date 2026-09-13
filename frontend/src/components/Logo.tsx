import { cn } from "@/lib/utils"

// A shield holding an open eye: protection and watchfulness, which is what raqeeb means.
// Deliberately carries no national, ministry or company emblem, so it sits equally well in a
// government operations room and a private security firm's console.
export function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className={cn("shrink-0", className)}>
      <path
        d="M16 2.75 26.5 6.6v8.15c0 6.55-4.35 11.9-10.5 14.5-6.15-2.6-10.5-7.95-10.5-14.5V6.6z"
        className="fill-primary"
      />
      <path
        d="M16 4.4 25 7.7v1.1L16 5.5 7 8.8V7.7z"
        className="fill-white/25"
      />
      <path
        d="M8.75 16c1.9-3.1 4.3-4.65 7.25-4.65S21.35 12.9 23.25 16c-1.9 3.1-4.3 4.65-7.25 4.65S10.65 19.1 8.75 16z"
        fill="none"
        strokeWidth="1.7"
        strokeLinejoin="round"
        className="stroke-primary-foreground"
      />
      <circle cx="16" cy="16" r="2.3" className="fill-primary-foreground" />
    </svg>
  )
}
