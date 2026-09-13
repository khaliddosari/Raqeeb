export type Lang = "en" | "ar"

const STORAGE_KEY = "raqeeb.lang"

export function initialLang(): Lang {
  try {
    return localStorage.getItem(STORAGE_KEY) === "ar" ? "ar" : "en"
  } catch {
    return "en"
  }
}

export function rememberLang(lang: Lang) {
  try {
    localStorage.setItem(STORAGE_KEY, lang)
  } catch {
    // private windows and blocked storage: the choice just does not persist
  }
}

export function applyDocumentLang(lang: Lang) {
  const root = document.documentElement
  root.lang = lang
  root.dir = lang === "ar" ? "rtl" : "ltr"
}

const identity = (value: string) => value

const en = {
  brand: "Raqeeb",
  brandMark: "R",
  docTitle: "Raqeeb · Checkpoint Monitor",
  switchTo: "العربية",
  switchToLang: "ar" as Lang,
  switchToLabel: "Switch to Arabic",
  timeZone: "AST",
  team: "Team",
  onLinkedIn: (name: string) => `${name} on LinkedIn`,
  dismiss: "Click to dismiss",
  footer: "Raqeeb · automated checkpoint security agent",

  // detection classes, severities and pipeline states come from the backend as codes
  detectionClass: identity,
  severity: identity,
  status: identity,

  preview: {
    title: "Detection preview",
    caption: "The trained detector tracking prohibited items across a belt clip, frame by frame.",
    status: "Live loop",
    pause: "Pause preview",
    play: "Play preview",
    description:
      "A YOLOv8-OBB model flags prohibited items in X-ray baggage scans, an employee physically verifies the find, and a voice agent then collects the details, writes the report, routes it to the responsible authority and phones them to request dispatch.",
  },

  inference: {
    title: "Inference",
    caption:
      "Upload any X-ray frame, or run the bundled one. The model returns an annotated render and the flagged class, which starts an incident.",
    awaiting: "awaiting frame",
    employee: "Employee",
    employeeId: "Employee ID",
    frame: "Frame image",
    chooseFile: "Choose file",
    noFile: "No file chosen",
    runDetection: "Run detection",
    runningDetection: "Running detection…",
    runTest: "Run test image",
    runningTest: "Running…",
    testCaption: "A bundled X-ray frame, for trying the pipeline without finding an image.",
    testAria: "Run detection on the bundled test image",
    testAlt: "Bundled X-ray test frame",
    annotatedOutput: "Annotated output",
    input: "Input",
    noFrame: "No frame selected",
    annotatedAlt: "Annotated detection",
    selectedAlt: "Selected frame",
    confidence: (pct: string) => `${pct}% confidence`,
    pipeline: "Pipeline",
    openIncident: "Run a detection to open an incident.",
    confirm: "Confirm threat",
    falsePositive: "False positive",
    falsePositiveClosed: "Marked a false positive by the employee. The incident is closed.",
    submitted: "Details submitted. The report, call and judgment continue below.",
    suspectDetails: "Suspect details",
    suspectHelp:
      "Typed alternative to collecting these by voice. Both fields are required before a report can be generated.",
    fullName: "Full name",
    fullNamePlaceholder: "e.g. Faisal Al-Harbi",
    idNumber: "ID number",
    idNumberPlaceholder: "e.g. 1093847562",
    notes: "Inspection notes (optional)",
    notesPlaceholder: "e.g. Cooperative, detained at checkpoint",
    submit: "Submit suspect details",
    generating: "Generating report…",
  },

  report: {
    title: "Incident report",
    caption: "Generated from the verified detection, then routed to the responsible authority.",
    generated: "generated",
    pending: "pending",
    record: "Record",
    narrative: "Narrative",
    incident: "Incident",
    detectedItem: "Detected item",
    confidence: "Confidence",
    location: "Location",
    severity: "Severity",
    suspect: "Suspect",
    suspectId: "Suspect ID",
    employee: "Employee",
    notes: "Notes",
    empty: "No report yet. Run a detection and confirm it to generate one.",
  },

  call: {
    title: "Authority call monitor",
    caption: "The outbound call to the responsible authority, streamed turn by turn as it happens.",
    ended: "ended",
    inProgress: "in progress",
    noCall: "no call",
    authority: "Authority",
    number: "Number",
    callSid: "Call SID",
    transcript: "Transcript",
    connected: "connected",
    disconnected: "disconnected",
    role: identity,
    empty: "No transcript. Turns appear here once a live call is running; mock telephony places no call.",
  },

  judgment: {
    title: "Judgment",
    caption: "Why the system acted as it did, and what the authority decided.",
    dispatchConfirmedPill: "dispatch confirmed",
    awaitingDecision: "awaiting decision",
    pending: "pending",
    decision: "Authority decision",
    dispatchConfirmed: "Dispatch confirmed",
    dispatchNotConfirmed: "Dispatch not confirmed",
    noDecision: "No decision recorded. This is filled by the authority during the call.",
    reasoning: "System reasoning",
    detection: "Detection",
    detectionBody: (cls: string, pct: string) => [`Flagged `, cls, ` at `, pct, `, above the configured threshold.`],
    verification: "Verification",
    verifiedBy: (name: string) => `Physically confirmed by ${name}. The model never overrides this.`,
    theEmployee: "the employee",
    notVerified: "Not yet confirmed by an employee.",
    routing: "Routing",
    routingBody: (severity: string, authority: string) => [
      `Severity `,
      severity,
      ` for this class, routed to `,
      authority,
      ` per the class-to-authority mapping.`,
    ],
    recommendedAction: "Recommended action",
    empty: "Nothing to explain yet.",
  },
}

