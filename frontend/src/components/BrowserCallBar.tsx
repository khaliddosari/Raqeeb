import { Mic, MicOff, PhoneOff } from "lucide-react"
import { useCallback, useEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { browserCallResult, browserCallToken } from "@/lib/api"
import { MicrophoneDenied, startBrowserCall, type BrowserCall, type CallLine } from "@/lib/browserCall"
import type { TranscriptLine } from "@/components/CallTranscript"

export type BrowserCallLabels = {
  start: string
  connecting: string
  live: string
  end: string
  ended: string
  denied: string
  failed: string
  hint: string
}

type Phase = "idle" | "connecting" | "live" | "finishing" | "done" | "denied" | "failed"

// Runs the dispatch conversation in this browser and hands its lines up to the dashboard, which
// renders them in the same transcript panel a phone call uses. The decision and the finished
// transcript go back to the server, which closes the incident exactly as the phone path does.
export function BrowserCallBar({
  incidentId,
  labels,
  onLines,
  onFinished,
}: {
  incidentId: string
  labels: BrowserCallLabels
  onLines: (lines: TranscriptLine[]) => void
  onFinished: () => void
}) {
  const [phase, setPhase] = useState<Phase>("idle")
  const callRef = useRef<BrowserCall | null>(null)
  const linesRef = useRef<Map<string, CallLine>>(new Map())
  const decisionRef = useRef<{ confirmed: boolean; statement: string } | null>(null)
  const reportedRef = useRef(false)

  // whatever happens, the microphone stops when this panel goes away
  useEffect(() => () => callRef.current?.stop(), [])

  const ordered = useCallback((): TranscriptLine[] => {
    return [...linesRef.current.values()].map((line, index) => ({
      role: line.role,
      text: line.text,
      final: line.final,
      seq: index,
      animate: true,
    }))
  }, [])

  const report = useCallback(
    async (outcome: "answered" | "failed") => {
      if (reportedRef.current) return
      reportedRef.current = true
      const decision = decisionRef.current
      try {
        await browserCallResult(incidentId, {
          outcome,
          dispatch_confirmed: Boolean(decision?.confirmed),
          authority_statement: decision?.statement ?? "",
          transcript: [...linesRef.current.values()]
            .filter((line) => line.text.trim())
            .map((line) => ({ role: line.role, text: line.text.trim() })),
        })
      } finally {
        onFinished()
      }
    },
    [incidentId, onFinished],
  )

  const start = async () => {
    setPhase("connecting")
    linesRef.current.clear()
    decisionRef.current = null
    reportedRef.current = false
    try {
      const { client_secret, max_seconds } = await browserCallToken(incidentId)
      callRef.current = await startBrowserCall(client_secret, max_seconds, {
        onLine: (line) => {
          linesRef.current.set(line.id, line)
          onLines(ordered())
        },
        onDecision: (decision) => {
          decisionRef.current = decision
        },
        onEnd: () => {
          setPhase("done")
          void report("answered")
        },
      })
      setPhase("live")
    } catch (error) {
      const denied = error instanceof MicrophoneDenied
      setPhase(denied ? "denied" : "failed")
      // an incident whose conversation never happened is held as one that reached no one
      void report("failed")
    }
  }

  const end = () => {
    setPhase("finishing")
    callRef.current?.stop()
  }

  const live = phase === "live" || phase === "finishing"
  const message = {
    idle: labels.hint,
    connecting: labels.connecting,
    live: labels.live,
    finishing: labels.ended,
    done: labels.ended,
    denied: labels.denied,
    failed: labels.failed,
  }[phase]

  return (
    <div className="flex shrink-0 flex-col gap-2">
      {live ? (
        <Button variant="destructive" onClick={end} disabled={phase === "finishing"} className="h-11 w-full sm:h-9">
          <PhoneOff aria-hidden="true" />
          {labels.end}
        </Button>
      ) : (
        phase !== "done" && (
          <Button onClick={start} disabled={phase === "connecting"} className="h-11 w-full sm:h-9">
            {phase === "denied" || phase === "failed" ? <MicOff aria-hidden="true" /> : <Mic aria-hidden="true" />}
            {phase === "connecting" ? labels.connecting : labels.start}
          </Button>
        )
      )}
      <p
        role="status"
        aria-live="polite"
        className={`text-center text-xs ${phase === "denied" || phase === "failed" ? "text-destructive" : "text-muted-foreground"}`}
      >
        {message}
      </p>
    </div>
  )
}
