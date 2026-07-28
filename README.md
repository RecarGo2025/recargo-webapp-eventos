# RecarGo x Vibra — Webapp temporal de alquiler de baterías

Herramienta mínima y robusta para operar el alquiler de baterías portátiles de
RecarGo durante el festival **Vibra Perú** (2 días, ~500 usuarios, 2 estaciones,
3 operadores). FastAPI + Jinja2 + SQLite (WAL) + Tailwind precompilado.
Sin build step en runtime, sin framework de frontend.

## Cómo funciona (resumen operativo)

- El operador entra a `/admin`, elige su **estación** y crea el alquiler pidiendo
  el **documento** del usuario (DNI, pasaporte o cualquier documento — sin formato fijo).
- Al crear, la app pide a Bajie que **expulse la batería con mayor carga** de esa
  estación. **La renta se crea SIEMPRE**, aunque Bajie no responda: en ese caso
  queda marcada con ⚠ *expulsión manual* y el operador saca la batería a mano.
  Nunca se detiene la operación por la API.
- El usuario escanea el QR fijo → `vibra.recargo.pe`, busca su documento y ve un
  **contador en vivo** de tiempo y costo. Al finalizar, el operador cierra la renta
  con el documento y la pantalla del usuario muestra el **monto final** para el POS
  de Vibra (el cobro es externo, la app no procesa pagos).

## Regla de precio

`horas_cobradas = max(1, ceil((duración_min − tolerancia_min) / 60))`
`monto = horas_cobradas × tarifa_hora` (tarifa **congelada** al crear la renta).
Tolerancia y tarifa se editan en vivo desde *Configuración* (no afecta rentas ya iniciadas).

---

## Desarrollo local

```bash
cp .env.example .env          # BAJIE_MOCK="1" para trabajar sin hardware
./scripts/run-dev.sh          # http://127.0.0.1:8099
```

- Público: `http://127.0.0.1:8099/`
- Admin: `http://127.0.0.1:8099/admin` (usuarios en `ADMIN_USERS` del `.env`)

### Recompilar el CSS (solo si editas plantillas/JS)

El CSS de Tailwind está **precompilado** en `app/static/vibra.css` y se commitea.
Para regenerarlo tras cambiar clases:

```bash
# baja una vez el binario standalone a ./bin/tailwindcss (ver scripts/build_css.sh)
./scripts/build_css.sh
```

---

## Deploy en el VPS (Ubuntu) — paso a paso

> Requisitos: DNS de `vibra.recargo.pe` apuntando al VPS, nginx y certbot instalados.

### 1. Copiar el proyecto

```bash
sudo mkdir -p /opt/vibra
sudo chown "$USER":"$USER" /opt/vibra
rsync -av --exclude .venv --exclude '*.db*' --exclude backups ./ /opt/vibra/
cd /opt/vibra
```

### 2. Entorno Python

```bash
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt
```

### 3. Configurar `.env` de producción

```bash
cp .env.example .env
python3 -c "import secrets; print('SECRET_KEY='+secrets.token_hex(32))"   # pega el valor
nano .env
```

Ajusta en `.env`:
- `SECRET_KEY` (el generado arriba)
- `ADMIN_USERS` (usuarios reales de los 3 operadores)
- `BAJIE_CHARGING_BASIC_AUTH_KEY` (la key real de Bajie)
- `BAJIE_MOCK="0"`

### 4. Inicializar la base y permisos

```bash
./.venv/bin/python -c "from app import db; db.init_db()"
sudo chown -R www-data:www-data /opt/vibra
```

> Los `device_id` de las 2 estaciones se dejan **vacíos** en el seed y se cargan
> desde el panel admin → *Estaciones* el día del evento.

### 5. Servicio systemd

```bash
sudo cp deploy/vibra.service /etc/systemd/system/vibra.service
sudo systemctl daemon-reload
sudo systemctl enable --now vibra
systemctl status vibra          # debe estar active (running)
curl -s http://127.0.0.1:8000/health   # {"ok":true}
```

### 6. nginx + SSL

```bash
sudo cp deploy/nginx-vibra.conf /etc/nginx/sites-available/vibra.recargo.pe
sudo ln -s /etc/nginx/sites-available/vibra.recargo.pe /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d vibra.recargo.pe      # emite y configura el SSL
```

Verifica: `https://vibra.recargo.pe` (público) y `https://vibra.recargo.pe/admin`.

### 7. Backup horario (cron)

```bash
chmod +x scripts/backup.sh
sudo crontab -u www-data -e
# añade:
0 * * * * cd /opt/vibra && /opt/vibra/scripts/backup.sh >> /opt/vibra/backups/backup.log 2>&1
```

Los respaldos quedan en `/opt/vibra/backups/` (conserva las últimas 72 copias).

### 8. Configuración del día del evento (en el panel admin)

1. Entra a `/admin`, sección **Estaciones**: pega el `device_id` (cabinetid de Bajie) de cada una.
2. Sección **Configuración de precio**: fija tarifa por hora y tolerancia.
3. Cada operador selecciona su estación en el header.

### Reinicio / actualización

```bash
cd /opt/vibra && git pull    # o rsync de nuevo
sudo systemctl restart vibra
```

La app sobrevive reinicios del servidor (systemd `enable`). La base `vibra.db`
persiste en `/opt/vibra/`.

---

## Integración con Bajie (aislada en `app/bajie.py`)

- Base URL y auth Basic vienen del `.env`. Timeout 5 s + 1 reintento + logging.
- `GET rent/cabinet/query?deviceId=…` → lista de baterías con su carga (`vol`).
- `POST cabinet/ejectByRepair?cabinetid=…&slotNum=…` → expulsa; OK si `msg == "Successful operation"`.
- Estrategia: se expulsa el slot de **mayor carga**. Si algo falla, `bajie.py`
  reporta `ok=False` con el motivo y **el flujo de negocio continúa** (nunca lanza
  hacia arriba de forma que bloquee). Un cambio en la API solo toca este archivo.

## Estructura

```
app/
  main.py            # ensamblado FastAPI, middleware de sesión, startup
  config.py          # lee .env
  db.py              # SQLite WAL, esquema, seed, helpers de config
  pricing.py         # regla de precio con tolerancia
  timeutil.py        # tiempos en America/Lima (servidor = verdad)
  bajie.py           # cliente Bajie aislado + mock local
  auth.py            # sesión por cookie firmada
  rentals.py         # lógica de negocio (crear/finalizar/cancelar, view-model)
  routes/
    public.py        # /, /buscar, /r/{id}, /api/r/{id}
    admin.py         # /admin/*  (login, panel, acciones, config, CSV)
  templates/         # Jinja2
  static/            # vibra.css (Tailwind precompilado), app.js, favicon
deploy/              # vibra.service, nginx-vibra.conf
scripts/             # run-dev.sh, build_css.sh, backup.sh
tailwind/            # config + input.css (para recompilar el CSS)
```
