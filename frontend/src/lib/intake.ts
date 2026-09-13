// Mirrors agent/intake.py. The backend is the gate and refuses anything else; these copies only
// let the form say so before a request is sent.

export const CHECKPOINT_LOCATIONS = [
  "Terminal 1",
  "Terminal 2",
  "Terminal 3",
  "Terminal 4",
  "Terminal 5",
  "Private Aviation Terminal",
] as const

export type CheckpointLocation = (typeof CHECKPOINT_LOCATIONS)[number]

const SAUDI_MOBILE = /^(?:\+?966|0)?(5\d{8})$/

/** +9665XXXXXXXX for any common way of writing a Saudi mobile, otherwise null. */
export function normalizeSaudiMobile(raw: string): string | null {
  const match = SAUDI_MOBILE.exec(raw.replace(/[\s\-()]/g, ""))
  return match ? `+966${match[1]}` : null
}
