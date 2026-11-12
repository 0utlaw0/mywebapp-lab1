# mywebapp: Notes Service

Лабораторна робота №1 «Розгортання Web-сервісу з автоматизацією». Репозиторій містить веб-застосунок, скрипти автоматичного розгортання на Linux та документацію.

## 1. Варіант індивідуального завдання

Номер залікової книжки N = 6. За формулами із завдання виходить V2 = (6 % 2) + 1 = 1, V3 = (6 % 3) + 1 = 1 та V5 = (6 % 5) + 1 = 2.

Значення V3 = 1 означає, що застосунок називається mywebapp і є Notes Service, тобто простим сервісом для зберігання текстових нотаток. Значення V2 = 1 визначає, що застосунок конфігурується аргументами командного рядка (без конфігураційного файлу), а як СУБД використовується MariaDB. Значення V5 = 2 задає порт застосунку 5200. Застосунок слухає лише адресу 127.0.0.1, база даних доступна лише з локальної машини на 127.0.0.1:3306, а назовні на порту 80 відкритий тільки nginx.

Архітектура: клієнт → nginx (reverse proxy, 0.0.0.0:80) → mywebapp (127.0.0.1:5200) → MariaDB (127.0.0.1:3306).

## 2. Веб-застосунок

### Призначення

Notes Service зберігає текстові нотатки. Кожна нотатка має поля id, title, content і created_at. Застосунок написаний на Python з використанням Flask, з'єднання з MariaDB виконується через PyMySQL, у production застосунок запускається через gunicorn.

### Структура репозиторію

Каталог `app/` містить `mywebapp.py` (застосунок), `migrate.py` (скрипт міграції БД), `server.py` (запуск через gunicorn) і `requirements.txt`. Каталог `deploy/` містить `install.sh`, `mywebapp.service`, `mywebapp.socket`, `nginx-mywebapp.conf` та `sudoers-operator`.

### Налаштування середовища для розробки

Потрібен Python 3.10 або новіший. У каталозі `app` створіть віртуальне середовище та встановіть залежності. gunicorn на Windows не працює, тому для локальної розробки достатньо Flask і PyMySQL.

```
cd app
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt # на Windows: pip install Flask PyMySQL
```

Для повноцінної перевірки бізнес-логіки потрібна локальна MariaDB з порожньою базою та користувачем, що має на неї повні права.

### Запуск застосунку

Уся конфігурація передається аргументами командного рядка. Обов'язкові аргументи лише `--db-user` і `--db-name`, решта має значення за замовчуванням: `--host 127.0.0.1`, `--port 5200`, `--db-host 127.0.0.1` і `--db-port 3306`. Аргумент `--db-password` за замовчуванням береться зі змінної оточення `DB_PASSWORD` (або порожній, якщо її немає). У production пароль передається саме через оточення з файлу `/etc/mywebapp/db.env`, а не аргументом, щоб він не з'являвся у виводі `ps` і `systemctl status`. Спочатку виконується міграція, потім запускається застосунок:

```
python migrate.py --db-user USER --db-password PASS --db-name NAME
python mywebapp.py --db-user USER --db-password PASS --db-name NAME
```

У production використовується `server.py`, який приймає ті самі аргументи та запускає застосунок через gunicorn із двома worker-процесами.

### Скрипт міграції

`migrate.py` підключається до БД, створює таблицю `schema_version` і застосовує всі міграції, номер яких більший за поточну версію схеми. Тому його можна безпечно запускати і на порожній БД, і на БД, уже створеній цим скриптом. Перша міграція створює таблицю `notes` та індекс за полем `created_at`.

### API

Ендпоінт `GET /health/alive` завжди повертає HTTP 200 з текстом OK. Ендпоінт `GET /health/ready` повертає 200 з текстом OK, якщо застосунок може підключитися до БД, інакше повертає 500 з коротким описом проблеми. Ці два ендпоінти доступні лише напряму до застосунку на 127.0.0.1:5200, через nginx вони закриті.

