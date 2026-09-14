import jsQR from "jsqr"
import { useEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { readDutyPass, type DutyPass } from "@/lib/pass"
import { cn } from "@/lib/utils"

type Labels = {
  preview: string
  starting: string
  prompt: string
  reading: string
  denied: string
  unavailable: string
  invalid: string
  unreachable: string
  retry: string
}

type Status = "starting" | "scanning" | "reading" | "denied" | "unavailable"

type BarcodeDetectorLike = { detect: (source: CanvasImageSource) => Promise<{ rawValue: string }[]> }

const SCAN_INTERVAL_MS = 150
const FRAME_WIDTH = 640

// Reads a duty pass QR code through the device camera. The camera runs only while this is on
// screen and stops the moment a valid pass is read or the component unmounts. Decoding uses the
// browser's BarcodeDetector where it exists (Chrome on macOS and Android) and jsQR elsewhere,
// which includes Chrome on Windows.
export function PassScanner({ onPass, labels }: { onPass: (pass: DutyPass) => void; labels: Labels }) {
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const onPassRef = useRef(onPass)
  const [status, setStatus] = useState<Status>("starting")
  const [notice, setNotice] = useState<"invalid" | "unreachable" | null>(null)
  const [mirrored, setMirrored] = useState(true)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    onPassRef.current = onPass
  }, [onPass])

  useEffect(() => {
    let cancelled = false
    let stream: MediaStream | null = null
    let timer = 0
    let rejected: string | null = null
    const canvas = document.createElement("canvas")
    const context = canvas.getContext("2d", { willReadFrequently: true })
    const Detector = (window as unknown as { BarcodeDetector?: new (options: { formats: string[] }) => BarcodeDetectorLike })
      .BarcodeDetector
    const detector = Detector ? new Detector({ formats: ["qr_code"] }) : null

    const decode = async (video: HTMLVideoElement): Promise<string | null> => {
      if (!context || !video.videoWidth) return null
      const scale = Math.min(1, FRAME_WIDTH / video.videoWidth)
      canvas.width = Math.round(video.videoWidth * scale)
      canvas.height = Math.round(video.videoHeight * scale)
      context.drawImage(video, 0, 0, canvas.width, canvas.height)
      if (detector) {
        try {
          const codes = await detector.detect(canvas)
          return codes[0]?.rawValue ?? null
        } catch {
          // fall through to jsQR
        }
      }
      const frame = context.getImageData(0, 0, canvas.width, canvas.height)
      return jsQR(frame.data, frame.width, frame.height, { inversionAttempts: "dontInvert" })?.data ?? null
    }

    const tick = async () => {
      if (cancelled) return
      const video = videoRef.current
      const text = video && video.readyState >= 2 ? await decode(video) : null
      if (cancelled) return
      // the same rejected code stays in front of the camera for a while; do not refetch it every frame
      if (text && text !== rejected) {
        setStatus("reading")
        const result = await readDutyPass(text)
        if (cancelled) return
        if (result.ok) {
          setNotice(null)
          onPassRef.current(result.pass)
          return
        }
        rejected = text
        setNotice(result.reason)
        setStatus("scanning")
      }
      timer = window.setTimeout(tick, SCAN_INTERVAL_MS)
    }

    const start = async () => {
      setStatus("starting")
      setNotice(null)
      if (!navigator.mediaDevices?.getUserMedia) {
        setStatus("unavailable")
        return
      }
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "environment", width: { ideal: 1280 }, height: { ideal: 720 } },
          audio: false,
        })
      } catch (error) {
        if (!cancelled) setStatus(error instanceof DOMException && error.name === "NotAllowedError" ? "denied" : "unavailable")
        return
      }
      if (cancelled) {
        stream.getTracks().forEach((track) => track.stop())
        return
      }
      // a laptop's front camera reads more naturally as a mirror; a rear camera should not flip
      setMirrored(stream.getVideoTracks()[0]?.getSettings().facingMode !== "environment")
      const video = videoRef.current
      if (video) {
        video.srcObject = stream
        await video.play().catch(() => {})
      }
      setStatus("scanning")
      void tick()
    }

    void start()
    return () => {
      cancelled = true
      window.clearTimeout(timer)
      stream?.getTracks().forEach((track) => track.stop())
    }
  }, [attempt])

  const blocked = status === "denied" || status === "unavailable"
  const message = blocked
    ? labels[status]
    : status === "starting"
      ? labels.starting
      : status === "reading"
        ? labels.reading
        : notice
          ? labels[notice]
          : labels.prompt

  return (
    <div className="flex flex-col gap-2">
      <div className="relative aspect-video overflow-hidden rounded-xl bg-slate-950 ring-1 ring-primary/15 desk:aspect-auto desk:h-40 desk-short:h-32 desk-tight:h-24">
        <video
          ref={videoRef}
          muted
          playsInline
          aria-label={labels.preview}
          className={cn("size-full object-cover transition-opacity", mirrored && "-scale-x-100", blocked && "opacity-0")}
        />
        {!blocked && (
          <div aria-hidden="true" className="pointer-events-none absolute inset-0 grid place-items-center">
            {/* viewfinder corners and a sweeping line, sized to frame a code held at arm's length */}
            <div className="relative size-28 desk-short:size-24 desk-tight:size-20">
              <span className="absolute inset-s-0 top-0 size-5 rounded-ss-lg border-s-3 border-t-3 border-white/90" />
              <span className="absolute inset-e-0 top-0 size-5 rounded-se-lg border-e-3 border-t-3 border-white/90" />
              <span className="absolute inset-s-0 bottom-0 size-5 rounded-es-lg border-s-3 border-b-3 border-white/90" />
              <span className="absolute inset-e-0 bottom-0 size-5 rounded-ee-lg border-e-3 border-b-3 border-white/90" />
              {status === "scanning" && (
                <span className="absolute inset-x-2 h-0.5 rounded-full bg-sky-300 shadow-[0_0_12px_2px] shadow-sky-300/60 motion-safe:animate-[raqeeb-qr-sweep_2.2s_ease-in-out_infinite]" />
              )}
            </div>
          </div>
        )}
        {blocked && (
          <div className="absolute inset-0 grid place-items-center p-4 text-center">
            <Button type="button" variant="secondary" size="sm" onClick={() => setAttempt((n) => n + 1)} className="h-11 desk:h-8">
              {labels.retry}
            </Button>
          </div>
        )}
      </div>
      <p
        role="status"
        aria-live="polite"
        className={cn(
          "text-center text-xs",
          blocked || notice ? "text-destructive" : "text-muted-foreground",
        )}
      >
        {message}
      </p>
    </div>
  )
}
