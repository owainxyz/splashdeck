const W = 800, H = 480;
const $ = (id) => document.getElementById(id);
const canvas = $("canvas"), ctx = canvas.getContext("2d", { willReadFrequently: true });
const overlay = $("overlay"), octx = overlay.getContext("2d");

const st = {
  img: null, oriented: null, name: "",
  mode: "fill", bg: "black", color: "#808080",
  zoom: 1, offX: 0, offY: 0, rot: 0, flipH: false, flipV: false,
  adj: { bright: 100, contrast: 100, sat: 100, gray: false },
  keys: false, device: null, busy: false, settings: {},
};

let api = null;
let renderQueued = false;

function toast(text, kind = "") {
  const el = document.createElement("div");
  el.className = "toast " + kind;
  el.innerHTML = '<span></span>';
  el.lastChild.textContent = text;
  $("toasts").appendChild(el);
  setTimeout(() => { el.classList.add("out"); setTimeout(() => el.remove(), 250); }, 2600);
}

function ago(t) {
  const s = Math.max(0, Date.now() / 1000 - t);
  if (s < 60) return "just now";
  if (s < 3600) return Math.floor(s / 60) + "m ago";
  if (s < 86400) return Math.floor(s / 3600) + "h ago";
  return Math.floor(s / 86400) + "d ago";
}

function saveSettings(values) {
  Object.assign(st.settings, values);
  if (api) api.saveSettings(values);
}

function buildOriented() {
  if (!st.img) { st.oriented = null; return; }
  const sw = st.img.naturalWidth, sh = st.img.naturalHeight;
  const quarter = st.rot % 180 !== 0;
  const c = document.createElement("canvas");
  c.width = quarter ? sh : sw;
  c.height = quarter ? sw : sh;
  const g = c.getContext("2d");
  g.translate(c.width / 2, c.height / 2);
  g.rotate((st.rot * Math.PI) / 180);
  g.scale(st.flipH ? -1 : 1, st.flipV ? -1 : 1);
  g.drawImage(st.img, -sw / 2, -sh / 2);
  st.oriented = c;
}

function geometry() {
  const o = st.oriented;
  const w = o.width, h = o.height;
  if (st.mode === "stretch") return { x: 0, y: 0, w: W, h: H, maxX: 0, maxY: 0 };
  const base = st.mode === "fill" ? Math.max(W / w, H / h) : Math.min(W / w, H / h);
  const s = base * st.zoom;
  const dw = w * s, dh = h * s;
  const maxX = Math.abs(dw - W) / 2, maxY = Math.abs(dh - H) / 2;
  st.offX = Math.max(-maxX, Math.min(maxX, st.offX));
  st.offY = Math.max(-maxY, Math.min(maxY, st.offY));
  return { x: (W - dw) / 2 + st.offX, y: (H - dh) / 2 + st.offY, w: dw, h: dh, maxX, maxY };
}

function boxBlur(d, w, h, r) {
  const out = new Uint8ClampedArray(d.length);
  for (let pass = 0; pass < 2; pass++) {
    const src = pass ? out.slice() : d, dst = out;
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      let rs = 0, gs = 0, bs = 0, n = 0;
      for (let k = -r; k <= r; k++) {
        const xx = pass ? x : Math.min(w - 1, Math.max(0, x + k));
        const yy = pass ? Math.min(h - 1, Math.max(0, y + k)) : y;
        const i = (yy * w + xx) * 4;
        rs += src[i]; gs += src[i + 1]; bs += src[i + 2]; n++;
      }
      const o = (y * w + x) * 4;
      dst[o] = rs / n; dst[o + 1] = gs / n; dst[o + 2] = bs / n; dst[o + 3] = 255;
    }
  }
  return out;
}

function blurred(o) {
  const w = 200, h = 120;
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  const g = c.getContext("2d", { willReadFrequently: true });
  const s = Math.max(w / o.width, h / o.height);
  g.drawImage(o, (w - o.width * s) / 2, (h - o.height * s) / 2, o.width * s, o.height * s);
  const im = g.getImageData(0, 0, w, h);
  let d = im.data;
  for (let i = 0; i < 3; i++) d = boxBlur(d, w, h, 6);
  im.data.set(d);
  g.putImageData(im, 0, 0);
  return c;
}

