import requests
import random
from bs4 import BeautifulSoup
import time
import logging
from io import BytesIO
import re
import concurrent.futures
import sys
import locale

# Настройка кодировки системы
try:
    locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
except:
    pass

sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None
sys.stderr.reconfigure(encoding='utf-8') if hasattr(sys.stderr, 'reconfigure') else None

# Настройка логирования с явным указанием кодировки UTF-8
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Создаем форматтер с поддержкой UTF-8
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# Консольный вывод
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Файловый вывод с UTF-8
try:
    file_handler = logging.FileHandler("proxy_parser.log", encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
except Exception as e:
    logger.error(f"Ошибка создания файлового логгера: {str(e)}")

# --- Настройки ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1"
}

MAX_RETRIES = 1000
TIMEOUT = 30
BASE_URL = "https://infostart.ru/1c/articles/"
MAX_PROXY_RETRIES = 10
PROXY_CHECK_URL = "http://httpbin.org/ip"
PROXY_SOURCES = [
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=5000&country=all&ssl=all&anonymity=all",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
    "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt"
]

# --- Настройки Telegram ---
TELEGRAM_TOKEN = "8114950949:AAF_pK08B4IL17I0PgKthvLvqmxeRWmOA4w"
TELEGRAM_CHAT = "@VsratiyIS"
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"

# --- Настройки Hugging Face ---
HF_API_URL = "https://api-inference.huggingface.co/models/Salesforce/blip-image-captioning-base"
HF_TOKEN = "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"
HF_TIMEOUT = 60

# Глобальный список рабочих прокси
WORKING_PROXIES = []
LAST_PROXY_UPDATE = 0
PROXY_UPDATE_INTERVAL = 1800  # 30 минут

# --- Функции для работы с прокси ---
def update_proxy_list():
    """Обновляет список рабочих прокси из различных источников"""
    global WORKING_PROXIES, LAST_PROXY_UPDATE
    
    if time.time() - LAST_PROXY_UPDATE < PROXY_UPDATE_INTERVAL and WORKING_PROXIES:
        return
    
    logger.info("🔄 Обновление списка прокси...")
    all_proxies = []
    
    for source in PROXY_SOURCES:
        try:
            response = requests.get(source, timeout=15)
            if response.status_code == 200:
                proxies = re.findall(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+', response.text)
                all_proxies.extend(proxies)
                logger.info(f"Получено {len(proxies)} прокси из {source}")
        except Exception as e:
            logger.warning(f"Ошибка получения прокси из {source}: {str(e)}")
    
    # Удаляем дубликаты
    all_proxies = list(set(all_proxies))
    logger.info(f"Всего получено уникальных прокси: {len(all_proxies)}")
    
    # Проверяем работоспособность прокси
    if all_proxies:
        WORKING_PROXIES = check_proxies(all_proxies)
        LAST_PROXY_UPDATE = time.time()
        logger.info(f"✅ Обновлено рабочих прокси: {len(WORKING_PROXIES)}")
    else:
        logger.warning("⚠️ Не удалось получить список прокси")

def check_proxy(proxy):
    """Проверяет работоспособность одного прокси"""
    proxy_url = f"http://{proxy}"
    proxies = {"http": proxy_url, "https": proxy_url}
    
    try:
        start_time = time.time()
        response = requests.get(
            PROXY_CHECK_URL,
            proxies=proxies,
            timeout=10,
            headers=HEADERS
        )
        if response.status_code == 200:
            speed = time.time() - start_time
            return proxy, speed
    except Exception:
        pass
    return None

def check_proxies(proxies, max_workers=50):
    """Проверяет список прокси на работоспособность с использованием многопоточности"""
    valid_proxies = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(check_proxy, proxy) for proxy in proxies]
        
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                proxy, speed = result
                # Фильтруем слишком медленные прокси
                if speed < 5.0:
                    valid_proxies.append(proxy)
    
    return valid_proxies

def get_random_proxy():
    """Возвращает случайный рабочий прокси"""
    if not WORKING_PROXIES:
        update_proxy_list()
    
    if WORKING_PROXIES:
        return random.choice(WORKING_PROXIES)
    return None

def make_request(url, method="GET", timeout=TIMEOUT, retries=MAX_PROXY_RETRIES):
    """Выполняет запрос через случайный рабочий прокси"""
    for attempt in range(retries):
        proxy = get_random_proxy()
        if not proxy:
            logger.error("Нет доступных рабочих прокси")
            time.sleep(10)
            continue
            
        proxy_url = f"http://{proxy}"
        proxies = {"http": proxy_url, "https": proxy_url}
        
        try:
            logger.info(f"Попытка {attempt+1}/{retries} с прокси: {proxy}")
            
            if method == "GET":
                response = requests.get(
                    url, 
                    headers=HEADERS, 
                    proxies=proxies, 
                    timeout=timeout
                )
            elif method == "HEAD":
                response = requests.head(
                    url, 
                    headers=HEADERS, 
                    proxies=proxies, 
                    timeout=timeout
                )
            else:
                response = requests.request(
                    method,
                    url, 
                    headers=HEADERS, 
                    proxies=proxies, 
                    timeout=timeout
                )
            
            if response.status_code == 200:
                return response
            else:
                logger.warning(f"Ошибка {response.status_code} при запросе {url}")
        except requests.exceptions.ProxyError:
            # Удаляем нерабочий прокси из списка
            if proxy in WORKING_PROXIES:
                WORKING_PROXIES.remove(proxy)
                logger.warning(f"Удален нерабочий прокси: {proxy}")
        except Exception as e:
            logger.warning(f"Ошибка подключения: {str(e)}")
        
        time.sleep(random.uniform(1, 3))
    
    logger.error(f"Не удалось выполнить запрос после {retries} попыток")
    return None

