import { DirectionProvider } from "@base-ui/react/direction-provider"
import { MapPin, Pause as PauseIcon, Play as PlayIcon } from "lucide-react"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { AgencyMark } from "@/components/AgencyMark"
import { CallTranscript, type TranscriptLine } from "@/components/CallTranscript"
import {
  CallIllustration,
  JudgmentIllustration,
  ReportIllustration,
  ScanIllustration,
  TimelineIllustration,
} from "@/components/Illustrations"
import { Logo } from "@/components/Logo"
import { SectionShell, StatusPill, type Tone } from "@/components/SectionShell"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Progress } from "@/components/ui/progress"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  detect,
  getIncident,
  monitorSocket,
  submitInfo,
  uploadsUrl,
  verify,
  type Incident,
  type MonitorEvent,
} from "@/lib/api"
import { isAgency } from "@/lib/agency"
import { applyDocumentLang, initialLang, rememberLang, STRINGS, type Lang } from "@/lib/i18n"
import { CHECKPOINT_LOCATIONS, normalizeSaudiMobile, type CheckpointLocation } from "@/lib/intake"
import { toPlainText } from "@/lib/plaintext"
import { cn } from "@/lib/utils"

// Each person's own spelling, in both languages.
const TEAM: { name: Record<Lang, string>; url: string }[] = [
  { name: { en: "Khalid Al Dosari", ar: "خالد آل دوسري" }, url: "https://www.linkedin.com/in/khalid-al-dosari/" },
  { name: { en: "Nawaf Alsharani", ar: "نواف الشهراني" }, url: "https://www.linkedin.com/in/nawaf-alsharani-a431b731a/" },
  { name: { en: "Yazeed Bin Shihah", ar: "يزيد بن شيحة" }, url: "https://www.linkedin.com/in/yazeed-bin-shihah-57aa1b309/" },
  { name: { en: "Omar Al-Dhawyan", ar: "عمر الضويان" }, url: "https://www.linkedin.com/in/omar-al-dhawyan-789336269/" },
]

const RIYADH_TIME = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Riyadh",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
})

const TEST_IMAGE_URL = `${import.meta.env.BASE_URL}test-image.png`

// Prefilled demo values, Arabic in both interface languages: everything that reaches the call is Arabic.
const PREFILL = {
  employee: "خالد آل دوسري",
  suspectName: "فيصل",
  suspectId: "1093847562",
  notes: "المشتبه به متعاون وهادئ",
}

const percent = (fraction: number | null | undefined) => (fraction == null ? "—" : `${(fraction * 100).toFixed(2)}%`)

const PIPELINE = ["detected", "pending_verification", "verified", "report_sent", "call_in_progress", "closed"]

function StatusDot({ tone }: { tone: Tone }) {
  const color = { idle: "bg-slate-400", running: "bg-blue-600", done: "bg-green-600", malfunction: "bg-red-600" }[tone]
  return (
    <span className="relative flex size-2">
      {tone === "running" && (
        <span className={`absolute inline-flex size-full rounded-full ${color} opacity-60 motion-safe:animate-ping`} />
      )}
      <span className={`relative inline-flex size-2 rounded-full ${color}`} />
    </span>
  )
}

// Where an incident's status sits on the four universal states.
function pipelineTone(status: string | undefined): Tone {
  if (!status || status === "false_positive") return "idle"
  if (status === "report_send_failed" || status === "closed_unconfirmed") return "malfunction"
  if (status === "closed") return "done"
  return "running"
}

// Placeholder for a panel still waiting on the pipeline: artwork, a short heading and what fills it.
// At desk the box is a size container, so on a short window it sheds the artwork and then the
// description rather than making an empty panel scroll.
function Placeholder({ art, title, body }: { art: React.ReactNode; title: string; body: string }) {
  return (
    <div className="flex min-h-0 flex-col desk:flex-1 desk:@container-size desk:[container-name:placeholder]">
      <Empty className="min-h-0 gap-2 overflow-hidden p-4 box-micro:hidden desk:p-2">
        <EmptyHeader className="gap-1.5">
          <EmptyMedia className="mb-1 text-primary box-short:hidden">{art}</EmptyMedia>
          <EmptyTitle role="heading" aria-level={3} className="text-sm font-semibold">
            {title}
          </EmptyTitle>
          <EmptyDescription className="text-xs/relaxed box-tiny:hidden">{body}</EmptyDescription>
        </EmptyHeader>
      </Empty>
    </div>
  )
}

