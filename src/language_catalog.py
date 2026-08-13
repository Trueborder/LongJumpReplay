from __future__ import annotations


# Native names keep the language selector understandable before the interface
# has changed language. Dict insertion order is the order shown in Settings.
LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "cs": "Čeština",
    "sk": "Slovenčina",
    "pl": "Polski",
    "hu": "Magyar",
    "de": "Deutsch",
    "zh": "中文（简体）",
    "hi": "हिन्दी",
    "es": "Español",
    "fr": "Français",
    "ar": "العربية",
    "bn": "বাংলা",
    "pt": "Português",
    "ru": "Русский",
    "id": "Bahasa Indonesia",
    "ur": "اردو",
}

SUPPORTED_LANGUAGES: tuple[str, ...] = tuple(LANGUAGE_NAMES)
LANGUAGE_OPTIONS: tuple[str, ...] = tuple(f"{name} ({code})" for code, name in LANGUAGE_NAMES.items())


def normalize_language(language: str) -> str:
    """Return a supported language code, defaulting safely to English."""
    return language if language in LANGUAGE_NAMES else "en"


def language_option(language: str) -> str:
    code = normalize_language(language)
    return f"{LANGUAGE_NAMES[code]} ({code})"


def language_from_option(value: str) -> str:
    for code in SUPPORTED_LANGUAGES:
        if value == language_option(code):
            return code
    return normalize_language(value)


# Frequently used operator controls are translated for every supported locale.
# The main i18n table supplies English for specialist strings that do not yet
# have a locale override, so adding a language can never expose raw key names.
CORE_KEYS = (
    "app.subtitle",
    "menu.file", "menu.view", "menu.help", "menu.settings", "menu.exit",
    "competition.boys", "competition.girls",
    "button.freeze", "button.live", "button.previous_frame", "button.next_frame",
    "button.valid", "button.foul", "button.review", "button.not_decided",
    "competition.current", "competition.previous", "competition.next",
    "attempts.title", "board.title",
    "status.not_decided", "status.valid", "status.foul", "status.review",
    "settings.title", "settings.cancel", "settings.apply",
    "overlay.waiting_video", "overlay.no_video",
    "timeline.title", "timeline.waiting", "common.open",
    "license.activate", "license.cancel",
)


def _core(*values: str) -> dict[str, str]:
    if len(values) != len(CORE_KEYS):
        raise ValueError(f"Expected {len(CORE_KEYS)} core translations, got {len(values)}")
    return dict(zip(CORE_KEYS, values, strict=True))


