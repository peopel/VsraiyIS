import requests
import random
from bs4 import BeautifulSoup
import time
import os
import base64
from io import BytesIO
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Настройки ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

MAX_RETRIES = 1000
TIMEOUT = 100
BASE_URL = "https://infostart.ru/1c/articles/"

# --- Настройки Telegram ---
TELEGRAM_TOKEN = "8114950949:AAF_pK08B4IL17I0PgKthvLvqmxeRWmOA4w"
TELEGRAM_CHAT = "@VsratiyIS"
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"

# --- Настройки Hugging Face ---
# Используем другую модель, совместимую с API
HF_API_URL = "https://api-inference.huggingface.co/models/Salesforce/blip-image-captioning-base"
HF_TOKEN = "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"
HF_TIMEOUT = 60

# --- Функция: получить URL случайной статьи ---
def get_random_article_url():
    for attempt in range(MAX_RETRIES):
        article_id = random.randint(1755375, 1755375)
        url = f"{BASE_URL}{article_id}/"
        try:
            response = requests.head(url, headers=HEADERS, timeout=TIMEOUT)
            if response.status_code == 200:
                logger.info(f"✅ Статья найдена: {url}")
                return url
            else:
                logger.debug(f"❌ Статья {article_id} не найдена (код {response.status_code})")
        except requests.exceptions.RequestException as e:
            logger.warning(f"⚠️ Ошибка подключения к {url}: {e}")
        time.sleep(0.1)
    return None

