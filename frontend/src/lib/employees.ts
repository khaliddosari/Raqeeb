// The on-duty employees the picker offers, as the backend lists them.
//
// Deliberately no phone numbers: this bundle is public. The mobile the dispatch call rings is
// configured on the server (ADMIN_CALL_NUMBERS) and never sent here, not even to a signed-in
// dashboard, which only learns whether a number exists at all.

export type Employee = {
  key: string
  name_ar: string
  name_en: string
  badge: string
  /** only present for a signed-in dashboard: whether this person can be phoned at all */
  has_number?: boolean
}

export const employeeName = (employee: Employee, lang: "en" | "ar") =>
  lang === "ar" ? employee.name_ar : employee.name_en

export const employeeByKey = (employees: readonly Employee[], key: string): Employee | null =>
  employees.find((employee) => employee.key === key) ?? employees[0] ?? null