Кореневий ендпоінт `GET /` повертає лише HTML зі списком ендпоінтів бізнес-логіки. Ендпоінт `GET /notes` повертає список нотаток (id та title). Ендпоінт `POST /notes` створює нотатку з полями title і content, які можна передати як JSON або як дані форми, і повертає код 201; якщо title порожній, повертається 400. Ендпоінт `GET /notes/<id>` повертає повну нотатку (id, title, created_at, content) або 404, якщо такої нотатки немає.

Формат відповіді бізнес-ендпоінтів залежить від заголовка `Accept`. Для `text/html` повертається проста HTML-сторінка без JavaScript і стилів, де списки виводяться таблицею; для `application/json` повертаються дані у форматі JSON; для інших значень повертається 406.

Приклади:

```
curl -H "Accept: application/json" http://<host>/notes
curl -X POST -H "Content-Type: application/json" -H "Accept: application/json" \
     -d '{"title":"Test","content":"Hello"}' http://<host>/notes
curl -H "Accept: text/html" http://<host>/notes/1
```

## 3. Розгортання

### Віртуальна машина

Використовується офіційний образ Ubuntu Server 24.04 LTS з сайту https://ubuntu.com/download/server. Рекомендовані ресурси ВМ: 2 vCPU, 2 ГБ RAM і 20 ГБ диска. Окремої розбивки диска не потрібно, достатньо розмітки за замовчуванням. Під час встановлення бажано ввімкнути OpenSSH server. Гіпервізор: VirtualBox. Мережа ВМ складається з двох адаптерів:

