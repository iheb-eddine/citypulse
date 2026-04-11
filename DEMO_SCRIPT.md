# CityPulse Demo Video Script

## AlgoFest 2026 — Smart Cities & IoT Track

**Target length:** 2:30–2:45  
**Format:** Screen recording with voiceover + auto-generated captions  
**Recording tool:** OBS Studio (1920×1080, 30fps, MP4) — or Loom as fallback  
**Webcam:** No  
**One take is fine.** Hackathon judges expect authenticity, not polish.

---

## BEFORE YOU RECORD — Preparation Checklist

### Recording Setup
- [ ] OBS Studio installed with screen capture + mic input configured
- [ ] Browser: Chrome or Firefox, zoomed to **125%** for readability on Devpost embed
- [ ] Browser window sized to ~1280×800
- [ ] Quiet room, water nearby
- [ ] Read the script once out loud before recording

### Browser Tabs (open these BEFORE hitting record)
- **Tab 1:** `https://citypulse.help` — Dashboard (verify markers and heatmap are visible)
- **Tab 2:** `https://citypulse.help/submit` — Submit form
- **Tab 3:** `https://citypulse.help/briefing` — Council briefing (pre-loaded)
- **Second browser window** (or incognito): `https://citypulse.help` — to show SSE live update

### Data & Content Prep
- [ ] Verify seed data is loaded and recent — run `python seed_data/seed.py` if the dashboard looks empty
- [ ] Have a test photo ready on your desktop (pothole or streetlight — grab one from `app/static/uploads/` if needed)
- [ ] Pre-test the AI chat question: type "What is the biggest problem in Stuttgart right now?" and verify you get a good response
- [ ] Note the actual numbers from the dashboard stats panel: **total reports** count and **neighborhood** count (17 neighborhoods configured) — you will say these in the closing
- [ ] Make sure the heatmap time slider layer is active on the dashboard (click the layer control icon on the map)

---

## THE SCRIPT

### SECTION 1: HOOK [0:00 – 0:05]

| | |
|---|---|
| **Screen** | Dashboard already open. Map with colored markers visible. Heatmap time slider layer active — the colored heat overlay is the first thing judges see. |
| **Voiceover** | *"What if every phone in your city was a smart sensor?"* |
| **Action** | None. Let the visual hook do the work. |

---

### SECTION 2: PROBLEM + SOLUTION [0:05 – 0:20]

| | |
|---|---|
| **Screen** | Stay on dashboard. Slowly mouse over 2–3 markers to show popups with photos, categories, and severity badges. |
| **Voiceover** | *"Cities struggle to find and prioritize urban issues — potholes, broken lights, illegal dumping. CityPulse turns citizen photos into classified, geolocated, prioritized reports — automatically. Let me show you how."* |
| **Action** | Click one marker popup so judges can see the photo, category, severity badge, department, and status controls. |

---

### SECTION 3: CORE LOOP — Submit → AI → Real-time Update [0:20 – 0:55]

| | |
|---|---|
| **Screen** | Switch to Tab 2 (Submit page). |
| **Voiceover** | *"Here is the citizen experience. Upload a photo..."* |
| **Action** | Click the upload area, select the test photo from desktop. Photo preview appears. |

| | |
|---|---|
| **Voiceover** | *"...GPS auto-detected..."* |
| **Action** | Click "📍 Use my location" button. Location fields populate. |

| | |
|---|---|
| **Voiceover** | *"...hit submit."* |
| **Action** | Click the Submit button. Wait for the success card to appear. |

| | |
|---|---|
| **Voiceover** | *"The AI classified it instantly — [read the actual result: e.g., pothole, high severity, routed to roads]."* |
| **Action** | Point cursor to the classification result card showing category, severity, department. Pause 2 seconds so judges can read it. |

| | |
|---|---|
| **Screen** | Switch to the second browser window showing the dashboard. |
| **Voiceover** | *"And watch the dashboard — every connected client gets the update in real time via Server-Sent Events."* |
| **Action** | The SSE toast notification should appear in the bottom-right corner. Point to it. |

---

### SECTION 4: CLUSTERING + SCORES [0:55 – 1:10]

| | |
|---|---|
| **Screen** | Back on main dashboard. Point to the stats panel on the right. |
| **Voiceover** | *"The dashboard clusters reports into hotspots using DBSCAN. Two scores track city health: overall wellbeing at [read actual score] out of 100, and accessibility impact at [read actual score] — weighted for how issues affect people with disabilities. The heatmap shows report density evolving day by day."* |
| **Action** | Point to: Health Score → Accessibility Score → Top Hotspots list → Risk Zone circles on the map. Briefly drag the heatmap time slider if visible. |

---

### SECTION 5: AI CHAT [1:10 – 1:30]

