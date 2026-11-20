"""Report strings in Turkmen, Russian and English."""

from __future__ import annotations

LANGUAGES = ("tk", "ru", "en")
DEFAULT_LANGUAGE = "tk"

TEXTS: dict[str, dict[str, str]] = {
    "title": {
        "tk": "Deepfake barlagynyň hasabaty",
        "ru": "Отчёт о проверке на дипфейк",
        "en": "Deepfake analysis report",
    },
    "subtitle": {
        "tk": "Dipfeýkleri kesgitleýän ulgam",
        "ru": "Система обнаружения дипфейков",
        "en": "Deepfake Detection System",
    },
    "file": {"tk": "Faýl", "ru": "Файл", "en": "File"},
    "name": {"tk": "Ady", "ru": "Имя", "en": "Name"},
    "type": {"tk": "Görnüşi", "ru": "Тип", "en": "Type"},
    "size": {"tk": "Ölçegi", "ru": "Размер", "en": "Size"},
    "duration": {"tk": "Dowamlylygy", "ru": "Длительность", "en": "Duration"},
    "resolution": {"tk": "Ölçegleri", "ru": "Разрешение", "en": "Resolution"},
    "uploaded": {"tk": "Ýüklenen wagty", "ru": "Загружен", "en": "Uploaded"},
    "user": {"tk": "Ulanyjy", "ru": "Пользователь", "en": "User"},
    "scan_id": {"tk": "Barlag belgisi", "ru": "ID проверки", "en": "Scan ID"},
    "image": {"tk": "Surat", "ru": "Изображение", "en": "Image"},
    "video": {"tk": "Wideo", "ru": "Видео", "en": "Video"},
    "audio": {"tk": "Ses", "ru": "Аудио", "en": "Audio"},
    "result": {"tk": "Netije", "ru": "Результат", "en": "Result"},
    "verdict": {"tk": "Höküm", "ru": "Вердикт", "en": "Verdict"},
    "probability": {
        "tk": "Galp bolmak ähtimallygy",
        "ru": "Вероятность подделки",
        "en": "Probability of forgery",
    },
    "real": {"tk": "HAKYKY", "ru": "ПОДЛИННЫЙ", "en": "REAL"},
    "suspicious": {"tk": "ŞÜBHELI", "ru": "ПОДОЗРИТЕЛЬНЫЙ", "en": "SUSPICIOUS"},
    "fake": {"tk": "GALP", "ru": "ПОДДЕЛКА", "en": "FAKE"},
    "inconclusive": {"tk": "KESGITLÄP BOLMADY", "ru": "НЕ ОПРЕДЕЛЕНО", "en": "INCONCLUSIVE"},
    "modalities": {
        "tk": "Seljermäniň jikme-jigi",
        "ru": "Детали анализа",
        "en": "Analysis details",
    },
    "modality": {"tk": "Ugur", "ru": "Модальность", "en": "Modality"},
    "visual": {"tk": "Şekil (ýüz)", "ru": "Изображение (лицо)", "en": "Picture (face)"},
    "sound": {"tk": "Ses", "ru": "Звук", "en": "Sound"},
    "band": {"tk": "Şübheli aralygy", "ru": "Зона сомнения", "en": "Suspicious band"},
    "model": {"tk": "Model", "ru": "Модель", "en": "Model"},
    "timeline_frames": {
        "tk": "Kadrlar boýunça ähtimallyk",
        "ru": "Вероятность по кадрам",
        "en": "Probability per frame",
    },
    "timeline_audio": {
        "tk": "Ses bölekleri boýunça ähtimallyk",
        "ru": "Вероятность по фрагментам звука",
        "en": "Probability per audio segment",
    },
    "regions": {
        "tk": "Bellenen ýerler (Grad-CAM)",
        "ru": "Отмеченные области (Grad-CAM)",
        "en": "Highlighted regions (Grad-CAM)",
    },
    "regions_hint": {
        "tk": "Gyzyl reňk modeliň galp diýen netijesine iň köp täsir eden ýerleri görkezýär.",
        "ru": "Красным отмечены области, сильнее всего повлиявшие на оценку «подделка».",
        "en": "Red marks the regions that pushed the model most towards “fake”.",
    },
    "frame": {"tk": "Kadr", "ru": "Кадр", "en": "Frame"},
    "face": {"tk": "Ýüz", "ru": "Лицо", "en": "Face"},
    "notes": {"tk": "Bellikler", "ru": "Примечания", "en": "Notes"},
    "note_no_face_found": {
        "tk": "Faýlda ýüz tapylmady, şonuň üçin şekil boýunça baha berilmedi.",
        "ru": "Лицо не найдено, поэтому оценка по изображению не выполнялась.",
        "en": "No face was found, so the picture could not be assessed.",
    },
    "note_faces_truncated": {
        "tk": "Suratda ýüz köp; diňe iň ulylary barlandy.",
        "ru": "На изображении много лиц; проверены только самые крупные.",
        "en": "The image has many faces; only the largest were analysed.",
    },
    "note_audio_silent": {
        "tk": "Ses ýoly sessiz, barlanmady.",
        "ru": "Звуковая дорожка беззвучна и не проверялась.",
        "en": "The sound track is silent and was not analysed.",
    },
    "note_audio_model_unavailable": {
        "tk": "Ses modeli gurnalmadyk, ses ýoly barlanmady.",
        "ru": "Аудиомодель не установлена, звук не проверялся.",
        "en": "The audio model is not installed; the sound track was not analysed.",
    },
    "note_audio_unreadable": {
        "tk": "Ses ýoluny okap bolmady.",
        "ru": "Звуковую дорожку не удалось прочитать.",
        "en": "The sound track could not be decoded.",
    },
    "note_provisional": {
        "tk": "Model synag görnüşinde: bosagalar entek doly barlanmadyk.",
        "ru": "Модель в пробном режиме: пороги ещё не откалиброваны полностью.",
        "en": "The model is provisional: its thresholds are not fully calibrated yet.",
    },
    "note_video_audio": {
        "tk": "Wideonyň sesi diňe goşmaça maglumat: ol hökümi «Şübheli» derejesine çenli "
        "ýokarlandyryp bilýär.",
        "ru": "Звук видео учитывается как дополнительный признак: он может повысить вердикт "
        "только до «Подозрительный».",
        "en": "A video's sound track is supporting evidence only: it can raise the verdict "
        "to “Suspicious” at most.",
    },
    "disclaimer_title": {"tk": "Çäklendirmeler", "ru": "Ограничения", "en": "Limitations"},
    "disclaimer": {
        "tk": "Bu netije awtomatiki modeliň bahasydyr we kepillik däldir. Model okadylan "
        "maglumatlaryna meňzemeýän täze usullar bilen döredilen galp materiallary "
        "tanamazlygy mümkin, şeýle hem güýçli gysylan ýa-da pes hilli hakyky faýllary "
        "şübheli diýip bilmegi mümkin. Möhüm karar üçin hünärmeniň barlagy zerur.",
        "ru": "Результат является оценкой автоматической модели и не служит гарантией. "
        "Модель может не распознать подделки, созданные новыми методами, непохожими на "
        "обучающие данные, а сильно сжатые или некачественные подлинные файлы может "
        "счесть подозрительными. Для важных решений необходима экспертная проверка.",
        "en": "This result is an automated model's estimate, not a guarantee. The model may "
        "miss forgeries made with new methods unlike its training data, and may flag "
        "heavily compressed or low-quality genuine files as suspicious. Important "
        "decisions require review by an expert.",
    },
    "generated": {"tk": "Döredilen wagty", "ru": "Сформирован", "en": "Generated"},
    "page": {"tk": "Sahypa", "ru": "Страница", "en": "Page"},
    "seconds": {"tk": "s", "ru": "с", "en": "s"},
}


def text(key: str, lang: str) -> str:
    entry = TEXTS.get(key)
    if entry is None:
        return key
    return entry.get(lang) or entry[DEFAULT_LANGUAGE]
