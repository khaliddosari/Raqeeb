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
  docTitle: "Raqeeb · Checkpoint Monitor",
  switchTo: "العربية",
  switchToLang: "ar" as Lang,
  switchToLabel: "Switch to Arabic",
  timeZone: "AST",
  team: "Team",
  onLinkedIn: (name: string) => `${name} on LinkedIn`,
  dismiss: "Click to dismiss",
  footer: "Raqeeb · screening and response for government and private security",

  // detection classes, severities, pipeline states, agencies and checkpoints come from the
  // backend as codes
  detectionClass: identity,
  severity: identity,
  status: identity,
  location: identity,
  agency: (key: string) => ({ police: "Police", airport_security: "Airport Security" })[key] ?? key,

  preview: {
    title: "Detection preview",
    caption: "The trained detector tracking prohibited items across a belt clip, frame by frame.",
    status: "Live loop",
    paused: "Paused",
    pause: "Pause preview",
    play: "Play preview",
    description:
      "Built for government and private security agencies. A YOLOv8-OBB model flags five classes of prohibited item in X-ray baggage scans: guns, knives, pliers, scissors and wrenches. An employee verifies the find on the spot, then a voice agent writes the report and calls the right authority: the police for guns and knives, airport security for the tools.",
  },

  inference: {
    title: "Inference",
    caption:
      "Upload any X-ray frame, or run the bundled one. The model returns an annotated render and the flagged class, which starts an incident.",
    awaiting: "awaiting frame",
    analysing: "analysing",
    failed: "failed",
    employee: "Employee",
    employeeNumber: "Employee number",
    employeeNumberPlaceholder: "05X XXX XXXX",
    employeeNumberHelp: "Saudi mobile. The dispatch call rings this number.",
    employeeNumberInvalid: "Enter a Saudi mobile number, such as 0551234567.",
    location: "Location",
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
    annotatedAlt: "Annotated detection",
    selectedAlt: "Selected frame",
    confidence: (pct: string) => `${pct}% confidence`,
    routesTo: "Routes to",
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
    generating: "generating",
    sendFailed: "delivery failed",
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
    notified: "Notified",
    emptyTitle: "No report yet",
    empty: "Run a detection and confirm it to generate one.",
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
    emptyTitle: "No transcript yet",
    empty: "Turns appear here once a live call is running; mock telephony places no call.",
  },

  judgment: {
    title: "Judgment",
    caption: "Why the system acted as it did, and what the authority decided.",
    dispatchConfirmedPill: "dispatch confirmed",
    notConfirmedPill: "not confirmed",
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
    emptyTitle: "Nothing to explain yet",
    empty: "The reasoning behind each decision appears here once a detection opens an incident.",
  },
}

type Dict = typeof en