| | |
|---|---|
| **Screen** | Click the 💬 chat FAB button in the bottom-right corner. Chat panel opens. |
| **Voiceover** | *"Officials can ask the AI assistant about city conditions — it pulls from live report data and local news."* |
| **Action** | Type: `What is the biggest problem in Stuttgart right now?` and hit send. |

| | |
|---|---|
| **Voiceover** | *(Pause while the AI response types out word by word. Let it finish — the typing animation is part of the demo.)* |
| **Action** | Wait for the full response. Point to a specific detail in the answer if it cites a neighborhood or category. |

---

### SECTION 6: COUNCIL BRIEFING [1:30 – 1:45]

| | |
|---|---|
| **Screen** | Switch to Tab 3 (Briefing page). |
| **Voiceover** | *"For city council meetings, CityPulse auto-generates a formal briefing — executive summary, key findings with real numbers, and recommended priorities. All from live data."* |
| **Action** | Slowly scroll through the briefing text so judges can see the paragraph structure. |

---

### SECTION 7: UPVOTE + RESOLUTION [1:45 – 2:00]

| | |
|---|---|
| **Screen** | Back to dashboard. Click a marker popup. |
| **Voiceover** | *"Citizens can confirm reports they see in person — three confirmations auto-escalate the severity. City staff track resolution through open, in progress, and resolved."* |
| **Action** | Click the "👍 Confirm" button in the popup (watch the count increment). Then click the "In Progress" status button. |

---

### SECTION 8: QUICK-FIRE FEATURES [2:00 – 2:15]

| | |
|---|---|
| **Screen** | Switch to submit page briefly, then back to dashboard. |
| **Voiceover** | *"Voice input for accessibility..."* |
| **Action** | Point to the 🎙️ mic button on the submit form. |

| | |
|---|---|
| **Voiceover** | *"...all photo metadata stripped automatically for privacy..."* |
| **Action** | Point to the "🔒 Privacy Protected" badge under the upload area. |

| | |
|---|---|
| **Voiceover** | *"...and the architecture is multi-city ready."* |
| **Action** | Switch back to dashboard. No need to demo the city selector. |

---

### SECTION 9: ARCHITECTURE [2:15 – 2:30]

| | |
|---|---|
| **Screen** | Stay on the dashboard (no diagram needed — just narrate). |
| **Voiceover** | *"Built with FastAPI, SQLite, Groq Llama 4 Scout for vision classification, DBSCAN for spatial clustering, Folium for interactive maps, and Server-Sent Events for real-time push. All deployed and live at citypulse.help."* |
| **Action** | None. The dashboard on screen reinforces "this is real and deployed." |

---

### SECTION 10: CLOSING [2:30 – 2:45]

| | |
|---|---|
| **Screen** | Dashboard with Health Score prominently visible. |
| **Voiceover** | *"CityPulse has processed [X] reports across [Y] neighborhoods in Stuttgart. One photo. One tap. AI does the rest. Turn every phone into a smart city sensor."* |
| **Action** | Hold on the dashboard for 3 seconds. End recording. |

> ⚠️ **Fill in [X] and [Y] from the dashboard stats panel before recording.**  
> X = total reports number, Y = count of neighborhoods with reports (check the hotspots/risk list).

---

## POST-RECORDING

1. **Trim** dead air at the start and end (OBS: Edit in any video editor, or just re-record — it is one take)
2. **Remux** if needed: OBS → File → Remux Recordings (converts .mkv to .mp4)
3. **Upload** to YouTube (unlisted) or Loom
4. **Captions:** YouTube auto-generates them. Loom has built-in captions. Either works.
5. **Embed** the video URL on your Devpost project page
6. **Total target:** 2:30–2:45. If you run over 3:00, cut the architecture narration shorter.

## RECORDING TIPS FOR 4AM

- **One take is fine.** If you stumble on a sentence, pause 2 seconds and re-say it. Do not restart.
- **Energy matters more than perfection.** Sound like you believe in what you built.
- **Pace:** Slightly slower than conversation. Let judges absorb what they see.
- **Do not say "um" or "so basically."** If you need to think, just pause silently.
- **The first 5 seconds decide if judges keep watching.** That is why the dashboard is already on screen when you start.

---

## JUDGING CRITERIA COVERAGE

| Criterion (Weight) | Where it is covered in the video |
|---|---|
| **Innovation (25%)** | AI vision classification, DBSCAN clustering, accessibility impact scoring, AI chat with live data context |
| **Technical Complexity (25%)** | Architecture narration (Section 9), SSE real-time demo, vision model + NLP chat, spatial clustering |
| **Practical Impact (20%)** | Problem statement (Section 2), council briefing for government use, accessibility score, citizen engagement loop |
| **Design/UX (15%)** | Live dashboard visual, mobile-first submit form, chat widget UX, one-tap submit flow |
| **Presentation (15%)** | Hook-first structure, tight pacing, deployed live app, professional voiceover |
