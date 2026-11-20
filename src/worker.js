// RecarGo eventos: panel de alquiler de baterías (Cloudflare Worker + D1).
// Todo el servidor está en este archivo. La página está en public/index.html.

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // Enlace con llave: /?llave=XXXX guarda la llave en una cookie del celular y
    // limpia la dirección. Después no se vuelve a pedir nada en ese celular.
    const llaveUrl = url.searchParams.get("llave");
    if (llaveUrl !== null) {
      if (!llaveValida(llaveUrl, env)) return sinAcceso();
      url.searchParams.delete("llave");
      return new Response(null, {
        status: 302,
        headers: {
          Location: url.pathname + url.search,
          "Set-Cookie": `${COOKIE}=${encodeURIComponent(llaveUrl)}; Path=/; Max-Age=${60 * 24 * 3600}; HttpOnly; Secure; SameSite=Lax`,
        },
      });
    }
    if (!llaveValida(leerCookie(request, COOKIE), env)) return sinAcceso();

    if (!url.pathname.startsWith("/api/")) return env.ASSETS.fetch(request);

    try {
      return await api(request, env, url);
    } catch (err) {
      console.error(err);
      return json({ error: "Error del servidor: " + err.message }, 500);
    }
  },
};

// ── Acceso: llave secreta PANEL_LLAVE (va en el enlace y luego en una cookie) ──
const COOKIE = "rg_llave";

function llaveValida(llave, env) {
  if (!env.PANEL_LLAVE || !llave) return false;
  const a = new TextEncoder().encode(llave);
  const b = new TextEncoder().encode(env.PANEL_LLAVE);
  return a.byteLength === b.byteLength && crypto.subtle.timingSafeEqual(a, b);
}

function leerCookie(request, nombre) {
  for (const parte of (request.headers.get("Cookie") || "").split(";")) {
    const [k, ...v] = parte.trim().split("=");
    if (k === nombre) {
      try {
        return decodeURIComponent(v.join("="));
      } catch {
        return "";
      }
    }
  }
  return "";
}

function sinAcceso() {
  const html = `<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>RecarGo eventos</title><body style="margin:0;min-height:100vh;display:grid;place-items:center;background:#FFFAF4;color:#03359B;font-family:system-ui,sans-serif;text-align:center;padding:24px">
<div><h1 style="font-size:22px">Acceso restringido</h1><p>Abre el enlace del panel que te compartió RecarGo.</p></div></body></html>`;
  return new Response(html, { status: 401, headers: { "Content-Type": "text/html; charset=utf-8" } });
}