function drawBackground() {
  if (st.mode !== "fit") return;
  if (st.bg === "blur") {
    if (!st.blurCache || st.blurCache.src !== st.oriented) st.blurCache = { src: st.oriented, canvas: blurred(st.oriented) };
    ctx.drawImage(st.blurCache.canvas, 0, 0, W, H);
    ctx.fillStyle = "rgba(0,0,0,0.3)";
    ctx.fillRect(0, 0, W, H);
    return;
  }
  ctx.fillStyle = st.bg === "white" ? "#fff" : st.bg === "custom" ? st.color : "#000";
  ctx.fillRect(0, 0, W, H);
}

function applyAdjust() {
  const a = st.adj;
  if (a.bright === 100 && a.contrast === 100 && a.sat === 100 && !a.gray) return;
  const im = ctx.getImageData(0, 0, W, H), d = im.data;
  const b = a.bright / 100, c = a.contrast / 100, s = a.gray ? 0 : a.sat / 100;
  for (let i = 0; i < d.length; i += 4) {
    let r = d[i] * b, g = d[i + 1] * b, bl = d[i + 2] * b;
    r = (r - 128) * c + 128; g = (g - 128) * c + 128; bl = (bl - 128) * c + 128;
    const l = 0.2126 * r + 0.7152 * g + 0.0722 * bl;
    d[i] = l + (r - l) * s; d[i + 1] = l + (g - l) * s; d[i + 2] = l + (bl - l) * s;
  }
  ctx.putImageData(im, 0, 0);
}

function render() {
  renderQueued = false;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, W, H);
  $("empty").style.display = st.img ? "none" : "flex";
  if (st.oriented) {
    drawBackground();
    const g = geometry();
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(st.oriented, g.x, g.y, g.w, g.h);
    applyAdjust();
  }
  refreshUi();
}

function queueRender() {
  if (!renderQueued) { renderQueued = true; requestAnimationFrame(render); }
}

function drawOverlay() {
  octx.clearRect(0, 0, W, H);
  octx.fillStyle = "rgba(0,0,0,0.55)";
  octx.fillRect(0, 0, W, H);
  const k = 128, gap = 26, mx = (W - 5 * k - 4 * gap) / 2, my = (H - 3 * k - 2 * gap) / 2;
  octx.globalCompositeOperation = "destination-out";
  for (let r = 0; r < 3; r++) for (let c = 0; c < 5; c++) {
    const x = mx + c * (k + gap), y = my + r * (k + gap);
    octx.beginPath();
    octx.roundRect ? octx.roundRect(x, y, k, k, 14) : octx.rect(x, y, k, k);
    octx.fill();
  }
  octx.globalCompositeOperation = "source-over";
  octx.strokeStyle = "rgba(255,255,255,0.35)";
  octx.lineWidth = 2;
  for (let r = 0; r < 3; r++) for (let c = 0; c < 5; c++) {
    const x = mx + c * (k + gap), y = my + r * (k + gap);
    octx.beginPath();
    octx.roundRect ? octx.roundRect(x, y, k, k, 14) : octx.rect(x, y, k, k);
    octx.stroke();
  }
}

function refreshUi() {
  const ready = !!st.img && !!st.device && !st.busy;
  $("sendBtn").disabled = !ready;
  $("exportBtn").disabled = !st.img;
  $("bgField").classList.toggle("disabled", st.mode !== "fit");
  $("zoomVal").textContent = Math.round(st.zoom * 100) + "%";
  $("zoom").disabled = st.mode === "stretch";
  $("sourceName").textContent = st.img ? `${st.name} · ${st.img.naturalWidth} × ${st.img.naturalHeight}` : "";
  document.querySelectorAll("#mode button").forEach((b) => b.classList.toggle("on", b.dataset.v === st.mode));
  document.querySelectorAll("#bg .sw").forEach((b) => b.classList.toggle("on", b.dataset.v === st.bg || (st.bg === "custom" && b.classList.contains("custom"))));
  document.querySelector(".sw.custom span").style.setProperty("--custom", st.color);
  $("keysBtn").classList.toggle("on", st.keys);
  $("overlay").classList.toggle("on", st.keys);
  $("flipH").classList.toggle("on", st.flipH);
  $("flipV").classList.toggle("on", st.flipV);
}

