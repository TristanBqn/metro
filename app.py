import json
import time
from collections import deque

import numpy as np
import plotly.graph_objects as go
import streamlit as st
from streamlit.components.v1 import html

# -------------------------------
# ⚙️ CONFIG
# -------------------------------
st.set_page_config(page_title="Gyroscope Tracker", layout="centered")
st.title("🚇 Analyse du mouvement du métro (gyroscope + accéléromètre)")
st.markdown(
    "Autorisez l’accès aux capteurs de votre téléphone pour suivre les mouvements en temps réel. "
    "Les tracés sont lissés par un filtre de Kalman et les phases de mouvement sont détectées automatiquement."
)

# -------------------------------
# 🗄️ STATE
# -------------------------------
if "is_running" not in st.session_state:
    st.session_state.is_running = False

if "positions" not in st.session_state:
    st.session_state.positions = deque(maxlen=1000)

if "velocity" not in st.session_state:
    st.session_state.velocity = [0.0, 0.0]

if "accel_data" not in st.session_state:
    st.session_state.accel_data = [0.0, 0.0, 0.0]

if "last_ts" not in st.session_state:
    st.session_state.last_ts = None

# -------------------------------
# 🎚️ CONTROLES
# -------------------------------
col1, col2, col3 = st.columns(3)
if col1.button("▶️ Start"):
    st.session_state.is_running = True
if col2.button("⏸️ Stop"):
    st.session_state.is_running = False
if col3.button("🔄 Reset"):
    st.session_state.positions.clear()
    st.session_state.velocity = [0.0, 0.0]
    st.session_state.accel_data = [0.0, 0.0, 0.0]
    st.session_state.last_ts = None
    st.session_state.is_running = False

# -------------------------------
# 🧮 KALMAN (simple)
# -------------------------------
class KalmanFilter:
    def __init__(self, process_variance=1e-3, measurement_variance=1e-2):
        self.x = 0.0
        self.P = 1.0
        self.Q = process_variance
        self.R = measurement_variance

    def update(self, measurement: float) -> float:
        # Prediction
        self.P += self.Q
        # Correction
        K = self.P / (self.P + self.R)
        self.x += K * (measurement - self.x)
        self.P *= (1.0 - K)
        return self.x

kalman_x = KalmanFilter()
kalman_y = KalmanFilter()

# -------------------------------
# 📡 CAPTEURS (JS)
# -------------------------------
html(
    """
<script>
(async () => {
  // iOS 13+ nécessite une permission explicite
  try {
    if (typeof DeviceMotionEvent !== 'undefined' && typeof DeviceMotionEvent.requestPermission === 'function') {
      try { await DeviceMotionEvent.requestPermission(); } catch(e) {}
    }
  } catch(e) {}

  // Écoute des capteurs et injection dans l'URL (?sensor=...)
  window.addEventListener('devicemotion', (e) => {
    const acc = (e.acceleration) || (e.accelerationIncludingGravity) || {};
    const payload = {
      acceleration: {
        x: (typeof acc.x === 'number') ? acc.x : 0,
        y: (typeof acc.y === 'number') ? acc.y : 0,
        z: (typeof acc.z === 'number') ? acc.z : 0
      },
      ts: Date.now()
    };
    const q = new URLSearchParams(window.location.search);
    q.set('sensor', JSON.stringify(payload));
    // Mise à jour silencieuse de l'URL pour éviter le rechargement
    history.replaceState(null, '', window.location.pathname + '?' + q.toString());
  }, true);
})();
</script>
""",
    height=0,
)

# -------------------------------
# 🔄 INGESTION
# -------------------------------
params = st.experimental_get_query_params()
sensor_raw = params.get("sensor", [None])[0]

if st.session_state.is_running and sensor_raw:
    try:
        data = json.loads(sensor_raw)
        ax = float(data.get("acceleration", {}).get("x", 0.0))
        ay = float(data.get("acceleration", {}).get("y", 0.0))
        az = float(data.get("acceleration", {}).get("z", 0.0))
        ts = float(data.get("ts", 0.0))

        # Filtrage Kalman
        ax_f = kalman_x.update(ax)
        ay_f = kalman_y.update(ay)

        # dt basé sur timestamp
        last_ts = st.session_state.last_ts
        dt = max(0.01, (ts - last_ts) / 1000.0) if last_ts else 0.05
        st.session_state.last_ts = ts

        # Intégration v et x
        vx, vy = st.session_state.velocity
        vx += ax_f * dt
        vy += ay_f * dt

        if st.session_state.positions:
            x_prev, y_prev = st.session_state.positions[-1]
        else:
            x_prev, y_prev = 0.0, 0.0

        x = x_prev + vx * dt
        y = y_prev + vy * dt

        st.session_state.velocity = [vx, vy]
        st.session_state.positions.append((x, y))
        st.session_state.accel_data = [ax_f, ay_f, az]
    except Exception as e:
        st.warning(f"Erreur de lecture capteur: {e}")

# -------------------------------
# 🚦 PHASE
# -------------------------------
ax, ay, az = st.session_state.accel_data
magnitude = float(np.sqrt(ax**2 + ay**2 + az**2))
if magnitude > 1.5:
    phase = "🟢 Accélération"
elif magnitude < 0.5:
    phase = "🔴 Freinage"
else:
    phase = "⚪ Phase stable"
st.markdown(f"Phase détectée : {phase}")

# -------------------------------
# 📈 TRACÉ
# -------------------------------
if st.session_state.positions:
    fig = go.Figure()
    x_vals = [p[0] for p in st.session_state.positions]
    y_vals = [p[1] for p in st.session_state.positions]

    fig.add_trace(
        go.Scatter(
            x=x_vals, y=y_vals, mode="lines",
            line=dict(width=3), name="Trajectoire"
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[x_vals[-1]], y=[y_vals[-1]],
            mode="markers",
            marker=dict(size=10, color="red"),
            name="Position actuelle"
        )
    )

    # Cadrage dynamique + ratio 1:1
    pad = 0.1
    if len(x_vals) >= 2:
        xmin, xmax = min(x_vals), max(x_vals)
        ymin, ymax = min(y_vals), max(y_vals)
        dx = max(1e-6, xmax - xmin)
        dy = max(1e-6, ymax - ymin)
        fig.update_xaxes(range=[xmin - pad * dx, xmax + pad * dx], title="X")
        fig.update_yaxes(range=[ymin - pad * dy, ymax + pad * dy], title="Y", scaleanchor="x", scaleratio=1)
    else:
        fig.update_xaxes(title="X")
        fig.update_yaxes(title="Y", scaleanchor="x", scaleratio=1)

    fig.update_layout(
        width=500,
        height=500,
        margin=dict(l=10, r=10, t=30, b=10),
        showlegend=False,
    )

    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Appuyez sur ▶️ Start et bougez votre téléphone pour commencer à tracer.")

# -------------------------------
# ♻️ AUTO-REFRESH LÉGER
# -------------------------------
# Pendant la capture, on force un rafraîchissement toutes les ~200 ms
if st.session_state.is_running:
    time.sleep(0.2)
    st.experimental_rerun()
