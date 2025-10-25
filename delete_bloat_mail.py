#!/usr/bin/env python3
from __future__ import print_function
import os
import sys
import pickle
import time
import signal
from textwrap import dedent
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# Универсальный ANSI-режим для Windows (цвета и очистка строк)
try:
    from colorama import init as colorama_init
    colorama_init()
except ImportError:
    pass

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
BLOAT_FILE = "list-bloat.txt"
WHITE_FILE = "list-white.txt"
STOPPED = False  # флаг остановки


# ────────────────────────────────────────────────
# CTRL-C / SIGINT обработка
# ────────────────────────────────────────────────
def handle_interrupt(signum, frame):
    global STOPPED
    STOPPED = True
    print("\n🛑 Прервано пользователем (Ctrl-C).")
    sys.exit(0)


signal.signal(signal.SIGINT, handle_interrupt)
signal.signal(signal.SIGTERM, handle_interrupt)


# ────────────────────────────────────────────────
# HELP
# ────────────────────────────────────────────────
def show_help():
    print(
        dedent(
            f"""
            📬 Gmail Bloat Cleaner — автоочистка нежелательных писем

            Использование:
              python {os.path.basename(__file__)} run     # запустить очистку
              python {os.path.basename(__file__)} help    # показать справку

            📂 Файлы конфигурации:
              • {BLOAT_FILE} — фильтры писем для удаления
              • {WHITE_FILE} — белый список (не трогать)

            Примеры строк:
              unsubscribe
              "За покупку от" "сформирован электронный документ"
              mail:receipt@kari.com
              subject:(GitHub)

            Белый список:
              mail:support@zomro.com
              subject:(Apple)
              "Google One"

            ⚙️ Алгоритм:
              • ищет письма по каждому фильтру из {BLOAT_FILE}
              • исключает совпадения из {WHITE_FILE}
              • найденные письма → корзина (TRASH)
              • аккуратный live-вывод, без "висячих" ❌
            """
        ).strip()
    )
    sys.exit(0)


# ────────────────────────────────────────────────
# GMAIL AUTH
# ────────────────────────────────────────────────
def get_service():
    creds = None
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists("client_secret.json"):
                print("❌ Не найден client_secret.json — скачай его из Google Cloud Console.")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)
    return build("gmail", "v1", credentials=creds)


# ────────────────────────────────────────────────
# FILE OPS
# ────────────────────────────────────────────────
def ensure_default_files():
    if not os.path.exists(BLOAT_FILE):
        with open(BLOAT_FILE, "w", encoding="utf-8") as f:
            f.write(
                "# Фильтры для удаления писем\n"
                "unsubscribe\nотписаться\n"
                "\"За покупку от\" \"сформирован электронный документ\"\n"
                "mail:receipt@kari.com\n"
            )
    if not os.path.exists(WHITE_FILE):
        with open(WHITE_FILE, "w", encoding="utf-8") as f:
            f.write(
                "# Белый список писем, которые нельзя удалять\n"
                "mail:support@zomro.com\nsubject:(Apple)\n\"Google One\"\n"
            )


def read_filters(path):
    with open(path, "r", encoding="utf-8") as f:
        filters = []
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if s.lower().startswith("mail:"):
                s = f"from:{s.split(':', 1)[1].strip()}"
            filters.append(s)
        return filters


# ────────────────────────────────────────────────
# GMAIL OPS
# ────────────────────────────────────────────────
def move_batch(service, msg_ids):
    if not msg_ids:
        return
    body = {"ids": msg_ids, "addLabelIds": ["TRASH"], "removeLabelIds": []}
    service.users().messages().batchModify(userId="me", body=body).execute()


def search_messages(service, query):
    results = service.users().messages().list(userId="me", q=query, maxResults=500).execute()
    messages = results.get("messages", [])
    while "nextPageToken" in results and not STOPPED:
        results = service.users().messages().list(
            userId="me", q=query, pageToken=results["nextPageToken"], maxResults=500
        ).execute()
        messages.extend(results.get("messages", []))
    return [m["id"] for m in messages]


def process_query(service, query, whitelist):
    """Live-обновление в одной строке"""
    if STOPPED:
        return 0

    def update_line(text):
        print(f"\r\033[K{text}", end="", flush=True)

    update_line(f"🔍 {query}")
    ids = search_messages(service, query)

    if not ids:
        update_line(f"🔍 {query} — ❌ Ничего не найдено.")
        time.sleep(0.25)
        return 0

    white_ids = set()
    for w in whitelist:
        white_ids.update(search_messages(service, w))
        if STOPPED:
            return 0

    real_targets = [i for i in ids if i not in white_ids]

    if not real_targets:
        update_line(f"🔍 {query} — ⚪ В белом списке.")
        print()
        time.sleep(0.25)
        return 0

    for i in range(0, len(real_targets), 100):
        if STOPPED:
            return 0
        move_batch(service, real_targets[i : i + 100])

    update_line(f"🔍 {query} — ✅ {len(real_targets)} писем → корзина.")
    print()
    time.sleep(0.2)
    return len(real_targets)


# ────────────────────────────────────────────────
# MAIN
# ────────────────────────────────────────────────
def main():
    if len(sys.argv) == 1 or sys.argv[1] in {"-h", "--help", "help"}:
        show_help()

    if sys.argv[1] != "run":
        print("Неизвестная команда. Используй `python delete_bloat_mail.py help`.")
        sys.exit(1)

    ensure_default_files()
    service = get_service()
    bloat_filters = read_filters(BLOAT_FILE)
    white_filters = read_filters(WHITE_FILE)

    print(f"✅ Найдено {len(bloat_filters)} фильтров, {len(white_filters)} исключений.\n")

    start = time.time()
    total = 0

    try:
        for i, q in enumerate(bloat_filters, start=1):
            if STOPPED:
                break
            total += process_query(service, q, white_filters)
    except KeyboardInterrupt:
        handle_interrupt(None, None)

    # очищаем последнюю строку
    print("\r\033[K", end="", flush=True)

    elapsed = time.time() - start
    print(f"\n🎯 Всего перемещено в корзину: {total}")
    print(f"⏱ Выполнено за {elapsed:.2f} сек.\n")


if __name__ == "__main__":
    main()
