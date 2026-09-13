// The agencies an authority can belong to, as sent by the backend in authority_agency.
// Mirrors the `agency` field in config/authority_mapping.yaml.
export type Agency = "police" | "airport_security"

export function isAgency(value: unknown): value is Agency {
  return value === "police" || value === "airport_security"
}
