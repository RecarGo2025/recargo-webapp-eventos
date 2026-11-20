# RecarGo eventos: panel de alquiler de baterías

Panel para operadores en eventos (primero: **TOYOTA LAND**). Corre en Cloudflare
(Worker + base D1), sin servidor propio. La versión anterior en Python (festival
Vibra Perú) sigue en la rama `main`.

## Qué hace

- **Registrar alquiler** con documento (DNI, CE o pasaporte, formato libre) y
  teléfono (9 dígitos, empieza con 9). Un documento no puede tener dos alquileres en curso.
- **Expulsar batería** (botón aparte): suelta la de mayor carga de la máquina seleccionada.
- **Máquina seleccionada** en la cabecera. Cada celular o laptop recuerda la suya.
- **Alquileres**: en curso, devueltos o todos; buscar por documento o teléfono;
  **Devolver** (se registra en la máquina seleccionada) y **Eliminar** (solo en curso, para errores).
- **Inventario** por máquina: `esperadas = empezó con − salieron + volvieron`.
  Se calcula desde los alquileres, así que devolver o eliminar lo corrige solo.
  **Ver en máquina** consulta a Bajie cuántas reporta de verdad (no expulsa nada).
- **Configuración**: nombre, ID de máquina (Bajie) y con cuántas baterías empezó.
- **CSV** con todos los alquileres.
- El panel se refresca cada 30 s con la pestaña visible (cuida el límite gratis de D1: 5 M filas leídas por día).
- Todo el panel pide una clave (`PANEL_PASSWORD`). El usuario puede ser cualquiera.

No incluye cobro, página pública para el cliente ni verificación por SMS.

## Archivos

```
src/worker.js      servidor: API, clave del panel y llamadas a Bajie
public/index.html  la página del panel (HTML + JS, sin build): pantalla principal
                   (registro + expulsar + menú) y ventanas para Alquileres,
                   Inventario y Configuración
public/marca/      firma bicolor e íconos base, copiados sin cambios de la
                   biblioteca de marca (marca_recargo.zip, 01-biblioteca)
public/fonts/      Poppins 400/600/700 local + licencia OFL
schema.sql         tablas de la base
wrangler.jsonc     configuración de Cloudflare (nombre del evento en EVENTO_NOMBRE)
```

## Probar en local

```bash
npm install
printf 'PANEL_PASSWORD="prueba"\nBAJIE_MOCK="1"\n' > .dev.vars   # modo prueba: no expulsa nada real
npm run db:local
npm run dev          # http://127.0.0.1:8787  (clave: prueba)
```

## Publicar en Cloudflare (una sola vez)

```bash
npx wrangler login                                                  # cuenta donde está recargo.pe
npx wrangler d1 create recargo-eventos                              # crea la base: copia el database_id que imprime
                                                                    # en wrangler.jsonc, dentro de d1_databases
npm run db:remote                                                   # crea las tablas
npm run deploy                                                      # publica y muestra la URL
npx wrangler secret put PANEL_PASSWORD                              # clave del panel
npx wrangler secret put BAJIE_KEY                                   # clave Basic de Bajie
```

Dirección publicada: **https://eventos.recargo.pe** (dominio propio en `wrangler.jsonc`, `routes`).
Para cambiar la contraseña del panel: `npx wrangler secret put PANEL_PASSWORD` y listo, sin redeploy.

## Día del evento

1. Abrir el panel, poner la clave.
2. **Configuración de máquinas**: agregar cada máquina con su ID de Bajie y con cuántas empezó.
3. Cada operador elige su máquina arriba.
4. Probar **Ver en máquina** antes de abrir: si responde con un número, la conexión con Bajie está bien.

Para otro evento: cambiar `EVENTO_NOMBRE` en `wrangler.jsonc` y vaciar la base
(`npx wrangler d1 execute recargo-eventos --remote --command "DELETE FROM rentals; DELETE FROM stations;"`).
