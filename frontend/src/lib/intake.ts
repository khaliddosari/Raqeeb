// Mirrors agent/intake.py, whose checkpoints and scenarios live in agent/checkpoints.py. The backend
// is the gate and refuses anything else; these copies only let the form say so before a request is sent.

export const CHECKPOINT_LOCATIONS = [
  "Private Aviation Terminal",
  "LEAP 2026 Exhibition",
  "Future Investment Initiative",
  "Saudi Falcons and Hunting Exhibition",
  "Money20/20 Middle East",
  "Black Hat MEA",
] as const

export type CheckpointLocation = (typeof CHECKPOINT_LOCATIONS)[number]

const SAUDI_MOBILE = /^(?:\+?966|0)?(5\d{8})$/

/** +9665XXXXXXXX for any common way of writing a Saudi mobile, otherwise null. */
export function normalizeSaudiMobile(raw: string): string | null {
  const match = SAUDI_MOBILE.exec(raw.replace(/[\s\-()]/g, ""))
  return match ? `+966${match[1]}` : null
}