// A label over its value, one line each (or a fixed number of lines), so a grid of them has a
// known height and a panel of facts never needs to scroll. The full value stays in the tooltip.
function RecordItem({
  label,
  children,
  title,
  className,
  lines,
}: {
  label: string
  children: React.ReactNode
  title?: string
  className?: string
  lines?: 2
}) {
  return (
    <div className={cn("min-w-0", className)}>
      <dt className="truncate text-xs text-muted-foreground">{label}</dt>
      <dd
        className={cn("mt-0.5 text-sm leading-snug font-medium", lines === 2 ? "line-clamp-2 desk-tight:line-clamp-1" : "truncate")}
        title={title}
      >
        {children}
      </dd>
    </div>
  )
}

export default function App() {
  const [lang, setLang] = useState<Lang>(initialLang)
  const t = STRINGS[lang]
  const [employeeName, setEmployeeName] = useState(PREFILL.employee)
  // Required: the employee's identifier on the report, and the mobile the dispatch call rings.
  const [employeePhone, setEmployeePhone] = useState("")
  const [location, setLocation] = useState<CheckpointLocation>(CHECKPOINT_LOCATIONS[0])
  const [file, setFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [annotated, setAnnotated] = useState<string | null>(null)
  const [loadedSrc, setLoadedSrc] = useState<string | null>(null)
  const [incident, setIncident] = useState<Incident | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [feed, setFeed] = useState<MonitorEvent[]>([])
  const [clock, setClock] = useState(() => new Date())
  const socketRef = useRef<WebSocket | null>(null)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const [playing, setPlaying] = useState(true)
  const [suspectName, setSuspectName] = useState(PREFILL.suspectName)
  const [suspectId, setSuspectId] = useState(PREFILL.suspectId)
  const [suspectNotes, setSuspectNotes] = useState(PREFILL.notes)

  useEffect(() => {
    applyDocumentLang(lang)
    document.title = t.docTitle
    rememberLang(lang)
  }, [lang, t])

  useEffect(() => {
    const timer = setInterval(() => setClock(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])

  const toggleVideo = useCallback(() => {
    const v = videoRef.current
    if (!v) return
    // play() rejects when autoplay is blocked; onPlay/onPause drive the icon, so
    // swallowing the rejection keeps the button honest either way.
    if (v.paused) void v.play().catch(() => {})
    else v.pause()
  }, [])

  const refresh = useCallback(async (id: string) => {
    try {
      setIncident(await getIncident(id))
    } catch (e) {
      setError(String(e))
    }
  }, [])

  // One socket per incident, carrying status changes, call transcript and the dispatch
  // decision. Closed and reopened whenever the incident changes.
  useEffect(() => {
    if (!incident?.id) return
    const ws = monitorSocket(incident.id)
    socketRef.current = ws
    ws.onmessage = (ev) => {
      const parsed: MonitorEvent = JSON.parse(ev.data)
      if (parsed.type === "ping") return
      setFeed((prev) => [...prev, parsed])
      if (parsed.type === "status" || parsed.type === "dispatch") void refresh(incident.id)
    }
    return () => {
      ws.close()
      socketRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [incident?.id])

  const phoneE164 = normalizeSaudiMobile(employeePhone)
  const phoneInvalid = employeePhone.trim() !== "" && phoneE164 === null

  const onFile = (f: File | null) => {
    setFile(f)
    setAnnotated(null)
    setPreviewUrl(f ? URL.createObjectURL(f) : null)
  }

  const runDetection = async () => {
    if (!file) return
    setBusy("detect")
    setError(null)
    setFeed([])
    setSuspectName(PREFILL.suspectName)
    setSuspectId(PREFILL.suspectId)
    setSuspectNotes(PREFILL.notes)
    try {
      const res = await detect(file, employeeName, phoneE164, location)
      if (res.annotated_filename) setAnnotated(uploadsUrl(res.annotated_filename))
      await refresh(res.incident_id)
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(null)
    }
  }

  const runTestImage = async () => {
    setBusy("detect")
    setError(null)
    setFeed([])
    setSuspectName(PREFILL.suspectName)
    setSuspectId(PREFILL.suspectId)
    setSuspectNotes(PREFILL.notes)
    try {
      const blob = await (await fetch(TEST_IMAGE_URL)).blob()
      const testFile = new File([blob], "test-image.png", { type: blob.type || "image/png" })
      setFile(testFile)
      setPreviewUrl(TEST_IMAGE_URL)
      setAnnotated(null)
      const res = await detect(testFile, employeeName, phoneE164, location)
      if (res.annotated_filename) setAnnotated(uploadsUrl(res.annotated_filename))
      await refresh(res.incident_id)
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(null)
    }
  }

  const act = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label)
    setError(null)
    try {
      await fn()
      if (incident) await refresh(incident.id)
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(null)
    }
  }

  const stageIndex = useMemo(() => {
    if (!incident) return -1
    const i = PIPELINE.indexOf(incident.status)
    return i === -1 ? 0 : i
  }, [incident])

  // Live lines are re-sent whole as they grow, keyed by item_id: keep the latest version of each
  // and order by seq, the turn's place in the conversation, since the authority's words are often
  // transcribed after the agent has already started answering. Lines without an id (the
  // audio-bridged call path) are appended in arrival order. After a restart, the stored
  // transcript stands in.
  const transcript = useMemo<TranscriptLine[]>(() => {
    const keyed = new Map<string, TranscriptLine>()
    const loose: TranscriptLine[] = []
    let arrival = 0
    for (const event of feed) {
      if (event.type !== "transcript") continue
      arrival += 1
      const line = { role: event.role, text: event.text, final: event.final ?? true, seq: event.seq ?? arrival, animate: true }
      if (event.item_id) keyed.set(event.item_id, line)
      else loose.push(line)
    }
    const live = [...keyed.values(), ...loose].sort((a, b) => a.seq - b.seq)
    if (live.length) return live
    return (incident?.authority_response?.raw_transcript ?? []).map((line, i) => ({
      ...line,
      final: true,
      seq: i,
      animate: false,
    }))
  }, [feed, incident])

  const dispatch = incident?.authority_response
  const report = incident?.report
  const confidencePct = ((incident?.detection_confidence ?? 0) * 100).toFixed(2)
  const agency = incident && isAgency(incident.authority_agency) ? incident.authority_agency : null
  const authorityName = (lang === "ar" && incident?.authority_name_ar) || incident?.authority_name || null

  // Each panel's pill, on the universal idle / running / done / malfunction scale.
  const inferenceStatus: { label: string; tone: Tone } =
    busy === "detect"
      ? { label: t.inference.analysing, tone: "running" }
      : incident
        ? { label: t.detectionClass(incident.detection_class ?? ""), tone: "done" }
        : error
          ? { label: t.inference.failed, tone: "malfunction" }
          : { label: t.inference.awaiting, tone: "idle" }
  const reportStatus: { label: string; tone: Tone } = report
    ? incident?.status === "report_send_failed"
      ? { label: t.report.sendFailed, tone: "malfunction" }
      : { label: t.report.generated, tone: "done" }
    : busy === "info"
      ? { label: t.report.generating, tone: "running" }
      : { label: t.report.pending, tone: "idle" }
  const callStatus: { label: string; tone: Tone } = incident?.call_sid
    ? ["closed", "closed_unconfirmed"].includes(incident.status)
      ? { label: t.call.ended, tone: "done" }
      : { label: t.call.inProgress, tone: "running" }
    : { label: t.call.noCall, tone: "idle" }
  const judgmentStatus: { label: string; tone: Tone } = dispatch?.dispatch_confirmed
    ? { label: t.judgment.dispatchConfirmedPill, tone: "done" }
    : incident?.status === "closed_unconfirmed"
      ? { label: t.judgment.notConfirmedPill, tone: "malfunction" }
      : incident?.status === "false_positive"
        ? { label: t.status("false_positive"), tone: "idle" }
        : incident
          ? { label: t.judgment.awaitingDecision, tone: "running" }
          : { label: t.judgment.pending, tone: "idle" }

  return (
    <DirectionProvider direction={lang === "ar" ? "rtl" : "ltr"}>
      <div className="min-h-screen text-foreground desk:flex desk:h-dvh desk:flex-col desk:overflow-hidden">
        {/* Sticky only from lg: on a phone the header wraps to two rows of names and would pin a
            third of the screen, so it scrolls away with the page there. */}
        <header className="z-20 border-b border-primary/10 bg-background/65 backdrop-blur-xl backdrop-saturate-150 lg:sticky lg:top-0 desk:static desk:shrink-0">
          {/* From lg the header is three columns with equal outer tracks, so the team sits on the page's
              true centre rather than midway between a narrow brand and a wide clock. */}
          <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 lg:grid lg:grid-cols-[1fr_auto_1fr] desk:h-12 desk:max-w-[112rem] desk:py-0">
            <div className="flex min-w-0 items-center gap-2 lg:justify-self-start">
              <Logo className="size-8 drop-shadow-sm" />
              <h1 className="font-brand text-xl leading-none font-black">{t.brand}</h1>
            </div>

            {/* its own full-width row under the brand until there is room to sit inline */}
            <nav
              aria-label={t.team}
              className="order-last flex w-full flex-wrap items-center justify-center gap-x-6 gap-y-1 lg:order-0 lg:w-auto"
            >
              {TEAM.map((m) => (
                <a
                  key={m.url}
                  href={m.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  title={t.onLinkedIn(m.name[lang])}
                  className="inline-block py-1 text-sm font-bold text-foreground underline-offset-4 transition-colors hover:text-primary hover:underline"
                >
                  {m.name[lang]}
                </a>
              ))}
            </nav>

            <div className="ms-auto flex items-center gap-3 lg:ms-0 lg:justify-self-end">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setLang(t.switchToLang)}
                aria-label={t.switchToLabel}
                className="h-10 bg-white/70 px-3 text-sm lg:h-8"
              >
                <span lang={t.switchToLang}>{t.switchTo}</span>
              </Button>
              <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <span className="font-mono tabular-nums">{RIYADH_TIME.format(clock)}</span>
                <span>{t.timeZone}</span>
              </span>
            </div>
          </div>
        </header>

        {/* Below the desk breakpoint this is a scrolling column of panels. At desk it locks to the
            viewport: the live preview and the inference workspace share the top row, and the three
            downstream stages sit along the bottom in pipeline order. In Arabic the grid mirrors. */}
        <main className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-6 sm:py-8 desk:grid desk:min-h-0 desk:max-w-[112rem] desk:flex-1 desk:grid-cols-3 desk:grid-rows-[minmax(0,1.35fr)_minmax(0,1fr)] desk:gap-3 desk:py-3">
          {error && (
            <Alert
              variant="destructive"
              onClick={() => setError(null)}
              title={t.dismiss}
              className="cursor-pointer text-start desk:fixed desk:top-14 desk:left-1/2 desk:z-30 desk:w-[min(40rem,calc(100vw-2rem))] desk:-translate-x-1/2 desk:bg-white/95 desk:shadow-lg desk:backdrop-blur-xl"
            >
              <AlertDescription dir="ltr" className="font-mono text-xs break-all">
                {error}
              </AlertDescription>
            </Alert>
          )}

          {/* 01 PREVIEW */}
          <SectionShell
            index={1}
            id="preview"
            title={t.preview.title}
            caption={t.preview.caption}
            status={playing ? { label: t.preview.status, tone: "running" } : { label: t.preview.paused, tone: "idle" }}
            className="desk:col-start-1 desk:row-start-1"
          >
            <div className="relative overflow-hidden rounded-xl bg-black desk:min-h-0 desk:flex-1">
              <video
                ref={videoRef}
                src={`${import.meta.env.BASE_URL}test_clip_tracked.mp4`}
                autoPlay
                loop
                muted
                playsInline
                onPlay={() => setPlaying(true)}
                onPause={() => setPlaying(false)}
                onClick={toggleVideo}
                className="block aspect-960/580 w-full cursor-pointer object-cover desk:aspect-auto desk:h-full"
              />
              <Button
                type="button"
                size="icon"
                variant="secondary"
                onClick={toggleVideo}
                aria-label={playing ? t.preview.pause : t.preview.play}
                className="absolute inset-s-4 bottom-4 size-12 rounded-full opacity-90 shadow-sm transition hover:opacity-100 focus-visible:opacity-100 desk:inset-s-3 desk:bottom-3 desk:size-10"
              >
                {playing ? <PauseIcon className="size-5" /> : <PlayIcon className="size-5" />}
              </Button>
            </div>
            <p className="shrink-0 text-xs leading-relaxed text-muted-foreground">{t.preview.description}</p>
          </SectionShell>

          {/* 02 INFERENCE */}
          <SectionShell
            index={2}
            id="inference"
            title={t.inference.title}
            caption={t.inference.caption}
            status={inferenceStatus}
            className="desk:col-span-2 desk:col-start-2 desk:row-start-1"
          >
            <div className="grid gap-3 md:grid-cols-2 desk:min-h-0 desk:flex-1 desk:grid-cols-[minmax(0,1fr)_minmax(0,1.45fr)_minmax(0,1fr)] desk:grid-rows-[minmax(0,1fr)]">
              {/* input */}
              <ScrollArea className="desk:h-full desk:min-h-0">
                <div className="flex flex-col gap-3 desk:gap-2 desk:p-1 desk:pe-3 desk-short:gap-1">
                  <div className="grid gap-1.5 desk:gap-1">
                    <Label htmlFor="emp-name">{t.inference.employee}</Label>
                    <Input
                      id="emp-name"
                      value={employeeName}
                      onChange={(e) => setEmployeeName(e.target.value)}
                      autoComplete="name"
                      className="h-11 text-center desk:h-8"
                    />
                  </div>
                  <div className="grid gap-1.5 desk:gap-1">
                    <Label htmlFor="emp-phone">
                      {t.inference.employeeNumber}
                      <span aria-hidden="true" className="text-destructive">
                        *
                      </span>
                    </Label>
                    <Input
                      id="emp-phone"
                      type="tel"
                      inputMode="tel"
                      autoComplete="tel"
                      dir="ltr"
                      value={employeePhone}
                      onChange={(e) => setEmployeePhone(e.target.value)}
                      placeholder={t.inference.employeeNumberPlaceholder}
                      required
                      aria-invalid={phoneInvalid || undefined}
                      aria-describedby="emp-phone-help"
                      className="h-11 text-center font-mono tabular-nums desk:h-8"
                    />
                    <p
                      id="emp-phone-help"
                      className={
                        phoneInvalid ? "text-xs text-destructive" : "text-xs text-muted-foreground desk:sr-only"
                      }
                    >
                      {phoneInvalid ? t.inference.employeeNumberInvalid : t.inference.employeeNumberHelp}
                    </p>
                  </div>
                  <div className="grid gap-1.5 desk:gap-1">
                    <Label id="location-label" className="desk-short:sr-only">{t.inference.location}</Label>
                    <Select value={location} onValueChange={(v) => v && setLocation(v as CheckpointLocation)}>
                      <SelectTrigger
                        aria-labelledby="location-label"
                        className="w-full data-[size=default]:h-11 desk:data-[size=default]:h-8"
                      >
                        <SelectValue className="justify-center gap-1.5 text-center">
                          {(value: string) => (
                            <>
                              <MapPin aria-hidden="true" className="size-3.5 text-primary" />
                              {t.location(value)}
                            </>
                          )}
                        </SelectValue>
                      </SelectTrigger>
                      <SelectContent>
                        {CHECKPOINT_LOCATIONS.map((value) => (
                          <SelectItem key={value} value={value} className="min-h-10 desk:min-h-0">
                            {t.location(value)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="grid gap-1.5 desk:gap-1">
                    <Label htmlFor="frame" className="desk-short:sr-only">{t.inference.frame}</Label>
                    {/* The native picker's "Choose File / No file chosen" is browser chrome that follows the
                        OS language, not the page. The real input stays for keyboard and screen readers, and
                        announces the chosen file through frame-status; the pill is its visible face. */}
                    <input
                      id="frame"
                      type="file"
                      accept="image/*"
                      aria-describedby="frame-status"
                      className="peer sr-only"
                      onChange={(e) => onFile(e.target.files?.[0] ?? null)}
                    />
                    <label
                      htmlFor="frame"
                      aria-hidden="true"
                      className="font-ornate flex h-11 w-full min-w-0 cursor-pointer items-center justify-center rounded-lg bg-secondary px-3 text-sm font-medium text-secondary-foreground ring-1 ring-primary/15 transition-colors hover:bg-accent peer-focus-visible:ring-3 peer-focus-visible:ring-ring/50 desk:h-8"
                    >
                      <span className="truncate">{t.inference.chooseFile}</span>
                    </label>
                    <span id="frame-status" className="sr-only">
                      {file ? file.name : t.inference.noFile}
                    </span>
                  </div>
                  <Button onClick={runDetection} disabled={!file || busy !== null || !phoneE164} className="h-11 w-full desk:h-8">
                    {busy === "detect" ? t.inference.runningDetection : t.inference.runDetection}
                  </Button>

                  {/* the bundled frame: its thumbnail beside the button, at every size */}
                  <div className="flex flex-row-reverse items-center gap-2.5 rounded-xl bg-white/55 p-2.5 ring-1 ring-primary/12 desk-short:p-2">
                    <div className="flex min-w-0 flex-1 flex-col gap-1.5">
                      <Button
                        variant="secondary"
                        onClick={runTestImage}
                        disabled={busy !== null || !phoneE164}
                        className="h-11 w-full desk:h-8"
                      >
                        {busy === "detect" ? t.inference.runningTest : t.inference.runTest}
                      </Button>
                      <p className="text-xs text-muted-foreground desk:hidden">{t.inference.testCaption}</p>
                    </div>
                    <button
                      type="button"
                      onClick={runTestImage}
                      disabled={busy !== null || !phoneE164}
                      aria-label={t.inference.testAria}
                      className="w-24 shrink-0 overflow-hidden rounded-lg ring-1 ring-primary/12 disabled:cursor-not-allowed desk-short:w-16"
                    >
                      <img
                        src={TEST_IMAGE_URL}
                        alt={t.inference.testAlt}
                        className="block aspect-3/2 w-full cursor-pointer bg-white object-cover transition hover:opacity-90"
                      />
                    </button>
                  </div>
                </div>
              </ScrollArea>

              {/* output */}
              <div className="flex min-h-0 flex-col overflow-hidden rounded-xl bg-white/55 ring-1 ring-primary/12 desk:h-full">
                <div className="flex shrink-0 items-center justify-between gap-2 border-b border-primary/10 px-3 py-2 text-xs">
                  <h3 className="font-semibold">{annotated ? t.inference.annotatedOutput : t.inference.input}</h3>
                  {incident && <span className="truncate font-mono text-muted-foreground">{incident.id}</span>}
                </div>
                {/* at desk the image is positioned into this box so object-contain can fit it to any height */}
                <div className="relative flex min-h-56 flex-1 items-center justify-center p-2 desk:min-h-0">
                  {busy === "detect" ? (
                    <Skeleton className="h-52 w-full desk:absolute desk:inset-2 desk:h-auto desk:w-auto" />
                  ) : annotated ? (
                    <>
                      {loadedSrc !== annotated && <Skeleton className="absolute inset-2" />}
                      <img
                        src={annotated}
                        alt={t.inference.annotatedAlt}
                        onLoad={() => setLoadedSrc(annotated)}
                        className={`block w-full rounded-md object-contain transition-opacity duration-300 desk:absolute desk:inset-2 desk:size-[calc(100%-1rem)] ${
                          loadedSrc === annotated ? "opacity-100" : "opacity-0"
                        }`}
                      />
                    </>
                  ) : previewUrl ? (
                    <img
                      src={previewUrl}
                      alt={t.inference.selectedAlt}
                      className="block w-full rounded-md object-contain opacity-70 desk:absolute desk:inset-2 desk:size-[calc(100%-1rem)]"
                    />
                  ) : (
                    <ScanIllustration className="w-44 max-w-[70%] text-primary desk:max-h-[80%]" />
                  )}
                </div>
                {incident?.detection_class && (
                  <div className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1.5 border-t border-primary/10 px-3 py-2">
                    <Badge className="font-mono text-xs uppercase rtl:font-sans">{t.detectionClass(incident.detection_class)}</Badge>
                    <span className="text-xs tabular-nums text-muted-foreground">{t.inference.confidence(confidencePct)}</span>
                    {agency && (
                      <span className="ms-auto flex items-center gap-1.5 text-xs">
                        <span className="text-muted-foreground">{t.inference.routesTo}</span>
                        <AgencyMark agency={agency} className="size-6" />
                        <span className="font-semibold">{t.agency(agency)}</span>
                      </span>
                    )}
                  </div>
                )}
              </div>

              {/* verification */}
              <ScrollArea className="md:col-span-2 desk:col-span-1 desk:h-full desk:min-h-0">
                <div className="flex flex-col gap-3 desk:p-1 desk:pe-3">
                  <div className="flex flex-col gap-2 rounded-xl bg-white/55 p-3 ring-1 ring-primary/12">
                    <div className="flex items-center justify-between gap-2 text-xs">
                      <h3 className="font-semibold">{t.inference.pipeline}</h3>
                      <StatusPill label={t.status(incident?.status ?? "idle")} tone={pipelineTone(incident?.status)} />
                    </div>
                    <Progress
                      aria-label={t.inference.pipeline}
                      value={stageIndex >= 0 ? ((stageIndex + 1) / PIPELINE.length) * 100 : 0}
                    />
                    {!incident && (
                      <div className="flex flex-col items-center gap-2 py-2 text-center">
                        <TimelineIllustration className="w-full max-w-56 text-primary desk-short:max-w-40" />
                        <p className="text-xs text-muted-foreground">{t.inference.openIncident}</p>
                      </div>
                    )}
                    {incident?.status === "pending_verification" && (
                      <div className="flex flex-wrap gap-2 pt-1">
                        <Button
                          size="sm"
                          className="h-11 flex-1 text-sm sm:h-8"
                          onClick={() => act("verify", () => verify(incident.id, true))}
                          disabled={busy !== null}
                        >
                          {t.inference.confirm}
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-11 flex-1 text-sm sm:h-8"
                          onClick={() => act("verify", () => verify(incident.id, false))}
                          disabled={busy !== null}
                        >
                          {t.inference.falsePositive}
                        </Button>
                      </div>
                    )}
                    {incident?.status === "false_positive" && (
                      <p className="text-xs text-muted-foreground">{t.inference.falsePositiveClosed}</p>
                    )}
                    {incident && !["pending_verification", "verified", "false_positive"].includes(incident.status) && (
                      <p className="text-xs text-muted-foreground">{t.inference.submitted}</p>
                    )}
                  </div>

                  {incident?.status === "verified" && (
                    <form
                      className="flex flex-col gap-3 rounded-xl bg-white/55 p-3 ring-1 ring-primary/12"
                      onSubmit={(e) => {
                        e.preventDefault()
                        void act("info", () =>
                          submitInfo(incident.id, suspectName.trim(), suspectId.trim(), suspectNotes.trim() || undefined),
                        )
                      }}
                    >
                      <div>
                        <h3 className="text-sm font-semibold">{t.inference.suspectDetails}</h3>
                        <p className="mt-0.5 text-xs text-muted-foreground">{t.inference.suspectHelp}</p>
                      </div>
                      <div className="grid gap-3 sm:grid-cols-2 desk:grid-cols-1">
                        <div className="grid gap-1.5">
                          <Label htmlFor="suspect-name">{t.inference.fullName}</Label>
                          <Input
                            id="suspect-name"
                            value={suspectName}
                            onChange={(e) => setSuspectName(e.target.value)}
                            placeholder={t.inference.fullNamePlaceholder}
                            autoComplete="off"
                            className="text-center"
                          />
                        </div>
                        <div className="grid gap-1.5">
                          <Label htmlFor="suspect-id">{t.inference.idNumber}</Label>
                          <Input
                            id="suspect-id"
                            value={suspectId}
                            onChange={(e) => setSuspectId(e.target.value)}
                            placeholder={t.inference.idNumberPlaceholder}
                            inputMode="numeric"
                            autoComplete="off"
                            dir="ltr"
                            className="text-center font-mono"
                          />
                        </div>
                      </div>
                      <div className="grid gap-1.5">
                        <Label htmlFor="suspect-notes">{t.inference.notes}</Label>
                        <Input
                          id="suspect-notes"
                          value={suspectNotes}
                          onChange={(e) => setSuspectNotes(e.target.value)}
                          placeholder={t.inference.notesPlaceholder}
                          autoComplete="off"
                          dir="auto"
                          className="text-center"
                        />
                      </div>
                      <Button
                        type="submit"
                        className="h-11 w-full sm:h-9"
                        disabled={busy !== null || !suspectName.trim() || !suspectId.trim()}
                      >
                        {busy === "info" ? t.inference.generating : t.inference.submit}
                      </Button>
                    </form>
                  )}
                </div>
              </ScrollArea>
            </div>
          </SectionShell>

          {/* 03 REPORT */}
          <SectionShell
            index={3}
            id="report"
            title={t.report.title}
            caption={t.report.caption}
            status={reportStatus}
            className="desk:col-start-1 desk:row-start-2"
          >
            {report ? (
              <Tabs defaultValue="record" className="min-h-0 gap-2 desk:flex-1">
                <div className="flex shrink-0 items-center justify-between gap-2">
                  {/* the triggers fill the list minus its padding, so 52px here gives 44px tap targets */}
                  <TabsList className="h-13! shrink-0 desk:h-8!">
                    <TabsTrigger value="record">{t.report.record}</TabsTrigger>
                    <TabsTrigger value="narrative">{t.report.narrative}</TabsTrigger>
                  </TabsList>
                  <span dir="ltr" className="truncate font-mono text-xs text-muted-foreground" title={report.incident_id}>
                    {report.incident_id}
                  </span>
                </div>
                {/* Base UI makes each tab panel a tab stop, as the tabs pattern expects; the shadcn panel
                    removes its outline, so the ring is put back here */}
                <TabsContent value="record" className="min-h-0 rounded-lg focus-visible:ring-3 focus-visible:ring-ring/50">
                  {/* one line per value in a tight grid, so the whole record reads without scrolling */}
                  <dl className="grid grid-cols-2 gap-x-3 gap-y-2 sm:grid-cols-3 desk-short:grid-cols-4 desk-short:gap-y-1.5">
                    <RecordItem label={t.report.detectedItem}>{t.detectionClass(report.detected_item)}</RecordItem>
                    <RecordItem label={t.report.confidence}>
                      <bdi className="tabular-nums">{percent(report.yolo_confidence)}</bdi>
                    </RecordItem>
                    <RecordItem label={t.report.severity}>
                      <Badge variant="outline" className="text-xs">
                        {t.severity(report.severity)}
                      </Badge>
                    </RecordItem>
                    <RecordItem label={t.report.location}>{t.location(report.location)}</RecordItem>
                    <RecordItem label={t.report.notified}>
                      {agency ? (
                        <span className="inline-flex items-center gap-1.5 align-middle">
                          <AgencyMark agency={agency} className="size-5" />
                          {t.agency(agency)}
                        </span>
                      ) : (
                        "—"
                      )}
                    </RecordItem>
                    <RecordItem label={t.report.employee} title={report.employee?.name}>
                      <bdi>{report.employee?.name ?? "—"}</bdi>
                    </RecordItem>
                    <RecordItem label={t.report.suspect} title={report.suspect?.name}>
                      <bdi>{report.suspect?.name ?? "—"}</bdi>
                    </RecordItem>
                    <RecordItem label={t.report.suspectId}>
                      <span className="font-mono tabular-nums">{report.suspect?.id_number ?? "—"}</span>
                    </RecordItem>
                    <RecordItem label={t.report.employeeNumber}>
                      <span dir="ltr" className="font-mono tabular-nums">
                        {report.employee?.id ?? "—"}
                      </span>
                    </RecordItem>
                    <RecordItem
                      label={t.report.notes}
                      title={report.inspection_notes}
                      className="col-span-full desk-short:col-span-3"
                    >
                      <bdi>{report.inspection_notes || "—"}</bdi>
                    </RecordItem>
                  </dl>
                </TabsContent>
                <TabsContent value="narrative" className="min-h-0 rounded-lg focus-visible:ring-3 focus-visible:ring-ring/50">
                  <ScrollArea className="h-72 desk:h-full">
                    <p dir="auto" className="whitespace-pre-wrap pe-3 text-sm leading-relaxed text-muted-foreground">
                      {toPlainText(incident?.report_summary)}
                    </p>
                  </ScrollArea>
                </TabsContent>
              </Tabs>
            ) : (
              <Placeholder
                art={<ReportIllustration className="h-24 w-auto desk:h-20" />}
                title={t.report.emptyTitle}
                body={t.report.empty}
              />
            )}
          </SectionShell>

          {/* 04 LIVE CALL: the conversation itself, nothing else */}
          <SectionShell
            index={4}
            id="call"
            title={t.call.title}
            caption={t.call.caption}
            status={callStatus}
            className="desk:col-start-2 desk:row-start-2"
          >
            {transcript.length ? (
              <CallTranscript
                lines={transcript}
                className="h-80 desk:h-auto desk:flex-1"
                speaker={(line) => (line.role === "authority" ? (agency ? t.agency(agency) : t.call.role(line.role)) : t.brand)}
                label={(line) =>
                  line.role === "authority" ? (
                    <>
                      {agency && <AgencyMark agency={agency} className="size-4" />}
                      {agency ? t.agency(agency) : t.call.role(line.role)}
                    </>
                  ) : (
                    <>
                      <Logo className="size-4" />
                      {t.brand}
                    </>
                  )
                }
              />
            ) : (
              <Placeholder
                art={<CallIllustration className="h-24 w-auto desk:h-20" />}
                title={t.call.emptyTitle}
                body={t.call.empty}
              />
            )}
          </SectionShell>

          {/* 05 JUDGMENT: the decision first, then the reasoning as a compact grid */}
          <SectionShell
            index={5}
            id="judgment"
            title={t.judgment.title}
            caption={t.judgment.caption}
            status={judgmentStatus}
            className="desk:col-start-3 desk:row-start-2"
          >
            {incident ? (
              <div className="flex min-h-0 flex-col gap-2.5 desk-short:gap-2">
                <div className="flex shrink-0 items-start gap-2.5 rounded-xl bg-white/55 px-3 py-2.5 ring-1 ring-primary/12 desk-short:py-2">
                  <span className="mt-1.5">
                    <StatusDot tone={judgmentStatus.tone} />
                  </span>
                  <div className="min-w-0">
                    <h3 className="text-xs font-medium text-muted-foreground">{t.judgment.decision}</h3>
                    <p className="text-sm font-semibold">
                      {dispatch
                        ? dispatch.dispatch_confirmed
                          ? t.judgment.dispatchConfirmed
                          : t.judgment.dispatchNotConfirmed
                        : t.judgment.noDecision}
                    </p>
                    {dispatch?.authority_statement && (
                      <p
                        dir="auto"
                        className="mt-0.5 line-clamp-2 text-xs text-muted-foreground desk-tight:line-clamp-1"
                        title={dispatch.authority_statement}
                      >
                        “{dispatch.authority_statement}”
                      </p>
                    )}
                  </div>
                </div>
                <dl className="grid shrink-0 grid-cols-2 gap-x-3 gap-y-2 desk:grid-cols-3 desk-short:gap-y-1.5">
                  <RecordItem label={t.judgment.detection}>
                    {t.detectionClass(incident.detection_class ?? "")} · <bdi className="tabular-nums">{confidencePct}%</bdi>
                  </RecordItem>
                  <RecordItem label={t.judgment.verification} title={incident.employee_name ?? undefined}>
                    {incident.verification_status === "confirmed" ? (
                      <bdi>{incident.employee_name ?? t.judgment.theEmployee}</bdi>
                    ) : (
                      t.judgment.notVerified
                    )}
                  </RecordItem>
                  <RecordItem label={t.judgment.routing} title={authorityName ?? undefined}>
                    <span className="inline-flex items-center gap-1.5 align-middle">
                      {agency && <AgencyMark agency={agency} className="size-5" />}
                      {agency ? t.agency(agency) : "—"}
                      {report?.severity && <span className="text-muted-foreground">· {t.severity(report.severity)}</span>}
                    </span>
                  </RecordItem>
                  {report?.recommended_action && (
                    <RecordItem
                      label={t.judgment.recommendedAction}
                      title={toPlainText(report.recommended_action)}
                      className="col-span-full"
                      lines={2}
                    >
                      <span dir="auto">{toPlainText(report.recommended_action)}</span>
                    </RecordItem>
                  )}
                </dl>
              </div>
            ) : (
              <Placeholder
                art={<JudgmentIllustration className="h-24 w-auto desk:h-20" />}
                title={t.judgment.emptyTitle}
                body={t.judgment.empty}
              />
            )}
          </SectionShell>

          <footer className="border-t border-border/60 pt-6 text-center text-xs text-muted-foreground desk:hidden">
            {t.footer}
          </footer>
        </main>
      </div>
    </DirectionProvider>
  )
}
