import { useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/lib/utils"

export type TranscriptLine = {
  role: string
  text: string
  final: boolean
  /** position of the turn in the conversation */
  seq: number
  /** reveal word by word; false for a transcript that was already complete when it loaded */
  animate: boolean
}

const reducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false

// Releases a line one word at a time. The call's text arrives in bursts of several words per
// update, so each word gets its own short beat instead, and the beat shortens as a backlog builds
// so the screen stays close behind the live call rather than drifting further back.
function StreamingText({ text, final, animate }: { text: string; final: boolean; animate: boolean }) {
  const words = useMemo(() => text.match(/\S+\s*/g) ?? [], [text])
  const [shown, setShown] = useState(() => (animate && !reducedMotion() ? 0 : words.length))
  const visible = Math.min(shown, words.length)

  useEffect(() => {
    if (shown >= words.length) return
    const backlog = words.length - shown
    const beat = backlog > 12 ? 30 : backlog > 5 ? 60 : 110
    const timer = window.setTimeout(() => setShown((count) => count + 1), beat)
    return () => window.clearTimeout(timer)
  }, [shown, words.length])

  return (
    <p dir="auto" className="text-sm leading-relaxed">
      {words.slice(0, visible).map((word, i) => (
        // one span per whole word, so Arabic letters still join within it
        <span key={i} className={animate ? "motion-safe:animate-in motion-safe:fade-in-0 motion-safe:duration-300" : undefined}>
          {word}
        </span>
      ))}
      {(!final || visible < words.length) && (
        <span
          aria-hidden="true"
          className="ms-1 inline-block size-1.5 rounded-full bg-blue-600 align-middle motion-safe:animate-pulse"
        />
      )}
    </p>
  )
}

type Props = {
  lines: TranscriptLine[]
  /** visible heading for a turn, such as the speaker's name and mark */
  label: (line: TranscriptLine) => ReactNode
  /** the same heading as plain text, for the screen reader announcement */
  speaker: (line: TranscriptLine) => string
  className?: string
}

// The live call as a conversation. It keeps the newest words in view as they stream in; scrolling
// up with a wheel, touch, the keyboard or the scrollbar pauses that, and returning to the bottom
// resumes it. Only finished turns are announced to screen readers, not every word.
export function CallTranscript({ lines, label, speaker, className }: Props) {
  const rootRef = useRef<HTMLDivElement | null>(null)
  const contentRef = useRef<HTMLDivElement | null>(null)
  const follow = useRef(true)

  useEffect(() => {
    const root = rootRef.current
    const content = contentRef.current
    const viewport = content?.closest<HTMLElement>("[data-slot=scroll-area-viewport]")
    if (!root || !content || !viewport) return

    const atBottom = () => viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight < 24
    const toBottom = () =>
      viewport.scrollTo({ top: viewport.scrollHeight, behavior: reducedMotion() ? "auto" : "smooth" })
    // The smooth scroll fires scroll events of its own, so only the operator's input may turn
    // following off; any scroll that lands at the bottom turns it back on.
    const afterUserScroll = () => requestAnimationFrame(() => (follow.current = atBottom()))
    const onScroll = () => {
      if (atBottom()) follow.current = true
    }
    const grew = new ResizeObserver(() => {
      if (follow.current) toBottom()
    })

    grew.observe(content)
    viewport.addEventListener("wheel", afterUserScroll, { passive: true })
    viewport.addEventListener("touchmove", afterUserScroll, { passive: true })
    viewport.addEventListener("keydown", afterUserScroll)
    root.addEventListener("pointerup", afterUserScroll)
    viewport.addEventListener("scroll", onScroll, { passive: true })
    toBottom()
    return () => {
      grew.disconnect()
      viewport.removeEventListener("wheel", afterUserScroll)
      viewport.removeEventListener("touchmove", afterUserScroll)
      viewport.removeEventListener("keydown", afterUserScroll)
      root.removeEventListener("pointerup", afterUserScroll)
      viewport.removeEventListener("scroll", onScroll)
    }
  }, [])

  const lastFinished = [...lines].reverse().find((line) => line.final)

  return (
    <div ref={rootRef} className={cn("flex min-h-0 flex-col", className)}>
      <ScrollArea className="min-h-0 flex-1">
        <div ref={contentRef} className="flex flex-col gap-2.5 pe-3 pb-1">
          {lines.map((line) => (
            <div
              key={line.seq}
              className={cn(
                "flex max-w-[92%] flex-col gap-1 rounded-xl px-3 py-2 ring-1 ring-primary/10",
                line.role === "authority" ? "self-end bg-white/85" : "self-start bg-primary/[0.07]",
              )}
            >
              <span className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">{label(line)}</span>
              <StreamingText text={line.text} final={line.final} animate={line.animate} />
            </div>
          ))}
        </div>
      </ScrollArea>
      <div className="sr-only" aria-live="polite">
        {lastFinished ? `${speaker(lastFinished)}: ${lastFinished.text}` : ""}
      </div>
    </div>
  )
}
