import { Pause as PauseIcon, Play as PlayIcon } from "lucide-react"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { SectionShell } from "@/components/SectionShell"
import { toPlainText } from "@/lib/plaintext"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Progress } from "@/components/ui/progress"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableRow } from "@/components/ui/table"
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

const TEAM = [
  { name: "Khalid Al-Dosari", role: "Detection model, tracking benchmark", url: "https://www.linkedin.com/in/khalid-al-dosari/" },
  { name: "Nawaf Alsharani", role: "Report generation", url: "https://www.linkedin.com/in/nawaf-alsharani-a431b731a/" },
  { name: "Yazeed Bin Shihah", role: "Voice agent, telephony, dashboard", url: "https://www.linkedin.com/in/yazeed-bin-shihah-57aa1b309/" },
  { name: "Omar Al-Dhawyan", role: "Project", url: "https://www.linkedin.com/in/omar-al-dhawyan-789336269/" },
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
      <TableCell className="py-2 align-top text-xs uppercase tracking-wide text-muted-foreground sm:w-44">
        {label}
      </TableCell>
      <TableCell className={`py-2 text-sm wrap-break-word ${mono ? "font-mono tabular-nums" : ""}`}>
        {value ?? "—"}
      </TableCell>
    </TableRow>
  )
}

