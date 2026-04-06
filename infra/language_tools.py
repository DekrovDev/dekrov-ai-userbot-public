from __future__ import annotations

import re


SUPPORTED_LANGUAGES = ("ru", "uk", "en", "it", "es", "fr", "de")
DEFAULT_FALLBACK_LANGUAGE = "ru"

CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")
LATIN_WORD_RE = re.compile(r"[A-Za-zÃ€-Ã¿']+")

LANGUAGE_NAMES = {
    "ru": "Russian",
    "uk": "Ukrainian",
    "en": "English",
    "it": "Italian",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
}

LANGUAGE_HINT_WORDS: dict[str, set[str]] = {
    "uk": {
        "Ð¿Ñ€Ð¸Ð²Ñ–Ñ‚",
        "Ð±ÑƒÐ´ÑŒ",
        "Ð»Ð°ÑÐºÐ°",
        "Ð´ÑÐºÑƒÑŽ",
        "Ñ…Ñ‚Ð¾",
        "Ñ‰Ð¾",
        "Ñ‡Ð¾Ð¼Ñƒ",
        "ÑÐº",
        "Ñ‚ÐµÐ±Ðµ",
        "Ð¼ÐµÐ½Ðµ",
        "ÑÐ¿Ñ€Ð°Ð²Ð¸",
        "ÑÑ‚Ð²Ð¾Ñ€Ð¸Ð²",
        "ÑÑ‚Ð²Ð¾Ñ€ÐµÐ½Ð¸Ð¹",
        "Ð¿Ð¾ÑÐ¸Ð»Ð°Ð½Ð½Ñ",
        "Ñ†ÐµÐ¹",
        "Ð·Ñ€Ð¾Ð·ÑƒÐ¼Ñ–Ð²",
    },
    "en": {
        "the",
        "and",
        "are",
        "can",
        "creator",
        "created",
        "do",
        "does",
        "how",
        "what",
        "who",
        "why",
        "you",
        "your",
    },
    "it": {
        "chi",
        "come",
        "creato",
        "creatore",
        "del",
        "della",
        "domani",
        "oggi",
        "per",
        "puoi",
        "sei",
        "sono",
        "una",
        "un",
    },
    "es": {
        "como",
        "creador",
        "creado",
        "eres",
        "hoy",
        "maÃ±ana",
        "para",
        "puedes",
        "que",
        "quien",
        "soy",
        "una",
        "uno",
    },
    "fr": {
        "bonjour",
        "comment",
        "crÃ©ateur",
        "crÃ©Ã©",
        "demain",
        "est",
        "pour",
        "qui",
        "quoi",
        "suis",
        "tu",
        "une",
        "un",
        "vous",
    },
    "de": {
        "bist",
        "dich",
        "du",
        "ein",
        "eine",
        "erstellt",
        "heute",
        "ich",
        "kann",
        "morgen",
        "wer",
        "was",
        "wie",
    },
}

LANGUAGE_CHAR_HINTS = {
    "uk": "Ñ–Ñ—Ñ”Ò‘",
    "it": "Ã Ã¨Ã©Ã¬Ã­Ã®Ã²Ã³Ã¹",
    "es": "Ã¡Ã©Ã­Ã³ÃºÃ±Â¿Â¡",
    "fr": "Ã Ã¢Ã¦Ã§Ã©Ã¨ÃªÃ«Ã®Ã¯Ã´Å“Ã¹Ã»Ã¼Ã¿",
    "de": "Ã¤Ã¶Ã¼ÃŸ",
}