const AR_CLASSES: Record<string, string> = {
  Gun: "سلاح ناري",
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

const AR_LOCATIONS: Record<string, string> = {
  "Terminal 1": "الصالة 1",
  "Terminal 2": "الصالة 2",
  "Terminal 3": "الصالة 3",
  "Terminal 4": "الصالة 4",
  "Terminal 5": "الصالة 5",
  "Private Aviation Terminal": "صالة الطيران الخاص",
}

const AR_AGENCIES: Record<string, string> = {
  police: "الشرطة",
  airport_security: "أمن المطار",
}

const AR_ROLES: Record<string, string> = {
  assistant: "الوكيل",
  authority: "الجهة",
}

const lookup = (table: Record<string, string>) => (value: string) => table[value] ?? value

const ar: Dict = {
  brand: "رقيب",
  docTitle: "رقيب · شاشة مراقبة نقطة التفتيش",
  switchTo: "English",
  switchToLang: "en",
  switchToLabel: "التبديل إلى الإنجليزية",
  timeZone: "بتوقيت السعودية",
  team: "الفريق",
  onLinkedIn: (name: string) => `${name} على لينكدإن`,
  dismiss: "انقر للإغلاق",
  footer: "رقيب · الفحص والاستجابة للجهات الأمنية الحكومية والخاصة",

  detectionClass: lookup(AR_CLASSES),
  severity: lookup(AR_SEVERITY),
  status: lookup(AR_STATUS),
  location: lookup(AR_LOCATIONS),
  agency: lookup(AR_AGENCIES),

  preview: {
    title: "معاينة الكشف",
    caption: "النموذج المدرَّب يتتبع المواد المحظورة على سير الأمتعة إطارًا بإطار.",
    status: "عرض حي",
    paused: "متوقف مؤقتًا",
    pause: "إيقاف المعاينة مؤقتًا",
    play: "تشغيل المعاينة",
    description:
      "مصمَّم للجهات الأمنية الحكومية والخاصة. يرصد نموذج YOLOv8-OBB خمس فئات من المواد المحظورة في صور الأشعة السينية للأمتعة: الأسلحة النارية والسكاكين والكماشات والمقصات ومفاتيح الربط. يتحقق منها الموظف ميدانيًا، ثم يكتب وكيل صوتي البلاغ ويتصل بالجهة المختصة: الشرطة للأسلحة النارية والسكاكين، وأمن المطار للأدوات.",
  },

  inference: {
    title: "الفحص",
    caption:
      "ارفع أي صورة أشعة سينية أو شغّل الصورة التجريبية، فيعيد النموذج صورة موسومة والفئة المرصودة، وتُفتح بذلك حادثة.",
    awaiting: "بانتظار صورة",
    analysing: "جارٍ التحليل",
    failed: "تعذّر الكشف",
    employee: "الموظف",
    employeeNumber: "رقم الموظف",
    employeeNumberPlaceholder: "05X XXX XXXX",
    employeeNumberHelp: "رقم جوال سعودي، ويُوجَّه إليه اتصال الإبلاغ.",
    employeeNumberInvalid: "أدخل رقم جوال سعوديًا، مثل 0551234567.",
    location: "الموقع",
    frame: "صورة الفحص",
    chooseFile: "اختيار ملف",
    noFile: "لم يُختر ملف",
    runDetection: "تحليل الكشف",
    runningDetection: "جارٍ الكشف…",
    runTest: "رفع صورة جاهزة للإختبار",
    runningTest: "جارٍ التشغيل…",
    testCaption: "صورة أشعة سينية مرفقة لتجربة المسار دون البحث عن صورة.",
    testAria: "تحليل الكشف على الصورة التجريبية المرفقة",
    testAlt: "صورة أشعة سينية تجريبية",
    annotatedOutput: "النتيجة الموسومة",
    input: "الصورة المدخلة",
    annotatedAlt: "صورة الكشف الموسومة",
    selectedAlt: "الصورة المختارة",
    // Isolated: after Arabic letters, bidi rules would otherwise move the percent sign to the far side.
    confidence: (pct: string) => `نسبة الثقة \u2066${pct}%\u2069`,
    routesTo: "يُحال إلى",
    pipeline: "الخط الزمني للبلاغ",
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
    title: "كرت البلاغ",
    caption: "يُنشأ من الكشف المُتحقَّق منه، ثم يُوجَّه إلى الجهة المختصة.",
    generated: "أُنشئ",
    generating: "جارٍ الإنشاء",
    sendFailed: "تعذّر الإرسال",
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
    notified: "الجهة المُبلَّغة",
    emptyTitle: "لا يوجد بلاغ بعد",
    empty: "شغّل الكشف وأكّده لإنشاء بلاغ.",
  },

  call: {
    title: "بث الإتصال الحي",
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
    emptyTitle: "لا يوجد نص بعد",
    empty: "تظهر الحوارات هنا عند بدء اتصال فعلي، ولا يُجري وضع المحاكاة أي اتصال.",
  },

  judgment: {
    title: "التقييم",
    caption: "لماذا تصرّف النظام على هذا النحو، وماذا قررت الجهة.",
    dispatchConfirmedPill: "تأكّد الإرسال",
    notConfirmedPill: "لم يتأكد",
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
    emptyTitle: "لا شيء لتوضيحه بعد",
    empty: "يظهر هنا منطق كل قرار بعد أن يفتح الكشف حادثة.",
  },
}

export const STRINGS: Record<Lang, Dict> = { en, ar }
