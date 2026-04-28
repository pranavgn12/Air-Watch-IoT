from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
import json
import os
import threading
import time
import random
from google import genai

data_store = {
    "temp": 0,
    "hum": 0,
    "mq135": 0,
    "dust": 0,
}

min_temp = max_temp = None
min_hum = max_hum = None
min_mq = max_mq = None
min_dust = max_dust = None

# Global variable to store the latest LLM conclusion
llm_conclusion = "Initializing AI analysis..."

def fmt_number(v):
    if v is None:
        return "--"
    try:
        n = float(v)
        return str(int(n)) if n.is_integer() else f"{n:.1f}"
    except Exception:
        return "--"

def llm_worker_thread():
    """Background thread to fetch LLM updates every 5 seconds."""
    global llm_conclusion
    try:
        client = genai.Client()
    except Exception as e:
        llm_conclusion = f"AI API Error: {e}. Check GEMINI_API_KEY."
        return

    while True:
        time.sleep(5)
        
        # Grab current formatted data
        t = fmt_number(data_store['temp'])
        h = fmt_number(data_store['hum'])
        mq = fmt_number(data_store['mq135'])
        d = fmt_number(data_store['dust'])
        
        # Build prompt with min/max context and a random seed
        prompt = (
            f"You are an environmental AI system analyzing raw sensor data. "
            f"Current Temp: {t}C (Min: {fmt_number(min_temp)}, Max: {fmt_number(max_temp)}). "
            f"Humidity: {h}% (Min: {fmt_number(min_hum)}, Max: {fmt_number(max_hum)}). "
            f"Air Quality Score: {mq} (Min: {fmt_number(min_mq)}, Max: {fmt_number(max_mq)}). "
            f"Dust Density: {d} µg/m³ (Min: {fmt_number(min_dust)}, Max: {fmt_number(max_dust)}). "
            f"Write a 1 or 2 sentence interesting & humorous conclusion about the current environment and keep it simple, dont use nsfw words like sauna, peel etc and short. "
            f"Be concise, engaging, and do not use markdown formatting. "
            f"Random Seed for variety: {random.randint(1, 100000)}"
        )
        
        try:
            response = client.models.generate_content(
                model="gemma-4-26b-a4b-it", 
                contents=prompt
            )
            if response.text:
                # Clean up any residual markdown the model might output
                llm_conclusion = response.text.replace('*', '').strip()
        except Exception as e:
            print(f"LLM update failed: {e}")

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        global data_store, min_temp, max_temp, min_hum, max_hum, min_mq, max_mq, min_dust, max_dust, llm_conclusion

        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/update":
            for key in ("temp", "hum", "mq135", "gas", "dust"):
                if key in query:
                    try:
                        value = float(query[key][0])
                        if key == "gas":
                            data_store["mq135"] = value
                        else:
                            data_store[key] = value
                    except ValueError:
                        pass

            t = data_store["temp"]
            h = data_store["hum"]
            m = data_store["mq135"]
            d = data_store["dust"]

            if min_temp is None or t < min_temp:
                min_temp = t
            if max_temp is None or t > max_temp:
                max_temp = t

            if min_hum is None or h < min_hum:
                min_hum = h
            if max_hum is None or h > max_hum:
                max_hum = h

            if min_mq is None or m < min_mq:
                min_mq = m
            if max_mq is None or m > max_mq:
                max_mq = m

            if min_dust is None or d < min_dust:
                min_dust = d
            if max_dust is None or d > max_dust:
                max_dust = d

            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"OK")
            return

        if path == "/data":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            out = {
                "temp": data_store["temp"],
                "hum": data_store["hum"],
                "mq135": data_store["mq135"],
                "dust": data_store["dust"],
                "min_t": min_temp,
                "max_t": max_temp,
                "min_h": min_hum,
                "max_h": max_hum,
                "min_mq": min_mq,
                "max_mq": max_mq,
                "min_dust": min_dust,
                "max_dust": max_dust,
                "llm_conclusion": llm_conclusion,
            }
            self.wfile.write(json.dumps(out).encode("utf-8"))
            return

        if path == "/background.jpg":
            file_path = "background.jpg"
            if not os.path.exists(file_path):
                self.send_response(404)
                self.end_headers()
                return
            try:
                with open(file_path, "rb") as f:
                    self.send_response(200)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Cache-Control", "public, max-age=86400")
                    self.end_headers()
                    self.wfile.write(f.read())
            except Exception:
                self.send_response(500)
                self.end_headers()
            return

        if path == "/bg.mp4":
            file_path = "bg.mp4"
            if not os.path.exists(file_path):
                self.send_response(404)
                self.end_headers()
                return

            file_size = os.path.getsize(file_path)
            range_header = self.headers.get("Range")

            start = 0
            end = file_size - 1

            if range_header:
                try:
                    bytes_range = range_header.replace("bytes=", "").split("-")
                    start = int(bytes_range[0]) if bytes_range[0] else 0
                    if len(bytes_range) > 1 and bytes_range[1]:
                        end = int(bytes_range[1])
                except Exception:
                    start = 0
                    end = file_size - 1

            if start < 0:
                start = 0
            if end >= file_size:
                end = file_size - 1

            length = end - start + 1

            try:
                with open(file_path, "rb") as f:
                    f.seek(start)
                    chunk = f.read(length)

                if range_header:
                    self.send_response(206)
                    self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                else:
                    self.send_response(200)

                self.send_header("Content-Type", "video/mp4")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(len(chunk)))
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                self.wfile.write(chunk)
            except Exception:
                self.send_response(500)
                self.end_headers()
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

        html = r"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@500;600;700;800;900&display=swap" rel="stylesheet">
  <title>Air Watch</title>
   <link rel="icon" type="image/x-icon" href="http://10.28.229.167:8000/favicon.svg">
  <style>
    :root{
      --text: #043454;
      --muted: rgba(4, 52, 84, 0.85);
      --navy: #023047;
      --blue: #8ecae6;
      --blue2: #219ebc;
      --amber: #ffb703;
      --orange: #fb8500;
    }

    * { box-sizing: border-box; }

    html, body {
      margin: 0;
      min-height: 100%;
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
    }

    body {
      overflow-y: auto;
      overflow-x: hidden;
      # background: url("/background.jpg") no-repeat center center fixed;
      # background-size: cover;
    }

    video.bg {
      position: fixed;
      inset: 0;
      width: 100%;
      height: 100%;
      object-fit: cover;
      z-index: -1;
      pointer-events: none;
    }

    .page {
      max-width: 1280px;
      margin: 0 auto;
      padding: clamp(12px, 2vw, 20px);
      display: grid;
      gap: 14px;
    }

    .topbar {
      display: flex;
      text-align: center;
      justify-content: center;
      align-items: flex-start;
      gap: 12px;
      flex-wrap: wrap;
    }

    .title-wrap h1 {
      margin: 0;
      font-size: clamp(28px, 4vw, 42px);
      line-height: 0.98;
      letter-spacing: -0.05em;
      -webkit-text-stroke: 1.5px black;
      font-weight: 900;
      color: #ffffff;
      text-shadow: 2px 2px 5px rgba(0, 0, 0, 0.3);
      font-family: 'Poppins', sans-serif;
    }

    .title-wrap p {
          margin: 6px 0 0;
    color: rgb(255 255 255);
    font-size: 18px;
    text-shadow: 0px 0px 5px rgb(0 0 0);
    font-family: 'Poppins', sans-serif;
    font-weight: 600;
    }

    /* LIQUID GLASS: Status Chip */
    .live-chip {
      margin-top: 10px;
      display: inline-flex;
      align-items: center;
      gap: 7px;
      padding: 7px 11px;
      border-radius: 999px;
      background: linear-gradient(135deg, rgba(255, 255, 255, 0.5) 0%, rgba(255, 255, 255, 0.2) 100%);
      border: 1px solid rgba(255, 255, 255, 0.6);
      border-bottom: 1px solid rgba(255, 255, 255, 0.2);
      border-right: 1px solid rgba(255, 255, 255, 0.2);
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1), inset 0 1px 1px rgba(255, 255, 255, 0.8);
      backdrop-filter: blur(12px) saturate(140%);
      -webkit-backdrop-filter: blur(12px) saturate(140%);
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
      text-shadow: 0 1px 2px rgba(255, 255, 255, 0.8);
    }

    .dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #ff5151;
      flex: 0 0 auto;
      box-shadow: 0 0 8px #ff5151;
    }

    .layout {
      display: grid;
      grid-template-columns: minmax(0, 1.6fr) minmax(290px, 0.92fr);
      gap: 14px;
      align-items: start;
    }

    /* LIQUID GLASS: Main Outer Containers */
    .main-card,
    .side-card {
      background: linear-gradient(135deg, rgba(255, 255, 255, 0.25) 0%, rgba(255, 255, 255, 0.05) 100%);
      border: 1px solid rgba(255, 255, 255, 0.5);
      border-right: 1px solid rgba(255, 255, 255, 0.15);
      border-bottom: 1px solid rgba(255, 255, 255, 0.15);
      border-radius: 24px;
      box-shadow: 0 16px 40px rgba(0, 0, 0, 0.15), inset 0 1px 0 rgba(255, 255, 255, 0.4);
      backdrop-filter: blur(15px) saturate(160%);
      -webkit-backdrop-filter: blur(22px) saturate(160%);
      overflow: clip;
    }

    .main-card {
      padding: 16px;
      min-width: 0;
    }

    .side-card {
      padding: 16px;
      position: sticky;
      top: 14px;
    }

    .gauges {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
      align-items: stretch;
    }

    /* LIQUID GLASS: Inner Gauge Cards */
    .gauge-card {
      background: linear-gradient(135deg, rgba(255, 255, 255, 0.45) 0%, rgba(255, 255, 255, 0.15) 100%);
      border: 1px solid rgba(255, 255, 255, 0.6);
      border-right: 1px solid rgba(255, 255, 255, 0.2);
      border-bottom: 1px solid rgba(255, 255, 255, 0.2);
      border-radius: 20px;
      padding: 14px 14px 12px;
      min-width: 0;
      display: flex;
      flex-direction: column;
      gap: 10px;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1), inset 0 1px 1px rgba(255, 255, 255, 0.7);
      backdrop-filter: blur(16px) saturate(130%);
      -webkit-backdrop-filter: blur(16px) saturate(130%);
    }

    .gauge-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
    }

    .gauge-title {
      margin: 0;
      font-size: 17px;
      font-weight: 900;
      color: var(--navy);
      text-shadow: 0 1px 5px rgba(255, 255, 255, 0.9);
    }

    .status {
      font-size: 12px;
      font-weight: 800;
      padding: 6px 10px;
      border-radius: 999px;
      border: 1px solid transparent;
      white-space: nowrap;
      backdrop-filter: blur(8px);
      -webkit-backdrop-filter: blur(8px);
      box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }

    .status.cool { background: rgba(33, 158, 188, 0.25); color: var(--navy); border-color: rgba(33, 158, 188, 0.4); }
    .status.normal, .status.good { background: rgba(142, 202, 230, 0.35); color: var(--navy); border-color: rgba(142, 202, 230, 0.5); }
    .status.warm { background: rgba(251, 133, 0, 0.25); color: #7a3300; border-color: rgba(251, 133, 0, 0.4); }
    .status.hot, .status.verybad { background: rgba(2, 48, 71, 0.92); color: #fefae0; border-color: rgba(2, 48, 71, 0.92); }
    .status.dry { background: rgba(233, 237, 201, 0.95); color: var(--navy); border-color: rgba(4, 52, 84, 0.12); }
    .status.comfort { background: rgba(142, 202, 230, 0.25); color: var(--navy); border-color: rgba(33, 158, 188, 0.4); }
    .status.humid, .status.poor { background: rgba(2, 48, 71, 0.92); color: #fefae0; border-color: rgba(2, 48, 71, 0.92); }

    .gauge-wrap {
     width: 58%;
      max-width: 340px;
      margin: 0 auto;
      aspect-ratio: 1.65 / 1;
      position: relative;
    }

    .gauge-svg {
      width: 100%;
      height: 100%;
      display: block;
      overflow: visible;
      filter: drop-shadow(0px 4px 6px rgba(0,0,0,0.08));
    }

    .dial-value {
      left: 0;
      right: 0;
      bottom: -10px;
      display: flex;
      justify-content: center;
      align-items: baseline;
      gap: 4px;
      pointer-events: none;
      color: var(--navy);
    }

    .big-value {
      font-size: clamp(36px, 5vw, 50px);
      font-weight: 900;
      line-height: 1;
      letter-spacing: -0.05em;
      text-shadow: 0 1px 6px rgba(255, 255, 255, 0.9);
    }

    .big-unit {
      font-size: 20px;
      font-weight: 800;
      color: var(--muted);
      text-shadow: 0 1px 4px rgba(255, 255, 255, 0.9);
    }

    .minmax {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      margin-top: auto;
    }

    .mini {
      background: linear-gradient(135deg, rgba(255, 255, 255, 0.5) 0%, rgba(255, 255, 255, 0.2) 100%);
      border: 1px solid rgba(255, 255, 255, 0.6);
      border-right: 1px solid rgba(255, 255, 255, 0.25);
      border-bottom: 1px solid rgba(255, 255, 255, 0.25);
      border-radius: 14px;
      padding: 9px 10px 10px;
      min-width: 0;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.05), inset 0 1px 1px rgba(255, 255, 255, 0.7);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
    }

    .mini .k {
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 4px;
      text-align: center;
      text-shadow: 0 1px 3px rgba(255, 255, 255, 0.8);
      font-weight: 600;
    }

    .mini .v {
      text-align: center;
      font-size: 16px;
      font-weight: 900;
      color: var(--navy);
      line-height: 1.05;
      word-break: break-word;
      text-shadow: 0 1px 4px rgba(255, 255, 255, 0.9);
    }

    .side-card h2 {
      margin: 0 0 12px;
      text-align: center;
      font-size: 18px;
      font-weight: 900;
      color: var(--navy);
      text-shadow: 0px 0px 14px rgb(255 255 255);
    }

    .side-stack {
      display: grid;
      gap: 10px;
    }

    .stat-box {
      background: linear-gradient(135deg, rgba(255, 255, 255, 0.55) 0%, rgba(255, 255, 255, 0.25) 100%);
      border: 1px solid rgba(255, 255, 255, 0.6);
      border-right: 1px solid rgba(255, 255, 255, 0.25);
      border-bottom: 1px solid rgba(255, 255, 255, 0.25);
      border-radius: 16px;
      padding: 12px;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.05), inset 0 1px 1px rgba(255, 255, 255, 0.8);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
    }

    #overallMood {
      color: #6a0088;
    }

    .stat-box .k {
      font-size: 14px;
      color: var(--muted);
      margin-bottom: 6px;
      font-weight: 600;
      text-shadow: 0 1px 3px rgba(255, 255, 255, 0.8);
    }

    .stat-box .v {
      font-size: 17px;
      font-weight: 900;
      color: var(--navy);
      line-height: 1.15;
      word-break: break-word;
      text-shadow: 0 1px 4px rgba(255, 255, 255, 0.9);
    }
    
    /* Dedicated styling for the LLM output box to distinguish it visually */
    #llmBox {
      font-size: clamp(13px, 1.4vw, 18px);
      font-weight: 700;
      line-height: 1.45;
      color: #9a0000;
      text-shadow: 0 1px 2px rgba(255, 255, 255, 0.9);
      word-break: break-word;
    }

    .footer-note {
      margin-top: 10px;
      font-size: 12px;
      line-height: 1.45;
      color: var(--navy);
      font-weight: 600;
      text-shadow: 0 1px 3px rgba(255, 255, 255, 0.8);
    }

    .needle {
      transform-origin: 100px 100px;
      transition: transform 0.25s cubic-bezier(.2,.8,.2,1);
    }

    .ring-track { stroke: rgba(4, 52, 84, 0.12); }
    .temp-ring { stroke: url(#tempGradient); }
    .hum-ring { stroke: url(#humGradient); }
    .mq-ring { stroke: url(#mqGradient); }

    .tick {
      stroke: rgba(4, 52, 84, 0.25);
      stroke-width: 2;
      stroke-linecap: round;
    }

    .needle-line {
      stroke: var(--navy);
      stroke-width: 4;
      stroke-linecap: round;
    }

    .needle-dot { fill: var(--navy); }

    @media (max-width: 1100px) {
      .layout {
        grid-template-columns: 1fr;
      }
      .side-card {
        position: static;
      }
      .gauges {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
    }

    @media (max-width: 760px) {
      .page { padding: 8px; gap: 8px; }
      .layout { gap: 8px; }
      .gauges { grid-template-columns: repeat(2, 1fr); gap: 8px; }
      .main-card, .side-card { padding: 8px; border-radius: 16px; }
      .gauge-card { padding: 8px; gap: 6px; }
      .gauge-title { font-size: 13px; }
      .status { font-size: 10px; padding: 3px 6px; }
      .gauge-wrap { max-width: 100%; aspect-ratio: 1.4 / 1; }
      .big-value { font-size: 20px; }
      .big-unit { font-size: 12px; }
      .dial-value { bottom: -4px; }
      .mini { padding: 6px; border-radius: 10px;}
      .mini .k { font-size: 10px; }
      .mini .v { font-size: 11px; }
      .stat-box { padding: 8px; border-radius: 12px;}
      .stat-box .k { font-size: 12px; }
      .stat-box .v { font-size: 13px; }
      .side-stack { gap: 6px; }
      .footer-note { font-size: 10px; }
    }

    #topt{
      display: inline-flex;
      width: 100%;
      gap: 20px;
      justify-content: center;
      flex-direction: row;
      align-items: baseline;
    }
  </style>
</head>
<body>
<video autoplay muted loop playsinline class="bg">
  <source src="http://10.28.229.167:8000/bg.mp4" type="video/mp4">
</video>

  <div class="page">
    <div class="topbar">
      <div class="title-wrap">
        <h1 class="title">Air Watch 📡</h1>
        <p>Real-Time Environment Air Monitor</p>
      </div>
    </div>

    <div class="layout">
      <div class="main-card">
        <div class="gauges">

          <div class="gauge-card">
            <div class="gauge-head">
              <h3 class="gauge-title">Temp</h3>
              <div class="status normal" id="tempStatus">Normal</div>
            </div>

            <div class="gauge-wrap">
              <svg class="gauge-svg" viewBox="0 0 200 120" aria-label="Temperature gauge">
                <defs>
                  <linearGradient id="tempGradient" x1="20" y1="100" x2="180" y2="100" gradientUnits="userSpaceOnUse">
                    <stop offset="0%" stop-color="#8ecae6"/>
                    <stop offset="55%" stop-color="#ffb703"/>
                    <stop offset="100%" stop-color="#fb8500"/>
                  </linearGradient>
                  <linearGradient id="humGradient" x1="20" y1="100" x2="180" y2="100" gradientUnits="userSpaceOnUse">
                    <stop offset="0%" stop-color="#8ecae6"/>
                    <stop offset="55%" stop-color="#219ebc"/>
                    <stop offset="100%" stop-color="#023047"/>
                  </linearGradient>
                  <linearGradient id="mqGradient" x1="20" y1="100" x2="180" y2="100" gradientUnits="userSpaceOnUse">
                    <stop offset="0%" stop-color="#8ecae6"/>
                    <stop offset="50%" stop-color="#ffb703"/>
                    <stop offset="100%" stop-color="#fb8500"/>
                  </linearGradient>
                </defs>

                <path d="M20 100 A80 80 0 0 1 180 100" fill="none" stroke-width="14" class="ring-track" stroke-linecap="round"></path>
                <path d="M20 100 A80 80 0 0 1 180 100" fill="none" stroke-width="14" class="temp-ring" stroke-linecap="round"></path>

                <g id="tempTicks"></g>

                <g class="needle" id="tempNeedle">
                  <line x1="100" y1="100" x2="100" y2="30" class="needle-line"></line>
                  <circle cx="100" cy="100" r="7" class="needle-dot"></circle>
                </g>

                <text x="20" y="118" text-anchor="middle" font-size="12" fill="var(--muted)" font-weight="800" style="text-shadow: 0 1px 2px rgba(255,255,255,0.9)">0</text>
                <text x="180" y="118" text-anchor="middle" font-size="12" fill="var(--muted)" font-weight="800" style="text-shadow: 0 1px 2px rgba(255,255,255,0.9)">50</text>
              </svg>
            </div>

            <div class="dial-value">
              <div class="big-value"><span id="tempValue">--</span></div>
              <div class="big-unit">°C</div>
            </div>

            <div class="minmax">
              <div class="mini">
                <div class="k">Min temp</div>
                <div class="v"><span id="minTemp">--</span>°C</div>
              </div>
              <div class="mini">
                <div class="k">Max temp</div>
                <div class="v"><span id="maxTemp">--</span>°C</div>
              </div>
            </div>
          </div>

          <div class="gauge-card">
            <div class="gauge-head">
              <h3 class="gauge-title">Air Moist</h3>
              <div class="status comfort" id="humStatus">Comfort</div>
            </div>

            <div class="gauge-wrap">
              <svg class="gauge-svg" viewBox="0 0 200 120" aria-label="Humidity gauge">
                <path d="M20 100 A80 80 0 0 1 180 100" fill="none" stroke-width="14" class="ring-track" stroke-linecap="round"></path>
                <path d="M20 100 A80 80 0 0 1 180 100" fill="none" stroke-width="14" class="hum-ring" stroke-linecap="round"></path>

                <g id="humTicks"></g>

                <g class="needle" id="humNeedle">
                  <line x1="100" y1="100" x2="100" y2="30" class="needle-line"></line>
                  <circle cx="100" cy="100" r="7" class="needle-dot"></circle>
                </g>

                <text x="20" y="118" text-anchor="middle" font-size="12" fill="var(--muted)" font-weight="800" style="text-shadow: 0 1px 2px rgba(255,255,255,0.9)">0</text>
                <text x="180" y="118" text-anchor="middle" font-size="12" fill="var(--muted)" font-weight="800" style="text-shadow: 0 1px 2px rgba(255,255,255,0.9)">100</text>
              </svg>
            </div>

            <div class="dial-value">
              <div class="big-value"><span id="humValue">--</span></div>
              <div class="big-unit">%</div>
            </div>

            <div class="minmax">
              <div class="mini">
                <div class="k">Min humid</div>
                <div class="v"><span id="minHum">--</span>%</div>
              </div>
              <div class="mini">
                <div class="k">Max humid</div>
                <div class="v"><span id="maxHum">--</span>%</div>
              </div>
            </div>
          </div>

          <div class="gauge-card">
            <div class="gauge-head">
              <h3 class="gauge-title">Air Q</h3>
              <div class="status good" id="mqStatus">Good</div>
            </div>

            <div class="gauge-wrap">
              <svg class="gauge-svg" viewBox="0 0 200 120" aria-label="MQ-135 gauge">
                <path d="M20 100 A80 80 0 0 1 180 100" fill="none" stroke-width="14" class="ring-track" stroke-linecap="round"></path>
                <path d="M20 100 A80 80 0 0 1 180 100" fill="none" stroke-width="14" class="mq-ring" stroke-linecap="round"></path>

                <g id="mqTicks"></g>

                <g class="needle" id="mqNeedle">
                  <line x1="100" y1="100" x2="100" y2="30" class="needle-line"></line>
                  <circle cx="100" cy="100" r="7" class="needle-dot"></circle>
                </g>

                <text x="20" y="118" text-anchor="middle" font-size="12" fill="var(--muted)" font-weight="800" style="text-shadow: 0 1px 2px rgba(255,255,255,0.9)">0</text>
                <text x="180" y="118" text-anchor="middle" font-size="12" fill="var(--muted)" font-weight="800" style="text-shadow: 0 1px 2px rgba(255,255,255,0.9)">200</text>
              </svg>
            </div>

            <div class="dial-value">
              <div class="big-value"><span id="mqValue">--</span></div>
              <div class="big-unit">raw</div>
            </div>

            <div class="minmax">
              <div class="mini">
                <div class="k">Min Score</div>
                <div class="v"><span id="minMq">--</span></div>
              </div>
              <div class="mini">
                <div class="k">Max Score</div>
                <div class="v"><span id="maxMq">--</span></div>
              </div>
            </div>
          </div>

          <div class="gauge-card">
            <div class="gauge-head">
              <h3 class="gauge-title">Dust</h3>
              <div class="status normal" id="dustStatus">Normal</div>
            </div>

            <div class="gauge-wrap">
              <svg class="gauge-svg" viewBox="0 0 200 120" aria-label="Dust gauge">
                <defs>
                  <linearGradient id="dustGradient" x1="20" y1="100" x2="180" y2="100" gradientUnits="userSpaceOnUse">
                    <stop offset="0%" stop-color="#8ecae6"/>
                    <stop offset="55%" stop-color="#ffb703"/>
                    <stop offset="100%" stop-color="#fb8500"/>
                  </linearGradient>
                </defs>

                <path d="M20 100 A80 80 0 0 1 180 100" fill="none" stroke-width="14" class="ring-track" stroke-linecap="round"></path>
                <path d="M20 100 A80 80 0 0 1 180 100" fill="none" stroke-width="14" style="stroke: url(#dustGradient);" stroke-linecap="round"></path>

                <g id="dustTicks"></g>

                <g class="needle" id="dustNeedle">
                  <line x1="100" y1="100" x2="100" y2="30" class="needle-line"></line>
                  <circle cx="100" cy="100" r="7" class="needle-dot"></circle>
                </g>

                <text x="20" y="118" text-anchor="middle" font-size="12" fill="var(--muted)" font-weight="800" style="text-shadow: 0 1px 2px rgba(255,255,255,0.9)">0</text>
                <text x="180" y="118" text-anchor="middle" font-size="12" fill="var(--muted)" font-weight="800" style="text-shadow: 0 1px 2px rgba(255,255,255,0.9)">500</text>
              </svg>
            </div>

            <div class="dial-value">
              <div class="big-value"><span id="dustValue">--</span></div>
              <div class="big-unit">µg/m³</div>
            </div>

            <div class="minmax">
              <div class="mini">
                <div class="k">Min dust</div>
                <div class="v"><span id="minDust">--</span></div>
              </div>
              <div class="mini">
                <div class="k">Max dust</div>
                <div class="v"><span id="maxDust">--</span></div>
              </div>
            </div>
          </div>

        </div>
      </div>

      <div class="side-card">
        <div id="topt">
            <h2>Status</h2>
            <div class="live-chip"><span class="dot"></span><span id="conn">Live</span></div>
        </div>
        <div class="side-stack">
          <div class="stat-box">
            <div class="k">Temperature mood</div>
            <div class="v" id="tempMoodBig">Waiting for data</div>
          </div>

          <div class="stat-box">
            <div class="k">Humidity mood</div>
            <div class="v" id="humMoodBig">Waiting for data</div>
          </div>

          <div class="stat-box">
            <div class="k">Air Quality mood</div>
            <div class="v" id="mqMoodBig">Waiting for data</div>
          </div>

          <div class="stat-box">
            <div class="k">Dust mood</div>
            <div class="v" id="dustMoodBig">Waiting for data</div>
          </div>

          <div class="stat-box">
            <div class="k">Environment Status</div>
            <div class="v" id="overallMood">Monitoring</div>
          </div>

          <div class="stat-box">
            <div class="k">Last updated</div>
            <div class="v" style="font-size:14px; font-weight:800;" id="updatedAt">--</div>
          </div>
          
          <div class="stat-box">
            <div class="k">AI Says</div>
            <div class="v" id="llmBox">Initializing AI...</div>
          </div>
        </div>

        <div class="footer-note">
          Temperature, humidity, MQ-135, and dust data are pulled from <code>/data</code> every 250 ms. 
        </div>
      </div>
    </div>
  </div>

<script>
  const tempMax = 50;
  const humMax = 100;
  const mqMax = 200;
  const dustMax = 500;

  function clamp(n, min, max) {
    return Math.max(min, Math.min(max, n));
  }

  function fmt(n) {
    if (n === null || n === undefined || Number.isNaN(Number(n))) return "--";
    const num = Number(n);
    return Number.isInteger(num) ? String(num) : num.toFixed(1);
  }

  function setGauge(needleId, value, max, ticksId) {
    const v = clamp(Number(value) || 0, 0, max);
    const pct = (v / max) * 100;
    const angle = -90 + (pct / 100) * 180;
    const needle = document.getElementById(needleId);
    if (needle) needle.style.transform = `rotate(${angle}deg)`;

    const ticks = document.getElementById(ticksId);
    if (ticks && !ticks.dataset.ready) {
      let html = "";
      for (let i = 0; i <= 10; i++) {
        const a = -180 + i * 18;
        const major = i % 2 === 0;
        const r1 = major ? 66 : 70;
        const r2 = 78;
        const rad = a * Math.PI / 180;
        const x1 = 100 + r1 * Math.cos(rad);
        const y1 = 100 + r1 * Math.sin(rad);
        const x2 = 100 + r2 * Math.cos(rad);
        const y2 = 100 + r2 * Math.sin(rad);
        html += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" class="tick"></line>`;
      }
      ticks.innerHTML = html;
      ticks.dataset.ready = "1";
    }
  }

  function tempMood(t) {
    if (t < 18) return { label: "Cool", detail: "Cool", cls: "cool" };
    if (t < 28) return { label: "Normal", detail: "Comfortable", cls: "normal" };
    if (t < 35) return { label: "Warm", detail: "Getting warm", cls: "warm" };
    return { label: "Hot", detail: "Hot", cls: "hot" };
  }

  function humMood(h) {
    if (h < 35) return { label: "Dry", detail: "Dry", cls: "dry" };
    if (h < 65) return { label: "Comfort", detail: "Comfortable", cls: "comfort" };
    return { label: "Humid", detail: "Humid", cls: "humid" };
  }

  function mqMood(m) {
    if (m < 800) return { label: "Good", detail: "Good air", cls: "good" };
    if (m < 1600) return { label: "Moderate", detail: "Moderate", cls: "normal" };
    if (m < 2600) return { label: "Poor", detail: "Poor air", cls: "poor" };
    return { label: "Very bad", detail: "Very bad", cls: "verybad" };
  }

  function dustMood(d) {
    if (d < 35) return { label: "Good", detail: "Very low dust", cls: "good" };
    if (d < 80) return { label: "Normal", detail: "Acceptable dust", cls: "normal" };
    if (d < 150) return { label: "Poor", detail: "Dust rising", cls: "warm" };
    return { label: "High", detail: "High dust", cls: "verybad" };
  }

  function overallStatus(t, h, m, d) {
    const temp = Number(t);
    const hum = Number(h);
    const mq = Number(m);
    const dust = Number(d);

    const excellentTemp = temp >= 18 && temp < 28;
    const excellentHum = hum >= 35 && hum < 65;
    const excellentAir = mq < 20;
    const excellentDust = dust < 35;

    const okayTemp = temp >= 18 && temp < 35;
    const okayHum = hum >= 30 && hum < 70;
    const okayAir = mq < 100;
    const okayDust = dust < 80;

    const badAir = mq >= 120;
    const badTemp = temp >= 35 || temp < 12;
    const badHum = hum < 25 || hum >= 75;
    const badDust = dust >= 150;

    if (excellentTemp && excellentHum && excellentAir && excellentDust) {
      return { text: "Excellent overall condition", cls: "good" };
    }

    if (okayTemp && okayHum && okayAir && okayDust) {
      return { text: "Healthy and balanced environment", cls: "normal" };
    }

    if (badAir || badTemp || badHum || badDust) {
      return { text: "Needs attention", cls: "warm" };
    }

    return { text: "Monitoring", cls: "normal" };
  }

  function setStatus(el, mood) {
    el.className = `status ${mood.cls}`;
    el.textContent = mood.label;
  }

  async function loadData() {
    try {
      const res = await fetch("/data", { cache: "no-store" });
      const data = await res.json();

      const t = Number(data.temp);
      const h = Number(data.hum);
      const m = Number(data.mq135);
      const d = Number(data.dust);

      document.getElementById("tempValue").textContent = fmt(t);
      document.getElementById("humValue").textContent = fmt(h);
      document.getElementById("mqValue").textContent = fmt(m);
      document.getElementById("dustValue").textContent = fmt(d);

      document.getElementById("minTemp").textContent = data.min_t == null ? "--" : fmt(data.min_t);
      document.getElementById("maxTemp").textContent = data.max_t == null ? "--" : fmt(data.max_t);
      document.getElementById("minHum").textContent = data.min_h == null ? "--" : fmt(data.min_h);
      document.getElementById("maxHum").textContent = data.max_h == null ? "--" : fmt(data.max_h);
      document.getElementById("minMq").textContent = data.min_mq == null ? "--" : fmt(data.min_mq);
      document.getElementById("maxMq").textContent = data.max_mq == null ? "--" : fmt(data.max_mq);
      document.getElementById("minDust").textContent = data.min_dust == null ? "--" : fmt(data.min_dust);
      document.getElementById("maxDust").textContent = data.max_dust == null ? "--" : fmt(data.max_dust);

      const temp = tempMood(t);
      const hum = humMood(h);
      const mq = mqMood(m);
      const dust = dustMood(d);
      const overall = overallStatus(t, h, m, d);

      setStatus(document.getElementById("tempStatus"), temp);
      setStatus(document.getElementById("humStatus"), hum);
      setStatus(document.getElementById("mqStatus"), mq);
      setStatus(document.getElementById("dustStatus"), dust);

      document.getElementById("tempMoodBig").textContent = temp.detail;
      document.getElementById("humMoodBig").textContent = hum.detail;
      document.getElementById("mqMoodBig").textContent = mq.detail;
      document.getElementById("dustMoodBig").textContent = dust.detail;

      const overallEl = document.getElementById("overallMood");
      overallEl.textContent = overall.text;
      overallEl.className = `v ${overall.cls}`;
      
      // Update the LLM conclusion box
      document.getElementById("llmBox").textContent = data.llm_conclusion || "Waiting for AI...";

      setGauge("tempNeedle", t, tempMax, "tempTicks");
      setGauge("humNeedle", h, humMax, "humTicks");
      setGauge("mqNeedle", m, mqMax, "mqTicks");
      setGauge("dustNeedle", d, dustMax, "dustTicks");

      document.getElementById("updatedAt").textContent =
        new Date().toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit"
        });

      document.getElementById("conn").textContent = "Live";
    } catch (e) {
      document.getElementById("conn").textContent = "Offline";
    }
  }

  loadData();
  setInterval(loadData, 250);
</script>
</body>
</html>
"""
        self.wfile.write(html.encode("utf-8"))


if __name__ == "__main__":
    # Start the LLM background thread as a daemon so it dies when the server stops
    llm_thread = threading.Thread(target=llm_worker_thread, daemon=True)
    llm_thread.start()

    server = HTTPServer(("0.0.0.0", 5000), Handler)
    print("Server running on port 5000...")
    server.serve_forever()