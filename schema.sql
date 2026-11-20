-- Máquinas (estaciones Bajie) que se usan en el evento.
CREATE TABLE IF NOT EXISTS stations (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre    TEXT NOT NULL,
  device_id TEXT NOT NULL UNIQUE,
  inicial   INTEGER NOT NULL DEFAULT 0  -- baterías con las que empezó la máquina
);

-- Alquileres. status: 'en_curso' | 'devuelta'
CREATE TABLE IF NOT EXISTS rentals (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  dni               TEXT NOT NULL,
  telefono          TEXT NOT NULL,
  station_id        INTEGER NOT NULL,   -- máquina donde se registró
  return_station_id INTEGER,            -- máquina donde se devolvió
  start_at          INTEGER NOT NULL,   -- epoch ms
  end_at            INTEGER,
  status            TEXT NOT NULL DEFAULT 'en_curso'
);

-- Un documento solo puede tener UN alquiler en curso.
CREATE UNIQUE INDEX IF NOT EXISTS uniq_en_curso_dni ON rentals(dni) WHERE status = 'en_curso';
CREATE INDEX IF NOT EXISTS idx_rentals_status ON rentals(status);
CREATE INDEX IF NOT EXISTS idx_rentals_station ON rentals(station_id);
CREATE INDEX IF NOT EXISTS idx_rentals_return ON rentals(return_station_id);