type Dict = typeof en

const AR_CLASSES: Record<string, string> = {
  Gun: "مسدس",
  Knife: "سكين",
  Pliers: "كماشة",
  Scissors: "مقص",
  Wrench: "مفتاح ربط",
}

const AR_SEVERITY: Record<string, string> = {
  low: "منخفضة",
  medium: "متوسطة",
  high: "عالية",
  critical: "حرجة",
}

const AR_STATUS: Record<string, string> = {
  idle: "خامل",
  detected: "كُشف",
  pending_verification: "بانتظار التحقق",
  verified: "تم التحقق",
  collecting_information: "جمع البيانات",
  awaiting_more_information: "بانتظار بيانات إضافية",
  information_validated: "اكتملت البيانات",
  report_generated: "أُنشئ البلاغ",
  authority_determined: "حُددت الجهة",
  report_sent: "أُرسل البلاغ",
  report_send_failed: "تعذّر إرسال البلاغ",
  call_in_progress: "الاتصال جارٍ",
  authority_responded: "ردّت الجهة",
  closed: "مغلقة",
  closed_unconfirmed: "مغلقة دون تأكيد",
  false_positive: "إنذار خاطئ",
}

const AR_ROLES: Record<string, string> = {
  assistant: "الوكيل",
  authority: "الجهة",
}

const lookup = (table: Record<string, string>) => (value: string) => table[value] ?? value

