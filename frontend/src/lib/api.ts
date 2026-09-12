// Same-origin by default so FastAPI can serve the built bundle; set VITE_API_BASE_URL
// when the frontend is deployed separately (Vercel) from the backend (Modal).
export const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "")

export type Incident = {
  id: string
  status: string
  detection_class: string | null
  detection_confidence: number | null
  image_filename: string | null
  annotated_filename: string | null
  verification_status: string | null
  employee_name: string | null
  employee_id: string | null
  incident_data: Record<string, unknown>
  report: Record<string, any> | null
  report_summary: string | null
  authority_name: string | null
  authority_phone: string | null
  call_sid: string | null
  authority_response: {
    dispatch_confirmed?: boolean
    authority_statement?: string
    raw_transcript?: { role: string; text: string }[]
  } | null
  created_at: string
  updated_at: string
}

export type MonitorEvent =
  | { type: "snapshot"; status: string | null }
  | { type: "status"; status: string; detection_class?: string; authority_name?: string; call_sid?: string }
  | { type: "transcript"; role: string; text: string }
  | { type: "dispatch"; confirmed: boolean; statement: string }
  | { type: "ping" }

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error((await res.text().catch(() => "")) || `${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

export const uploadsUrl = (filename: string) => `${API_BASE}/uploads/${filename}`

export async function detect(file: File, employeeName: string, employeeId: string) {
  const form = new FormData()
  form.append("image", file)
  form.append("employee_name", employeeName)
  form.append("employee_id", employeeId)
  return json<{
    incident_id: string
    interrupt: Record<string, any>
    image_filename: string | null
    annotated_filename: string | null
  }>(await fetch(`${API_BASE}/api/detect`, { method: "POST", body: form }))
}

export async function getIncident(id: string) {
  return json<Incident>(await fetch(`${API_BASE}/api/incidents/${id}`))
}

export async function verify(id: string, confirmed: boolean, notes?: string) {
  return json<any>(
    await fetch(`${API_BASE}/api/incidents/${id}/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmed, notes }),
    }),
  )
}

export async function submitInfo(id: string, suspectName: string, suspectId: string, notes?: string) {
  return json<any>(
    await fetch(`${API_BASE}/api/incidents/${id}/manual-info`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ suspect_name: suspectName, suspect_id_number: suspectId, notes }),
    }),
  )
}

export function monitorSocket(id: string): WebSocket {
  const base = API_BASE || window.location.origin
  const url = new URL(`/ws/monitor/${id}`, base)
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:"
  return new WebSocket(url.toString())
}
