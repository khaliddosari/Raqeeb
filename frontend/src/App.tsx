import { DirectionProvider } from "@base-ui/react/direction-provider"
import { Pause as PauseIcon, Play as PlayIcon } from "lucide-react"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { SectionShell } from "@/components/SectionShell"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Progress } from "@/components/ui/progress"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableRow } from "@/components/ui/table"
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
import { applyDocumentLang, initialLang, rememberLang, STRINGS, type Lang } from "@/lib/i18n"
import { toPlainText } from "@/lib/plaintext"

// Names stay in the spelling each person uses on LinkedIn, in both languages.
const TEAM = [
  { name: "Khalid Al-Dosari", url: "https://www.linkedin.com/in/khalid-al-dosari/" },
  { name: "Nawaf Alsharani", url: "https://www.linkedin.com/in/nawaf-alsharani-a431b731a/" },
  { name: "Yazeed Bin Shihah", url: "https://www.linkedin.com/in/yazeed-bin-shihah-57aa1b309/" },
  { name: "Omar Al-Dhawyan", url: "https://www.linkedin.com/in/omar-al-dhawyan-789336269/" },
]

const RIYADH_TIME = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Riyadh",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
})

const TEST_IMAGE_URL = `${import.meta.env.BASE_URL}test-image.png`

const SUSPECT_DEFAULTS = {
  name: "Faisal",
  id: "1093847562",
  notes: "Suspect is cooperative and calm",
}

const PIPELINE = ["detected", "pending_verification", "verified", "report_sent", "call_in_progress", "closed"]

function StatusDot({ tone }: { tone: "idle" | "active" | "done" | "alert" }) {
  const color =
    tone === "done" ? "bg-emerald-600" : tone === "active" ? "bg-amber-600" : tone === "alert" ? "bg-red-600" : "bg-muted-foreground/40"
  return (
    <span className="relative flex size-2">
      {tone === "active" && <span className={`absolute inline-flex size-full animate-ping rounded-full ${color} opacity-60`} />}
      <span className={`relative inline-flex size-2 rounded-full ${color}`} />
    </span>
  )
}

function Field({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <TableRow className="border-border/50">
      <TableCell className="py-1.5 align-top text-xs uppercase tracking-wide text-muted-foreground sm:w-36">
        {label}
      </TableCell>
      <TableCell className={`py-1.5 text-sm wrap-break-word ${mono ? "font-mono tabular-nums" : ""}`}>
        {value ?? "—"}
      </TableCell>
    </TableRow>
  )
}