export default function App() {
  const [employeeName, setEmployeeName] = useState("Khalid Al-Dosari")
  const [employeeId, setEmployeeId] = useState("EMP-4471")
  const [file, setFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [annotated, setAnnotated] = useState<string | null>(null)
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
    const t = setInterval(() => setClock(new Date()), 1000)
    return () => clearInterval(t)
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
    setBusy("Running detection")
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
    setBusy("Running detection")
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

  return (
    <div className="min-h-screen text-foreground">
      <header className="sticky top-0 z-20 border-b border-white/40 bg-background/55 backdrop-blur-xl backdrop-saturate-150">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 sm:gap-x-6">
          <div className="flex min-w-0 items-center gap-2">
            <div className="grid size-7 shrink-0 place-items-center rounded-lg bg-primary text-primary-foreground text-xs font-bold shadow-sm ring-1 ring-white/20">
              R
            </div>
            <span className="font-semibold tracking-tight">Raqeeb</span>
            <Badge variant="outline" className="ml-1 hidden font-mono text-xs uppercase sm:inline-flex">
              Border control
            </Badge>
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <StatusDot tone={live ? "done" : "idle"} />
            <span className="hidden sm:inline">{live ? "Monitor link active" : "Monitor idle"}</span>
            <span className="sm:hidden">{live ? "Live" : "Idle"}</span>
          </div>
          <div className="ml-auto flex items-center gap-3 font-mono text-xs tabular-nums text-muted-foreground sm:gap-4">
            <span className="hidden md:inline">Main Terminal · Checkpoint 1</span>
            <span>{RIYADH_TIME.format(clock)} AST</span>
          </div>
        </div>
      </header>

      <main className="mx-auto flex max-w-6xl flex-col gap-10 px-4 py-6 sm:gap-12 sm:py-8">
        {error && (
          <Alert variant="destructive">
            <AlertDescription className="font-mono text-xs break-all">{error}</AlertDescription>
          </Alert>
        )}

        {/* 01 PREVIEW */}
        <SectionShell
          index={1}
          id="preview"
          title="Detection preview"
          caption="The trained detector tracking prohibited items across a belt clip, frame by frame."
          status={{ label: "Live loop", tone: "active" }}
        >
          <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
            <Card className="overflow-hidden py-0">
              {/* h-full so the video fills the card, which the grid stretches to match
                  the taller column beside it. object-cover then crops rather than
                  letterboxing. Below lg the card is not stretched, so the aspect box
                  keeps the video from collapsing. */}
              <div className="relative h-full">
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
                  className="aspect-960/580 block w-full cursor-pointer bg-black object-cover lg:aspect-auto lg:h-full"
                />
                <Button
                  type="button"
                  size="icon"
                  variant="secondary"
                  onClick={toggleVideo}
                  aria-label={playing ? "Pause preview" : "Play preview"}
                  className="absolute bottom-4 left-4 size-12 rounded-full opacity-90 shadow-sm transition hover:opacity-100 focus-visible:opacity-100"
                >
                  {playing ? <PauseIcon className="size-5" /> : <PlayIcon className="size-5" />}
                </Button>
              </div>
            </Card>
            <div className="flex flex-col gap-4">
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">What this is</CardTitle>
                </CardHeader>
                <CardContent className="text-sm text-muted-foreground">
                  A YOLOv8-OBB model flags prohibited items in X-ray baggage scans, an employee physically
                  verifies the find, and a voice agent then collects the details, writes the report, routes it to
                  the responsible authority and phones them to request dispatch.
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">Team</CardTitle>
                </CardHeader>
                <CardContent className="flex flex-col gap-3">
                  {TEAM.map((m) => (
                    <a
                      key={m.url}
                      href={m.url}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="group flex flex-col rounded-md px-2 py-1 -mx-2 transition-colors hover:bg-accent"
                    >
                      <span className="text-sm font-medium group-hover:underline">{m.name}</span>
                      <span className="text-xs text-muted-foreground">{m.role}</span>
                    </a>
                  ))}
                </CardContent>
              </Card>
            </div>
          </div>
        </SectionShell>

        {/* 02 INFERENCE */}
        <SectionShell
          index={2}
          id="inference"
          title="Inference"
          caption="Upload any X-ray frame. The model returns an annotated render and the flagged class, which starts an incident."
          status={
            incident
              ? { label: incident.detection_class ?? "detected", tone: "done" }
              : { label: "awaiting frame", tone: "idle" }
          }
        >
          <div className="grid gap-6 lg:grid-cols-[1fr_1.3fr]">
            <Card>
              <CardContent className="flex flex-col gap-4 pt-6">
                <div className="grid gap-2">
                  <Label htmlFor="emp-name">Employee</Label>
                  <Input id="emp-name" value={employeeName} onChange={(e) => setEmployeeName(e.target.value)} />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="emp-id">Employee ID</Label>
                  <Input id="emp-id" value={employeeId} onChange={(e) => setEmployeeId(e.target.value)} />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="frame">Frame image</Label>
                  <Input id="frame" type="file" accept="image/*" onChange={(e) => onFile(e.target.files?.[0] ?? null)} />
                </div>
                <Button onClick={runDetection} disabled={!file || busy !== null} className="w-full">
                  {busy === "Running detection" ? "Running detection…" : "Run detection"}
                </Button>

                <div className="flex flex-col gap-2 rounded-xl border border-white/50 bg-white/40 p-3 backdrop-blur-sm">
                  <Button
                    variant="secondary"
                    onClick={runTestImage}
                    disabled={busy !== null}
                    className="w-full"
                  >
                    {busy === "Running detection" ? "Running…" : "Run test image"}
                  </Button>
                  <button
                    type="button"
                    onClick={runTestImage}
                    disabled={busy !== null}
                    className="overflow-hidden rounded-lg border border-white/60 disabled:cursor-not-allowed"
                    aria-label="Run detection on the bundled test image"
                  >
                    <img
                      src={TEST_IMAGE_URL}
                      alt="Bundled X-ray test frame"
                      className="block w-full cursor-pointer bg-white transition hover:opacity-90"
                    />
                  </button>
                  <p className="text-xs text-muted-foreground">
                    A bundled X-ray frame, for trying the pipeline without finding an image.
                  </p>
                </div>

                {incident && (
                  <p className="font-mono text-xs text-muted-foreground wrap-break-word">{incident.id}</p>
                )}
              </CardContent>
            </Card>

            <Card className="overflow-hidden">
              <CardHeader>
                <CardTitle className="text-sm">{annotated ? "Annotated output" : "Input"}</CardTitle>
              </CardHeader>
              <CardContent>
                {busy === "Running detection" ? (
                  <Skeleton className="aspect-video w-full" />
                ) : annotated ? (
                  <img src={annotated} alt="Annotated detection" className="w-full rounded-md border border-border/60" />
                ) : previewUrl ? (
                  <img src={previewUrl} alt="Selected frame" className="w-full rounded-md border border-border/60 opacity-70" />
                ) : (
                  <div className="grid aspect-video place-items-center rounded-md border border-dashed border-border text-sm text-muted-foreground">
                    No frame selected
                  </div>
                )}
                {incident?.detection_class && (
                  <div className="mt-4 flex items-center gap-3">
                    <Badge className="font-mono text-xs uppercase">{incident.detection_class}</Badge>
                    <span className="font-mono text-sm tabular-nums text-muted-foreground">
                      {((incident.detection_confidence ?? 0) * 100).toFixed(2)}% confidence
                    </span>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {incident && stageIndex >= 0 && (
            <Card className="mt-6">
              <CardContent className="flex flex-col gap-4 pt-6">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">Pipeline</span>
                  <span className="font-mono text-xs uppercase text-muted-foreground">{incident.status}</span>
                </div>
                <Progress value={((stageIndex + 1) / PIPELINE.length) * 100} />
                <div className="flex flex-wrap gap-2">
                  {incident.status === "pending_verification" && (
                    <>
                      <Button size="sm" className="h-11 flex-1 sm:h-8 sm:flex-none" onClick={() => act("verify", () => verify(incident.id, true))} disabled={busy !== null}>
                        Confirm threat
                      </Button>
                      <Button
                        size="sm"
                        className="h-11 flex-1 sm:h-8 sm:flex-none"
                        variant="outline"
                        onClick={() => act("verify", () => verify(incident.id, false))}
                        disabled={busy !== null}
                      >
                        False positive
                      </Button>
                    </>
                  )}
                </div>

                {incident.status === "verified" && (
                  <form
                    className="flex flex-col gap-4 rounded-xl border border-white/50 bg-white/40 p-4 backdrop-blur-sm"
                    onSubmit={(e) => {
                      e.preventDefault()
                      void act("info", () =>
                        submitInfo(incident.id, suspectName.trim(), suspectId.trim(), suspectNotes.trim() || undefined),
                      )
                    }}
                  >
                    <div>
                      <p className="text-sm font-medium">Suspect details</p>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        Typed alternative to collecting these by voice. Both fields are required before a
                        report can be generated.
                      </p>
                    </div>
                    <div className="grid gap-4 sm:grid-cols-2">
                      <div className="grid gap-2">
                        <Label htmlFor="suspect-name">Full name</Label>
                        <Input
                          id="suspect-name"
                          value={suspectName}
                          onChange={(e) => setSuspectName(e.target.value)}
                          placeholder="e.g. Faisal Al-Harbi"
                          autoComplete="off"
                        />
                      </div>
                      <div className="grid gap-2">
                        <Label htmlFor="suspect-id">ID number</Label>
                        <Input
                          id="suspect-id"
                          value={suspectId}
                          onChange={(e) => setSuspectId(e.target.value)}
                          placeholder="e.g. 1093847562"
                          inputMode="numeric"
                          autoComplete="off"
                          className="font-mono"
                        />
                      </div>
                    </div>
                    <div className="grid gap-2">
                      <Label htmlFor="suspect-notes">Inspection notes (optional)</Label>
                      <Input
                        id="suspect-notes"
                        value={suspectNotes}
                        onChange={(e) => setSuspectNotes(e.target.value)}
                        placeholder="e.g. Cooperative, detained at checkpoint"
                        autoComplete="off"
                      />
                    </div>
                    <Button
                      type="submit"
                      className="h-11 w-full sm:h-9 sm:w-auto sm:self-start"
                      disabled={busy !== null || !suspectName.trim() || !suspectId.trim()}
                    >
                      {busy === "info" ? "Generating report…" : "Submit suspect details"}
                    </Button>
                  </form>
                )}
              </CardContent>
            </Card>
          )}
        </SectionShell>

        {/* 03 REPORT */}
        <SectionShell
          index={3}
          id="report"
          title="Incident report"
          caption="Generated from the verified detection, then routed to the responsible authority."
          status={report ? { label: "generated", tone: "done" } : { label: "pending", tone: "idle" }}
        >
          {report ? (
            <div className="grid gap-6 md:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">Structured record</CardTitle>
                </CardHeader>
                <CardContent>
                  <Table>
                    <TableBody>
                      <Field label="Incident" value={report.incident_id} mono />
                      <Field label="Detected item" value={report.detected_item} />
                      <Field label="Confidence" value={report.yolo_confidence} mono />
                      <Field label="Location" value={report.location} />
                      <Field label="Severity" value={<Badge variant="outline" className="text-xs uppercase">{report.severity}</Badge>} />
                      <Field label="Suspect" value={report.suspect?.name} />
                      <Field label="Suspect ID" value={report.suspect?.id_number} mono />
                      <Field label="Employee" value={`${report.employee?.name} · ${report.employee?.id}`} />
                      <Field label="Notes" value={report.inspection_notes} />
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">Narrative summary</CardTitle>
                </CardHeader>
                <CardContent>
                  <ScrollArea className="h-72 pr-4">
                    <p
                      dir="auto"
                      className="whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground"
                    >
                      {toPlainText(incident?.report_summary)}
                    </p>
                  </ScrollArea>
                </CardContent>
              </Card>
            </div>
          ) : (
            <Card>
              <CardContent className="py-10 text-center text-sm text-muted-foreground">
                No report yet. Run a detection and confirm it to generate one.
              </CardContent>
            </Card>
          )}
        </SectionShell>

        {/* 04 LIVE CALL */}
        <SectionShell
          index={4}
          id="call"
          title="Authority call monitor"
          caption="The outbound call to the responsible authority, streamed turn by turn as it happens."
          status={
            incident?.call_sid
              ? incident.status === "closed"
                ? { label: "ended", tone: "done" }
                : { label: "in progress", tone: "active" }
              : { label: "no call", tone: "idle" }
          }
        >
          <div className="grid gap-6 lg:grid-cols-[1fr_1.4fr]">
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Channel</CardTitle>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableBody>
                    <Field label="Authority" value={incident?.authority_name} />
                    <Field label="Number" value={incident?.authority_phone} mono />
                    <Field label="Call SID" value={incident?.call_sid} mono />
                    <Field
                      label="Monitor"
                      value={
                        <span className="flex items-center gap-2">
                          <StatusDot tone={live ? "done" : "idle"} />
                          {live ? "connected" : "disconnected"}
                        </span>
                      }
                    />
                  </TableBody>
                </Table>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Transcript</CardTitle>
              </CardHeader>
              <CardContent>
                <ScrollArea className="h-72 pr-4">
                  {transcript.length ? (
                    <div className="flex flex-col gap-3">
                      {transcript.map((line, i) => (
                        <div key={i} className="flex flex-col gap-1">
                          <span className="font-mono text-xs uppercase tracking-wide text-muted-foreground">
                            {line.role}
                          </span>
                          <p className="text-sm leading-relaxed">{line.text}</p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="py-10 text-center text-sm text-muted-foreground">
                      No transcript. Turns appear here once a live call is running; mock telephony places no call.
                    </p>
                  )}
                </ScrollArea>
              </CardContent>
            </Card>
          </div>
        </SectionShell>

        {/* 05 JUDGMENT */}
        <SectionShell
          index={5}
          id="judgment"
          title="Judgment"
          caption="Why the system acted as it did, and what the authority decided."
          status={
            dispatch?.dispatch_confirmed
              ? { label: "dispatch confirmed", tone: "done" }
              : incident
                ? { label: "awaiting decision", tone: "active" }
                : { label: "pending", tone: "idle" }
          }
        >
          <div className="grid gap-6 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">System reasoning</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-4 text-sm">
                {incident ? (
                  <>
                    <div>
                      <p className="text-xs uppercase tracking-wide text-muted-foreground">Detection</p>
                      <p className="mt-1">
                        Flagged <strong>{incident.detection_class}</strong> at{" "}
                        <span className="font-mono tabular-nums">
                          {((incident.detection_confidence ?? 0) * 100).toFixed(2)}%
                        </span>
                        , above the configured threshold.
                      </p>
                    </div>
                    <Separator />
                    <div>
                      <p className="text-xs uppercase tracking-wide text-muted-foreground">Verification</p>
                      <p className="mt-1">
                        {incident.verification_status === "confirmed"
                          ? `Physically confirmed by ${incident.employee_name ?? "the employee"}. The model never overrides this.`
                          : "Not yet confirmed by an employee."}
                      </p>
                    </div>
                    <Separator />
                    <div>
                      <p className="text-xs uppercase tracking-wide text-muted-foreground">Routing</p>
                      <p className="mt-1">
                        Severity <strong>{report?.severity ?? "—"}</strong> for this class, routed to{" "}
                        <strong>{incident.authority_name ?? "—"}</strong> per the class-to-authority mapping.
                      </p>
                    </div>
                    {report?.recommended_action && (
                      <>
                        <Separator />
                        <div>
                          <p className="text-xs uppercase tracking-wide text-muted-foreground">Recommended action</p>
                          <p dir="auto" className="mt-1 leading-relaxed">{toPlainText(report.recommended_action)}</p>
                        </div>
                      </>
                    )}
                  </>
                ) : (
                  <p className="py-10 text-center text-muted-foreground">Nothing to explain yet.</p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Authority decision</CardTitle>
              </CardHeader>
              <CardContent>
                {dispatch ? (
                  <div className="flex flex-col gap-4">
                    <div className="flex items-center gap-3">
                      <StatusDot tone={dispatch.dispatch_confirmed ? "done" : "alert"} />
                      <span className="text-sm font-medium">
                        {dispatch.dispatch_confirmed ? "Dispatch confirmed" : "Dispatch not confirmed"}
                      </span>
                    </div>
                    {dispatch.authority_statement && (
                      <p className="rounded-xl border border-white/50 bg-white/45 p-3 text-sm leading-relaxed backdrop-blur-sm">
                        “{dispatch.authority_statement}”
                      </p>
                    )}
                  </div>
                ) : (
                  <p className="py-10 text-center text-sm text-muted-foreground">
                    No decision recorded. This is filled by the authority during the call.
                  </p>
                )}
              </CardContent>
            </Card>
          </div>
        </SectionShell>

        <footer className="border-t border-border/60 pt-6 text-center text-xs text-muted-foreground">
          Raqeeb · automated checkpoint security agent
        </footer>
      </main>
    </div>
  )
}