// ── API ──────────────────────────────────────────────────────────
async function api(request, env, url) {
  const db = env.DB;
  const m = request.method;
  const p = url.pathname;
  let id;

  // Estado completo: máquinas con inventario + alquileres filtrados.
  if (m === "GET" && p === "/api/estado") {
    const estado = url.searchParams.get("estado") || "en_curso";
    const q = (url.searchParams.get("q") || "").trim().toUpperCase();
    const enCurso = await db.prepare("SELECT COUNT(*) AS n FROM rentals WHERE status = 'en_curso'").first();
    return json({
      evento: env.EVENTO_NOMBRE || "Evento",
      en_curso: enCurso.n,
      maquinas: await maquinasConInventario(db),
      alquileres: await listarAlquileres(db, estado, q),
    });
  }

  // Registrar alquiler (no expulsa: la expulsión es un botón aparte).
  if (m === "POST" && p === "/api/alquileres") {
    const body = await request.json();
    const dni = String(body.dni || "").trim().toUpperCase();
    const telefono = normalizarTelefono(body.telefono);
    const stationId = Number(body.station_id);
    if (!dni) return json({ error: "Falta el documento." }, 400);
    if (!telefono) return json({ error: "Teléfono inválido: deben ser 9 dígitos y empezar con 9." }, 400);
    if (!(await maquina(db, stationId))) return json({ error: "Selecciona una máquina." }, 400);

    const previo = await db
      .prepare("SELECT id FROM rentals WHERE dni = ? AND status = 'en_curso'")
      .bind(dni)
      .first();
    if (previo) return json({ error: `El documento ${dni} ya tiene un alquiler en curso.` }, 409);

    try {
      const r = await db
        .prepare("INSERT INTO rentals (dni, telefono, station_id, start_at) VALUES (?, ?, ?, ?)")
        .bind(dni, telefono, stationId, Date.now())
        .run();
      return json({ ok: true, id: r.meta.last_row_id });
    } catch (err) {
      if (String(err.message).includes("UNIQUE")) {
        return json({ error: `El documento ${dni} ya tiene un alquiler en curso.` }, 409);
      }
      throw err;
    }
  }

  // Devolver: se registra en la máquina seleccionada en ese momento.
  if (m === "POST" && (id = match(p, /^\/api\/alquileres\/(\d+)\/devolver$/))) {
    const body = await request.json();
    const stationId = Number(body.station_id);
    if (!(await maquina(db, stationId))) return json({ error: "Selecciona una máquina." }, 400);
    const r = await db
      .prepare(
        "UPDATE rentals SET status = 'devuelta', end_at = ?, return_station_id = ? " +
          "WHERE id = ? AND status = 'en_curso'"
      )
      .bind(Date.now(), stationId, id)
      .run();
    if (!r.meta.changes) return json({ error: "Ese alquiler ya no está en curso." }, 409);
    return json({ ok: true });
  }

  // Eliminar (alquiler en curso cargado por error). Irreversible.
  // Solo en curso: borrar uno ya devuelto descuadraría el inventario.
  if (m === "DELETE" && (id = match(p, /^\/api\/alquileres\/(\d+)$/))) {
    const r = await db.prepare("DELETE FROM rentals WHERE id = ? AND status = 'en_curso'").bind(id).run();
    if (!r.meta.changes) return json({ error: "Solo se pueden eliminar alquileres en curso." }, 409);
    return json({ ok: true });
  }

  // Expulsar la batería con más carga de la máquina seleccionada.
  if (m === "POST" && p === "/api/expulsar") {
    const body = await request.json();
    const st = await maquina(db, Number(body.station_id));
    if (!st) return json({ error: "Selecciona una máquina." }, 400);
    return json(await expulsarMayorCarga(env, st.device_id));
  }

  // Solo lectura: cuántas baterías reporta la máquina (no expulsa nada).
  if (m === "GET" && (id = match(p, /^\/api\/maquinas\/(\d+)\/consulta$/))) {
    const st = await maquina(db, id);
    if (!st) return json({ error: "Máquina no encontrada." }, 404);
    const c = await consultarBaterias(env, st.device_id);
    return json(c.error ? { ok: false, msg: c.error } : { ok: true, n: c.baterias.length });
  }

  // Configuración de máquinas.
  if (m === "POST" && p === "/api/maquinas") {
    const d = datosMaquina(await request.json());
    if (d.error) return json(d, 400);
    try {
      await db
        .prepare("INSERT INTO stations (nombre, device_id, inicial) VALUES (?, ?, ?)")
        .bind(d.nombre, d.device_id, d.inicial)
        .run();
    } catch (err) {
      if (String(err.message).includes("UNIQUE")) return json({ error: "Ese ID de máquina ya está agregado." }, 409);
      throw err;
    }
    return json({ ok: true });
  }

  if (m === "PUT" && (id = match(p, /^\/api\/maquinas\/(\d+)$/))) {
    const d = datosMaquina(await request.json());
    if (d.error) return json(d, 400);
    try {
      await db
        .prepare("UPDATE stations SET nombre = ?, device_id = ?, inicial = ? WHERE id = ?")
        .bind(d.nombre, d.device_id, d.inicial, id)
        .run();
    } catch (err) {
      if (String(err.message).includes("UNIQUE")) return json({ error: "Ese ID de máquina ya está agregado." }, 409);
      throw err;
    }
    return json({ ok: true });
  }

  if (m === "DELETE" && (id = match(p, /^\/api\/maquinas\/(\d+)$/))) {
    const usado = await db
      .prepare("SELECT COUNT(*) AS n FROM rentals WHERE station_id = ?1 OR return_station_id = ?1")
      .bind(id)
      .first();
    if (usado.n > 0) return json({ error: "Esta máquina tiene alquileres registrados; no se puede quitar." }, 409);
    await db.prepare("DELETE FROM stations WHERE id = ?").bind(id).run();
    return json({ ok: true });
  }

  // Exportar todo a CSV (abre en Excel).
  if (m === "GET" && p === "/api/export.csv") {
    const filas = await listarAlquileres(db, "todos", "", null); // sin límite
    const cab = ["id", "documento", "telefono", "maquina", "maquina_devolucion", "estado", "inicio", "fin"];
    const lineas = [cab.join(",")].concat(
      filas.map((r) =>
        [r.id, r.dni, r.telefono, r.maquina, r.maquina_devolucion || "", r.status, fechaLima(r.start_at), fechaLima(r.end_at)]
          .map(celdaCsv)
          .join(",")
      )
    );
    return new Response("﻿" + lineas.join("\r\n"), {
      headers: {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": 'attachment; filename="alquileres.csv"',
      },
    });
  }

  return json({ error: "No encontrado" }, 404);
}

