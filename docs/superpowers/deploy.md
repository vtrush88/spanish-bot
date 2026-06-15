# Spanish Bot — Deploy Run-book (DigitalOcean)

Пошаговый провижининг с нуля. Значения в угловых скобках (`<DROPLET_IP>`,
`<MAC_REPO>`) подставляются по ходу. Дизайн: `specs/2026-06-15-spanish-bot-deploy-design.md`.

## 0. Предусловия (на маке)
- Аккаунт DigitalOcean и SSH-ключ для входа на дроплет (`~/.ssh/id_ed25519`).
- Локальный репо: `<MAC_REPO>` = `Projects/Spanish Bot/app`.
- Рабочий `.env` и `spanish_bot.db` в `<MAC_REPO>`.

## 1. Приватный GitHub-репозиторий
```bash
cd "<MAC_REPO>"
# через gh (если установлен) — создаёт приватный репо и добавляет remote:
gh repo create spanish-bot --private --source=. --remote=origin --push
# либо вручную: создать приватный репо на github.com, затем:
#   git remote add origin git@github.com:<USER>/spanish-bot.git && git push -u origin main
```
Проверка: `git remote -v` показывает `origin`, на GitHub виден `main`.

## 2. Дроплет
- DigitalOcean → Create Droplet: Ubuntu 24.04 LTS, Basic, самый дешёвый
  (512 MiB $4/mo или 1 GiB $6/mo), регион Frankfurt/Amsterdam, аутентификация — твой SSH-ключ.
- Запиши `<DROPLET_IP>`.
```bash
ssh root@<DROPLET_IP>          # первый вход
```

## 3. Пользователь, пакеты, firewall (на сервере, под root)
```bash
adduser --disabled-password --gecos "" spanishbot
apt update && apt install -y python3.12 python3.12-venv git sqlite3
ufw allow OpenSSH && ufw --force enable
```

Дать `spanishbot` SSH-доступ (иначе `scp spanishbot@...` и вход не сработают —
у нового пользователя нет `authorized_keys`). Переиспользуем ключ Victoria,
который DigitalOcean уже положил для `root`:
```bash
mkdir -p /home/spanishbot/.ssh
cp ~/.ssh/authorized_keys /home/spanishbot/.ssh/authorized_keys
chown -R spanishbot:spanishbot /home/spanishbot/.ssh
chmod 700 /home/spanishbot/.ssh
chmod 600 /home/spanishbot/.ssh/authorized_keys
```

Ограниченный sudoers — чтобы рутинные `restart`/`status` работали из-под
`spanishbot` без полного root (у `--disabled-password` пароля и sudo нет):
```bash
cat > /etc/sudoers.d/spanishbot-service <<'EOF'
spanishbot ALL=(root) NOPASSWD: /usr/bin/systemctl restart spanish-bot, /usr/bin/systemctl status spanish-bot
EOF
chmod 440 /etc/sudoers.d/spanishbot-service
visudo -c        # проверка синтаксиса sudoers

# чтение журнала сервиса без sudo — членством в группе (надёжнее wildcard в sudoers):
usermod -aG systemd-journal spanishbot   # вступит в силу при следующем входе spanishbot
```

## 4. Deploy key — доступ сервера к приватному репо (read-only)
```bash
su - spanishbot
ssh-keygen -t ed25519 -f ~/.ssh/spanish_bot_deploy -N ""
cat ~/.ssh/spanish_bot_deploy.pub        # скопировать вывод
```
На GitHub: репо → Settings → Deploy keys → Add deploy key → вставить ключ,
**не** включать «Allow write access». Затем на сервере направить git на этот ключ:
```bash
cat >> ~/.ssh/config <<'EOF'
Host github.com
    IdentityFile ~/.ssh/spanish_bot_deploy
    IdentitiesOnly yes
EOF
ssh -T git@github.com    # ожидается "Hi <USER>/spanish-bot! You've successfully authenticated"
```

