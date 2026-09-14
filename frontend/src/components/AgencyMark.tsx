import { PlaneTakeoff, Siren, type LucideIcon } from "lucide-react"
import type { Agency } from "@/lib/agency"
import { cn } from "@/lib/utils"

// Official marks are the agencies' own artwork and are not recreated here. To show them, add
// the files under frontend/public/authorities/ and set `logo` to that path, for example
// "authorities/police.svg". Until then each agency shows a plain icon badge in its place.
const AGENCIES: Record<Agency, { logo: string | null; icon: LucideIcon; badge: string }> = {
  // Saudi Public Security police emblem, CC BY-SA 4.0; credit in public/authorities/CREDITS.md
  police: { logo: "authorities/police.png", icon: Siren, badge: "bg-blue-900 text-white" },
  airport_security: { logo: null, icon: PlaneTakeoff, badge: "bg-sky-700 text-white" },
}

// Decorative: the agency's name is always written beside it.
export function AgencyMark({ agency, className }: { agency: Agency; className?: string }) {
  const { logo, icon: Icon, badge } = AGENCIES[agency]
  if (logo) {
    return (
      <img
        src={`${import.meta.env.BASE_URL}${logo}`}
        alt=""
        aria-hidden="true"
        className={cn("size-8 shrink-0 object-contain", className)}
      />
    )
  }
  return (
    <span
      aria-hidden="true"
      className={cn("grid size-8 shrink-0 place-items-center rounded-full shadow-sm ring-2 ring-white", badge, className)}
    >
      <Icon className="size-[55%]" strokeWidth={2.25} />
    </span>
  )
}