TRANSLATIONS: dict[str, dict[str, str]] = {
    "question_reference_default": {
        "ru": "ÐŸÐ¾ ÑÑ‚Ð¾Ð¼Ñƒ Ð²Ð¾Ð¿Ñ€Ð¾ÑÑƒ",
        "en": "On that question",
        "it": "Su questa richiesta",
        "es": "Sobre esa pregunta",
        "fr": "Sur cette question",
        "de": "Zu dieser Frage",
    },
    "question_reference_topic": {
        "ru": "ÐÐ° Ð²Ð¾Ð¿Ñ€Ð¾Ñ {topic}",
        "en": "On the question of {topic}",
        "it": "Sulla richiesta di {topic}",
        "es": "Sobre la pregunta de {topic}",
        "fr": "Sur la question de {topic}",
        "de": "Zur Frage nach {topic}",
    },
    "failure_generic": {
        "ru": "ÐŸÐ¾ÐºÐ° Ð½Ðµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ ÐºÐ¾Ñ€Ñ€ÐµÐºÑ‚Ð½Ð¾ Ð¾Ñ‚Ð²ÐµÑ‚Ð¸Ñ‚ÑŒ Ð½Ð° ÑÑ‚Ð¾Ñ‚ Ð·Ð°Ð¿Ñ€Ð¾Ñ.",
        "en": "I couldn't answer that request correctly yet.",
        "it": "Per ora non sono riuscito a rispondere correttamente a questa richiesta.",
        "es": "TodavÃ­a no pude responder correctamente a esa solicitud.",
        "fr": "Je n'ai pas encore rÃ©ussi Ã  rÃ©pondre correctement Ã  cette demande.",
        "de": "Ich konnte auf diese Anfrage noch nicht korrekt antworten.",
    },
    "failure_with_reference": {
        "ru": "{reference} â€” Ð¿Ð¾ÐºÐ° Ð½Ðµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ ÐºÐ¾Ñ€Ñ€ÐµÐºÑ‚Ð½Ð¾ Ð¾Ñ‚Ð²ÐµÑ‚Ð¸Ñ‚ÑŒ.",
        "en": "{reference} â€” I couldn't answer it correctly yet.",
        "it": "{reference} â€” per ora non sono riuscito a rispondere correttamente.",
        "es": "{reference} â€” todavÃ­a no pude responder correctamente.",
        "fr": "{reference} â€” je n'ai pas encore rÃ©ussi Ã  rÃ©pondre correctement.",
        "de": "{reference} â€” ich konnte darauf noch nicht korrekt antworten.",
    },
    "unclear_question": {
        "ru": "Ð¯ Ð½Ðµ Ð¿Ð¾Ð½ÑÐ», Ñ‡Ñ‚Ð¾ Ð¸Ð¼ÐµÐ½Ð½Ð¾ Ð²Ñ‹ Ð¸Ð¼ÐµÐµÑ‚Ðµ Ð² Ð²Ð¸Ð´Ñƒ Ð² ÑÑ‚Ð¾Ð¼ Ð²Ð¾Ð¿Ñ€Ð¾ÑÐµ.",
        "en": "I didn't understand what exactly you mean in that question.",
        "it": "Non ho capito cosa intendi esattamente in questa domanda.",
        "es": "No entendÃ­ quÃ© quieres decir exactamente en esa pregunta.",
        "fr": "Je n'ai pas compris ce que vous voulez dire exactement dans cette question.",
        "de": "Ich habe nicht verstanden, was du mit dieser Frage genau meinst.",
    },
    "topic_generic": {
        "ru": "Ð¾Ð± ÑÑ‚Ð¾Ð¼ Ð²Ð¾Ð¿Ñ€Ð¾ÑÐµ",
        "en": "that question",
        "it": "questa richiesta",
        "es": "esa pregunta",
        "fr": "cette question",
        "de": "diese Frage",
    },
    "topic_about_words": {
        "ru": "Ð¾ {words}",
        "en": "about {words}",
        "it": "su {words}",
        "es": "sobre {words}",
        "fr": "Ã  propos de {words}",
        "de": "zu {words}",
    },
    "topic_favorites_send": {
        "ru": "Ð¾Ð± Ð¾Ñ‚Ð¿Ñ€Ð°Ð²ÐºÐµ Ð² Ð¸Ð·Ð±Ñ€Ð°Ð½Ð½Ð¾Ðµ",
        "en": "sending something to Saved Messages",
        "it": "l'invio nei messaggi salvati",
        "es": "enviar algo a los mensajes guardados",
        "fr": "l'envoi dans les messages enregistrÃ©s",
        "de": "das Senden in die gespeicherten Nachrichten",
    },
    "topic_favorites": {
        "ru": "Ð¾Ð± Ð¸Ð·Ð±Ñ€Ð°Ð½Ð½Ð¾Ð¼",
        "en": "Saved Messages",
        "it": "i messaggi salvati",
        "es": "los mensajes guardados",
        "fr": "les messages enregistrÃ©s",
        "de": "die gespeicherten Nachrichten",
    },
    "topic_view_chats": {
        "ru": "Ð¾ Ð¿Ñ€Ð¾ÑÐ¼Ð¾Ñ‚Ñ€Ðµ Ñ‡Ð°Ñ‚Ð¾Ð²",
        "en": "viewing chats",
        "it": "la visualizzazione delle chat",
        "es": "ver chats",
        "fr": "la consultation des chats",
        "de": "das Anzeigen von Chats",
    },
    "topic_search_chats": {
        "ru": "Ð¾ Ð¿Ð¾Ð¸ÑÐºÐµ Ð¿Ð¾ Ñ‡Ð°Ñ‚Ð°Ð¼",
        "en": "searching chats",
        "it": "la ricerca nelle chat",
        "es": "buscar en chats",
        "fr": "la recherche dans les chats",
        "de": "die Suche in Chats",
    },
    "topic_chat_summary": {
        "ru": "Ð¾ ÑÐ²Ð¾Ð´ÐºÐµ Ð¿Ð¾ Ñ‡Ð°Ñ‚Ñƒ",
        "en": "a chat summary",
        "it": "un riepilogo della chat",
        "es": "un resumen del chat",
        "fr": "un rÃ©sumÃ© du chat",
        "de": "eine Chat-Zusammenfassung",
    },
    "topic_chats": {
        "ru": "Ð¾ Ñ‡Ð°Ñ‚Ð°Ñ…",
        "en": "chats",
        "it": "le chat",
        "es": "los chats",
        "fr": "les chats",
        "de": "Chats",
    },
    "topic_weather": {
        "ru": "Ð¾ Ð¿Ð¾Ð³Ð¾Ð´Ðµ",
        "en": "the weather",
        "it": "il meteo",
        "es": "el clima",
        "fr": "la mÃ©tÃ©o",
        "de": "das Wetter",
    },
    "topic_weather_in": {
        "ru": "Ð¾ Ð¿Ð¾Ð³Ð¾Ð´Ðµ Ð² {location}",
        "en": "the weather in {location}",
        "it": "il meteo a {location}",
        "es": "el clima en {location}",
        "fr": "la mÃ©tÃ©o Ã  {location}",
        "de": "das Wetter in {location}",
    },
    "topic_news": {
        "ru": "Ð¾ Ð½Ð¾Ð²Ð¾ÑÑ‚ÑÑ…",
        "en": "the news",
        "it": "le notizie",
        "es": "las noticias",
        "fr": "les actualitÃ©s",
        "de": "die Nachrichten",
    },
    "topic_exchange_rate": {
        "ru": "Ð¾ ÐºÑƒÑ€ÑÐµ Ð²Ð°Ð»ÑŽÑ‚",
        "en": "exchange rates",
        "it": "il tasso di cambio",
        "es": "el tipo de cambio",
        "fr": "le taux de change",
        "de": "den Wechselkurs",
    },
    "topic_price": {
        "ru": "Ð¾ Ñ†ÐµÐ½Ðµ",
        "en": "the price",
        "it": "il prezzo",
        "es": "el precio",
        "fr": "le prix",
        "de": "den Preis",
    },
    "topic_meaning": {
        "ru": "Ð¾ ÑÐ¼Ñ‹ÑÐ»Ðµ ÑÑ‚Ð¾Ð³Ð¾",
        "en": "what that means",
        "it": "il significato di questo",
        "es": "lo que significa eso",
        "fr": "la signification de cela",
        "de": "was das bedeutet",
    },
    "identity_canonical": {
        "ru": "Ð¯ Project Assistant, Ð¼ÐµÐ½Ñ ÑÐ¾Ð·Ð´Ð°Ð» ProjectOwner. Telegram-ÐºÐ°Ð½Ð°Ð» ÑÐ¾Ð·Ð´Ð°Ñ‚ÐµÐ»Ñ: https://t.me/example_channel",
        "en": "I am Project Assistant, created by ProjectOwner. Creator Telegram channel: https://t.me/example_channel",
        "it": "Sono Project Assistant, creato da ProjectOwner. Canale Telegram del creatore: https://t.me/example_channel",
        "es": "Soy Project Assistant, creado por ProjectOwner. Canal de Telegram del creador: https://t.me/example_channel",
        "fr": "Je suis Project Assistant, crÃ©Ã© par ProjectOwner. Canal Telegram du crÃ©ateur : https://t.me/example_channel",
        "de": "Ich bin Project Assistant, erstellt von ProjectOwner. Telegram-Kanal des Erstellers: https://t.me/example_channel",
    },
    "safety_refusal": {
        "ru": "Ð¯ Ð½Ðµ Ð¼Ð¾Ð³Ñƒ Ð¿Ð¾Ð¼Ð¾Ñ‡ÑŒ Ñ Ñ‚Ð°ÐºÐ¸Ð¼ Ð·Ð°Ð¿Ñ€Ð¾ÑÐ¾Ð¼.",
        "en": "I can't help with that request.",
        "it": "Non posso aiutare con questa richiesta.",
        "es": "No puedo ayudar con esa solicitud.",
        "fr": "Je ne peux pas aider avec cette demande.",
        "de": "Ich kann bei dieser Anfrage nicht helfen.",
    },
    "rate_limit_reached": {
        "ru": "Ð›Ð¸Ð¼Ð¸Ñ‚ Ð·Ð°Ð¿Ñ€Ð¾ÑÐ¾Ð² Ð²Ñ€ÐµÐ¼ÐµÐ½Ð½Ð¾ Ð¸ÑÑ‡ÐµÑ€Ð¿Ð°Ð½. ÐŸÐ¾Ð¿Ñ€Ð¾Ð±ÑƒÐ¹ Ñ‡ÑƒÑ‚ÑŒ Ð¿Ð¾Ð·Ð¶Ðµ.",
        "en": "The request limit is temporarily exhausted. Try again a bit later.",
        "it": "Il limite di richieste Ã¨ temporaneamente esaurito. Riprova tra poco.",
        "es": "El lÃ­mite de solicitudes se agotÃ³ temporalmente. IntÃ©ntalo un poco mÃ¡s tarde.",
        "fr": "La limite de requÃªtes est temporairement atteinte. RÃ©essaie un peu plus tard.",
        "de": "Das Anfrage-Limit ist vorÃ¼bergehend erschÃ¶pft. Versuch es etwas spÃ¤ter noch einmal.",
    },
    "ai_unreachable": {
        "ru": "ÐÐµ Ð´Ð¾Ñ‚ÑÐ½ÑƒÐ»ÑÑ Ð´Ð¾ AI-ÑÐµÑ€Ð²Ð¸ÑÐ°. ÐŸÐ¾Ð²Ñ‚Ð¾Ñ€Ð¸ Ñ‡ÑƒÑ‚ÑŒ Ð¿Ð¾Ð·Ð¶Ðµ.",
        "en": "I couldn't reach the AI service. Try again a bit later.",
        "it": "Non sono riuscito a raggiungere il servizio AI. Riprova tra poco.",
        "es": "No pude conectar con el servicio de IA. IntÃ©ntalo un poco mÃ¡s tarde.",
        "fr": "Je n'ai pas pu joindre le service IA. RÃ©essaie un peu plus tard.",
        "de": "Ich konnte den KI-Dienst nicht erreichen. Versuch es etwas spÃ¤ter noch einmal.",
    },
    "model_rejected_request": {
        "ru": "Ð’Ñ‹Ð±Ñ€Ð°Ð½Ð½Ð°Ñ Ð¼Ð¾Ð´ÐµÐ»ÑŒ Ð½Ðµ Ð¿Ñ€Ð¸Ð½ÑÐ»Ð° Ð·Ð°Ð¿Ñ€Ð¾Ñ.",
        "en": "The selected model rejected the request.",
        "it": "Il modello selezionato ha rifiutato la richiesta.",
        "es": "El modelo seleccionado rechazÃ³ la solicitud.",
        "fr": "Le modÃ¨le sÃ©lectionnÃ© a rejetÃ© la demande.",
        "de": "Das ausgewÃ¤hlte Modell hat die Anfrage abgelehnt.",
    },
    "ai_service_error": {
        "ru": "AI-ÑÐµÑ€Ð²Ð¸Ñ Ð²ÐµÑ€Ð½ÑƒÐ» Ð¾ÑˆÐ¸Ð±ÐºÑƒ.",
        "en": "The AI service returned an error.",
        "it": "Il servizio AI ha restituito un errore.",
        "es": "El servicio de IA devolviÃ³ un error.",
        "fr": "Le service IA a renvoyÃ© une erreur.",
        "de": "Der KI-Dienst hat einen Fehler zurÃ¼ckgegeben.",
    },
    "request_processing_error": {
        "ru": "ÐŸÑ€Ð¸ Ð¾Ð±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐµ Ð·Ð°Ð¿Ñ€Ð¾ÑÐ° Ñ‡Ñ‚Ð¾-Ñ‚Ð¾ Ð¿Ð¾ÑˆÐ»Ð¾ Ð½Ðµ Ñ‚Ð°Ðº.",
        "en": "Something went wrong while processing the request.",
        "it": "Qualcosa Ã¨ andato storto durante l'elaborazione della richiesta.",
        "es": "Algo saliÃ³ mal al procesar la solicitud.",
        "fr": "Quelque chose s'est mal passÃ© pendant le traitement de la demande.",
        "de": "Beim Verarbeiten der Anfrage ist etwas schiefgelaufen.",
    },
    "live_data_unavailable": {
        "ru": "Ð¡ÐµÐ¹Ñ‡Ð°Ñ Ñƒ Ð¼ÐµÐ½Ñ Ð½ÐµÑ‚ Ð¿Ð¾Ð´ÐºÐ»ÑŽÑ‡Ñ‘Ð½Ð½Ð¾Ð³Ð¾ live-Ð´Ð¾ÑÑ‚ÑƒÐ¿Ð° Ðº Ð°ÐºÑ‚ÑƒÐ°Ð»ÑŒÐ½Ñ‹Ð¼ Ð´Ð°Ð½Ð½Ñ‹Ð¼, Ð¿Ð¾ÑÑ‚Ð¾Ð¼Ñƒ Ñ Ð½Ðµ Ð¼Ð¾Ð³Ñƒ Ð½Ð°Ð´Ñ‘Ð¶Ð½Ð¾ Ð¾Ñ‚Ð²ÐµÑ‚Ð¸Ñ‚ÑŒ Ð½Ð° Ñ‚Ð°ÐºÐ¾Ð¹ Ð·Ð°Ð¿Ñ€Ð¾Ñ.",
        "en": "I don't have live access to current data right now, so I can't answer that request reliably.",
        "it": "In questo momento non ho accesso live ai dati aggiornati, quindi non posso rispondere in modo affidabile a questa richiesta.",
        "es": "Ahora mismo no tengo acceso en vivo a datos actualizados, asÃ­ que no puedo responder de forma fiable a esa solicitud.",
        "fr": "Je n'ai pas d'accÃ¨s en direct aux donnÃ©es actuelles pour le moment, donc je ne peux pas rÃ©pondre fiablement Ã  cette demande.",
        "de": "Ich habe im Moment keinen Live-Zugriff auf aktuelle Daten, daher kann ich diese Anfrage nicht zuverlÃ¤ssig beantworten.",
    },
    "rates_parse_failed": {
        "ru": "ÐÐµ ÑÐ¼Ð¾Ð³ Ð½Ð¾Ñ€Ð¼Ð°Ð»ÑŒÐ½Ð¾ Ñ€Ð°Ð·Ð¾Ð±Ñ€Ð°Ñ‚ÑŒ, ÐºÐ°ÐºÐ¸Ðµ Ð²Ð°Ð»ÑŽÑ‚Ñ‹ Ð½ÑƒÐ¶Ð½Ñ‹.",
        "en": "I couldn't clearly determine which currencies you need.",
        "it": "Non sono riuscito a capire con chiarezza quali valute ti servono.",
        "es": "No pude determinar con claridad quÃ© monedas necesitas.",
        "fr": "Je n'ai pas rÃ©ussi Ã  dÃ©terminer clairement quelles devises il faut.",
        "de": "Ich konnte nicht klar erkennen, welche WÃ¤hrungen du brauchst.",
    },
    "news_not_found": {
        "ru": "ÐÐµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ Ð½Ð°Ð¹Ñ‚Ð¸ ÑÐ²ÐµÐ¶Ð¸Ðµ Ð¿ÑƒÐ±Ð»Ð¸ÐºÐ°Ñ†Ð¸Ð¸ Ð¿Ð¾ Ð·Ð°Ð¿Ñ€Ð¾ÑÑƒ.",
        "en": "I couldn't find recent publications for that request.",
        "it": "Non sono riuscito a trovare pubblicazioni recenti per questa richiesta.",
        "es": "No pude encontrar publicaciones recientes para esa solicitud.",
        "fr": "Je n'ai pas trouvÃ© de publications rÃ©centes pour cette demande.",
        "de": "Ich konnte keine aktuellen VerÃ¶ffentlichungen zu dieser Anfrage finden.",
    },
    "search_not_found": {
        "ru": "ÐÐµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ Ð½Ð°Ð¹Ñ‚Ð¸ Ð°ÐºÑ‚ÑƒÐ°Ð»ÑŒÐ½Ñ‹Ðµ Ð´Ð°Ð½Ð½Ñ‹Ðµ Ð¿Ð¾ Ð·Ð°Ð¿Ñ€Ð¾ÑÑƒ.",
        "en": "I couldn't find current data for that request.",
        "it": "Non sono riuscito a trovare dati attuali per questa richiesta.",
        "es": "No pude encontrar datos actuales para esa solicitud.",
        "fr": "Je n'ai pas trouvÃ© de donnÃ©es actuelles pour cette demande.",
        "de": "Ich konnte keine aktuellen Daten zu dieser Anfrage finden.",
    },
    "live_data_failed": {
        "ru": "ÐÐµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ Ð¿Ð¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ Ð°ÐºÑ‚ÑƒÐ°Ð»ÑŒÐ½Ñ‹Ðµ Ð´Ð°Ð½Ð½Ñ‹Ðµ Ð¿Ð¾ Ð·Ð°Ð¿Ñ€Ð¾ÑÑƒ.",
        "en": "I couldn't fetch current data for that request.",
        "it": "Non sono riuscito a recuperare dati aggiornati per questa richiesta.",
        "es": "No pude obtener datos actuales para esa solicitud.",
        "fr": "Je n'ai pas rÃ©ussi Ã  rÃ©cupÃ©rer des donnÃ©es actuelles pour cette demande.",
        "de": "Ich konnte keine aktuellen Daten zu dieser Anfrage abrufen.",
    },
    "weather_now": {
        "ru": "Ð¡ÐµÐ¹Ñ‡Ð°Ñ Ð² {location} {condition}",
        "en": "Right now in {location} it is {condition}",
        "it": "Adesso a {location} c'Ã¨ {condition}",
        "es": "Ahora en {location} estÃ¡ {condition}",
        "fr": "En ce moment Ã  {location}, c'est {condition}",
        "de": "Gerade ist es in {location} {condition}",
    },
    "weather_for_day": {
        "ru": "Ð·Ð° Ð´ÐµÐ½ÑŒ {temp_range}",
        "en": "for the day {temp_range}",
        "it": "nella giornata {temp_range}",
        "es": "durante el dÃ­a {temp_range}",
        "fr": "sur la journÃ©e {temp_range}",
        "de": "im Tagesverlauf {temp_range}",
    },
    "weather_precip_chance": {
        "ru": "Ð²ÐµÑ€Ð¾ÑÑ‚Ð½Ð¾ÑÑ‚ÑŒ Ð¾ÑÐ°Ð´ÐºÐ¾Ð² {precipitation}",
        "en": "precipitation chance {precipitation}",
        "it": "probabilitÃ  di precipitazioni {precipitation}",
        "es": "probabilidad de precipitaciÃ³n {precipitation}",
        "fr": "probabilitÃ© de prÃ©cipitations {precipitation}",
        "de": "Niederschlagswahrscheinlichkeit {precipitation}",
    },
    "weather_wind": {
        "ru": "Ð²ÐµÑ‚ÐµÑ€ {wind}",
        "en": "wind {wind}",
        "it": "vento {wind}",
        "es": "viento {wind}",
        "fr": "vent {wind}",
        "de": "Wind {wind}",
    },
    "weather_tomorrow": {
        "ru": "Ð—Ð°Ð²Ñ‚Ñ€Ð° Ð² {location} {condition}",
        "en": "Tomorrow in {location} it will be {condition}",
        "it": "Domani a {location} ci sarÃ  {condition}",
        "es": "MaÃ±ana en {location} habrÃ¡ {condition}",
        "fr": "Demain Ã  {location}, ce sera {condition}",
        "de": "Morgen wird es in {location} {condition}",
    },
    "weather_precip_up_to": {
        "ru": "Ð¾ÑÐ°Ð´ÐºÐ¸ Ð´Ð¾ {precipitation}",
        "en": "precipitation up to {precipitation}",
        "it": "precipitazioni fino a {precipitation}",
        "es": "precipitaciones de hasta {precipitation}",
        "fr": "prÃ©cipitations jusqu'Ã  {precipitation}",
        "de": "Niederschlag bis zu {precipitation}",
    },
    "weather_wind_up_to": {
        "ru": "Ð²ÐµÑ‚ÐµÑ€ Ð´Ð¾ {wind}",
        "en": "wind up to {wind}",
        "it": "vento fino a {wind}",
        "es": "viento de hasta {wind}",
        "fr": "vent jusqu'Ã  {wind}",
        "de": "Wind bis {wind}",
    },
    "news_brief": {
        "ru": "ÐšÐ¾Ñ€Ð¾Ñ‚ÐºÐ¾ Ð¿Ð¾ ÑÐ²ÐµÐ¶Ð¸Ð¼ Ð¿ÑƒÐ±Ð»Ð¸ÐºÐ°Ñ†Ð¸ÑÐ¼: {items}",
        "en": "Briefly from recent publications: {items}",
        "it": "In breve dalle pubblicazioni recenti: {items}",
        "es": "En breve, de las publicaciones recientes: {items}",
        "fr": "En bref sur les publications rÃ©centes : {items}",
        "de": "Kurz aus aktuellen VerÃ¶ffentlichungen: {items}",
    },
    "search_found": {
        "ru": "ÐŸÐ¾ ÑÐ²ÐµÐ¶Ð¸Ð¼ Ð´Ð°Ð½Ð½Ñ‹Ð¼ Ð½Ð°ÑˆÑ‘Ð» Ñ‚Ð°ÐºÐ¾Ðµ: {items}",
        "en": "From current data I found this: {items}",
        "it": "Dai dati attuali ho trovato questo: {items}",
        "es": "SegÃºn los datos actuales encontrÃ© esto: {items}",
        "fr": "D'aprÃ¨s les donnÃ©es actuelles, j'ai trouvÃ© ceci : {items}",
        "de": "Aus aktuellen Daten habe ich Folgendes gefunden: {items}",
    },
    "cross_chat_disabled": {
        "ru": "Ð’ ÑÑ‚Ð¾Ð¼ Ñ‡Ð°Ñ‚Ðµ ÐºÑ€Ð¾ÑÑ-Ñ‡Ð°Ñ‚ Ð´ÐµÐ¹ÑÑ‚Ð²Ð¸Ñ Ð¾Ñ‚ÐºÐ»ÑŽÑ‡ÐµÐ½Ñ‹.",
        "en": "Cross-chat actions are disabled in this chat.",
        "it": "In questa chat le azioni cross-chat sono disattivate.",
        "es": "Las acciones entre chats estÃ¡n desactivadas en este chat.",
        "fr": "Les actions inter-chats sont dÃ©sactivÃ©es dans ce chat.",
        "de": "Chat-Ã¼bergreifende Aktionen sind in diesem Chat deaktiviert.",
    },
    "summary_disabled": {
        "ru": "Ð”Ð»Ñ ÑÑ‚Ð¾Ð³Ð¾ Ñ‡Ð°Ñ‚Ð° ÑÐ²Ð¾Ð´ÐºÐ¸ Ð¾Ñ‚ÐºÐ»ÑŽÑ‡ÐµÐ½Ñ‹.",
        "en": "Summaries are disabled for this chat.",
        "it": "I riepiloghi sono disattivati per questa chat.",
        "es": "Los resÃºmenes estÃ¡n desactivados para este chat.",
        "fr": "Les rÃ©sumÃ©s sont dÃ©sactivÃ©s pour ce chat.",
        "de": "Zusammenfassungen sind fÃ¼r diesen Chat deaktiviert.",
    },
    "sent_result_to_chat": {
        "ru": "Ð“Ð¾Ñ‚Ð¾Ð²Ð¾. ÐžÑ‚Ð¿Ñ€Ð°Ð²Ð¸Ð» Ñ€ÐµÐ·ÑƒÐ»ÑŒÑ‚Ð°Ñ‚ Ð² {chat}.",
        "en": "Done. I sent the result to {chat}.",
        "it": "Fatto. Ho inviato il risultato in {chat}.",
        "es": "Hecho. EnviÃ© el resultado a {chat}.",
        "fr": "C'est fait. J'ai envoyÃ© le rÃ©sultat Ã  {chat}.",
        "de": "Fertig. Ich habe das Ergebnis an {chat} gesendet.",
    },
    "nothing_found_in_chat": {
        "ru": "Ð’ {chat} Ð½Ð¸Ñ‡ÐµÐ³Ð¾ Ð¿Ð¾Ñ…Ð¾Ð¶ÐµÐ³Ð¾ Ð½Ðµ Ð½Ð°ÑˆÑ‘Ð».",
        "en": "I didn't find anything similar in {chat}.",
        "it": "Non ho trovato nulla di simile in {chat}.",
        "es": "No encontrÃ© nada parecido en {chat}.",
        "fr": "Je n'ai rien trouvÃ© de similaire dans {chat}.",
        "de": "Ich habe in {chat} nichts Ã„hnliches gefunden.",
    },
    "found_in_chat": {
        "ru": "ÐÐ°ÑˆÑ‘Ð» Ð² {chat}:",
        "en": "I found this in {chat}:",
        "it": "Ho trovato questo in {chat}:",
        "es": "EncontrÃ© esto en {chat}:",
        "fr": "J'ai trouvÃ© ceci dans {chat} :",
        "de": "Ich habe das in {chat} gefunden:",
    },
    "chat_no_context": {
        "ru": "Ð’ {chat} Ð½ÐµÑ‚ Ð½Ð¾Ñ€Ð¼Ð°Ð»ÑŒÐ½Ð¾Ð³Ð¾ Ð½ÐµÐ´Ð°Ð²Ð½ÐµÐ³Ð¾ ÐºÐ¾Ð½Ñ‚ÐµÐºÑÑ‚Ð°.",
        "en": "There isn't enough useful recent context in {chat}.",
        "it": "Non c'Ã¨ abbastanza contesto recente utile in {chat}.",
        "es": "No hay suficiente contexto reciente Ãºtil en {chat}.",
        "fr": "Il n'y a pas assez de contexte rÃ©cent utile dans {chat}.",
        "de": "Es gibt in {chat} nicht genug nÃ¼tzlichen aktuellen Kontext.",
    },
    "saved_messages_label": {
        "ru": "Ð˜Ð·Ð±Ñ€Ð°Ð½Ð½Ð¾Ðµ",
        "en": "Saved Messages",
        "it": "Messaggi salvati",
        "es": "Mensajes guardados",
        "fr": "Messages enregistrÃ©s",
        "de": "Gespeicherte Nachrichten",
    },
    "parse_chat_error": {
        "ru": "ÐÐµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ Ñ€Ð°Ð·Ð¾Ð±Ñ€Ð°Ñ‚ÑŒ Ñ‡Ð°Ñ‚. Ð˜ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐ¹ @username, t.me ÑÑÑ‹Ð»ÐºÑƒ, chat id Ð¸Ð»Ð¸ me.",
        "en": "I couldn't parse the chat reference. Use @username, a t.me link, chat id, or me.",
        "it": "Non sono riuscito a interpretare il riferimento alla chat. Usa @username, un link t.me, chat id oppure me.",
        "es": "No pude interpretar la referencia del chat. Usa @username, un enlace t.me, chat id o me.",
        "fr": "Je n'ai pas pu interprÃ©ter la rÃ©fÃ©rence du chat. Utilise @username, un lien t.me, un chat id ou me.",
        "de": "Ich konnte die Chat-Referenz nicht erkennen. Nutze @username, einen t.me-Link, eine Chat-ID oder me.",
    },
    "open_chat_error": {
        "ru": "ÐÐµ ÑÐ¼Ð¾Ð³ Ð¾Ñ‚ÐºÑ€Ñ‹Ñ‚ÑŒ Ñ‡Ð°Ñ‚ {reference}. ÐŸÑ€Ð¾Ð²ÐµÑ€ÑŒ, Ñ‡Ñ‚Ð¾ Ð¾Ð½ ÑÑƒÑ‰ÐµÑÑ‚Ð²ÑƒÐµÑ‚ Ð¸ Ð´Ð¾ÑÑ‚ÑƒÐ¿ÐµÐ½.",
        "en": "I couldn't open chat {reference}. Check that it exists and is accessible.",
        "it": "Non sono riuscito ad aprire la chat {reference}. Controlla che esista e sia accessibile.",
        "es": "No pude abrir el chat {reference}. Verifica que exista y sea accesible.",
        "fr": "Je n'ai pas pu ouvrir le chat {reference}. VÃ©rifie qu'il existe et qu'il est accessible.",
        "de": "Ich konnte den Chat {reference} nicht Ã¶ffnen. PrÃ¼fe, ob er existiert und zugÃ¤nglich ist.",
    },
}


