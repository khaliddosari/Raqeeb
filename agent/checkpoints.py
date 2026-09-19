"""The checkpoints a detection can come from, each with a demo scenario.

This is the one backend source for locations: agent/intake.py validates against it, the call
reads the spoken names from it, and the report and the call both carry its scenario. The
dashboard keeps its own copies of the codes and display names (frontend/src/lib/intake.ts and
lib/i18n.ts), and frontend/design/render_passes.py builds the demo passes and the pass chooser
page from this file, so change them together.

The scenarios are fictional operational context for demonstrations: which gate, how crowded, who
carried the bag, what staff have already done, and how responders should come in. They are not
claims about how the real events are run. Each is written in Arabic with no Latin text, because
the voice agent reads them and may be asked about any of them on the call.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Suspect:
    """Fictional. Only frontend/design/render_passes.py reads this: the dashboard scans the pass
    and sends the name and number like typed details, so the backend never looks it up."""

    name: str
    id_number: str
    """Nine digits starting with a zero, a shape no Saudi ID can have: they are ten digits and
    start with 1 or 2. So a demo number cannot collide with a real person's."""
    pass_type: str
    """What the pass is, matching how the scenario's bag carrier line describes it."""


@dataclass(frozen=True)
class Checkpoint:
    code: str
    """Stored on the incident and sent by the dashboard."""
    name_ar: str
    """As the dashboard writes it."""
    spoken_ar: str
    """As the voice agent says it: Arabic script only, brand names transliterated."""
    pass_slug: str
    """frontend/public/passes/<slug>.json and its QR code."""
    scenario: tuple[tuple[str, str], ...]
    """Ordered (label, detail) pairs, in Arabic."""
    suspect: Suspect
    """The bag carrier the scenario describes, as printed on the pass they show at the checkpoint."""


