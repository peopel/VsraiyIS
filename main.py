import requests
import random
from bs4 import BeautifulSoup
import time
import os

# --- Настройки ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

MAX_RETRIES = 1000        # попыток найти одну статью
TIMEOUT = 2
BASE_URL = "https://infostart.ru/1c/articles/"  # ✅ Без пробелов!

# --- Настройки Telegram ---
TELEGRAM_TOKEN = "8114950949:AAF_pK08B4IL17I0PgKthvLvqmxeRWmOA4w"
TELEGRAM_CHAT = "@VsratiyIS"
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"  # ✅ Пробел убран!

# --- Функция: получить URL случайной статьи ---
def get_random_article_url():
    for _ in range(MAX_RETRIES):
        article_id = random.randint(1000000, 4100000)#(1755375,1755375)#
        url = f"{BASE_URL}{article_id}/"
        try:
            response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if response.status_code == 200:
                print(f"✅ Статья найдена: {url}")
                return url
            else:
                print(f"❌ Статья {article_id} не найдена (код {response.status_code}) ответ {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"⚠️ Ошибка подключения к {article_id}: {e}")
        time.sleep(0.3)
    return None

# --- Функция: найти изображения на странице ---
def get_images_from_article(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if response.status_code != 200:
            print(f"❌ Не удалось загрузить страницу: {url}")
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        image_urls = []

        # <img src="...">
        for img in soup.find_all('img', src=True):
            src = img['src']
            if src.startswith('/'):
                src = f"https://infostart.ru{src}"  # ✅ Без пробелов!
            image_urls.append(src)

        # style="background-image: url(...)"
        for div in soup.find_all(style=True):
            style = div.get('style')
            if 'background-image' in style:
                start = style.find("url(") + 4
                end = style.find(")", start)
                if start != -1 and end != -1:
                    bg_url = style[start:end].strip("'\" ")
                    if bg_url.startswith('/'):
                        bg_url = f"https://infostart.ru{bg_url}"  # ✅ Без пробелов!
                    elif not bg_url.startswith('http'):
                        bg_url = requests.compat.urljoin(url, bg_url)
                    image_urls.append(bg_url)

        # Фильтрация: только infostart и без no_avatar_forum
        filtered = [img for img in image_urls if 'infostart' in img and 'no_avatar_forum' not in img]
        return list(set(filtered))  # убираем дубли
    except Exception as e:
        print(f"⚠️ Ошибка при парсинге изображений: {e}")
        return []

# --- Функция: отправить фото в Telegram ---
def send_image_to_telegram(image_url, caption=""):
    if not is_valid_image(image_url):
        return

    try:
        response = requests.post(
            TELEGRAM_API,
            data={'chat_id': TELEGRAM_CHAT, 'caption': caption, 'parse_mode': 'HTML'},
            files={'photo': requests.get(image_url, headers=HEADERS, stream=True).raw},
            timeout=TIMEOUT
        )
        if response.status_code == 200:
            print(f"✅ Изображение отправлено в Telegram: {image_url}")
        else:
            print(f"❌ Ошибка отправки в Telegram: {response.status_code}, {response.text}")
    except Exception as e:
        print(f"⚠️ Исключение при отправке в Telegram: {e}")

def is_valid_image(url):
    valid_extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    ext = os.path.splitext(url)[1].lower()
    if ext not in valid_extensions:
        print(f"🚫 Игнорируем неподдерживаемый формат: {url}")
        return False
    return True

# --- Основной цикл ---
def main():
    print("🚀 Запуск парсера и отправки изображений в Telegram...")
    sent_count = 0

    while True:
        print("\n🔍 Поиск новой статьи...")
        article_url = get_random_article_url()
        if not article_url:
            print("Не удалось найти статью. Повтор...")
            #time.sleep(2)
            continue

        images = get_images_from_article(article_url)
        print(f"📷 Найдено изображений: {len(images)}")

        if images:
            for img in images:
                try:
                    caption = f"📌 Изображение из статьи:\n{article_url}"
                    send_image_to_telegram(img, caption=caption)
                    sent_count += 1
                    print(f"✅ Отправлено изображение {sent_count} из {len(images)}")
                except Exception as e:
                    print(f"❌ Ошибка при отправке изображения: {e}")
                    continue
            
            print(f"📤 Всего отправлено изображений: {sent_count}")
            time.sleep(300)
        else:
            print("🖼️ Изображения не найдены.")

        time.sleep(1)

if __name__ == "__main__":
    main()
