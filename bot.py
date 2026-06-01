import time
from dotenv import load_dotenv
load_dotenv()

import feedback

print("Бот запущен. Жду нажатий на кнопки... (Ctrl+C для остановки)")

while True:
    try:
        n = feedback.collect_feedback()
        if n:
            print(f"Обработано действий: {n}")
    except Exception as e:
        print(f"Ошибка: {e}")
    time.sleep(2)