def detect_language(text: str | None) -> str:
    sample = (text or "").strip()
    if not sample:
        return DEFAULT_FALLBACK_LANGUAGE

    cyrillic_count = len(CYRILLIC_RE.findall(sample))
    latin_words = [token.casefold() for token in LATIN_WORD_RE.findall(sample)]
    latin_letters = sum(1 for char in sample if "A" <= char <= "z" or ord(char) > 127 and char.isalpha())

    lowered = sample.casefold()
    if cyrillic_count >= 2 and cyrillic_count >= max(2, latin_letters // 2):
        uk_score = sum(3 for char in lowered if char in "Ñ–Ñ—Ñ”Ò‘")
        uk_score += sum(1 for token in re.findall(r"[^\W\d_]+", lowered, flags=re.UNICODE) if token in LANGUAGE_HINT_WORDS["uk"])
        if uk_score >= 2:
            return "uk"
        return "ru"
    if not latin_words:
        return "en"

    scores: dict[str, int] = {language: 0 for language in SUPPORTED_LANGUAGES if language != "ru"}

    for language, words in LANGUAGE_HINT_WORDS.items():
        scores[language] += sum(1 for token in latin_words if token in words)

    for language, chars in LANGUAGE_CHAR_HINTS.items():
        scores[language] += sum(2 for char in lowered if char in chars)

    if re.search(r"\b(who|what|why|how|can|could|please|your)\b", lowered):
        scores["en"] += 2

    best_language = max(scores.items(), key=lambda item: (item[1], item[0] == "en"))[0]
    if scores[best_language] <= 0:
        return DEFAULT_FALLBACK_LANGUAGE
    return best_language


def language_name(language: str | None) -> str:
    normalized = normalize_language(language)
    return LANGUAGE_NAMES.get(normalized, LANGUAGE_NAMES["en"])


def normalize_language(language: str | None) -> str:
    if language in SUPPORTED_LANGUAGES:
        return str(language)
    return DEFAULT_FALLBACK_LANGUAGE


def is_text_in_language(text: str | None, expected_language: str | None) -> bool:
    language = normalize_language(expected_language)
    sample = (text or "").strip()
    if not sample:
        return True

    if language == "ru":
        return len(CYRILLIC_RE.findall(sample)) >= 2
    if language == "uk":
        lowered = sample.casefold()
        if any(char in lowered for char in "Ñ–Ñ—Ñ”Ò‘"):
            return True
        return detect_language(sample) == "uk"

    if len(CYRILLIC_RE.findall(sample)) >= 3:
        return False

    detected = detect_language(sample)
    if detected == language:
        return True

    if language == "en" and detected not in {"ru", "uk", "it", "es", "fr", "de"}:
        return True

    return False


def tr(key: str, language: str | None, **kwargs: object) -> str:
    normalized_language = normalize_language(language)
    table = TRANSLATIONS.get(key)
    if table is None:
        raise KeyError(f"Unknown translation key: {key}")
    template = table.get(normalized_language) or table.get("en") or next(iter(table.values()))
    return template.format(**kwargs)