# --- Функция: найти изображения на странице ---
def get_images_from_article(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if response.status_code != 200:
            logger.error(f"❌ Не удалось загрузить страницу: {url}")
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        image_urls = []

        # Поиск обычных изображений
        for img in soup.find_all('img', src=True):
            src = img.get('src', '')
            if src:
                if src.startswith(('http://', 'https://')):
                    image_urls.append(src)
                elif src.startswith('/'):
                    image_urls.append(f"https://infostart.ru{src}")
        
        # Фильтрация изображений
        filtered = [
            img for img in image_urls 
            if 'infostart.ru' in img 
            and 'no_avatar_forum' not in img
            and any(img.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp'])
        ]
        return list(set(filtered))
    except Exception as e:
        logger.error(f"⚠️ Ошибка при парсинге изображений: {e}", exc_info=True)
        return []

# --- Функция: генерация описания изображения ---
def generate_image_caption(image_url):
    try:
        # Скачиваем изображение
        response = requests.get(image_url, headers=HEADERS, timeout=TIMEOUT)
        if response.status_code != 200:
            logger.error(f"❌ Не удалось скачать изображение: {image_url}")
            return None
            
        # Проверка размера изображения
        if len(response.content) > 3 * 1024 * 1024:  # 3 MB
            logger.warning(f"⚠️ Изображение слишком большое: {len(response.content)//1024} KB")
            return None
            
        # Подготовка запроса для Hugging Face
        headers = {"Authorization": f"Bearer {HF_TOKEN}"}
        
        # Отправляем бинарные данные изображения
        response_hf = requests.post(
            HF_API_URL,
            headers=headers,
            data=response.content,
            timeout=HF_TIMEOUT
        )
        
        # Обработка ответа
        if response_hf.status_code == 200:
            result = response_hf.json()
            if isinstance(result, list) and len(result) > 0:
                caption = result[0].get('generated_text', '')
                logger.info(f"🤖 Сгенерировано описание: {caption}")
                return caption
                
        elif response_hf.status_code == 503:
            # Обработка случая, когда модель загружается
            try:
                error_data = response_hf.json()
                estimated_time = error_data.get('estimated_time', 30)
                logger.info(f"⏳ Модель загружается, ожидаем {estimated_time} секунд...")
                time.sleep(estimated_time + 5)
                return generate_image_caption(image_url)  # Повторная попытка
            except:
                time.sleep(30)
                return None
                
        else:
            logger.error(f"❌ Ошибка Hugging Face ({response_hf.status_code}): {response_hf.text}")
            
    except Exception as e:
        logger.error(f"⚠️ Ошибка генерации описания: {e}", exc_info=True)
    return None

# --- Функция: отправить фото в Telegram ---
def send_image_to_telegram(image_url, article_url):
    if not is_valid_image(image_url):
        return

    try:
        # Скачиваем изображение для Telegram
        img_response = requests.get(image_url, stream=True, timeout=15, headers=HEADERS)
        img_response.raise_for_status()
        
        # Создаем временный файл
        with BytesIO() as buffer:
            buffer.write(img_response.content)
            buffer.seek(0)
            
            # Генерация описания нейросетью
            ai_caption = generate_image_caption(image_url)
            
            # Формируем описание
            caption = f"📌 Изображение из статьи:\n{article_url}"
            if ai_caption:
                caption += f"\n\n🤖 Описание нейросетью:\n{ai_caption}"
            
            # Обрезаем до 1024 символов
            caption = caption[:1024]

            # Отправляем в Telegram
            files = {'photo': buffer}
            data = {'chat_id': TELEGRAM_CHAT, 'caption': caption}
            
            tg_response = requests.post(
                TELEGRAM_API,
                data=data,
                files=files,
                timeout=20
            )
            
            if tg_response.status_code == 200:
                logger.info(f"✅ Изображение отправлено в Telegram")
            else:
                logger.error(f"❌ Ошибка Telegram ({tg_response.status_code}): {tg_response.text}")
            
    except Exception as e:
        logger.error(f"⚠️ Ошибка отправки в Telegram: {e}", exc_info=True)

def is_valid_image(url):
    try:
        # Проверяем расширение файла
        clean_url = url.split('?')[0].lower()
        if not any(clean_url.endswith(ext) for ext in ('.jpg', '.jpeg', '.png', '.webp')):
            logger.warning(f"🚫 Неподдерживаемый формат: {url}")
            return False
            
        # Проверяем размер файла по заголовкам
        head_response = requests.head(url, headers=HEADERS, timeout=5)
        content_length = head_response.headers.get('Content-Length')
        if content_length and int(content_length) > 10 * 1024 * 1024:  # 10 MB
            logger.warning(f"🚫 Изображение слишком большое: {int(content_length)//1024} KB")
            return False
            
        return True
    except:
        return False

# --- Основной цикл ---
def main():
    logger.info("🚀 Запуск парсера и отправки изображений в Telegram...")
    sent_count = 0

    while True:
        try:
            logger.info("\n🔍 Поиск новой статьи...")
            article_url = get_random_article_url()
            if not article_url:
                logger.warning("Не удалось найти статью. Повтор через 10 секунд...")
                time.sleep(10)
                continue

            images = get_images_from_article(article_url)
            logger.info(f"📷 Найдено изображений: {len(images)}")

            if images:
                for img in images:
                    try:
                        logger.info(f"🖼️ Обработка изображения: {img}")
                        send_image_to_telegram(img, article_url)
                        sent_count += 1
                        logger.info(f"✅ Отправлено изображений: {sent_count}")
                        time.sleep(3)  # Пауза между изображениями
                    except Exception as e:
                        logger.error(f"❌ Ошибка обработки изображения: {e}", exc_info=True)
                
                logger.info(f"📤 Всего отправлено изображений: {sent_count}")
                logger.info("⏳ Ожидание 5 минут перед следующей статьей...")
                time.sleep(300)  # Пауза после статьи
            else:
                logger.warning("🖼️ Изображения не найдены.")
                time.sleep(10)

        except KeyboardInterrupt:
            logger.info("🛑 Программа остановлена пользователем")
            break
        except Exception as e:
            logger.critical(f"🔥 Критическая ошибка в основном цикле: {e}", exc_info=True)
            time.sleep(30)

if __name__ == "__main__":
    main()