CHECKPOINTS: tuple[Checkpoint, ...] = (
    Checkpoint(
        code="Private Aviation Terminal",
        name_ar="صالة الطيران الخاص",
        spoken_ar="صالة الطيران الخاص",
        pass_slug="private-aviation",
        scenario=(
            ("الفعالية", "وصول رحلة طيران خاص تقلّ وفد أعمال من ستة أشخاص"),
            ("المكان", "صالة الطيران الخاص، منطقة استقبال كبار الزوار"),
            ("نقطة التفتيش", "جهاز فحص الأمتعة المحمولة رقم 2 قبل قاعة الانتظار"),
            ("الوضع وقت الرصد", "حركة محدودة، نحو 12 شخصًا بين مسافرين وطاقم وموظفين"),
            ("حامل الحقيبة", "أحد مرافقي الوفد، هادئ ومتعاون ولم يُبدِ أي اعتراض"),
            ("وصف الحقيبة", "حقيبة يد جلدية سوداء صغيرة"),
            ("الإجراءات المتخذة", "عُزلت الحقيبة عند الجهاز، ونُقل حاملها إلى غرفة التفتيش الثانوي بمرافقة موظف"),
            ("مسار وصول الفريق", "من البوابة الجانبية لساحة الطائرات مباشرة إلى منطقة التفتيش"),
            ("أقرب نقطة أمنية", "مكتب أمن الصالة على بعد نحو 40 مترًا"),
        ),
        suspect=Suspect(name="فيصل فهد", id_number="093847562", pass_type="بطاقة صعود الطائرة"),
    ),
    Checkpoint(
        code="LEAP 2026 Exhibition",
        name_ar="معرض LEAP 2026",
        spoken_ar="معرض ليب 2026",
        pass_slug="leap-2026",
        scenario=(
            ("الفعالية", "اليوم الثاني من المعرض التقني، في ذروة دخول الزوار صباحًا"),
            ("المكان", "مركز المعارض والمؤتمرات، مدخل القاعة الرئيسية"),
            ("نقطة التفتيش", "بوابة الزوار رقم 3، المسار السريع لحاملي التذاكر"),
            ("الوضع وقت الرصد", "ازدحام مرتفع، وطابور يتجاوز 200 زائر عند البوابة"),
            ("حامل الحقيبة", "زائر يحمل بطاقة دخول عامة، متعاون لكنه مستعجل"),
            ("وصف الحقيبة", "حقيبة ظهر رمادية تحتوي أجهزة إلكترونية وأسلاكًا"),
            ("الإجراءات المتخذة", "أُوقف المسار مؤقتًا، وعُزلت الحقيبة، وحُوّل الزوار إلى البوابة المجاورة"),
            ("مسار وصول الفريق", "من مدخل الخدمات الخلفي عبر الممر المخصص للطوارئ"),
            ("أقرب نقطة أمنية", "غرفة العمليات الأمنية للمعرض خلف البوابة رقم 3"),
        ),
        suspect=Suspect(name="سلطان عبدالعزيز", id_number="028459307", pass_type="بطاقة دخول عامة"),
    ),
    Checkpoint(
        code="Future Investment Initiative",
        name_ar="مبادرة مستقبل الاستثمار",
        spoken_ar="مؤتمر مبادرة مستقبل الاستثمار",
        pass_slug="fii",
        scenario=(
            ("الفعالية", "جلسة رئيسية بحضور كبار المستثمرين وقادة الشركات"),
            ("المكان", "مقر المؤتمر في الرياض، مدخل الوفود"),
            ("نقطة التفتيش", "نقطة تفتيش الوفود عند المدخل الرئيسي"),
            ("الوضع وقت الرصد", "توافد الوفود قبل الجلسة بعشرين دقيقة، مع حضور أمني مكثف"),
            ("حامل الحقيبة", "مشارك يحمل بطاقة وفد، هادئ وطلب التحدث مع منسّق وفده"),
            ("وصف الحقيبة", "حقيبة أوراق معدنية فضية"),
            ("الإجراءات المتخذة", "عُزلت الحقيبة في غرفة جانبية، وأُبلغ منسّق الوفود، ومُنع حاملها من الدخول مؤقتًا"),
            ("مسار وصول الفريق", "من مدخل الخدمة الشرقي تفاديًا لممر الوفود"),
            ("أقرب نقطة أمنية", "مركز القيادة الأمنية في الطابق الأرضي"),
        ),
        suspect=Suspect(name="ماجد سعد", id_number="076238415", pass_type="بطاقة وفد"),
    ),
    Checkpoint(
        code="Saudi Falcons and Hunting Exhibition",
        name_ar="معرض الصقور والصيد السعودي الدولي",
        spoken_ar="معرض الصقور والصيد السعودي الدولي",
        pass_slug="falcons",
        scenario=(
            ("الفعالية", "معرض الصيد والرحلات البرية، ويعرض فيه العارضون أدوات الصيد والتخييم"),
            ("المكان", "موقع المعرض شمال الرياض، مدخل أجنحة العارضين"),
            ("نقطة التفتيش", "بوابة الزوار رقم 1 المؤدية إلى أجنحة أدوات الصيد"),
            ("الوضع وقت الرصد", "إقبال عائلي متوسط في الفترة المسائية"),
            ("حامل الحقيبة", "زائر يحمل بطاقة زائر عام، أفاد بأنه اشترى المادة من أحد الأجنحة"),
            ("وصف الحقيبة", "حقيبة تسوق قماشية خضراء"),
            ("الإجراءات المتخذة", "احتُجزت المادة عند البوابة، ويُجرى التحقق من فاتورة الشراء مع الجناح المعني"),
            ("مسار وصول الفريق", "من بوابة المركبات الخدمية المجاورة لمواقف العارضين"),
            ("أقرب نقطة أمنية", "خيمة الأمن والسلامة بجوار البوابة رقم 1"),
        ),
        suspect=Suspect(name="تركي محمد", id_number="049571836", pass_type="بطاقة زائر عام"),
    ),
    Checkpoint(
        code="Money20/20 Middle East",
        name_ar="Money20/20 الشرق الأوسط",
        spoken_ar="مؤتمر موني عشرين عشرين الشرق الأوسط",
        pass_slug="money2020",
        scenario=(
            ("الفعالية", "مؤتمر التقنية المالية، اليوم الأول قبيل حفل الافتتاح"),
            ("المكان", "مركز المعارض والمؤتمرات، مدخل قاعة المؤتمرات"),
            ("نقطة التفتيش", "بوابة كبار الزوار والمتحدثين"),
            ("الوضع وقت الرصد", "ازدحام متوسط قبل الكلمة الافتتاحية"),
            ("حامل الحقيبة", "عارض يحمل بطاقة جناح، قال إن محتوى الحقيبة من معدات العرض"),
            ("وصف الحقيبة", "صندوق معدات أسود بعجلات"),
            ("الإجراءات المتخذة", "عُزل الصندوق في منطقة التفتيش الثانوي، وجرى التواصل مع إدارة الجناح"),
            ("مسار وصول الفريق", "من رصيف التحميل الخلفي المخصص للعارضين"),
            ("أقرب نقطة أمنية", "نقطة الأمن عند رصيف التحميل"),
        ),
        suspect=Suspect(name="رامي خالد", id_number="045718690", pass_type="بطاقة جناح"),
    ),
    Checkpoint(
        code="Black Hat MEA",
        name_ar="بلاك هات الشرق الأوسط وأفريقيا",
        spoken_ar="مؤتمر بلاك هات الشرق الأوسط وأفريقيا",
        pass_slug="blackhat",
        scenario=(
            ("الفعالية", "مؤتمر الأمن السيبراني، منطقة الورش والتحديات التقنية"),
            ("المكان", "مركز المعارض والمؤتمرات، مدخل قاعة الورش"),
            ("نقطة التفتيش", "بوابة المشاركين رقم 2"),
            ("الوضع وقت الرصد", "ازدحام مرتفع مع بدء فعاليات الورش"),
            ("حامل الحقيبة", "مشارك يحمل بطاقة ورشة، أفاد بأن الأدوات تخص ورشة للعتاد الإلكتروني"),
            ("وصف الحقيبة", "حقيبة أدوات صلبة زرقاء"),
            ("الإجراءات المتخذة", "عُزلت الحقيبة، ويُتحقق من تسجيله في الورشة مع منظمي المنطقة"),
            ("مسار وصول الفريق", "من ممر الطوارئ الغربي المؤدي مباشرة إلى بوابة المشاركين"),
            ("أقرب نقطة أمنية", "مكتب أمن القاعة بجوار منطقة التسجيل"),
        ),
        suspect=Suspect(name="نايف عبدالله", id_number="010268475", pass_type="بطاقة ورشة"),
    ),
)

BY_CODE: dict[str, Checkpoint] = {checkpoint.code: checkpoint for checkpoint in CHECKPOINTS}


def scenario_for(code: str | None) -> dict[str, str]:
    """The scenario for a checkpoint as an ordered label-to-detail mapping; empty if unknown."""
    checkpoint = BY_CODE.get(code or "")
    return dict(checkpoint.scenario) if checkpoint else {}