## 5. Клонирование и окружение (под spanishbot)
```bash
cd ~
git clone git@github.com:<USER>/spanish-bot.git
cd spanish-bot
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 6. Секреты и стартовая БД (с мака, в новом терминале)
Остановить локального бота, чтобы БД не писалась при копировании:
```bash
pkill -f "MacOS/Python bot.py"   # на маке
```
Скопировать `.env` и БД на сервер:
```bash
cd "<MAC_REPO>"
scp .env spanishbot@<DROPLET_IP>:/home/spanishbot/spanish-bot/.env
scp spanish_bot.db spanishbot@<DROPLET_IP>:/home/spanishbot/spanish-bot/spanish_bot.db
```
Файлы прилетели в домашнюю папку `spanishbot`, поэтому уже принадлежат ему —
`chown` не нужен (и под не-root упал бы). На сервере **под `spanishbot`** только
ужесточить права `.env` и прописать абсолютный путь к БД ровно одной строкой:
```bash
chmod 600 ~/spanish-bot/.env

# DB_PATH: заменить существующую строку или добавить — без дублей
# (.env.example уже содержит DB_PATH, локальный .env мог его принести)
cd ~/spanish-bot
if grep -q '^DB_PATH=' .env; then
    sed -i 's#^DB_PATH=.*#DB_PATH=/home/spanishbot/spanish-bot/spanish_bot.db#' .env
else
    echo "DB_PATH=/home/spanishbot/spanish-bot/spanish_bot.db" >> .env
fi
grep -c '^DB_PATH=' .env    # должно быть РОВНО 1
```
(Если после `scp` файлы вдруг оказались root-owned — выполнить под root
`chown spanishbot:spanishbot ~spanishbot/spanish-bot/.env ~spanishbot/spanish-bot/spanish_bot.db`.)

## 7. СВЕРКА МИГРАЦИИ (до запуска сервиса!)
```bash
# на сервере:
sqlite3 ~/spanish-bot/spanish_bot.db "SELECT COUNT(*) FROM cards;"
# на маке:
sqlite3 "<MAC_REPO>/spanish_bot.db" "SELECT COUNT(*) FROM cards;"
```
Числа ДОЛЖНЫ совпасть. Если на сервере 0 — БД не доехала/не читается; НЕ запускать
сервис (иначе init_db создаст пустую базу), разобраться с путём/правами и повторить.

## 8. systemd-сервис (на сервере, под root)
```bash
cp /home/spanishbot/spanish-bot/spanish-bot.service /etc/systemd/system/
systemctl daemon-reload
systemd-analyze verify /etc/systemd/system/spanish-bot.service   # синтаксис/пути
systemctl enable --now spanish-bot
systemctl status spanish-bot          # active (running)
journalctl -u spanish-bot -n 20       # "Start polling", без TelegramConflictError
```
⚠️ Локальный бот на маке с этого момента запускать НЕЛЬЗЯ (один поллер на токен).

## 9. Ночной бэкап (cron, под spanishbot)
```bash
crontab -e
# добавить строку (бэкап в 03:30 каждый день):
30 3 * * * /home/spanishbot/spanish-bot/scripts/backup-db.sh /home/spanishbot/spanish-bot/spanish_bot.db /home/spanishbot/backups >> /home/spanishbot/backup.log 2>&1
```
Проверить разово:
```bash
~/spanish-bot/scripts/backup-db.sh ~/spanish-bot/spanish_bot.db ~/backups
ls -1 ~/backups        # появился spanish_bot-<сегодня>.db
```

## 10. Проверка устойчивости
Ребут — под root (sudoers у `spanishbot` разрешает только restart/status сервиса,
не `reboot`):
```bash
ssh root@<DROPLET_IP> reboot
# через минуту:
ssh spanishbot@<DROPLET_IP> 'systemctl is-active spanish-bot'   # active
```
Живой тест в Telegram: `/start`, «Мой словарь» (старые слова на месте), добавить
слово, тренировка, аудио.

## Рутина обновлений
```bash
# на маке
git push
# на сервере
cd ~/spanish-bot && git pull
.venv/bin/pip install -r requirements.txt   # только если менялся requirements.txt
sudo systemctl restart spanish-bot
journalctl -u spanish-bot -n 20
```
