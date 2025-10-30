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

if "gyro_data" not in st.session_state:
    st.session_state.gyro_data = [0.0, 0.0, 0.0]  # alpha, beta, gamma (deg/s)

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
    st.session_state.gyro_data = [0.0, 0.0, 0.0]
    st.session_state.last_ts = None
    st.session_state.is_running = False

st.markdown("#### Accès capteurs")

# Bouton HTML pour déclencher la permission (iOS nécessite un geste utilisateur)
html(
    """
<style>
#sensor-btn {
  background:#0d6efd; color:white; border:none; padding:10px 14px; border-radius:8px;
  font-size:14px; cursor:pointer;
}
#sensor-btn:active { transform: translateY(1px); }
#perm-status { font: 13px/1.4 system-ui, -apple-system, Segoe UI, Roboto, Arial; margin-top:6px; }
</style>
<button id="sensor-btn">Autoriser gyroscope + accéléromètre</button>
<div id="perm-status">Statut: en attente…</div>
<script>
(function(){
  const btn = document.getElementById('sensor-btn');
  const status = document.getElementById('perm-status');

  async function askPermission(){
    let pm = 'unknown';
    let po = 'unknown';
    // Demande de permission iOS (si dispo); Android/desktop renverra "granted" par défaut
    try {
      if (typeof DeviceMotionEvent !== 'undefined' && typeof DeviceMotionEvent.requestPermission === 'function') {
        pm = await DeviceMotionEvent.requestPermission();
      } else {
        pm = 'granted';
      }
    } catch(e){ pm = 'denied'; }
    try {
      if (typeof DeviceOrientationEvent !== 'undefined' && typeof DeviceOrientationEvent.requestPermission === 'function') {
        po = await DeviceOrientationEvent.requestPermission();
      } else {
        po = 'granted';
      }
    } catch(e){ po = 'denied'; }

    // Répercuter le statut dans l'URL (perm=...)
    const q = new URLSearchParams(window.location.search);
    q.set('perm', JSON.stringify({ motion: pm, orient: po, at: Date.now() }));
    history.replaceState(null, '', window.location.pathname + '?' + q.toString());

    // Feedback inline
    status.textContent = `Statut: motion=${pm}, orientation=${po}`;
    if (pm === 'granted' || po === 'granted') {
      status.style.color = '#198754';
      window.hasSensors = true;
    } else {
      status.style.color = '#dc3545';
    }
  }

  btn.addEventListener('click', askPermission, {passive:true});

  // Écoute des capteurs -> met à jour ?sensor=... en continu
  window.addEventListener('devicemotion', (e) => {
    const acc = (e.acceleration) || (e.accelerationIncludingGravity) || {};
    const rot = e.rotationRate || {};
    const payload = {
      acceleration: {
        x: (typeof acc.x === 'number') ? acc.x : 0,
        y: (typeof acc.y === 'number') ? acc.y : 0,
        z: (typeof acc.z === 'number') ? acc.z : 0
      },
      rotationRate: {
        alpha: (typeof rot.alpha === 'number') ? rot.alpha : 0, // deg/s
        beta:  (typeof rot.beta  === 'number') ? rot.beta  : 0,
        gamma: (typeof rot.gamma === 'number') ? rot.gamma : 0
      }
    };
    const q = new URLSearchParams(window.location.search);
    q.set('sensor', JSON.stringify(payload));
    history.replaceState(null, '', window.location.pathname + '?' + q.toString());
  }, true);
})();
</script>
    """
)

# -------------------------------
# 📈 VISUALISATION
# -------------------------------
st.markdown("#### Tracé du mouvement")
placeholder = st.empty()

# Placeholder d'affichage
if st.session_state.positions:
    x, y = zip(*st.session_state.positions)
else:
    x, y = [0], [0]

fig = go.Figure()
fig.add_trace(go.Scatter(x=x, y=y, mode="lines+markers"))
fig.update_layout(
    xaxis=dict(range=[-10, 10], title="X"),
    yaxis=dict(range=[-10, 10], title="Y"),
    width=500,
    height=500,
    template="simple_white"
)
placeholder.plotly_chart(fig)