function resetView() {
  st.zoom = 1; st.offX = 0; st.offY = 0;
  $("zoom").value = 1;
}

function loadImageUrl(url, name) {
  const img = new Image();
  img.onload = () => {
    st.img = img;
    st.name = name || "pasted image";
    st.rot = 0; st.flipH = false; st.flipV = false;
    resetView();
    buildOriented();
    queueRender();
  };
  img.onerror = () => toast("Can't open", "bad");
  img.src = url;
}

window.loadInitial = (r) => { if (!st.img) loadImageUrl(r.url, r.name); };

function loadFile(file) {
  if (!file || !file.type.startsWith("image/")) { toast("Not an image", "bad"); return; }
  const fr = new FileReader();
  fr.onload = () => loadImageUrl(fr.result, file.name);
  fr.readAsDataURL(file);
}

async function openPicker() {
  if (st.busy) return;
  const r = await api.pickImage();
  if (!r) return;
  if (r.error) { toast(r.error, "bad"); return; }
  loadImageUrl(r.url, r.name);
}

async function loadWallpaper() {
  if (st.busy) return;
  const r = await api.wallpaper();
  if (!r || r.error) { toast("No wallpaper", "bad"); return; }
  st.mode = "fill";
  loadImageUrl(r.url, r.name);
}

async function pasteFromClipboard() {
  try {
    const items = await navigator.clipboard.read();
    for (const it of items) {
      const type = it.types.find((t) => t.startsWith("image/"));
      if (type) { loadFile(new File([await it.getType(type)], "pasted image", { type })); return; }
    }
    toast("No image", "bad");
  } catch {
    toast("Ctrl+V", "");
  }
}

window.onSendProgress = (p) => {
  $("bar").style.width = (p * 100).toFixed(1) + "%";
  $("sendLabel").textContent = `Sending ${Math.round(p * 100)}%`;
};

async function send() {
  if (st.busy || !st.img || !st.device) return;
  st.busy = true;
  refreshUi();
  $("progress").classList.add("on");
  $("bar").style.width = "0";
  $("sendLabel").textContent = "Erasing";
  let r;
  try { r = await api.send(canvas.toDataURL("image/png")); } catch { r = { error: "Failed" }; }
  if (!r || !r.started) window.onSendDone(r || { error: "Failed" });
}

window.onSendDone = (r) => {
  st.busy = false;
  $("sendLabel").textContent = "Send to deck";
  setTimeout(() => $("progress").classList.remove("on"), 400);
  if (r && r.ok) {
    toast("Sent", "ok");
    loadLibrary();
  } else {
    toast((r && r.error) || "Failed", "bad");
  }
  refreshUi();
};

async function exportPng() {
  if (!st.img) return;
  const name = await api.exportImage(canvas.toDataURL("image/png"));
  if (name) toast("Saved " + name, "ok");
}

async function loadLibrary() {
  const items = await api.history();
  const lib = $("library");
  lib.innerHTML = "";
  lib.closest(".card").style.display = items.length ? "" : "none";
  for (const it of items) {
    const el = document.createElement("div");
    el.className = "thumb";
    el.innerHTML = '<img alt=""><span class="when"></span><button class="del" title="Remove"><svg class="i" viewBox="0 0 24 24"><path d="M18 6 6 18M6 6l12 12"/></svg></button>';
    el.querySelector("img").src = it.thumb;
    el.querySelector(".when").textContent = ago(it.time);
    el.addEventListener("click", async () => {
      const r = await api.historyImage(it.id);
      if (r && r.url) {
        st.mode = "fill";
        loadImageUrl(r.url, ago(it.time));
      }
    });
    el.querySelector(".del").addEventListener("click", async (e) => {
      e.stopPropagation();
      await api.historyDelete(it.id);
      loadLibrary();
    });
    lib.appendChild(el);
  }
}

function infoRow(k, v) {
  const row = document.createElement("div");
  row.className = "kv";
  row.innerHTML = "<span></span><span class='mono'></span>";
  row.firstChild.textContent = k;
  row.lastChild.textContent = v ?? "—";
  return row;
}

