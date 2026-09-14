// The on-duty employees a demo can pick: the team. The dispatch call rings the chosen person's
// mobile unless a one-time number is typed for a single run. The name goes to the backend in
// Arabic in both interface languages, like everything else that reaches the call.

import type { Lang } from "@/lib/i18n"

export type Employee = { id: string; name: Record<Lang, string>; phone: string }

export const EMPLOYEES: readonly Employee[] = [
  { id: "khalid", name: { en: "Khalid Al Dosari", ar: "خالد آل دوسري" }, phone: "0553225155" },
  { id: "yazeed", name: { en: "Yazeed Bin Shihah", ar: "يزيد بن شيحة" }, phone: "0554626773" },
  { id: "nawaf", name: { en: "Nawaf Alsharani", ar: "نواف الشهراني" }, phone: "0540448590" },
  { id: "omar", name: { en: "Omar Al-Dhawyan", ar: "عمر الضويان" }, phone: "0565448517" },
]

export const employeeById = (id: string): Employee => EMPLOYEES.find((employee) => employee.id === id) ?? EMPLOYEES[0]
