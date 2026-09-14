// A duty pass: the on-duty employee, their mobile and the checkpoint, carried by a QR code so a
// demo can start without typing. The code holds a URL to the pass JSON, or the JSON itself.

import { locationCode } from "@/lib/i18n"
import { normalizeSaudiMobile, type CheckpointLocation } from "@/lib/intake"

export type DutyPass = {
  employeeName: string
  /** as written on the pass; normalized when the detection is sent */
  employeePhone: string
  location: CheckpointLocation
}

export type PassResult = { ok: true; pass: DutyPass } | { ok: false; reason: "invalid" | "unreachable" }

// A pass may use English keys or the Arabic labels printed on the pass itself.
const NAME_KEYS = ["employee_name", "الموظف المناوب", "الموظف"]
const NUMBER_KEYS = ["employee_number", "رقم الموظف"]
const LOCATION_KEYS = ["location", "الموقع"]

// Passes published on Raqeeb's own site are read from whichever deployment is scanning them, so
// the same printed code works on localhost and on preview deployments, not only in production.
const RAQEEB_HOSTS = new Set(["raqeeb.khalid-ai.dev"])

function field(record: Record<string, unknown>, keys: string[]): string | null {
  for (const key of keys) {
    const value = record[key]
    if (typeof value === "string" && value.trim()) return value.trim()
    if (typeof value === "number") return String(value)
  }
  return null
}

export function parseDutyPass(value: unknown): DutyPass | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null
  const record = value as Record<string, unknown>
  const employeeName = field(record, NAME_KEYS)
  const employeePhone = field(record, NUMBER_KEYS)
  const location = locationCode(field(record, LOCATION_KEYS) ?? "")
  if (!employeeName || employeeName.length > 80) return null
  if (!employeePhone || !normalizeSaudiMobile(employeePhone)) return null
  if (!location) return null
  return { employeeName, employeePhone, location: location as CheckpointLocation }
}

export async function readDutyPass(scanned: string): Promise<PassResult> {
  const text = scanned.trim()
  if (text.startsWith("{")) {
    try {
      const pass = parseDutyPass(JSON.parse(text))
      return pass ? { ok: true, pass } : { ok: false, reason: "invalid" }
    } catch {
      return { ok: false, reason: "invalid" }
    }
  }

  let url: URL
  try {
    url = new URL(text)
  } catch {
    return { ok: false, reason: "invalid" }
  }
  const local = url.host === window.location.host || RAQEEB_HOSTS.has(url.host)
  if (!local && url.protocol !== "https:") return { ok: false, reason: "invalid" }

  try {
    const response = await fetch(local ? `${url.pathname}${url.search}` : url.href, {
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(8000),
    })
    if (!response.ok) return { ok: false, reason: "unreachable" }
    const pass = parseDutyPass(await response.json())
    return pass ? { ok: true, pass } : { ok: false, reason: "invalid" }
  } catch (error) {
    return { ok: false, reason: error instanceof SyntaxError ? "invalid" : "unreachable" }
  }
}
