import { Lock, ShieldCheck } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { signIn } from "@/lib/api"

export type SignInLabels = {
  signIn: string
  signedIn: string
  signOut: string
  title: string
  body: string
  password: string
  submit: string
  submitting: string
  wrong: string
  cancel: string
}

// The team's way in. A visitor never needs this: the dashboard runs everything without it, and
// only the dispatch phone call is behind it. Native <dialog> so focus, Escape and the backdrop
// behave without a modal library.
export function AdminSignIn({
  admin,
  labels,
  onSignedIn,
  onSignOut,
}: {
  admin: boolean
  labels: SignInLabels
  onSignedIn: (token: string) => void
  onSignOut: () => void
}) {
  const dialogRef = useRef<HTMLDialogElement | null>(null)
  const [open, setOpen] = useState(false)
  const [password, setPassword] = useState("")
  const [busy, setBusy] = useState(false)
  const [wrong, setWrong] = useState(false)

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setWrong(false)
    try {
      const result = await signIn(password)
      if (!result) {
        setWrong(true)
        return
      }
      setPassword("")
      setOpen(false)
      onSignedIn(result.token)
    } catch {
      setWrong(true)
    } finally {
      setBusy(false)
    }
  }

  if (admin) {
    return (
      <Button variant="ghost" size="sm" onClick={onSignOut} className="h-9 gap-1.5 text-xs">
        <ShieldCheck aria-hidden="true" className="size-4 text-green-600" />
        <span className="max-sm:sr-only">{labels.signedIn}</span>
        <span aria-hidden="true" className="text-muted-foreground max-sm:hidden">
          ·
        </span>
        <span className="text-muted-foreground">{labels.signOut}</span>
      </Button>
    )
  }

  return (
    <>
      <Button variant="ghost" size="sm" onClick={() => setOpen(true)} className="h-9 gap-1.5 text-xs text-muted-foreground">
        <Lock aria-hidden="true" className="size-4" />
        <span className="max-sm:sr-only">{labels.signIn}</span>
      </Button>
      <dialog
        ref={dialogRef}
        onClose={() => setOpen(false)}
        aria-label={labels.title}
        className="m-auto w-[min(26rem,calc(100vw-2rem))] rounded-2xl bg-background p-0 text-foreground shadow-2xl backdrop:bg-slate-950/40 backdrop:backdrop-blur-sm"
      >
        <form onSubmit={submit} className="flex flex-col gap-3 p-5">
          <div>
            <h2 className="font-heading text-base font-semibold">{labels.title}</h2>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{labels.body}</p>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="admin-password">{labels.password}</Label>
            <Input
              id="admin-password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              aria-invalid={wrong || undefined}
              aria-describedby={wrong ? "admin-password-error" : undefined}
              className="h-11 text-center"
              autoFocus
            />
            {wrong && (
              <p id="admin-password-error" role="alert" className="text-xs text-destructive">
                {labels.wrong}
              </p>
            )}
          </div>
          <div className="flex gap-2">
            <Button type="submit" disabled={busy || !password} className="h-11 flex-1 sm:h-9">
              {busy ? labels.submitting : labels.submit}
            </Button>
            <Button type="button" variant="outline" onClick={() => setOpen(false)} className="h-11 sm:h-9">
              {labels.cancel}
            </Button>
          </div>
        </form>
      </dialog>
    </>
  )
}
