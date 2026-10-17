// The only file you edit per environment.
const PROD_API = "https://vegandle.onrender.com";   // your Render address, no trailing slash
const COFFEE_URL = "https://buymeacoffee.com/YOUR-NAME"; // your Buy Me a Coffee page
const VERSION = "0.2.0-beta";

// Same-origin calls when served locally or by Render itself; PROD_API is used on Netlify.
const SAME_ORIGIN = ["localhost", "127.0.0.1"].includes(location.hostname) || location.hostname.endsWith(".onrender.com");
const API = SAME_ORIGIN ? "" : PROD_API.replace(/\/+$/, "");

async function playerCount() {
  try { return (await (await fetch(API + "/api/stats")).json()).players; } catch { return null; }
}
function playerId() {  // random id kept in this browser; only used to count players
  try {
    let id = localStorage.getItem("vegandle:player");
    if (!id) {
      id = crypto.randomUUID ? crypto.randomUUID() : Date.now() + Math.random().toString(16).slice(2) + "xxxxxxxx";
      localStorage.setItem("vegandle:player", id);
    }
    return id;
  } catch { return null; }
}
document.addEventListener("DOMContentLoaded", () => {
  const b = document.createElement("div");
  b.textContent = "Beta v" + VERSION.replace("-beta", "");
  b.style.cssText = "position:fixed;top:8px;right:10px;font:12px system-ui,sans-serif;opacity:.7;padding:2px 8px;border:1px solid currentColor;border-radius:10px";
  document.body.appendChild(b);
  if (!COFFEE_URL.includes("YOUR-NAME")) {
    const f = document.createElement("p");
    f.innerHTML = `<a href="${COFFEE_URL}" target="_blank" rel="noopener">☕ Buy me a coffee</a>`;
    f.style.cssText = "text-align:center;font-size:.9rem;margin-top:24px";
    (document.querySelector("main") || document.body).appendChild(f);
  }
});