TRANSLATION_OVERRIDES: dict[str, dict[str, str]] = {
    "sk": _core(
        "STANOVISKO KONTROLY PREŠĽAPOV", "Súbor", "Zobrazenie", "Pomocník", "Nastavenia…", "Ukončiť",
        "Chlapci", "Dievčatá", "Zmraziť", "Naživo", "◀ Snímka", "Snímka ▶",
        "PLATNÝ", "PREŠĽAP", "KONTROLA", "NEROZHODNUTÉ", "AKTUÁLNY PRETEKÁR", "Predchádzajúci", "Ďalší",
        "ZÁZNAMY", "SÚŤAŽNÁ TABUĽA", "Nerozhodnuté", "Platný", "Prešľap", "Kontrola",
        "Nastavenia Long Jump Replay", "Zrušiť", "Použiť", "Čaká sa na video…", "Žiadne video",
        "ČASOVÁ OS", "Čaká sa na video", "Otvoriť", "Aktivovať", "Ukončiť",
    ),
    "pl": _core(
        "STANOWISKO KONTROLI SPALONYCH", "Plik", "Widok", "Pomoc", "Ustawienia…", "Zakończ",
        "Chłopcy", "Dziewczęta", "Zatrzymaj", "Na żywo", "◀ Klatka", "Klatka ▶",
        "WAŻNY", "SPALONY", "DO WERYFIKACJI", "NIEROZSTRZYGNIĘTY", "AKTUALNY ZAWODNIK", "Poprzedni", "Następny",
        "NAGRANIA", "TABLICA ZAWODÓW", "Nierozstrzygnięty", "Ważny", "Spalony", "Do weryfikacji",
        "Ustawienia Long Jump Replay", "Anuluj", "Zastosuj", "Oczekiwanie na obraz…", "Brak obrazu",
        "OŚ CZASU", "Oczekiwanie na obraz", "Otwórz", "Aktywuj", "Zakończ",
    ),
    "hu": _core(
        "BELÉPÉS-ELLENŐRZŐ ÁLLOMÁS", "Fájl", "Nézet", "Súgó", "Beállítások…", "Kilépés",
        "Fiúk", "Lányok", "Kimerevítés", "Élő", "◀ Képkocka", "Képkocka ▶",
        "ÉRVÉNYES", "BELÉPÉS", "FELÜLVIZSGÁLAT", "NINCS DÖNTÉS", "AKTUÁLIS VERSENYZŐ", "Előző", "Következő",
        "FELVÉTELEK", "VERSENYTÁBLA", "Nincs döntés", "Érvényes", "Belépés", "Felülvizsgálat",
        "Long Jump Replay beállítások", "Mégse", "Alkalmaz", "Várakozás a videóra…", "Nincs videó",
        "IDŐVONAL", "Várakozás a videóra", "Megnyitás", "Aktiválás", "Kilépés",
    ),
    "de": _core(
        "STATION ZUR ÜBERTRITTSKONTROLLE", "Datei", "Ansicht", "Hilfe", "Einstellungen…", "Beenden",
        "Jungen", "Mädchen", "Einfrieren", "Live", "◀ Bild", "Bild ▶",
        "GÜLTIG", "ÜBERTRITT", "PRÜFEN", "NICHT ENTSCHIEDEN", "AKTUELLER ATHLET", "Zurück", "Weiter",
        "AUFNAHMEN", "WETTKAMPFTAFEL", "Nicht entschieden", "Gültig", "Übertritt", "Prüfen",
        "Long Jump Replay-Einstellungen", "Abbrechen", "Anwenden", "Warten auf Video…", "Kein Video",
        "ZEITLEISTE", "Warten auf Video", "Öffnen", "Aktivieren", "Beenden",
    ),
    "zh": _core(
        "起跳犯规复核站", "文件", "视图", "帮助", "设置…", "退出", "男子", "女子", "定格", "实时",
        "◀ 上一帧", "下一帧 ▶", "有效", "犯规", "复核", "未判定", "当前运动员", "上一个", "下一个",
        "录像", "比赛面板", "未判定", "有效", "犯规", "复核", "Long Jump Replay 设置", "取消", "应用",
        "正在等待视频…", "无视频", "时间轴", "正在等待视频", "打开", "激活", "退出",
    ),
    "hi": _core(
        "फाउल समीक्षा स्टेशन", "फ़ाइल", "दृश्य", "सहायता", "सेटिंग्स…", "बाहर निकलें", "बालक", "बालिका",
        "फ़्रीज़", "लाइव", "◀ फ़्रेम", "फ़्रेम ▶", "मान्य", "फाउल", "समीक्षा", "निर्णय नहीं",
        "वर्तमान खिलाड़ी", "पिछला", "अगला", "रिकॉर्डिंग", "प्रतियोगिता बोर्ड", "निर्णय नहीं", "मान्य", "फाउल",
        "समीक्षा", "Long Jump Replay सेटिंग्स", "रद्द करें", "लागू करें", "वीडियो की प्रतीक्षा…", "कोई वीडियो नहीं",
        "समयरेखा", "वीडियो की प्रतीक्षा", "खोलें", "सक्रिय करें", "बाहर निकलें",
    ),
    "es": _core(
        "ESTACIÓN DE REVISIÓN DE NULOS", "Archivo", "Ver", "Ayuda", "Configuración…", "Salir",
        "Chicos", "Chicas", "Congelar", "En vivo", "◀ Fotograma", "Fotograma ▶", "VÁLIDO", "NULO", "REVISAR",
        "SIN DECIDIR", "ATLETA ACTUAL", "Anterior", "Siguiente", "GRABACIONES", "TABLERO DE COMPETICIÓN",
        "Sin decidir", "Válido", "Nulo", "Revisar", "Configuración de Long Jump Replay", "Cancelar", "Aplicar",
        "Esperando vídeo…", "Sin vídeo", "LÍNEA DE TIEMPO", "Esperando vídeo", "Abrir", "Activar", "Salir",
    ),
    "fr": _core(
        "POSTE DE CONTRÔLE DES MORDUS", "Fichier", "Affichage", "Aide", "Paramètres…", "Quitter",
        "Garçons", "Filles", "Figer", "Direct", "◀ Image", "Image ▶", "VALIDE", "MORDU", "VÉRIFIER",
        "NON DÉCIDÉ", "ATHLÈTE ACTUEL", "Précédent", "Suivant", "ENREGISTREMENTS", "TABLEAU DE COMPÉTITION",
        "Non décidé", "Valide", "Mordu", "Vérifier", "Paramètres Long Jump Replay", "Annuler", "Appliquer",
        "En attente de la vidéo…", "Aucune vidéo", "CHRONOLOGIE", "En attente de la vidéo", "Ouvrir", "Activer", "Quitter",
    ),
    "ar": _core(
        "محطة مراجعة الأخطاء", "ملف", "عرض", "مساعدة", "الإعدادات…", "خروج", "بنون", "بنات", "تجميد", "مباشر",
        "◀ إطار", "إطار ▶", "صحيح", "خطأ", "مراجعة", "غير محسوم", "اللاعب الحالي", "السابق", "التالي",
        "التسجيلات", "لوحة المسابقة", "غير محسوم", "صحيح", "خطأ", "مراجعة", "إعدادات Long Jump Replay",
        "إلغاء", "تطبيق", "بانتظار الفيديو…", "لا يوجد فيديو", "الخط الزمني", "بانتظار الفيديو", "فتح", "تفعيل", "خروج",
    ),
    "bn": _core(
        "ফাউল পর্যালোচনা স্টেশন", "ফাইল", "দেখুন", "সহায়তা", "সেটিংস…", "প্রস্থান", "বালক", "বালিকা",
        "স্থির করুন", "লাইভ", "◀ ফ্রেম", "ফ্রেম ▶", "বৈধ", "ফাউল", "পর্যালোচনা", "সিদ্ধান্ত হয়নি",
        "বর্তমান অ্যাথলিট", "আগের", "পরের", "রেকর্ডিং", "প্রতিযোগিতা বোর্ড", "সিদ্ধান্ত হয়নি", "বৈধ", "ফাউল",
        "পর্যালোচনা", "Long Jump Replay সেটিংস", "বাতিল", "প্রয়োগ", "ভিডিওর অপেক্ষায়…", "ভিডিও নেই",
        "টাইমলাইন", "ভিডিওর অপেক্ষায়", "খুলুন", "সক্রিয় করুন", "প্রস্থান",
    ),
    "pt": _core(
        "ESTAÇÃO DE REVISÃO DE FALTAS", "Ficheiro", "Ver", "Ajuda", "Definições…", "Sair", "Rapazes", "Raparigas",
        "Congelar", "Ao vivo", "◀ Fotograma", "Fotograma ▶", "VÁLIDO", "FALTA", "REVER", "NÃO DECIDIDO",
        "ATLETA ATUAL", "Anterior", "Seguinte", "GRAVAÇÕES", "QUADRO DA COMPETIÇÃO", "Não decidido", "Válido", "Falta",
        "Rever", "Definições do Long Jump Replay", "Cancelar", "Aplicar", "A aguardar vídeo…", "Sem vídeo",
        "LINHA TEMPORAL", "A aguardar vídeo", "Abrir", "Ativar", "Sair",
    ),
    "ru": _core(
        "СТАНЦИЯ ПРОВЕРКИ ЗАСТУПОВ", "Файл", "Вид", "Справка", "Настройки…", "Выход", "Юноши", "Девушки",
        "Стоп-кадр", "Прямой эфир", "◀ Кадр", "Кадр ▶", "ЗАЧЁТ", "ЗАСТУП", "ПРОВЕРКА", "НЕ РЕШЕНО",
        "ТЕКУЩИЙ СПОРТСМЕН", "Предыдущий", "Следующий", "ЗАПИСИ", "ТАБЛО СОРЕВНОВАНИЙ", "Не решено", "Зачёт",
        "Заступ", "Проверка", "Настройки Long Jump Replay", "Отмена", "Применить", "Ожидание видео…", "Нет видео",
        "ШКАЛА ВРЕМЕНИ", "Ожидание видео", "Открыть", "Активировать", "Выход",
    ),
    "id": _core(
        "STASIUN TINJAUAN PELANGGARAN", "Berkas", "Tampilan", "Bantuan", "Pengaturan…", "Keluar", "Putra", "Putri",
        "Bekukan", "Langsung", "◀ Bingkai", "Bingkai ▶", "SAH", "PELANGGARAN", "TINJAU", "BELUM DIPUTUSKAN",
        "ATLET SAAT INI", "Sebelumnya", "Berikutnya", "REKAMAN", "PAPAN KOMPETISI", "Belum diputuskan", "Sah",
        "Pelanggaran", "Tinjau", "Pengaturan Long Jump Replay", "Batal", "Terapkan", "Menunggu video…", "Tidak ada video",
        "LINIMASA", "Menunggu video", "Buka", "Aktifkan", "Keluar",
    ),
    "ur": _core(
        "فاؤل جائزہ اسٹیشن", "فائل", "منظر", "مدد", "ترتیبات…", "باہر نکلیں", "لڑکے", "لڑکیاں", "منجمد کریں", "براہ راست",
        "◀ فریم", "فریم ▶", "درست", "فاؤل", "جائزہ", "فیصلہ نہیں ہوا", "موجودہ کھلاڑی", "پچھلا", "اگلا",
        "ریکارڈنگز", "مقابلے کا بورڈ", "فیصلہ نہیں ہوا", "درست", "فاؤل", "جائزہ", "Long Jump Replay ترتیبات",
        "منسوخ", "لاگو کریں", "ویڈیو کا انتظار…", "ویڈیو نہیں", "ٹائم لائن", "ویڈیو کا انتظار", "کھولیں", "فعال کریں", "باہر نکلیں",
    ),
}
