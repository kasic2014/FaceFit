import fs from "node:fs/promises";

const baseUrl = process.env.FACEFIT_REVIEW_URL ?? "http://127.0.0.1:4173";
const outputDir = "output/design-review/screens";
const routes = [
  ["login", "/login"],
  ["signup", "/signup"],
  ["onboarding", "/onboarding"],
  ["equipment", "/equipment"],
  ["voice-profile", "/voice-profile"],
  ["consent", "/consent"],
  ["session-live", "/session/live"],
  ["analysis", "/analysis"],
  ["report", "/report"],
  ["dashboard", "/dashboard"],
  ["record-detail", "/records/naver-backend-20260710"],
  ["pricing", "/pricing"],
  ["policy", "/policy"],
  ["not-found", "/route-that-does-not-exist"],
];

await fs.mkdir(outputDir, { recursive: true });
const targets = await (await fetch("http://127.0.0.1:9222/json/list")).json();
const target = targets.find((item) => item.type === "page");
if (!target?.webSocketDebuggerUrl) throw new Error("Chrome CDP target not found");

const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => { socket.addEventListener("open", resolve, { once: true }); socket.addEventListener("error", reject, { once: true }); });
let sequence = 0;
const pending = new Map();
socket.addEventListener("message", (event) => {
  const message = JSON.parse(event.data);
  if (message.id && pending.has(message.id)) {
    pending.get(message.id)(message);
    pending.delete(message.id);
  }
});
const command = (method, params = {}) => new Promise((resolve) => {
  const id = ++sequence;
  pending.set(id, resolve);
  socket.send(JSON.stringify({ id, method, params }));
});

await command("Page.enable");
await command("Runtime.enable");
await command("Emulation.setDeviceMetricsOverride", { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
for (const [name, route] of routes) {
  await command("Page.navigate", { url: `${baseUrl}${route}` });
  await new Promise((resolve) => setTimeout(resolve, name === "analysis" ? 9500 : 1400));
  if (name === "session-live") {
    await command("Runtime.evaluate", { expression: "sessionStorage.setItem('facefit-consent-confirmed','true')" });
    await command("Page.navigate", { url: `${baseUrl}${route}` });
    await new Promise((resolve) => setTimeout(resolve, 1600));
  }
  const result = await command("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  await fs.writeFile(`${outputDir}/${name}.png`, Buffer.from(result.result.data, "base64"));
}
socket.close();
console.log(`Captured ${routes.length} desktop screens to ${outputDir}`);