function showDevice(d) {
  const changed = JSON.stringify(d) !== JSON.stringify(st.device);
  st.device = d;
  $("conn").className = "conn " + (d ? "ok" : "bad");
  $("connText").textContent = d ? "Connected" : "Offline";
  $("connSub").textContent = d ? `${d.model}${d.firmware ? " · " + d.firmware : ""}` : "No deck found";
  if (!changed) return;
  const box = $("devInfo");
  box.innerHTML = "";
  if (d) {
    $("devSub").textContent = `fifine ${d.model}`;
    box.append(
      infoRow("Model", "fifine " + d.model),
      infoRow("Firmware", d.firmware),
      infoRow("Serial", d.serial),
      infoRow("USB ID", d.usbId),
      infoRow("Port", d.bus && d.port ? `bus ${d.bus} · port ${d.port}` : null),
      infoRow("Speed", d.speed ? d.speed + " Mb/s" : null),
      infoRow("Node", d.path),
    );
    $("permPill").className = "pill " + (d.access ? "ok" : "bad");
    $("permPill").textContent = d.access ? "OK" : "No access";
  } else {
    $("devSub").textContent = "";
    box.append(infoRow("Status", "Offline"));
    $("permPill").className = "pill bad";
    $("permPill").textContent = "—";
  }
  refreshUi();
}

async function poll() {
  try {
    const s = await api.state();
    $("version").textContent = "v" + s.version;
    showDevice(s.device);
  } catch {}
}

let briTimer = 0;
function setBrightness(v, push = true) {
  $("bri").value = v;
  $("briVal").textContent = v + "%";
  if (!push) return;
  clearTimeout(briTimer);
  briTimer = setTimeout(async () => {
    const r = await api.control("brightness", Number(v));
    if (r && r.error) toast("Failed", "bad");
  }, 120);
}

