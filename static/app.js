const $ = (id) => document.getElementById(id);
const HASH_RE = /^0x[0-9a-fA-F]{64}$/;
const ADDR_RE = /^0x[0-9a-fA-F]{40}$/;
const LABELS = { high: "High risk", medium: "Worth reviewing", low: "Nothing risky found" };

$("form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const address = $("address").value.trim();
  $("result").hidden = true;

  if (!ADDR_RE.test(address)) {
    $("status").textContent = "Enter a valid address: 0x followed by 40 hex characters.";
    return;
  }

  $("go").disabled = true;
  $("status").textContent = "";
  $("loading").hidden = false;

  try {
    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ address :walletAddress }),
    });
    const data = await res.json();
    if (!res.ok) {
      $("status").textContent = data.error || "Something went wrong. Try again.";
      return;
    }
    render(data);
  }    catch (err) {
    console.error(err);
    $("status").textContent = "Display error: " + err.message;
  } finally {
    $("loading").hidden = true;
    $("go").disabled = false;
  }
});

function render(d) {
  const level = LABELS[d.level] ? d.level : "low";
  $("addr").textContent = d.address;
  $("count").textContent = String(d.findings.length);
  $("blocks").textContent = Number(d.scanned_blocks).toLocaleString();
  $("level").textContent = LABELS[level];
  $("level").dataset.level = level;
  $("summary").textContent = d.summary;
  $("mode").textContent = d.ai ? "AI-written from verified findings" : "Rule-based explanation";
  $("empty").hidden = d.findings.length > 0;

  const list = $("list");
  list.replaceChildren();
  d.findings.forEach((f) => {
    const li = document.createElement("li");
    li.className = "f";
    li.dataset.sev = f.severity === "high" ? "high" : "medium";

    const title = document.createElement("strong");
    title.textContent = f.title;
    const description = document.createElement("p");
    description.textContent = f.description || f.detail;
    const source = document.createElement("p");
    source.textContent = `Source: ${f.source}`;
    const confidence = document.createElement("p");
    confidence.textContent = `Confidence: ${f.confidence}`;
    const limitations = document.createElement("p");
    limitations.textContent = `Limitations: ${f.limitations}`;
    const meta = document.createElement("div");
    meta.className = "meta";
    meta.append("Method: rule-based. ");

    if (HASH_RE.test(f.tx_hash) && String(d.explorer_base).startsWith("https://")) {
      const a = document.createElement("a");
      a.href = d.explorer_base + f.tx_hash;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.textContent = "View the transaction";
      meta.append(a);
    }
    li.append(title, description, source, confidence, limitations, meta);
    list.append(li);
  });

  $("result").hidden = false;
  $("findings").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// Pointer parallax for the 3D orb (skipped when the user prefers reduced motion).
const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const hero = $("hero");
if (!still && hero) {
  let queued = false;
  hero.addEventListener("pointermove", (e) => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      const r = hero.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width - 0.5;
      const y = (e.clientY - r.top) / r.height - 0.5;
      hero.style.setProperty("--rx", (-y * 28).toFixed(1) + "deg");
      hero.style.setProperty("--ry", (x * 28).toFixed(1) + "deg");
      queued = false;
    });
  });
  hero.addEventListener("pointerleave", () => {
    hero.style.setProperty("--rx", "0deg");
    hero.style.setProperty("--ry", "0deg");
  });
}