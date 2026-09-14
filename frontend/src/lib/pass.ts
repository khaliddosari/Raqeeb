// A suspect's pass: the boarding pass or event badge the bag carrier shows, carried by a QR code so
// the suspect details need no typing. It also names the event it was issued for, which becomes the
// incident's location, so the report and the call describe that event's scenario. The code holds a
// URL to the pass JSON, or the JSON itself.

import { locationCode } from "@/lib/i18n"
import type { CheckpointLocation } from "@/lib/intake"

export type SuspectPass = {
  name: string
  idNumber: string
  /** what the pass is, such as a delegate badge; shown on the dashboard, not sent */
  passType: string | null
  location: CheckpointLocation
}

export type PassResult = { ok: true; pass: SuspectPass } | { ok: false; reason: "invalid" | "unreachable" }

// A pass may use English keys or the Arabic labels printed on the pass itself.
const NAME_KEYS = ["name", "suspect_name", "الاسم"]
const ID_KEYS = ["id_number", "suspect_id_number", "رقم الهوية"]
const TYPE_KEYS = ["pass_type", "نوع البطاقة"]
const LOCATION_KEYS = ["location", "event", "الفعالية", "الموقع"]
// national ID, residence permit or passport number
const ID_NUMBER = /^[0-9A-Za-z]{5,20}$/

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

export function parseSuspectPass(value: unknown): SuspectPass | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null
  const record = value as Record<string, unknown>
  const name = field(record, NAME_KEYS)
  const idNumber = field(record, ID_KEYS)
  const passType = field(record, TYPE_KEYS)
  const location = locationCode(field(record, LOCATION_KEYS) ?? "")
  if (!name || name.length > 80) return null
  if (!idNumber || !ID_NUMBER.test(idNumber)) return null
  if (!location) return null
  return { name, idNumber, passType: passType && passType.length <= 40 ? passType : null, location: location as CheckpointLocation }
}

export async function readSuspectPass(scanned: string): Promise<PassResult> {
  const text = scanned.trim()
  if (text.startsWith("{")) {
    try {
      const pass = parseSuspectPass(JSON.parse(text))
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
    const pass = parseSuspectPass(await response.json())
    return pass ? { ok: true, pass } : { ok: false, reason: "invalid" }
  } catch (error) {
    return { ok: false, reason: error instanceof SyntaxError ? "invalid" : "unreachable" }
  }
}