// ── Consultas ────────────────────────────────────────────────────
// Inventario calculado desde los alquileres (nunca un contador guardado):
// esperadas = inicial − salieron de aquí + volvieron aquí.
// Una sola pasada por tabla (D1 gratis cobra cada fila recorrida: 5 M/día).
async function maquinasConInventario(db) {
  const [st, sal, vol] = await db.batch([
    db.prepare("SELECT * FROM stations ORDER BY id"),
    db.prepare("SELECT station_id AS id, COUNT(*) AS n FROM rentals GROUP BY station_id"),
    db.prepare(
      "SELECT return_station_id AS id, COUNT(*) AS n FROM rentals WHERE status = 'devuelta' GROUP BY return_station_id"
    ),
  ]);
  const cuenta = (res) => Object.fromEntries(res.results.map((r) => [r.id, r.n]));
  const salieron = cuenta(sal);
  const volvieron = cuenta(vol);
  return st.results.map((s) => {
    const out = salieron[s.id] || 0;
    const back = volvieron[s.id] || 0;
    return { ...s, salieron: out, volvieron: back, esperadas: s.inicial - out + back };
  });
}

async function listarAlquileres(db, estado, q, limite = 1000) {
  let sql = `SELECT r.*, s.nombre AS maquina, s2.nombre AS maquina_devolucion
             FROM rentals r
             LEFT JOIN stations s ON s.id = r.station_id
             LEFT JOIN stations s2 ON s2.id = r.return_station_id
             WHERE 1 = 1`;
  const args = [];
  if (estado === "en_curso" || estado === "devuelta") {
    sql += " AND r.status = ?";
    args.push(estado);
  }
  if (q) {
    sql += " AND (r.dni LIKE ? OR r.telefono LIKE ?)";
    args.push(`%${q}%`, `%${q}%`);
  }
  sql += " ORDER BY r.start_at DESC";
  if (limite) sql += ` LIMIT ${Number(limite)}`;
  const { results } = await db.prepare(sql).bind(...args).all();
  return results;
}

function maquina(db, id) {
  if (!id) return null;
  return db.prepare("SELECT * FROM stations WHERE id = ?").bind(id).first();
}

// ── Bajie (API de las máquinas) ─────────────────────────────────
async function bajie(env, method, path, params) {
  const url = new URL(`${env.BAJIE_BASE_URL}/${path}`);
  for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v);
  const res = await fetch(url, {
    method,
    headers: { Authorization: `Basic ${env.BAJIE_KEY}` },
    signal: AbortSignal.timeout(8000),
  });
  return res.json();
}

