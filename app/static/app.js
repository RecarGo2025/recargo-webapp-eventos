/* RecarGo x Vibra — JS mínimo. El servidor es la fuente de verdad;
   esto solo anima contadores y coordina los modales del admin. */
(function () {
  "use strict";

  // ── Regla de precio (espejo exacto del servidor) ──────────────
  function horasCobradas(durMin, tol) {
    return Math.max(1, Math.ceil((durMin - tol) / 60));
  }
  function calcMonto(durMin, tol, tarifa) {
    return horasCobradas(durMin, tol) * tarifa;
  }
  function fmtDur(seg) {
    seg = Math.max(0, Math.floor(seg));
    var h = Math.floor(seg / 3600), m = Math.floor((seg % 3600) / 60), s = seg % 60;
    var p = function (n) { return n < 10 ? "0" + n : "" + n; };
    return p(h) + ":" + p(m) + ":" + p(s);
  }

  async function postForm(url, obj) {
    var res = await fetch(url, { method: "POST", body: new URLSearchParams(obj) });
    var data = {};
    try { data = await res.json(); } catch (e) {}
    return { status: res.status, data: data };
  }

  // ── Página pública: contador en vivo + polling ────────────────
  var VibraRental = {
    init: function () {
      var root = document.getElementById("rental-root");
      if (!root || root.dataset.status !== "activa") return;
      var start = parseFloat(root.dataset.start);
      var tarifa = parseFloat(root.dataset.tarifa);
      var tol = parseFloat(root.dataset.tolerancia);
      var offset = parseFloat(root.dataset.serverNow) - Date.now() / 1000;
      var timerEl = document.getElementById("timer");
      var montoEl = document.getElementById("monto");

      function tick() {
        var now = Date.now() / 1000 + offset;
        var durSeg = Math.max(0, now - start);
        timerEl.textContent = fmtDur(durSeg);
        montoEl.textContent = calcMonto(durSeg / 60, tol, tarifa).toFixed(2);
      }
      tick();
      setInterval(tick, 1000);

      // Polling: detecta si el operador finalizó la renta.
      setInterval(async function () {
        try {
          var res = await fetch("/api/r/" + root.dataset.id, { cache: "no-store" });
          if (!res.ok) return;
          var d = await res.json();
          if (d.status !== "activa") { location.reload(); return; }
          // Re-sincroniza el reloj con el servidor para evitar deriva.
          offset = d.server_now - Date.now() / 1000;
        } catch (e) {}
      }, 60000);
    },
  };

  // ── Panel admin ───────────────────────────────────────────────
  var finalizeRentalId = null;

  function toast(msg, kind) {
    var zone = document.getElementById("toast-zone");
    if (!zone) return alert(msg);
    var el = document.createElement("div");
    var cls = kind === "error" ? "toast-err" : kind === "warn" ? "toast-warn" : "toast-ok";
    el.className = "toast " + cls;
    el.textContent = msg;
    zone.prepend(el);
  }

  function show(id) { var m = document.getElementById(id); m.classList.remove("hidden"); m.classList.add("flex"); }
  function hide(id) { var m = document.getElementById(id); m.classList.add("hidden"); m.classList.remove("flex"); }

  var refreshTimer = null;
  function scheduleRefresh() {
    if (refreshTimer) clearTimeout(refreshTimer);
    refreshTimer = setTimeout(function () {
      // No refrescar con un modal abierto (perdería lo que el operador escribe).
      var open = document.querySelector(".fixed.inset-0.flex");
      if (open) { scheduleRefresh(); return; }
      location.reload();
    }, 30000);
  }

  var VibraAdmin = {
    init: function () {
      var rootNow = document.querySelector("[data-server-now]");
      var offset = rootNow ? parseFloat(rootNow.dataset.serverNow) - Date.now() / 1000 : 0;

      function tickRows() {
        var now = Date.now() / 1000 + offset;
        document.querySelectorAll('[data-live="1"]').forEach(function (row) {
          var start = parseFloat(row.dataset.start);
          var tarifa = parseFloat(row.dataset.tarifa);
          var tol = parseFloat(row.dataset.tolerancia);
          var durSeg = Math.max(0, now - start);
          var t = row.querySelector("[data-timer]");
          var mo = row.querySelector("[data-monto]");
          if (t) t.textContent = fmtDur(durSeg);
          if (mo) mo.textContent = calcMonto(durSeg / 60, tol, tarifa).toFixed(2);
        });
      }
      tickRows();
      setInterval(tickRows, 1000);
      scheduleRefresh();
    },

    close: hide,
    open: show,

    // Crear alquiler
    openCreate: function () {
      document.getElementById("create-dni").value = "";
      var m = document.getElementById("create-msg"); m.className = "mt-3 hidden"; m.textContent = "";
      document.getElementById("create-confirm").disabled = false;
      show("modal-create");
      setTimeout(function () { document.getElementById("create-dni").focus(); }, 50);
    },
    submitCreate: async function () {
      var dni = document.getElementById("create-dni").value.trim();
      var msg = document.getElementById("create-msg");
      var btn = document.getElementById("create-confirm");
      if (!dni) { msg.className = "toast toast-err mt-3"; msg.textContent = "Ingresa el documento."; return; }
      btn.disabled = true; btn.textContent = "Expulsando…";
      var r = await postForm("/admin/rentals", { dni: dni });
      btn.textContent = "Expulsar y crear";
      if (r.data.ok) {
        var kind = r.data.eject_ok ? "ok" : "warn";
        toast(r.data.mensaje, kind);
        hide("modal-create");
        setTimeout(function () { location.reload(); }, 700);
      } else {
        btn.disabled = false;
        var text = r.data.mensaje || "No se pudo crear la renta.";
        msg.className = "toast toast-err mt-3";
        msg.textContent = text;
        if (r.data.error === "renta_activa" && r.data.rental_id) {
          msg.innerHTML = text + ' <a class="font-extrabold underline" href="/r/' + r.data.rental_id + '">ver renta</a>';
        }
      }
    },

    // Finalizar (desde modal, por documento)
    openFinalize: function () {
      finalizeRentalId = null;
      document.getElementById("finalize-dni").value = "";
      document.getElementById("finalize-dni").classList.remove("hidden");
      document.getElementById("finalize-summary").className = "mt-4 hidden";
      document.getElementById("finalize-msg").className = "mt-3 hidden";
      document.getElementById("finalize-search").classList.remove("hidden");
      document.getElementById("finalize-confirm").classList.add("hidden");
      show("modal-finalize");
      setTimeout(function () { document.getElementById("finalize-dni").focus(); }, 50);
    },
    lookupFinalize: async function () {
      var dni = document.getElementById("finalize-dni").value.trim();
      var msg = document.getElementById("finalize-msg");
      if (!dni) return;
      var res = await fetch("/admin/lookup?dni=" + encodeURIComponent(dni));
      var d = await res.json();
      if (!d.found) {
        msg.className = "toast toast-err mt-3";
        msg.textContent = "No hay renta activa para ese documento.";
        return;
      }
      msg.className = "mt-3 hidden";
      finalizeRentalId = d.rental.id;
      var sum = document.getElementById("finalize-summary");
      sum.className = "mt-4 sticker p-4";
      sum.innerHTML =
        '<p class="text-xs font-extrabold uppercase tracking-wide text-ink-mute">Documento</p>' +
        '<p class="font-display text-xl text-ink">' + d.rental.dni + "</p>" +
        '<div class="mt-3 grid grid-cols-3 gap-2 text-center text-sm">' +
        '<div><p class="text-ink-mute">Inicio</p><p class="font-extrabold">' + d.rental.start_time_str + "</p></div>" +
        '<div><p class="text-ink-mute">Duración</p><p class="font-extrabold">' + d.rental.duracion_str + "</p></div>" +
        '<div><p class="text-ink-mute">Monto</p><p class="font-display text-coral">S/ ' + d.rental.monto.toFixed(2) + "</p></div></div>";
      document.getElementById("finalize-search").classList.add("hidden");
      document.getElementById("finalize-confirm").classList.remove("hidden");
    },
    submitFinalize: async function () {
      if (!finalizeRentalId) return;
      var btn = document.getElementById("finalize-confirm");
      btn.disabled = true; btn.textContent = "Finalizando…";
      var r = await postForm("/admin/finalize", { rental_id: finalizeRentalId });
      if (r.data.ok) {
        toast("Renta finalizada. Cobrar S/ " + r.data.rental.monto.toFixed(2) + " (" + r.data.rental.dni + ").", "ok");
        hide("modal-finalize");
        setTimeout(function () { location.reload(); }, 700);
      } else {
        btn.disabled = false; btn.textContent = "Confirmar cobro";
        var msg = document.getElementById("finalize-msg");
        msg.className = "mt-3 rounded-xl bg-red-50 px-4 py-3 text-sm font-semibold text-red-700";
        msg.textContent = r.data.mensaje || "No se pudo finalizar.";
      }
    },

    // Finalizar directo desde una fila
    finalizeId: async function (id, dni) {
      if (!confirm("¿Finalizar la renta de " + dni + "?")) return;
      var r = await postForm("/admin/finalize", { rental_id: id });
      if (r.data.ok) {
        toast("Renta finalizada. Cobrar S/ " + r.data.rental.monto.toFixed(2) + " (" + dni + ").", "ok");
        setTimeout(function () { location.reload(); }, 700);
      } else {
        toast(r.data.mensaje || "No se pudo finalizar.", "error");
      }
    },

    cancel: async function (id, dni) {
      if (!confirm("¿Cancelar la renta de " + dni + "? (no genera cobro)")) return;
      var r = await postForm("/admin/rentals/" + id + "/cancel", {});
      if (r.data.ok) {
        toast("Renta cancelada.", "ok");
        setTimeout(function () { location.reload(); }, 500);
      } else {
        toast(r.data.mensaje || "No se pudo cancelar.", "error");
      }
    },

    del: async function (id, dni) {
      if (!confirm("¿ELIMINAR de forma permanente la renta de " + dni + "?\n\nSe borra de la lista y del CSV. Esto NO se puede deshacer.\nÚsalo solo si la cargaste por error.")) return;
      var r = await postForm("/admin/rentals/" + id + "/delete", {});
      if (r.data.ok) {
        toast("Renta eliminada.", "ok");
        setTimeout(function () { location.reload(); }, 500);
      } else {
        toast(r.data.mensaje || "No se pudo eliminar.", "error");
      }
    },

    quickEject: async function () {
      if (!confirm("¿Expulsar la batería con más carga de la estación seleccionada?")) return;
      var r = await postForm("/admin/eject", {});
      toast(r.data.mensaje || "Listo.", r.data.ok ? "ok" : "warn");
    },
  };

  window.VibraRental = VibraRental;
  window.VibraAdmin = VibraAdmin;
})();
