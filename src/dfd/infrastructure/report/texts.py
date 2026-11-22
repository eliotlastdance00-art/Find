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
    "visual": {
        "tk": "Ýüz çalşygy",
        "ru": "Подмена лица",
        "en": "Face swap",
    },
    "sound": {"tk": "Ses", "ru": "Звук", "en": "Sound"},
    "band": {
        "tk": "Bosaga / aralyk",
        "ru": "Порог / диапазон",
        "en": "Threshold / band",
    },
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
        "tk": "Ýüz tapylmady; ýüz çalşygy barlanmady. AI-suratyň barlagy ýüz talap etmeýär.",
        "ru": (
            "Лицо не найдено; подмена лица не проверялась. Для проверки ИИ-генерации лицо "
            "не требуется."
        ),
        "en": (
            "No face was found; face swaps were not assessed. AI-image detection does not "
            "require a face."
        ),
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
    "note_audio_capped": {
        "tk": (
            "Ses modeli türkmen sesi bilen goşmaça okadyldy, ýöne ýalňyş duýduryş entek "
            "ýokary. Şonuň üçin ses hökümi iň köp «Şübheli» bolýar; «Hakyky» netijesi hem "
            "kepillik däl."
        ),
        "ru": (
            "Аудиомодель дообучена на туркменской речи, но ложных тревог ещё слишком много. "
            "Поэтому вердикт по звуку не выше «Подозрительный»; «Подлинный» тоже не "
            "гарантия."
        ),
        "en": (
            "The audio model was fine-tuned on Turkmen speech, but false alarms remain too "
            "frequent. Audio verdicts are capped at “Suspicious”; “Real” is not a guarantee "
            "either."
        ),
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
    "note_provenance_unverified": {
        "tk": (
            "Metadata goly barlanmadyk; ony üýtgedip ýa-da pozup bolýar. Bu bellikler "
            "hökümi özbaşdak üýtgetmeýär; C2PA golunyň barlagy ýerine ýetirilmedi."
        ),
        "ru": (
            "Подписи метаданных не проверены; метки можно изменить или удалить. Они сами по "
            "себе не меняют вердикт. Проверка подписи C2PA не выполнялась."
        ),
        "en": (
            "Metadata is unverified and can be edited or stripped. These hints do not "
            "change the verdict on their own. C2PA signatures were not verified."
        ),
    },
    "note_synthetic_model_unavailable": {
        "tk": (
            "Smaug gurnalmadyk ýa-da ýükläp bolmady: AI-suratyň barlagy geçirilmedi. "
            "Gurnamak/barlamak: dfd models --download, soň serweri täzeden işlediň."
        ),
        "ru": (
            "Smaug не установлен или не загрузился: проверка ИИ-генерации не выполнена. "
            "Выполните dfd models --download и перезапустите сервер."
        ),
        "en": (
            "Smaug is missing or could not load: AI-generation detection was not performed. "
            "Run dfd models --download, then restart the server."
        ),
    },
    "note_synthetic_failed": {
        "tk": (
            "Smaug barlagy şowsuz boldy. Netije diňe galan barlaglara esaslanýar; "
            "AI-suratyň barlagy doly däl."
        ),
        "ru": (
            "Проверка Smaug завершилась ошибкой. Результат основан только на остальных "
            "проверках; ИИ-генерация не оценена."
        ),
        "en": (
            "Smaug inference failed. The result uses only the remaining checks; "
            "AI-generation detection is incomplete."
        ),
    },
    "note_visual_model_unavailable": {
        "tk": "Ýüz çalşygyny barlaýan model ýok; bu ugur barlanmady.",
        "ru": "Модель подмены лица недоступна; эта проверка не выполнена.",
        "en": "The face-swap model is unavailable; that check was not performed.",
    },
    "note_synthetic_score": {
        "tk": (
            "Esasy göterim şekil modelleriniň iň uly bahasydyr, birleşdirilip kalibrlenen "
            "ähtimallyk däl. Höküm her modeliň öz bosagasyna görä çykarylýar. Smaug-yň 50% "
            "bosagasy wagtlaýyn; ýalňyş duýduryş derejesi entek ölçenmedi."
        ),
        "ru": (
            "Главный процент — максимальная оценка моделей изображения, а не калиброванная "
            "общая вероятность. Вердикт учитывает собственный порог каждой модели. Порог "
            "Smaug 50% предварительный; частота ложных тревог ещё не измерена."
        ),
        "en": (
            "The headline percentage is the highest image-model score, not a calibrated "
            "joint probability. Verdicts use each model’s own threshold. Smaug’s 50% "
            "threshold is provisional; the false-alarm rate has not been measured locally."
        ),
    },
    "note_synthetic_heatmap": {
        "tk": (
            "Ýylylyk kartalary diňe EfficientNet-iň ýüz çalşygy bahasyny düşündirýär. Olar "
            "Smaug-yň AI-suratyň bahasyny düşündirmeýär; Smaug üçin heatmap döredilmeýär."
        ),
        "ru": (
            "Тепловые карты объясняют только оценку подмены лица EfficientNet, а не оценку "
            "ИИ-генерации Smaug. Для Smaug тепловая карта не строится."
        ),
        "en": (
            "Heatmaps explain only EfficientNet’s face-swap score, not Smaug’s "
            "AI-generation score. No heatmap is produced for Smaug."
        ),
    },
    "score": {
        "tk": "Galplyk bahasy",
        "ru": "Оценка подделки",
        "en": "Forgery score",
    },
    "synthetic": {
        "tk": "AI surat",
        "ru": "ИИ-изображение",
        "en": "AI-generated image",
    },
    "provenance": {
        "tk": "Faýlyň gelip çykyş belgileri",
        "ru": "Метки происхождения файла",
        "en": "File provenance hints",
    },
    "provenance_ai_declared": {
        "tk": "XMP/IPTC-de AI bilen döredilendigi barada bellik bar.",
        "ru": "В XMP/IPTC есть декларация об ИИ-генерации.",
        "en": "XMP/IPTC contains an AI-generation declaration.",
    },
    "provenance_ai_workflow": {
        "tk": "PNG metadatasynda generasiýa sazlamalary bar.",
        "ru": "В метаданных PNG есть параметры генерации.",
        "en": "PNG metadata contains structured generation settings.",
    },
    "provenance_ai_software": {
        "tk": "Software belliginde AI generatory görkezilen.",
        "ru": "В теге Software указан ИИ-генератор.",
        "en": "The Software tag names an AI-generation tool.",
    },
    "provenance_none": {
        "tk": "Goldanýan AI belgisi tapylmady. Bu suratyň hakykydygyny subut etmeýär.",
        "ru": "Поддерживаемых меток ИИ не найдено. Это не доказывает подлинность изображения.",
        "en": "No supported AI metadata marker was found. This does not prove authenticity.",
    },
}


def text(key: str, lang: str) -> str:
    entry = TEXTS.get(key)
    if entry is None:
        return key
    return entry.get(lang) or entry[DEFAULT_LANGUAGE]