// Baterías dentro de la máquina, de mayor a menor carga: [{ slotNum, vol }].
// Devuelve { baterias } o { error }. Usa dos endpoints de lectura de Bajie:
//   1) rent/cabinet/query                      (el de la app principal)
//   2) cabinet/batteryListByCabinetId/{id}     (respaldo: el de la app de conciertos 2025)
async function consultarBaterias(env, deviceId) {
  if (env.BAJIE_MOCK === "1") return { baterias: [{ slotNum: 1, vol: 95 }, { slotNum: 2, vol: 80 }] };
  if (!env.BAJIE_KEY) return { error: "Falta configurar la clave de Bajie (BAJIE_KEY)." };

  let error1;
  try {
    const r = await bajie(env, "GET", "rent/cabinet/query", { deviceId });
    // Igual que la app principal: respuesta válida = trae `data`; si no, es error (ej. 401).
    if (r?.data) return ordenar((r.data.batteries || []).map((b) => ({ slotNum: b.slotNum, vol: b.vol })));
    error1 = `Bajie: ${r?.msg || "respuesta sin datos"}`;
  } catch (err) {
    error1 = "La máquina no respondió: " + err.message;
  }

  try {
    const r = await bajie(env, "GET", `cabinet/batteryListByCabinetId/${encodeURIComponent(deviceId)}`, {});
    if (Array.isArray(r?.data)) {
      return ordenar(r.data.map((b) => ({ slotNum: b.pKakou ?? b.pkakou, vol: b.pDianliang ?? b.pdianliang ?? 0 })));
    }
  } catch {
    // si el respaldo también falla, se informa el error del endpoint principal
  }
  return { error: error1 };
}

function ordenar(baterias) {
  baterias.sort((a, b) => Number(b.vol || 0) - Number(a.vol || 0));
  return { baterias };
}

async function expulsarMayorCarga(env, deviceId) {
  if (env.BAJIE_MOCK === "1") {
    return { ok: true, msg: "Expulsada (modo prueba, no se movió nada)", slot: 1, carga: 95 };
  }
  const c = await consultarBaterias(env, deviceId);
  if (c.error) return { ok: false, msg: c.error };
  if (!c.baterias.length) return { ok: false, msg: "La máquina no reporta baterías." };
  const top = c.baterias[0];

  // Sin reintento automático: si se cortó la respuesta, la batería pudo salir igual.
  try {
    const r = await bajie(env, "POST", "cabinet/ejectByRepair", { cabinetid: deviceId, slotNum: top.slotNum });
    const ok = r?.msg === "Successful operation";
    return { ok, msg: ok ? "Batería expulsada" : `Bajie: ${r?.msg || "respuesta inesperada"}`, slot: top.slotNum, carga: top.vol };
  } catch (err) {
    return { ok: false, msg: "Sin respuesta al expulsar; revisa la máquina antes de reintentar. " + err.message };
  }
}

// ── Utilidades ───────────────────────────────────────────────────
function normalizarTelefono(raw) {
  let t = String(raw || "").replace(/\D/g, "");
  if (t.length === 11 && t.startsWith("51")) t = t.slice(2);
  return /^9\d{8}$/.test(t) ? t : null;
}

function datosMaquina(b) {
  const nombre = String(b.nombre || "").trim();
  const device_id = String(b.device_id || "").trim();
  const inicial = Number(b.inicial);
  if (!nombre || !device_id) return { error: "Pon nombre e ID de la máquina." };
  if (!Number.isInteger(inicial) || inicial < 0) return { error: "Las baterías iniciales deben ser un número entero." };
  return { nombre, device_id, inicial };
}

function match(path, re) {
  const m = path.match(re);
  return m ? Number(m[1]) : null;
}

function json(data, status = 200) {
  return Response.json(data, { status });
}

function fechaLima(ms) {
  if (!ms) return "";
  return new Intl.DateTimeFormat("sv-SE", {
    timeZone: "America/Lima",
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(ms));
}

function celdaCsv(v) {
  let s = String(v ?? "");
  if (/^[=+\-@]/.test(s)) s = "'" + s; // evita fórmulas al abrir en Excel
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}