# --- Функция: получить URL случайной статьи ---
def get_random_article_url():
    """Находит случайную рабочую статью через прокси"""
    for attempt in range(MAX_RETRIES):
        article_id = random.randint(1, 2000000)
        url = f"{BASE_URL}{article_id}/"
        logger.info(f"Проверка статьи #{article_id}")
        
        response = make_request(url)
        if response and response.status_code == 200:
            logger.info(f"✅ Статья найдена: {url}")
            return url
        
        # Задержка между попытками
        time.sleep(random.uniform(0.5, 2))
    
    logger.error("Не удалось найти доступную статью")
    return None

# --- Функция: найти изображения на странице ---
def get_images_from_article(url):
    """Извлекает изображения из статьи через прокси"""
    try:
        response = make_request(url)
        if not response or response.status_code != 200:
            logger.error(f"❌ Не удалось загрузить страницу: {url}")
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        image_urls = []

        # Поиск всех изображений в статье
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
    """Генерирует описание изображения через Hugging Face API"""
    try:
        # Скачиваем изображение через прокси
        response = make_request(image_url)
        if not response or response.status_code != 200:
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
    """Отправляет изображение в Telegram с описанием"""
    if not is_valid_image(image_url):
        return

    try:
        # Скачиваем изображение через прокси
        response = make_request(image_url)
        if not response or response.status_code != 200:
            logger.error(f"❌ Не удалось скачать изображение: {image_url}")
            return
        
        # Создаем временный файл
        with BytesIO() as buffer:
            buffer.write(response.content)
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
    """Проверяет валидность изображения через HEAD-запрос"""
    try:
        # Проверяем расширение файла
        clean_url = url.split('?')[0].lower()
        if not any(clean_url.endswith(ext) for ext in ('.jpg', '.jpeg', '.png', '.webp')):
            logger.warning(f"🚫 Неподдерживаемый формат: {url}")
            return False
            
        # Проверяем размер файла через HEAD-запрос
        response = make_request(url, method="HEAD", timeout=5)
        if not response:
            return False
            
        content_length = response.headers.get('Content-Length')
        if content_length and int(content_length) > 10 * 1024 * 1024:  # 10 MB
            logger.warning(f"🚫 Изображение слишком большое: {int(content_length)//1024} KB")
            return False
            
        return True
    except Exception as e:
        logger.error(f"Ошибка проверки изображения: {str(e)}")
        return False

# --- Основной цикл ---
def main():
    logger.info("🚀 Запуск парсера с интеллектуальной системой прокси...")
    sent_count = 0
    update_proxy_list()  # Начальное обновление списка прокси

    while True:
        try:
            logger.info("\n" + "="*50)
            logger.info("🔍 Поиск новой статьи через прокси...")
            article_url = get_random_article_url()
            if not article_url:
                logger.warning("Не удалось найти статью. Повтор через 10 секунд...")
                time.sleep(10)
                continue

            logger.info(f"📄 Анализ статьи: {article_url}")
            images = get_images_from_article(article_url)
            logger.info(f"📷 Найдено изображений: {len(images)}")

            if images:
                for img in images:
                    try:
                        logger.info(f"🖼️ Обработка изображения: {img}")
                        send_image_to_telegram(img, article_url)
                        sent_count += 1
                        logger.info(f"✅ Отправлено изображений: {sent_count}")
                        time.sleep(random.uniform(2, 5))  # Случайная задержка
                    except Exception as e:
                        logger.error(f"❌ Ошибка обработки изображения: {e}", exc_info=True)
                
                logger.info(f"📤 Всего отправлено изображений: {sent_count}")
                logger.info("⏳ Ожидание 5 минут перед следующей статьей...")
                time.sleep(300)  # Длительная пауза после статьи
            else:
                logger.warning("🖼️ Изображения не найдены.")
                time.sleep(10)

        except KeyboardInterrupt:
            logger.info("🛑 Программа остановлена пользователем")
            break
        except Exception as e:
            logger.critical(f"🔥 Критическая ошибка: {e}", exc_info=True)
            time.sleep(30)
            
            # При критической ошибке обновляем прокси
            update_proxy_list()

if __name__ == "__main__":
    main()
