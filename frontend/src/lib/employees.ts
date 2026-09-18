// The on-duty employees the picker offers, as the backend lists them.
//
// No phone number is in this bundle: they are configured on the server (ADMIN_CALL_NUMBERS) and
// only sent to a signed-in dashboard, which prefills them into an editable field. A public
// dashboard never receives one, and a visitor types their own name instead of picking a person.

export type Employee = {
  key: string
  name_ar: string
  name_en: string
  badge: string
  /** only present for a signed-in dashboard: the mobile the dispatch call rings, editable there */
  phone?: string
}

export const employeeName = (employee: Employee, lang: "en" | "ar") =>
  lang === "ar" ? employee.name_ar : employee.name_en

export const employeeByKey = (employees: readonly Employee[], key: string): Employee | null =>
  employees.find((employee) => employee.key === key) ?? employees[0] ?? null
