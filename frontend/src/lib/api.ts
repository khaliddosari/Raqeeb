// Same-origin by default so FastAPI can serve the built bundle; set VITE_API_BASE_URL
// when the frontend is deployed separately (Vercel) from the backend (Modal).
import { adminHeaders } from "@/lib/admin"
import type { Employee } from "@/lib/employees"

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
  authority_name_ar: string | null
  authority_agency: string | null
  call_sid: string | null
  authority_response: {
    dispatch_confirmed?: boolean
    // "answered", or why the call reached no one: "voicemail", "no_answer", "busy", "failed"
    outcome?: string
    authority_statement?: string
    raw_transcript?: { role: string; text: string }[]
  } | null
  created_at: string
  updated_at: string
}

export type MonitorEvent =
  | { type: "snapshot"; status: string | null }
  | { type: "status"; status: string; detection_class?: string; authority_name?: string; call_sid?: string }
  // item_id and seq mark a line still being spoken: the same item_id is re-sent with the line's
  // whole text as it grows, and seq is the turn's position in the conversation.
  | { type: "transcript"; role: string; text: string; item_id?: string; seq?: number; final?: boolean }
  | { type: "dispatch"; confirmed: boolean; statement: string }
  | { type: "ping" }

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error((await res.text().catch(() => "")) || `${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

export const uploadsUrl = (filename: string) => `${API_BASE}/uploads/${filename}`

// Two shapes, matching the two dashboards: a visitor sends the name they typed, and a signed-in
// dashboard sends the employee it picked and the number to ring. A number sent without a session
// is ignored by the backend, which is what makes an anonymous run unable to phone anyone.
export async function detect(
  file: File,
  location: string,
  who: { employeeKey?: string; employeeName?: string; employeePhone?: string },
) {
  const form = new FormData()
  form.append("image", file)
  form.append("location", location)
  if (who.employeeKey) form.append("employee_key", who.employeeKey)
  if (who.employeeName) form.append("employee_name", who.employeeName)
  if (who.employeePhone) form.append("employee_phone", who.employeePhone)
  return json<{
    incident_id: string
    interrupt: Record<string, any>
    image_filename: string | null
    annotated_filename: string | null
  }>(await fetch(`${API_BASE}/api/detect`, { method: "POST", body: form, headers: adminHeaders() }))
}

export async function getEmployees() {
  return json<{ employees: Employee[] }>(await fetch(`${API_BASE}/api/employees`, { headers: adminHeaders() }))
}

export async function signIn(password: string) {
  const response = await fetch(`${API_BASE}/api/admin/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  })
  if (response.status === 401) return null
  return json<{ token: string; expires_at: number }>(response)
}

/** Whether the stored token still works, and whether this deployment has an admin at all. */
export async function adminSession() {
  return json<{ admin: boolean; available: boolean }>(
    await fetch(`${API_BASE}/api/admin/session`, { headers: adminHeaders() }),
  )
}

/** A client secret for this incident's browser conversation, and its ceiling in seconds. */
export async function browserCallToken(id: string) {
  return json<{ client_secret: string; expires_at: number | null; max_seconds: number }>(
    await fetch(`${API_BASE}/api/incidents/${id}/browser-call/token`, { method: "POST" }),
  )
}

export async function browserCallResult(
  id: string,
  result: {
    outcome: "answered" | "failed"
    dispatch_confirmed?: boolean
    authority_statement?: string
    transcript?: { role: string; text: string }[]
  },
) {
  return json<{ dispatch_confirmed: boolean }>(
    await fetch(`${API_BASE}/api/incidents/${id}/browser-call/result`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(result),
    }),
  )
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

// location: the event a scanned pass was issued for, which replaces the incident's location
export async function submitInfo(id: string, suspectName: string, suspectId: string, notes?: string, location?: string) {
  return json<any>(
    await fetch(`${API_BASE}/api/incidents/${id}/manual-info`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ suspect_name: suspectName, suspect_id_number: suspectId, notes, location }),
    }),
  )
}

// After a call that reached no one, places the dispatch call again. The team's to do.
export async function callAgain(id: string) {
  return json<any>(await fetch(`${API_BASE}/api/incidents/${id}/call-again`, { method: "POST", headers: adminHeaders() }))
}

export function monitorSocket(id: string): WebSocket {
  const base = API_BASE || window.location.origin
  const url = new URL(`/ws/monitor/${id}`, base)
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:"
  return new WebSocket(url.toString())
}
