University: [ITMO University](https://itmo.ru/ru/)

Faculty: [FICT](https://fict.itmo.ru)

Course: [Vibe Coding: AI-боты для бизнеса](https://github.com/itmo-ict-faculty/vibe-coding-for-business)

Year: 2026

Group: U4125

Author: Popova Alina Romanovna

Lab: Lab2

Date of create: 06.04.2026

Date of finished: 06.04.2026


## Отчет по лабораторной работе

1. Я буду делать интеграцию с файлом JSON. Так как для моего бота это самый оптимальный вариант - брать рецепты из Json файла (который будет дополняться). При помощи Chat GPT  я сгенерировала файл с 110 различными рецептами:
<img width="749" height="736" alt="image" src="https://github.com/user-attachments/assets/08931d84-fef8-450a-b4f6-e0bbb44f709b" />
2. Для добавления нового источника данных сгенерировала промт для Cursor
Улучши моего Telegram-бота, добавив работу с json файлом.

Текущий функционал бота:
На текущий момент бот дает возможность выбрать рецепт в различных категориях: Завтрак, Обед, Ужин, Быстро. А также составить меню на неделю или на день.Сейчас бот берет рецепты их файла recipes.py

Новый функционал:
- Необходимо брать рецепты из файла recipes_110_final.json
- Необходимо выбирать нужные рецепты из файла по запросу пользователя.

Данные:


Требования:
- Код должен быть простым и понятным
- Добавить обработку ошибок
- Хорошие комментарии в коде
- Сохранить существующий функционал

Создай:

1. Обновленный bot.py
2. Файл с данными (если нужно)
3. Обновленный README.md

3. Отправила запрос в Cursor, ИИ приступил к выполнению
<img width="411" height="755" alt="image" src="https://github.com/user-attachments/assets/e85e3eb9-838e-4d50-87bf-0f5edb099a8b" />

4. ИИ обнаружил, что в файле есть ошибки и добавил валидацию входных данных и обработку ошибок.
<img width="421" height="678" alt="image" src="https://github.com/user-attachments/assets/141f6c56-449b-439c-ab70-2f72b235994e" />
Если JSON поврежден, бот пытается восстановить рецепты из корректных фрагментов и продолжить работу.
5. После этого я попросила обновить файл. а также добавить КБЖУ к каждому рецепту.
<img width="412" height="529" alt="image" src="https://github.com/user-attachments/assets/b98e985f-8252-41d4-af39-dc766e5c197a" />
6. Код теперь обращается к файлу
<img width="583" height="566" alt="image" src="https://github.com/user-attachments/assets/f796b684-8e9b-45e7-8d60-7cf4e3f43e35" />
7. При запуске возникла ошибка - отсутствует модуль telegram
<img width="565" height="112" alt="image" src="https://github.com/user-attachments/assets/cbda43dc-c667-4025-91d1-a14834bb71c7" />
8. Загрузила модуль: 
<img width="773" height="288" alt="image" src="https://github.com/user-attachments/assets/4fa071be-9da4-444b-b4ac-21f220f9dbbc" />
9. Запустила бота 
<img width="774" height="146" alt="image" src="https://github.com/user-attachments/assets/72ecd9fc-51a5-4d85-ae87-b7f993b45639" />

Видео с работой бота: https://drive.google.com/file/d/19pS4qBDZXwwUBwshyRKPUxKP8dlN11KS/view?usp=sharing 