const ar: Dict = {
  brand: "رقيب",
  brandMark: "ر",
  docTitle: "رقيب · شاشة مراقبة نقطة التفتيش",
  switchTo: "English",
  switchToLang: "en",
  switchToLabel: "التبديل إلى الإنجليزية",
  timeZone: "بتوقيت الرياض",
  team: "الفريق",
  onLinkedIn: (name: string) => `${name} على لينكدإن`,
  dismiss: "انقر للإغلاق",
  footer: "رقيب · وكيل آلي لأمن نقاط التفتيش",

  detectionClass: lookup(AR_CLASSES),
  severity: lookup(AR_SEVERITY),
  status: lookup(AR_STATUS),

  preview: {
    title: "معاينة الكشف",
    caption: "النموذج المدرَّب يتتبع المواد المحظورة على سير الأمتعة إطارًا بإطار.",
    status: "عرض متواصل",
    pause: "إيقاف المعاينة مؤقتًا",
    play: "تشغيل المعاينة",
    description:
      "يرصد نموذج YOLOv8-OBB المواد المحظورة في صور الأشعة السينية للأمتعة، ويتحقق منها الموظف ميدانيًا، ثم يتولى وكيل صوتي جمع التفاصيل وكتابة البلاغ وتوجيهه إلى الجهة المختصة والاتصال بها لطلب إرسال فريق.",
  },

  inference: {
    title: "الفحص",
    caption:
      "ارفع أي صورة أشعة سينية أو شغّل الصورة التجريبية، فيعيد النموذج صورة موسومة والفئة المرصودة، وتُفتح بذلك حادثة.",
    awaiting: "بانتظار صورة",
    employee: "الموظف",
    employeeId: "الرقم الوظيفي",
    frame: "صورة الفحص",
    chooseFile: "اختيار ملف",
    noFile: "لم يُختر ملف",
    runDetection: "تشغيل الكشف",
    runningDetection: "جارٍ الكشف…",
    runTest: "تشغيل الصورة التجريبية",
    runningTest: "جارٍ التشغيل…",
    testCaption: "صورة أشعة سينية مرفقة لتجربة المسار دون البحث عن صورة.",
    testAria: "تشغيل الكشف على الصورة التجريبية المرفقة",
    testAlt: "صورة أشعة سينية تجريبية",
    annotatedOutput: "النتيجة الموسومة",
    input: "الصورة المدخلة",
    noFrame: "لم تُختر صورة",
    annotatedAlt: "صورة الكشف الموسومة",
    selectedAlt: "الصورة المختارة",
    confidence: (pct: string) => `نسبة الثقة ${pct}%`,
    pipeline: "مسار الحادثة",
    openIncident: "شغّل الكشف لفتح حادثة.",
    confirm: "تأكيد التهديد",
    falsePositive: "إنذار خاطئ",
    falsePositiveClosed: "صنّفه الموظف إنذارًا خاطئًا، وأُغلقت الحادثة.",
    submitted: "أُرسلت التفاصيل، ويُستكمل البلاغ والاتصال والتقييم في الأقسام التالية.",
    suspectDetails: "بيانات المشتبه به",
    suspectHelp: "بديل كتابي لجمع هذه البيانات صوتيًا. الحقلان مطلوبان قبل إنشاء البلاغ.",
    fullName: "الاسم",
    fullNamePlaceholder: "مثال: فيصل الحربي",
    idNumber: "رقم الهوية",
    idNumberPlaceholder: "مثال: 1093847562",
    notes: "ملاحظات الفحص (اختياري)",
    notesPlaceholder: "مثال: متعاون، ومحتجز في نقطة التفتيش",
    submit: "إرسال بيانات المشتبه به",
    generating: "جارٍ إنشاء البلاغ…",
  },

  report: {
    title: "بلاغ الحادثة",
    caption: "يُنشأ من الكشف المُتحقَّق منه، ثم يُوجَّه إلى الجهة المختصة.",
    generated: "أُنشئ",
    pending: "قيد الانتظار",
    record: "السجل",
    narrative: "السرد",
    incident: "رقم الحادثة",
    detectedItem: "المادة المرصودة",
    confidence: "نسبة الثقة",
    location: "الموقع",
    severity: "الخطورة",
    suspect: "المشتبه به",
    suspectId: "هوية المشتبه به",
    employee: "الموظف",
    notes: "الملاحظات",
    empty: "لا يوجد بلاغ بعد. شغّل الكشف وأكّده لإنشاء بلاغ.",
  },

  call: {
    title: "مراقبة الاتصال بالجهة",
    caption: "الاتصال الصادر بالجهة المختصة، يُبث حوارًا بحوار لحظة وقوعه.",
    ended: "انتهى",
    inProgress: "جارٍ",
    noCall: "لا يوجد اتصال",
    authority: "الجهة",
    number: "الرقم",
    callSid: "معرّف الاتصال",
    transcript: "نص المكالمة",
    connected: "متصل",
    disconnected: "غير متصل",
    role: lookup(AR_ROLES),
    empty: "لا يوجد نص بعد. تظهر الحوارات هنا عند بدء اتصال فعلي، ولا يُجري وضع المحاكاة أي اتصال.",
  },

  judgment: {
    title: "التقييم",
    caption: "لماذا تصرّف النظام على هذا النحو، وماذا قررت الجهة.",
    dispatchConfirmedPill: "تأكّد الإرسال",
    awaitingDecision: "بانتظار القرار",
    pending: "قيد الانتظار",
    decision: "قرار الجهة",
    dispatchConfirmed: "تأكّد إرسال الفريق",
    dispatchNotConfirmed: "لم يتأكد إرسال الفريق",
    noDecision: "لم يُسجَّل قرار بعد، وتُحدده الجهة أثناء الاتصال.",
    reasoning: "منطق النظام",
    detection: "الكشف",
    detectionBody: (cls: string, pct: string) => [`رُصد `, cls, ` بنسبة ثقة `, pct, `، أعلى من الحد المُعدّ.`],
    verification: "التحقق",
    verifiedBy: (name: string) => `تحقق منه ${name} ميدانيًا، ولا يتجاوز النموذج هذا القرار أبدًا.`,
    theEmployee: "الموظف",
    notVerified: "لم يتحقق منه موظف بعد.",
    routing: "التوجيه",
    routingBody: (severity: string, authority: string) => [
      `الخطورة `,
      severity,
      ` لهذه الفئة، ووُجّه البلاغ إلى `,
      authority,
      ` وفق جدول ربط الفئات بالجهات.`,
    ],
    recommendedAction: "الإجراء الموصى به",
    empty: "لا شيء لتوضيحه بعد.",
  },
}

export const STRINGS: Record<Lang, Dict> = { en, ar }
