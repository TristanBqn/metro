import streamlit as st
import plotly.graph_objects as go
from streamlit.components.v1 import html
from collections import deque
import numpy as np
import json

st.set_page_config(page_title="Gyroscope Tracker", layout="centered")

st.title("🚇 Analyse du mouvement du métro (gyroscope + accéléromètre)")
st.markdown("Autorisez l’accès aux capteurs de votre téléphone pour suivre les mouvements en temps réel. "
            "Les tracés sont lissés par un **filtre de Kalman** et les phases de mouvement sont détectées automatiquement.")

# --------------------------------------------------
# 🎛️ CONTROLES UTILISATEUR
# --------------------------------------------------
if "is_running" not in st.session_state:
    st.session_state.is_running = False
if "positions" not in st.session_state:
    st.session_state.positions = deque(maxlen=500)
if "velocity" not in st.session_state:
    st.session_state.velocity = [0, 0]
if "accel_data" not in st.session_state:
    st.session_state.accel_data = [0, 0, 0]

col1, col2, col3 = st.columns(3)
if col1.button("▶️ Start"):
    st.session_state.is_running = True
if col2.button("⏸️ Stop"):
    st.session_state.is_running = False
if col3.button("🔄 Reset"):
    st.session_state.positions.clear()
    st.session_state.velocity = [0, 0]
    st.session_state.accel_data = [0, 0, 0]
    st.session_state.is_running = False

# --------------------------------------------------
# 🧮 FILTRE DE KALMAN (simplifié)
# --------------------------------------------------
class KalmanFilter:
    def __init__(self, process_variance=1e-3, measurement_variance=1e-2):
        self.x = 0.0  # estimate
        self.P = 1.0  # covariance
        self.Q = process_variance
        self.R = measurement_variance

    def update(self, measurement):
        # Prediction step
        self.P += self.Q
        # Correction
        K = self.P / (self.P + self.R)
        self.x += K * (measurement - self.x)
        self.P *= (1 - K)
        return self.x

kalman_x = KalmanFilter()
kalman_y = KalmanFilter()

# --------------------------------------------------
# 📡 FRONTEND : CAPTEURS JS
# --------------------------------------------------
html("""
<script>
let lastSent = 0;

async function requestPermission() {
    if (typeof DeviceMotionEvent.requestPermission === 'function') {
        try {
            const response = await DeviceMotionEvent.requestPermission();
            if (response !== 'granted') {
                alert("Permission refusée. Veuillez autoriser l'accès aux capteurs.");
                return;
            }
        } catch (err) {
            alert("Erreur: " + err);
        }
    }
}

requestPermission();

window.addEventListener('devicemotion', (event) => {
    const now = Date.now();
    if (now - lastSent > 100) { // 10 Hz
        const acc = event.accelerationIncludingGravity;
        const rot = event.rotationRate;
        const payload = {
            acceleration: {
                x: acc?.x || 0,
                y: acc?.y || 0,
                z: acc?.z || 0
            },
            rotation: {
                alpha: rot?.alpha || 0,
                beta: rot?.beta || 0,
                gamma: rot?.gamma || 0
            }
        };
        window.location.hash = encodeURIComponent(JSON.stringify(payload));
        lastSent = now;
    }
});
</script>
""", height=0)

# --------------------------------------------------
# 🔄 TRAITEMENT DES DONNÉES
# --------------------------------------------------
gyro_raw = st.experimental_get_query_params().get("", [None])[0]

if st.session_state.is_running and gyro_raw:
    try:
        d = json.loads(gyro_raw)
        ax = d["acceleration"]["x"]
        ay = d["acceleration"]["y"]
        az = d["acceleration"]["z"]

        # Filtrage Kalman
        ax_f = kalman_x.update(ax)
        ay_f = kalman_y.update(ay)

        # Mise à jour vitesse et position
        vx, vy = st.session_state.velocity
        vx += ax_f * 0.05
        vy += ay_f * 0.05
        x = (st.session_state.positions[-1][0] if st.session_state.positions else 0) + vx * 0.05
        y = (st.session_state.positions[-1][1] if st.session_state.positions else 0) + vy * 0.05

        st.session_state.positions.append((x, y))
        st.session_state.velocity = [vx, vy]
        st.session_state.accel_data = [ax_f, ay_f, az]

    except Exception as e:
        st.write("Erreur de lecture :", e)

# --------------------------------------------------
# 🚦 DÉTECTION ACCÉLÉRATION / FREINAGE
# --------------------------------------------------
ax, ay, az = st.session_state.accel_data
magnitude = np.sqrt(ax**2 + ay**2 + az**2)
if magnitude > 1.5:
    phase = "🟢 Accélération"
elif magnitude < 0.5:
    phase = "🔴 Freinage"
else:
    phase = "⚪ Phase stable"

st.markdown(f"**Phase détectée :** {phase}")

# --------------------------------------------------
# 📈 VISUALISATION DU TRACÉ
# --------------------------------------------------
if st.session_state.positions:
    fig = go.Figure()
    x_vals = [p[0] for p in st.session_state.positions]
    y_vals = [p[1] for p in st.session_state.positions]

    fig.add_trace(go.Scatter(
        x=x_vals, y=y_vals, mode="lines", line=dict(width=3),
        name="Trajectoire"
    ))
    fig.add_trace(go.Scatter(
        x=[x_vals[-1]], y=[y_vals[-1]],
        mode="markers", marker=dict(size=10, color="red"),
        name="Position actuelle"
    ))

    fig.update_layout(
        xaxis=dict(range=[-10, 10], zeroline=True, title="X"),
        yaxis=dict(range=[-10, 10], zeroline=True, title="Y"),
        width=500, height=500,
        margin=dict(l=10, r=10, t=30, b=10),
        showlegend=False
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Appuyez sur ▶️ *Start* et bougez votre téléphone pour commencer à tracer.")