// Sentences with values spliced in come from the dictionary as [text, value, text, value, text].
// Values are bdi-isolated so an English authority name inside an Arabic sentence keeps its order.
function Emphasised({ parts }: { parts: string[] }) {
  return (
    <>
      {parts.map((part, i) =>
        i % 2 ? (
          <strong key={i}>
            <bdi>{part}</bdi>
          </strong>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </>
  )
}

export default function App() {
  const [lang, setLang] = useState<Lang>(initialLang)
  const t = STRINGS[lang]
  const [employeeName, setEmployeeName] = useState("Khalid Al-Dosari")
  const [employeeId, setEmployeeId] = useState("EMP-4471")
  const [file, setFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [annotated, setAnnotated] = useState<string | null>(null)
  const [loadedSrc, setLoadedSrc] = useState<string | null>(null)
  const [incident, setIncident] = useState<Incident | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [feed, setFeed] = useState<MonitorEvent[]>([])
  const [live, setLive] = useState(false)
  const [clock, setClock] = useState(() => new Date())
  const socketRef = useRef<WebSocket | null>(null)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const [playing, setPlaying] = useState(true)
  const [suspectName, setSuspectName] = useState(SUSPECT_DEFAULTS.name)
  const [suspectId, setSuspectId] = useState(SUSPECT_DEFAULTS.id)
  const [suspectNotes, setSuspectNotes] = useState(SUSPECT_DEFAULTS.notes)

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
    ws.onopen = () => setLive(true)
    ws.onclose = () => setLive(false)
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
    setSuspectName(SUSPECT_DEFAULTS.name)
    setSuspectId(SUSPECT_DEFAULTS.id)
    setSuspectNotes(SUSPECT_DEFAULTS.notes)
    try {
      const res = await detect(file, employeeName, employeeId)
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
    setSuspectName(SUSPECT_DEFAULTS.name)
    setSuspectId(SUSPECT_DEFAULTS.id)
    setSuspectNotes(SUSPECT_DEFAULTS.notes)
    try {
      const blob = await (await fetch(TEST_IMAGE_URL)).blob()
      const testFile = new File([blob], "test-image.png", { type: blob.type || "image/png" })
      setFile(testFile)
      setPreviewUrl(TEST_IMAGE_URL)
      setAnnotated(null)
      const res = await detect(testFile, employeeName, employeeId)
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

  const transcript = useMemo(() => {
    const liveLines = feed.filter((e): e is Extract<MonitorEvent, { type: "transcript" }> => e.type === "transcript")
    if (liveLines.length) return liveLines.map((l) => ({ role: l.role, text: l.text }))
    return incident?.authority_response?.raw_transcript ?? []
  }, [feed, incident])

  const dispatch = incident?.authority_response
  const report = incident?.report
  const confidencePct = ((incident?.detection_confidence ?? 0) * 100).toFixed(2)

  return (
    <DirectionProvider direction={lang === "ar" ? "rtl" : "ltr"}>
      <div className="min-h-screen text-foreground desk:flex desk:h-dvh desk:flex-col desk:overflow-hidden">
        <header className="sticky top-0 z-20 border-b border-white/40 bg-background/55 backdrop-blur-xl backdrop-saturate-150 desk:static desk:shrink-0">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 desk:h-12 desk:max-w-[112rem] desk:flex-nowrap desk:py-0">
            <div className="flex min-w-0 items-center gap-2">
              <div className="grid size-7 shrink-0 place-items-center rounded-lg bg-primary text-xs font-bold text-primary-foreground shadow-sm ring-1 ring-white/20">
                {t.brandMark}
              </div>
              <span className="font-semibold tracking-tight">{t.brand}</span>
            </div>

            {/* its own full-width row under the brand until there is room to sit inline */}
            <nav
              aria-label={t.team}
              className="order-last flex w-full flex-wrap items-center justify-center gap-x-5 gap-y-1 lg:order-0 lg:w-auto lg:flex-1"
            >
              {TEAM.map((m) => (
                <a
                  key={m.url}
                  href={m.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  title={t.onLinkedIn(m.name)}
                  dir="ltr"
                  className="text-sm text-muted-foreground underline-offset-4 transition-colors hover:text-foreground hover:underline"
                >
                  {m.name}
                </a>
              ))}
            </nav>

            <div className="ms-auto flex items-center gap-3 lg:ms-0">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setLang(t.switchToLang)}
                aria-label={t.switchToLabel}
                className="h-10 bg-white/50 px-3 lg:h-7"
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
            status={{ label: t.preview.status, tone: "active" }}
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
            status={
              incident
                ? { label: t.detectionClass(incident.detection_class ?? ""), tone: "done" }
                : { label: t.inference.awaiting, tone: "idle" }
            }
            className="desk:col-span-2 desk:col-start-2 desk:row-start-1"
          >
            <div className="grid gap-3 md:grid-cols-2 desk:min-h-0 desk:flex-1 desk:grid-cols-[minmax(0,1fr)_minmax(0,1.45fr)_minmax(0,1fr)] desk:grid-rows-[minmax(0,1fr)]">
              {/* input */}
              <ScrollArea className="desk:h-full desk:min-h-0">
                <div className="flex flex-col gap-3 desk:p-1 desk:pe-3 desk-short:gap-2">
                  <div className="grid gap-1.5">
                    <Label htmlFor="emp-name">{t.inference.employee}</Label>
                    <Input id="emp-name" value={employeeName} onChange={(e) => setEmployeeName(e.target.value)} />
                  </div>
                  <div className="grid gap-1.5">
                    <Label htmlFor="emp-id">{t.inference.employeeId}</Label>
                    <Input id="emp-id" value={employeeId} onChange={(e) => setEmployeeId(e.target.value)} />
                  </div>
                  <div className="grid gap-1.5">
                    <Label htmlFor="frame">{t.inference.frame}</Label>
                    {/* The native picker's "Choose File / No file chosen" is browser chrome that follows the
                        OS language, not the page. The real input stays for keyboard and screen readers;
                        this label is only its visible, translated face. */}
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
                      className="flex h-8 w-full min-w-0 cursor-pointer items-center gap-2 rounded-lg border border-input ps-1 pe-2.5 text-sm transition-colors hover:bg-white/40 peer-focus-visible:border-ring peer-focus-visible:ring-3 peer-focus-visible:ring-ring/50"
                    >
                      <span className="shrink-0 rounded-md bg-secondary px-2 py-0.5 text-xs font-medium text-secondary-foreground">
                        {t.inference.chooseFile}
                      </span>
                      <span id="frame-status" dir="auto" className="truncate text-muted-foreground">
                        {file ? file.name : t.inference.noFile}
                      </span>
                    </label>
                  </div>
                  <Button onClick={runDetection} disabled={!file || busy !== null} className="w-full">
                    {busy === "detect" ? t.inference.runningDetection : t.inference.runDetection}
                  </Button>

                  {/* stacked with the image below on small screens; a thumbnail beside the button at desk */}
                  <div className="flex flex-col gap-2 rounded-xl bg-white/40 p-2.5 ring-1 ring-white/60 desk:flex-row-reverse desk:items-center">
                    <div className="flex min-w-0 flex-1 flex-col gap-1.5">
                      <Button variant="secondary" onClick={runTestImage} disabled={busy !== null} className="w-full">
                        {busy === "detect" ? t.inference.runningTest : t.inference.runTest}
                      </Button>
                      <p className="text-xs text-muted-foreground desk:hidden">{t.inference.testCaption}</p>
                    </div>
                    <button
                      type="button"
                      onClick={runTestImage}
                      disabled={busy !== null}
                      aria-label={t.inference.testAria}
                      className="shrink-0 overflow-hidden rounded-lg ring-1 ring-white/60 disabled:cursor-not-allowed desk:w-24 desk-short:w-20"
                    >
                      <img
                        src={TEST_IMAGE_URL}
                        alt={t.inference.testAlt}
                        className="block w-full cursor-pointer bg-white object-cover transition hover:opacity-90 desk:aspect-3/2"
                      />
                    </button>
                  </div>
                </div>
              </ScrollArea>

              {/* output */}
              <div className="flex min-h-0 flex-col overflow-hidden rounded-xl bg-white/40 ring-1 ring-white/60 desk:h-full">
                <div className="flex shrink-0 items-center justify-between gap-2 border-b border-white/50 px-3 py-2 text-xs">
                  <span className="font-medium">{annotated ? t.inference.annotatedOutput : t.inference.input}</span>
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
                    <p className="text-sm text-muted-foreground">{t.inference.noFrame}</p>
                  )}
                </div>
                {incident?.detection_class && (
                  <div className="flex shrink-0 items-center gap-3 border-t border-white/50 px-3 py-2">
                    <Badge className="font-mono text-xs uppercase">{t.detectionClass(incident.detection_class)}</Badge>
                    <span className="text-xs tabular-nums text-muted-foreground">{t.inference.confidence(confidencePct)}</span>
                  </div>
                )}
              </div>

              {/* verification */}
              <ScrollArea className="md:col-span-2 desk:col-span-1 desk:h-full desk:min-h-0">
                <div className="flex flex-col gap-3 desk:p-1 desk:pe-3">
                  <div className="flex flex-col gap-2 rounded-xl bg-white/40 p-3 ring-1 ring-white/60">
                    <div className="flex items-center justify-between gap-2 text-xs">
                      <span className="font-medium">{t.inference.pipeline}</span>
                      <span className="truncate font-mono uppercase text-muted-foreground">
                        {t.status(incident?.status ?? "idle")}
                      </span>
                    </div>
                    <Progress value={stageIndex >= 0 ? ((stageIndex + 1) / PIPELINE.length) * 100 : 0} />
                    {!incident && <p className="text-xs text-muted-foreground">{t.inference.openIncident}</p>}
                    {incident?.status === "pending_verification" && (
                      <div className="flex flex-wrap gap-2 pt-1">
                        <Button
                          size="sm"
                          className="h-11 flex-1 sm:h-8"
                          onClick={() => act("verify", () => verify(incident.id, true))}
                          disabled={busy !== null}
                        >
                          {t.inference.confirm}
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-11 flex-1 sm:h-8"
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
                      className="flex flex-col gap-3 rounded-xl bg-white/40 p-3 ring-1 ring-white/60"
                      onSubmit={(e) => {
                        e.preventDefault()
                        void act("info", () =>
                          submitInfo(incident.id, suspectName.trim(), suspectId.trim(), suspectNotes.trim() || undefined),
                        )
                      }}
                    >
                      <div>
                        <p className="text-sm font-medium">{t.inference.suspectDetails}</p>
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
                            className="font-mono"
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
            status={report ? { label: t.report.generated, tone: "done" } : { label: t.report.pending, tone: "idle" }}
            className="desk:col-start-1 desk:row-start-2"
          >
            {report ? (
              <Tabs defaultValue="record" className="min-h-0 gap-2 desk:flex-1">
                <TabsList className="h-11! shrink-0 desk:h-8!">
                  <TabsTrigger value="record">{t.report.record}</TabsTrigger>
                  <TabsTrigger value="narrative">{t.report.narrative}</TabsTrigger>
                </TabsList>
                <TabsContent value="record" className="min-h-0">
                  <ScrollArea className="desk:h-full">
                    <Table>
                      <TableBody>
                        <Field label={t.report.incident} value={report.incident_id} mono />
                        <Field label={t.report.detectedItem} value={t.detectionClass(report.detected_item)} />
                        <Field label={t.report.confidence} value={report.yolo_confidence} mono />
                        <Field label={t.report.location} value={<bdi>{report.location}</bdi>} />
                        <Field
                          label={t.report.severity}
                          value={
                            <Badge variant="outline" className="text-xs uppercase">
                              {t.severity(report.severity)}
                            </Badge>
                          }
                        />
                        <Field label={t.report.suspect} value={<bdi>{report.suspect?.name}</bdi>} />
                        <Field label={t.report.suspectId} value={report.suspect?.id_number} mono />
                        <Field label={t.report.employee} value={<bdi>{`${report.employee?.name} · ${report.employee?.id}`}</bdi>} />
                        <Field label={t.report.notes} value={<bdi>{report.inspection_notes}</bdi>} />
                      </TableBody>
                    </Table>
                  </ScrollArea>
                </TabsContent>
                <TabsContent value="narrative" className="min-h-0">
                  <ScrollArea className="h-72 desk:h-full">
                    <p dir="auto" className="whitespace-pre-wrap pe-3 text-sm leading-relaxed text-muted-foreground">
                      {toPlainText(incident?.report_summary)}
                    </p>
                  </ScrollArea>
                </TabsContent>
              </Tabs>
            ) : (
              <div className="grid flex-1 place-items-center py-10 text-center text-sm text-muted-foreground desk:py-0">
                {t.report.empty}
              </div>
            )}
          </SectionShell>

          {/* 04 LIVE CALL */}
          <SectionShell
            index={4}
            id="call"
            title={t.call.title}
            caption={t.call.caption}
            status={
              incident?.call_sid
                ? incident.status === "closed"
                  ? { label: t.call.ended, tone: "done" }
                  : { label: t.call.inProgress, tone: "active" }
                : { label: t.call.noCall, tone: "idle" }
            }
            className="desk:col-start-2 desk:row-start-2"
          >
            <dl className="grid shrink-0 grid-cols-2 gap-x-3 gap-y-2 rounded-xl bg-white/40 p-3 ring-1 ring-white/60">
              <div className="col-span-2 min-w-0">
                <dt className="text-xs uppercase tracking-wide text-muted-foreground">{t.call.authority}</dt>
                <dd className="truncate text-sm" title={incident?.authority_name ?? undefined}>
                  <bdi>{incident?.authority_name ?? "—"}</bdi>
                </dd>
              </div>
              <div className="min-w-0">
                <dt className="text-xs uppercase tracking-wide text-muted-foreground">{t.call.number}</dt>
                <dd dir="ltr" className="truncate text-start font-mono text-sm tabular-nums">
                  {incident?.authority_phone ?? "—"}
                </dd>
              </div>
              <div className="min-w-0">
                <dt className="text-xs uppercase tracking-wide text-muted-foreground">{t.call.callSid}</dt>
                <dd className="truncate font-mono text-sm" title={incident?.call_sid ?? undefined}>
                  {incident?.call_sid ?? "—"}
                </dd>
              </div>
            </dl>
            <div className="flex min-h-0 flex-col gap-1.5 desk:flex-1">
              <div className="flex shrink-0 items-center justify-between gap-2 text-xs">
                <span className="font-medium">{t.call.transcript}</span>
                <span className="flex items-center gap-1.5 text-muted-foreground">
                  <StatusDot tone={live ? "done" : "idle"} />
                  {live ? t.call.connected : t.call.disconnected}
                </span>
              </div>
              <ScrollArea className="h-56 desk:h-auto desk:min-h-0 desk:flex-1">
                {transcript.length ? (
                  <div className="flex flex-col gap-3 pe-3">
                    {transcript.map((line, i) => (
                      <div key={i} className="flex flex-col gap-1">
                        <span className="font-mono text-xs uppercase tracking-wide text-muted-foreground">
                          {t.call.role(line.role)}
                        </span>
                        <p dir="auto" className="text-sm leading-relaxed">
                          {line.text}
                        </p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="py-8 text-center text-sm text-muted-foreground">{t.call.empty}</p>
                )}
              </ScrollArea>
            </div>
          </SectionShell>

          {/* 05 JUDGMENT */}
          <SectionShell
            index={5}
            id="judgment"
            title={t.judgment.title}
            caption={t.judgment.caption}
            status={
              dispatch?.dispatch_confirmed
                ? { label: t.judgment.dispatchConfirmedPill, tone: "done" }
                : incident
                  ? { label: t.judgment.awaitingDecision, tone: "active" }
                  : { label: t.judgment.pending, tone: "idle" }
            }
            className="desk:col-start-3 desk:row-start-2"
          >
            <div className="flex shrink-0 flex-col gap-1.5 rounded-xl bg-white/40 p-3 ring-1 ring-white/60">
              <p className="text-xs uppercase tracking-wide text-muted-foreground">{t.judgment.decision}</p>
              {dispatch ? (
                <>
                  <div className="flex items-center gap-2">
                    <StatusDot tone={dispatch.dispatch_confirmed ? "done" : "alert"} />
                    <span className="text-sm font-medium">
                      {dispatch.dispatch_confirmed ? t.judgment.dispatchConfirmed : t.judgment.dispatchNotConfirmed}
                    </span>
                  </div>
                  {dispatch.authority_statement && (
                    <p dir="auto" className="text-sm leading-relaxed">
                      “{dispatch.authority_statement}”
                    </p>
                  )}
                </>
              ) : (
                <p className="text-sm text-muted-foreground">{t.judgment.noDecision}</p>
              )}
            </div>
            <div className="flex min-h-0 flex-col gap-1.5 desk:flex-1">
              <p className="shrink-0 text-xs font-medium">{t.judgment.reasoning}</p>
              <ScrollArea className="desk:min-h-0 desk:flex-1">
                {incident ? (
                  <div className="flex flex-col gap-2.5 pe-3 text-sm">
                    <div>
                      <p className="text-xs uppercase tracking-wide text-muted-foreground">{t.judgment.detection}</p>
                      <p className="mt-0.5">
                        <Emphasised
                          parts={t.judgment.detectionBody(
                            t.detectionClass(incident.detection_class ?? ""),
                            `${confidencePct}%`,
                          )}
                        />
                      </p>
                    </div>
                    <Separator />
                    <div>
                      <p className="text-xs uppercase tracking-wide text-muted-foreground">{t.judgment.verification}</p>
                      <p className="mt-0.5">
                        {incident.verification_status === "confirmed"
                          ? t.judgment.verifiedBy(incident.employee_name ?? t.judgment.theEmployee)
                          : t.judgment.notVerified}
                      </p>
                    </div>
                    <Separator />
                    <div>
                      <p className="text-xs uppercase tracking-wide text-muted-foreground">{t.judgment.routing}</p>
                      <p className="mt-0.5">
                        <Emphasised
                          parts={t.judgment.routingBody(
                            report?.severity ? t.severity(report.severity) : "—",
                            incident.authority_name ?? "—",
                          )}
                        />
                      </p>
                    </div>
                    {report?.recommended_action && (
                      <>
                        <Separator />
                        <div>
                          <p className="text-xs uppercase tracking-wide text-muted-foreground">
                            {t.judgment.recommendedAction}
                          </p>
                          <p dir="auto" className="mt-0.5 leading-relaxed">
                            {toPlainText(report.recommended_action)}
                          </p>
                        </div>
                      </>
                    )}
                  </div>
                ) : (
                  <p className="py-8 text-center text-sm text-muted-foreground">{t.judgment.empty}</p>
                )}
              </ScrollArea>
            </div>
          </SectionShell>

          <footer className="border-t border-border/60 pt-6 text-center text-xs text-muted-foreground desk:hidden">
            {t.footer}
          </footer>
        </main>
      </div>
    </DirectionProvider>
  )
}