function bind() {
  document.querySelectorAll(".nav-item").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach((x) => x.classList.toggle("active", x === b));
    document.querySelectorAll(".page").forEach((p) => p.classList.toggle("active", p.id === "page-" + b.dataset.page));
  }));

  $("openBtn").onclick = openPicker;
  $("empty").onclick = openPicker;
  $("pasteBtn").onclick = pasteFromClipboard;
  $("wallBtn").onclick = loadWallpaper;
  $("exportBtn").onclick = exportPng;
  $("sendBtn").onclick = send;

  document.querySelectorAll("#mode button").forEach((b) => b.onclick = () => {
    st.mode = b.dataset.v; resetView(); queueRender();
  });
  document.querySelectorAll("#bg .sw[data-v]").forEach((b) => b.onclick = () => {
    st.bg = b.dataset.v; saveSettings({ bg: st.bg }); queueRender();
  });
  $("bgColor").oninput = (e) => { st.color = e.target.value; st.bg = "custom"; saveSettings({ bg: "custom", color: st.color }); queueRender(); };

  $("zoom").oninput = (e) => { st.zoom = Number(e.target.value); queueRender(); };
  $("rotL").onclick = () => { st.rot = (st.rot + 270) % 360; buildOriented(); resetView(); queueRender(); };
  $("rotR").onclick = () => { st.rot = (st.rot + 90) % 360; buildOriented(); resetView(); queueRender(); };
  $("flipH").onclick = () => { st.flipH = !st.flipH; buildOriented(); queueRender(); };
  $("flipV").onclick = () => { st.flipV = !st.flipV; buildOriented(); queueRender(); };
  $("center").onclick = () => { resetView(); queueRender(); };
  $("keysBtn").onclick = () => { st.keys = !st.keys; saveSettings({ keys: st.keys }); refreshUi(); };

  const adj = [["adjBright", "bright"], ["adjContrast", "contrast"], ["adjSat", "sat"]];
  for (const [id, key] of adj) $(id).oninput = (e) => { st.adj[key] = Number(e.target.value); $(id + "V").textContent = e.target.value; queueRender(); };
  $("adjGray").onclick = () => { st.adj.gray = !st.adj.gray; $("adjGray").classList.toggle("on", st.adj.gray); queueRender(); };
  $("adjReset").onclick = () => {
    st.adj = { bright: 100, contrast: 100, sat: 100, gray: false };
    for (const [id, key] of adj) { $(id).value = st.adj[key]; $(id + "V").textContent = st.adj[key]; }
    $("adjGray").classList.remove("on");
    queueRender();
  };

  let drag = null;
  canvas.addEventListener("pointerdown", (e) => {
    if (!st.img || st.mode === "stretch") return;
    drag = { x: e.clientX, y: e.clientY, ox: st.offX, oy: st.offY, scale: W / canvas.getBoundingClientRect().width };
    canvas.setPointerCapture(e.pointerId);
    canvas.classList.add("dragging");
  });
  canvas.addEventListener("pointermove", (e) => {
    if (!drag) return;
    st.offX = drag.ox + (e.clientX - drag.x) * drag.scale;
    st.offY = drag.oy + (e.clientY - drag.y) * drag.scale;
    queueRender();
  });
  const endDrag = () => { drag = null; canvas.classList.remove("dragging"); };
  canvas.addEventListener("pointerup", endDrag);
  canvas.addEventListener("pointercancel", endDrag);
  canvas.addEventListener("wheel", (e) => {
    if (!st.img || st.mode === "stretch") return;
    e.preventDefault();
    st.zoom = Math.max(1, Math.min(4, st.zoom * (e.deltaY < 0 ? 1.08 : 1 / 1.08)));
    $("zoom").value = st.zoom;
    queueRender();
  }, { passive: false });

  const stage = $("stage");
  let depth = 0;
  stage.addEventListener("dragenter", (e) => { e.preventDefault(); depth++; stage.classList.add("drag"); });
  stage.addEventListener("dragover", (e) => e.preventDefault());
  stage.addEventListener("dragleave", () => { if (--depth <= 0) { depth = 0; stage.classList.remove("drag"); } });
  stage.addEventListener("drop", (e) => {
    e.preventDefault(); depth = 0; stage.classList.remove("drag");
    loadFile(e.dataTransfer.files[0]);
  });
  document.addEventListener("dragover", (e) => e.preventDefault());
  document.addEventListener("drop", (e) => e.preventDefault());

  document.addEventListener("paste", (e) => {
    for (const it of e.clipboardData.items) {
      if (it.type.startsWith("image/")) { loadFile(it.getAsFile()); e.preventDefault(); return; }
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.target.tagName === "INPUT" && e.target.type !== "range") return;
    const c = e.ctrlKey || e.metaKey;
    if (c && e.key === "o") { e.preventDefault(); openPicker(); }
    else if (c && e.key === "Enter") { e.preventDefault(); send(); }
    else if (c && e.key === "e") { e.preventDefault(); exportPng(); }
    else if (!c && e.key === "r") $("rotR").click();
    else if (!c && e.key === "0") $("center").click();
  });

  $("bri").oninput = (e) => setBrightness(e.target.value);
  document.querySelectorAll("#briPresets button").forEach((b) => b.onclick = () => setBrightness(b.dataset.v));
  document.querySelectorAll(".action").forEach((b) => b.onclick = async () => {
    const r = await api.control(b.dataset.act);
    if (r && r.ok) toast({ logo: "Splash screen", wake: "On", sleep: "Off" }[b.dataset.act], "ok");
    else toast("No deck", "bad");
  });
  $("refreshBtn").onclick = () => { st.device = undefined; poll(); };
  $("copyRule").onclick = async () => {
    try { await navigator.clipboard.writeText($("udevRule").textContent); toast("Copied", "ok"); }
    catch { toast("Copy failed", "bad"); }
  };
}

async function init() {
  api = window.pywebview.api;
  bind();
  drawOverlay();
  st.settings = (await api.settings()) || {};
  const s = st.settings;
  if (s.bg) st.bg = s.bg;
  if (s.color) { st.color = s.color; $("bgColor").value = s.color; }
  if (s.keys) st.keys = true;
  setBrightness(s.brightness ?? 70, false);
  render();
  await poll();
  loadLibrary();
  setInterval(poll, 2000);
}

if (window.pywebview && window.pywebview.api) init();
else window.addEventListener("pywebviewready", init);
