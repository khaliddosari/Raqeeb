// The team's session. Signing in unlocks the parts of the dashboard that place a real phone
// call; a visitor without it runs the same incident with the dispatch conversation held in
// their own browser. The token is signed by the backend and only proves "the team", so the
// worst a stolen one does is place demo calls to the numbers configured on the server.

const STORAGE_KEY = "raqeeb.admin"

export function adminToken(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null // private windows and blocked storage: the dashboard stays public
  }
}

export function rememberAdmin(token: string | null) {
  try {
    if (token) localStorage.setItem(STORAGE_KEY, token)
    else localStorage.removeItem(STORAGE_KEY)
  } catch {
    // nothing to do: the session simply does not survive a reload
  }
}

export function adminHeaders(): Record<string, string> {
  const token = adminToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}
