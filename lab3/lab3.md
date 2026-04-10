University: [ITMO University](https://itmo.ru/ru/)

Faculty: [FICT](https://fict.itmo.ru)

Course: [Vibe Coding: AI-боты для бизнеса](https://github.com/itmo-ict-faculty/vibe-coding-for-business)

Year: 2026

Group: U4125

Author: Popova Alina Romanovna

Lab: Lab3

Date of create: 10.04.2026

Date of finished:


## Отчет по лабораторной работе

### Предварительные настройки

1. В качестве способа деплоя выбрала вариант - облачный хостинг (Railway)
2. Бот работает стабильно, без ошибок
3. Создала файл .gitignore
<img width="356" height="198" alt="image" src="https://github.com/user-attachments/assets/9464f7d7-097a-4b83-bfee-e11421418ba1" />
4. Доработала файл requirements.txt
<img width="480" height="145" alt="image" src="https://github.com/user-attachments/assets/60d68f70-cdec-4004-bcba-4f432389fbb3" />
5. Логгирование уже ранее было добавлено, изменения не вносила:
<img width="580" height="561" alt="image" src="https://github.com/user-attachments/assets/7d948beb-ef19-4569-b8ea-2797ecdae73b" />
6. Бот запущен и работает стабильно

### Деплой бота

1. Зарегистрировалась на Railway
2. Вошла через GitHub
3. Перенесла в свой репозиторий GitHub файлы по проекту.
4. Создала новый проект и подключила репозиторий
<img width="1434" height="833" alt="image" src="https://github.com/user-attachments/assets/6ea9594b-0c2c-4e8d-92f9-c5d6ef54dbcb" />
5. Добавила токен в переменные окружения
<img width="903" height="331" alt="image" src="https://github.com/user-attachments/assets/1fa39944-1150-4cc5-9ef0-9c1231603ce5" />
6. При деплое проекта он упал в ошибку:
<img width="1440" height="762" alt="image" src="https://github.com/user-attachments/assets/e692426a-32d7-480a-a224-287360960223" />
7. Проанализировала ошибку - версии были несовместимы. Исправила файл requirements.txt
<img width="1124" height="294" alt="image" src="https://github.com/user-attachments/assets/f71631b2-8080-4b1b-8d26-608b0cea28fe" />
9. После внесения изменений проект был успешно задеплоен
<img width="1439" height="476" alt="image" src="https://github.com/user-attachments/assets/e53d6a21-e120-464c-a5de-a5d0cee17ea9" />
10. Также были логи с ошибками из-за того, что бот параллельно было запущен локально. Остановила локально бота - проблемы ушли
11. После запуска необходимо взять URL, который сгенерирует Railway
12. Перешла в Settings - Networking, создала домен: 2026-chatbots-u4125-popovaar-production.up.railway.app
13. Перешла к настройке webhook - домен не открывался
14. Доработала код в питоне, добавив возможность работать с webhook
15. После этого еще сохранялись ошибки при деплое, я доработала файлы bot.py, requirements.txt и бот запустился
<img width="1439" height="765" alt="image" src="https://github.com/user-attachments/assets/0224f62a-5263-4912-9d58-16f73ac8f78b" />
16. Webhook создан
<img width="329" height="193" alt="image" src="https://github.com/user-attachments/assets/e52a06f6-8b54-446e-864f-ef1dd74496a9" />
17. После этого бот перестал отвечать, пришлось скорректировать код - бот заработал.
<img width="1062" height="588" alt="image" src="https://github.com/user-attachments/assets/f6ce1e95-5da5-4453-987d-bb405dd10f02" />

### Сбор обратной связи

1. Отправила бот на тестирование друзьям. (Суммарно воспользовалось около 7 человек, обратную связь получила от трех)
Обратная связь:
<img width="464" height="71" alt="image" src="https://github.com/user-attachments/assets/ded95dfd-b240-49a9-9a6e-12803987b7ec" />
<img width="929" height="38" alt="image" src="https://github.com/user-attachments/assets/f278f040-9cc5-47dd-be6f-e363f7965d9b" />
<img width="932" height="92" alt="image" src="https://github.com/user-attachments/assets/190cf64d-d278-41e8-b2fa-c2054e884aa3" />

Необходимо добавлять граммовки/стаканы к рецептам
Возможность перегенерировать предложенный список рецептов
Добавить картинки к рецептам (Возьмем в бэклог)

Также сама выявила, что необходимо добавить кнопку очистки списка покупок
2. Доработала бот с учетом нового функционала. Бот действительно стал удобнее
<img width="554" height="712" alt="image" src="https://github.com/user-attachments/assets/60fdffc5-8ed8-4cc5-8382-a3c10fe0b716" />
<img width="1041" height="552" alt="image" src="https://github.com/user-attachments/assets/736bd8e0-bdb2-4cb2-ae79-c7702b68767f" />
<img width="460" height="463" alt="image" src="https://github.com/user-attachments/assets/e1a6180f-6857-40a0-8976-269ebef1b4e2" />

Также дополнительно появились новые фильтры (низкокалорийное, белковое):
<img width="306" height="144" alt="image" src="https://github.com/user-attachments/assets/38da97ed-7c42-4d11-bd03-52a1ad254cba" />

## Вывод

Получилось развернуть бот, он работает стабильно. 
Ботом пользовались реальные люди извне, оставили свою обратную связь при помощи которой удалось улучшить бота.