- Adapter 1: NAT, використовується лише для виходу ВМ в інтернет (встановлення пакетів). Проброс портів не налаштовувався.
- Adapter 2: Host-Only Adapter зі статичною адресою 192.168.106.10, заданою вручну в налаштуваннях мережі ОС. Через нього хост підключається до ВМ: SSH (192.168.106.10:22) і HTTP (http://192.168.106.10/).

### Вхід на ВМ

Початковий вхід виконується через консоль гіпервізора або по SSH під користувачем, якого ви створили під час встановлення ОС: `vboxuser` з паролем `vboxuser`. Після виконання скрипта цей користувач блокується, і далі входити потрібно під користувачами student, teacher або operator з початковим паролем 12345678, який система зажадає змінити при першому вході.

### Запуск автоматизації

Єдина точка входу це `deploy/install.sh`. Склонуйте репозиторій на ВМ і запустіть скрипт від імені адміністратора:

```
sudo apt-get install -y git
git clone https://github.com/0utlaw0/mywebapp-lab1.git
cd mywebapp-lab1
sudo bash deploy/install.sh
```

Якщо скрипт запускається не з-під дефолтного користувача, його ім'я можна передати явно: `sudo DEFAULT_USER=<vboxuser> bash deploy/install.sh`. Скрипт ідемпотентний, повторний запуск оновлює код застосунку та конфігурацію, не скидаючи паролі користувачів і пароль БД.

Скрипт встановлює nginx, MariaDB, Python і curl; створює користувачів student і teacher з правами адміністратора, користувача operator з обмеженим sudo та системного користувача mywebapp без можливості входу (у таблиці завдання цей користувач позначений як `app`); записує число 6 у `/home/student/gradebook`; обмежує MariaDB адресою 127.0.0.1, створює БД і користувача БД та зберігає згенерований пароль у `/etc/mywebapp/db.env` із правами 640. Далі він копіює застосунок у `/opt/mywebapp`, створює віртуальне середовище, встановлює `mywebapp.service` та `mywebapp.socket` і вмикає socket activation. Застосунок запускається від користувача mywebapp, перед стартом виконує міграцію, а пароль до БД бере зі змінних оточення з файлу `db.env`, а не з unit-файлу чи аргументів командного рядка. Після цього скрипт підключає конфігурацію nginx, яка проксує лише `/`, `/notes` та `/notes/<id>` і веде журнал запитів у `/var/log/nginx/mywebapp_access.log`, встановлює sudoers-правила для operator та наприкінці блокує дефолтного користувача.

Користувач operator може через sudo лише запускати, зупиняти, перезапускати та переглядати статус сервісу mywebapp і його сокета mywebapp.socket, а також перезавантажувати конфігурацію nginx. Через socket activation зупинка лише сервісу тимчасова: наступний запит до порту 5200 знову його запускає. Щоб зупинити застосунок повністю, operator виконує `sudo systemctl stop mywebapp.socket` (зупиняє і сокет, і сервіс), а запускає через `sudo systemctl start mywebapp.socket`.

## 4. Тестування розгорнутої системи

Після завершення `install.sh` на ВМ виконайте такі перевірки.

Спочатку перевірте сервіси: `systemctl status mywebapp.socket mywebapp.service nginx mariadb`. Сокет має бути в стані active (listening), а сервіс mywebapp запускається при першому підключенні.

Потім перевірте застосунок напряму: `curl -i http://127.0.0.1:5200/health/alive` і `curl -i http://127.0.0.1:5200/health/ready` мають повернути 200 і OK. Щоб перевірити, що `/health/ready` реагує на недоступність БД, зупиніть MariaDB командою `sudo systemctl stop mariadb`, після чого запит має повернути 500, а потім знову запустіть MariaDB.

Далі перевірте роботу через nginx з іншої машини або з хоста: створіть нотатку через POST, отримайте список через `GET /notes` із заголовками `Accept: application/json` та `Accept: text/html`, отримайте нотатку за id та перевірте, що неіснуючий id дає 404. Також перевірте, що `http://<IP>/health/alive` та будь-який інший шлях поза бізнес-ендпоінтами через nginx повертають 404, а запит з `Accept: text/plain` до `/notes` повертає 406.

Перевірте міграцію: повторний запуск `sudo systemctl restart mywebapp` не повинен давати помилок, а в БД після двох запусків має бути один запис у `schema_version`.

Перевірте користувачів: `cat /home/student/gradebook` виводить 6; вхід під student і teacher вимагає зміни пароля 12345678 і дозволяє `sudo`; під operator команда `sudo systemctl restart mywebapp` працює без пароля, а, наприклад, `sudo systemctl stop nginx` або `sudo cat /etc/shadow` відхиляється. Спроба увійти під дефолтним користувачем має завершуватися відмовою. Файл `/etc/mywebapp/db.env` має права 640 і групу mywebapp: `sudo ls -l /etc/mywebapp/db.env`.

Перевірте керування сокетом: `sudo -u operator sudo -n systemctl stop mywebapp.socket` зупиняє застосунок повністю (запит до порту 5200 після цього не проходить), а `sudo -u operator sudo -n systemctl start mywebapp.socket` запускає його знову. Також переконайтеся, що пароль БД не видно в командному рядку процесу: `ps aux | grep '[s]erver.py'`.

Перевірте доступність БД: `ss -ltnp | grep 3306` має показувати прослуховування лише 127.0.0.1, а `ss -ltnp | grep 5200` також лише 127.0.0.1, при цьому порт 80 слухає на 0.0.0.0. Нарешті, перегляньте журнал запитів: `sudo tail /var/log/nginx/mywebapp_access.log`.

## 5. Результати тестування

Розгортання виконано на віртуальній машині у VirtualBox з Ubuntu Server 24.04 LTS. Мережа ВМ: Adapter 1 NAT (лише вихід в інтернет), Adapter 2 Host-Only зі статичною адресою 192.168.106.10. Запити з хоста в п. 5.2 надсилались на http://192.168.106.10/.

Скрипт `deploy/install.sh` відпрацював до кінця. Його вбудовані smoke-тести повернули код 200 для `/`, 200 для `/notes` та 404 для `/health/alive` через nginx. Під час першого запуску скрипт зупинився на створенні користувача `operator`, бо в Ubuntu вже існує системна група з такою назвою. Це виправлено окремим комітом, після чого повторний запуск пройшов успішно, що також підтверджує ідемпотентність скрипта.

### 5.1. Користувачі та доступ

- Вхід під користувачем `student` з паролем `12345678` спрацював, система одразу зажадала змінити пароль. Після цього `sudo` працює.
- Спроба входу під дефолтним користувачем `vboxuser` завершується відмовою `Permission denied` незалежно від введеного пароля, тобто блокування працює.
- Файл `/home/student/gradebook` містить число `6`.
- Конфігурація з паролем БД (`/etc/mywebapp/db.env`) недоступна звичайним користувачам.

### 5.2. Перевірка через nginx з хост-машини

| Запит | Результат |
|---|---|
| `GET /` | 200 |
| `GET /notes` | 200 |
| `GET /notes/<неіснуючий id>` | 404 |
| `GET /notes` з `Accept: text/plain` | 406 |
| `GET /health/alive` | 404 (закритий nginx-ом назовні) |
| `POST /notes` (title і content заповнені) | 201 |
| `POST /notes` (порожній title) | 400 |
| `GET /notes` з `Accept: application/json` | 200 |
| `GET /notes` з `Accept: text/html` | 200 |
| `GET /notes/1` з `Accept: application/json` | 200 |
| `GET /notes/1` з `Accept: text/html` | 200 |

### 5.3. Перевірка на самій ВМ

Виконані команди:

```bash
sudo whoami
systemctl is-active mywebapp.socket nginx mariadb
cat /home/student/gradebook
ls -l /etc/mywebapp/db.env
sudo ls -l /etc/mywebapp/db.env
ss -ltn | grep -E ':80 |:5200|:3306'
curl -s -o /dev/null -w "ready: %{http_code}\n" http://127.0.0.1:5200/health/ready
sudo systemctl stop mariadb
curl -s -o /dev/null -w "ready without db: %{http_code}\n" http://127.0.0.1:5200/health/ready
sudo systemctl start mariadb
sleep 3
curl -s -o /dev/null -w "ready again: %{http_code}\n" http://127.0.0.1:5200/health/ready
sudo -u operator sudo -n systemctl restart mywebapp; echo "operator restart: $?"
sudo -u operator sudo -n systemctl reload nginx; echo "operator reload: $?"
sudo -u operator sudo -n systemctl stop nginx; echo "operator stop nginx: $?"
systemctl is-active nginx
sudo systemctl restart mywebapp
sudo mysql mywebapp -e "SELECT * FROM schema_version;"
```

Вивід:

```text
root
active
active
active
6
ls: cannot access '/etc/mywebapp/db.env': Permission denied
-rw-r----- 1 root mywebapp 79 Nov 12 21:13 /etc/mywebapp/db.env
LISTEN 0      2048        127.0.0.1:5200       0.0.0.0:*
LISTEN 0      80          127.0.0.1:3306       0.0.0.0:*
LISTEN 0      511           0.0.0.0:80         0.0.0.0:*
LISTEN 0      511              [::]:80            [::]:*
ready: 200
ready without db: 500
ready again: 200
operator restart: 0
operator reload: 0
sudo: a password is required
operator stop nginx: 1
active
+---------+
| version |
+---------+
|       1 |
+---------+
```

Інтерпретація результатів:

- **Сервіси.** `mywebapp.socket`, `nginx` і `mariadb` мають стан `active`.
- **Мережа.** Застосунок (5200) і MariaDB (3306) слухають лише `127.0.0.1`, а nginx (80) приймає з'єднання на всіх інтерфейсах. Це відповідає вимогам до мережевих обмежень.
- **Health-check.** `/health/ready` повертає 200, коли БД працює, 500 після зупинки MariaDB і знову 200 після її запуску. Отже, застосунок коректно відновлює підключення без перезапуску.
- **Права `operator`.** Дозволені команди (`restart mywebapp`, `reload nginx`) виконуються з кодом 0. Команда `stop nginx` не входить до списку дозволених, тому `sudo` вимагає пароль і завершується з кодом 1. Nginx при цьому лишається `active`.
- **Секрети.** Звичайний користувач не може прочитати `/etc/mywebapp/db.env`.
- **Міграція.** Після повторного запуску сервісу в таблиці `schema_version` лишається один запис, тобто `migrate.py` ідемпотентний.
- **API.** Створення нотатки повертає 201, порожній `title` дає 400, список і окрема нотатка віддаються і в JSON, і в HTML залежно від `Accept`.
