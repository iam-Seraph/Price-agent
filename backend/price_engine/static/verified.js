"use strict";

const $ = (id) => document.getElementById(id);
let currentOffer = null;

async function api(path) {
  const response = await fetch(path, { cache: "no-store" });
  let body;
  try { body = await response.json(); } catch { throw new Error("Server returned invalid JSON"); }
  if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Request failed");
  return body;
}

function cell(row, value) {
  const td = document.createElement("td");
  td.textContent = String(value ?? "—");
  row.appendChild(td);
  return td;
}

function money(minor, currency) {
  if (!Number.isSafeInteger(minor) || minor < 0) return "—";
  const value = (minor / 100).toLocaleString("en-IN", {minimumFractionDigits: 2, maximumFractionDigits: 2});
  return (currency === "INR" ? "₹" : currency === "USD" ? "$" : "") + value;
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString();
}

function showMessage(target, message) {
  $(target).textContent = message;
}

function drawHistory(points, currency) {
  const canvas = $("history-chart");
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const W = canvas.width, H = canvas.height;
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = "#172334";
  ctx.fillRect(0, 0, W, H);
  const accepted = points.filter(p => Number.isSafeInteger(p.price_minor) && p.price_minor > 0);
  if (accepted.length === 0) {
    ctx.fillStyle = "#9fb0c6";
    ctx.font = "18px system-ui";
    ctx.fillText("No stored observations for this period", 24, H / 2);
    return;
  }
  const costs = accepted.map(x => x.price_minor);
  let lo = Math.min(...costs), hi = Math.max(...costs);
  const padding = Math.max(1, Math.ceil((hi - lo) * 0.1));
  lo -= padding; hi += padding;
  const x = i => 55 + (i / Math.max(1, accepted.length - 1)) * (W - 75);
  const y = v => H - 38 - ((v - lo) / Math.max(1, hi - lo)) * (H - 70);
  ctx.strokeStyle = "#46556a"; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(55, 20); ctx.lineTo(55, H - 38); ctx.lineTo(W - 20, H - 38); ctx.stroke();
  ctx.fillStyle = "#a8bbd0"; ctx.font = "14px system-ui";
  ctx.fillText(money(hi, currency), 6, 19);
  ctx.fillText(money(Math.max(0, lo), currency), 6, H - 15);
  ctx.beginPath();
  accepted.forEach((point, i) => {
    if (i === 0) ctx.moveTo(x(i), y(point.price_minor));
    else ctx.lineTo(x(i), y(point.price_minor));
  });
  ctx.strokeStyle = "#5cd8c2"; ctx.lineWidth = 3; ctx.stroke();
  accepted.forEach((point, i) => {
    ctx.beginPath();
    ctx.arc(x(i), y(point.price_minor), point.stock === "IN_STOCK" ? 4 : 2, 0, Math.PI * 2);
    ctx.fillStyle = point.stock === "IN_STOCK" ? "#5cd8c2" : "#eab65e";
    ctx.fill();
  });
}

async function chooseOffer(offer) {
  currentOffer = offer;
  $("selection").textContent = offer.title + " — " + offer.merchant;
  $("learning-selected").textContent = "Selected for feedback: " + offer.title + " — " + offer.merchant;
  for (const card of document.querySelectorAll(".offer-card")) {
    const selected = card.dataset.offerId === offer.offer_id;
    card.classList.toggle("is-selected", selected);
    const inspect = card.querySelector(".offer-actions button");
    if (inspect) inspect.setAttribute("aria-pressed", String(selected));
  }
  $("currency").value = offer.currency;
  showMessage("decision", "Select Analyze to evaluate source-backed deal rules.");
  $("checks").replaceChildren();
  await Promise.all([refreshHistory(), refreshIntelligence()]);
}

async function refreshHistory() {
  if (!currentOffer) return;
  try {
    const result = await api("/api/verified/offers/" + encodeURIComponent(currentOffer.offer_id) + "/history?days=30&limit=300");
    drawHistory(result.observations, result.currency);
    $("history-text").textContent = result.observations.length + " recorded provider observations in the past 30 days. Unknown or out-of-stock prices do not qualify as genuine deal evidence.";
  } catch (error) {
    drawHistory([], currentOffer.currency);
    showMessage("history-text", error.message);
  }
}

async function refreshIntelligence() {
  if (!currentOffer) return;
  const id = currentOffer.offer_id;
  $("intelligence-results").textContent = "Reading stored history…";
  $("intelligence-days").textContent = "";
  try {
    const data = await api("/api/verified/offers/" + encodeURIComponent(id) + "/intelligence?days=90");
    if (!currentOffer || currentOffer.offer_id !== id) return;
    const a = data.anomaly, t = data.trend, q = data.evidence;
    $("intelligence-results").textContent =
      "Anomaly: " + a.status.replaceAll("_", " ") +
      " • Observed trend: " + t.direction.replaceAll("_", " ") +
      " • Evidence completeness: " + q.evidence_completeness_score + "/100";
    $("intelligence-days").textContent =
      data.series.observed_days + " observed in-stock days in the last 90 days. " +
      data.series.records_discarded + " unknown/out-of-stock records excluded. " +
      (data.series.truncated_to_latest_1000 ? "History truncated to 1,000 records. " : "") +
      "Scores do not establish merchant trust or predict future prices.";
  } catch (error) {
    if (currentOffer && currentOffer.offer_id === id)
      $("intelligence-results").textContent = "Source evidence unavailable: " + error.message;
  }
}

function makeIcon(href) {
  const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  icon.setAttribute("aria-hidden", "true");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", href);
  icon.appendChild(use);
  return icon;
}

function safeSourceLink(value) {
  if (typeof value !== "string" || value.length > 2048) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}

function renderOfferCard(offer) {
  const card = document.createElement("article");
  card.className = "offer-card";
  card.setAttribute("role", "listitem");
  card.dataset.offerId = String(offer.offer_id);
  const visual = document.createElement("div");
  visual.className = "offer-art";
  const stamp = document.createElement("span");
  stamp.className = "art-label";
  stamp.textContent = "SAVED OBSERVATION";
  visual.appendChild(stamp);
  const glyph = document.createElement("span");
  glyph.className = "art-mark";
  glyph.setAttribute("aria-hidden", "true");
  // Abstract lettermark only. Do not invent retailer images or product photos.
  const words = String(offer.title || "").trim().split(/\s+/);
  glyph.textContent = words.slice(0, 2).map(word => word[0] || "").join("").toUpperCase().slice(0, 2) || "PS";
  visual.appendChild(glyph);
  const source = document.createElement("span");
  source.className = "art-source";
  source.textContent = "PROVIDER-REPORTED";
  visual.appendChild(source);
  const stock = document.createElement("span");
  stock.className = "stock-tag";
  stock.textContent = String(offer.stock || "UNKNOWN").replaceAll("_", " ");
  if (offer.stock === "IN_STOCK") stock.classList.add("in-stock");
  if (offer.stock === "OUT_OF_STOCK") stock.classList.add("out-stock");
  visual.appendChild(stock);
  card.appendChild(visual);

  const body = document.createElement("div");
  body.className = "offer-content";
  const overline = document.createElement("div");
  overline.className = "offer-eyebrow";
  overline.textContent = offer.currency === "INR" ? "GOOGLE SHOPPING • INR" :
                         offer.currency === "USD" ? "GOOGLE SHOPPING • USD" :
                         "PROVIDER-REPORTED LISTING";
  body.appendChild(overline);
  const heading = document.createElement("h3");
  heading.className = "offer-title";
  const productURL = safeSourceLink(offer.product_url);
  if (productURL) {
    const a = document.createElement("a");
    a.href = productURL;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = offer.title || "Untitled provider offer";
    a.setAttribute("aria-label", (offer.title || "Untitled provider offer") + " — open source listing in a new tab");
    heading.appendChild(a);
  } else {
    heading.textContent = offer.title || "Untitled provider offer";
  }
  body.appendChild(heading);
  const merchant = document.createElement("p");
  merchant.className = "offer-merchant";
  merchant.textContent = "Reported merchant · " + (offer.merchant || "Unknown");
  body.appendChild(merchant);
  const bottom = document.createElement("div");
  bottom.className = "offer-bottom";
  const priceBlock = document.createElement("div");
  const label = document.createElement("span");
  label.className = "caption";
  label.textContent = "LAST REPORTED PRICE";
  const price = document.createElement("strong");
  price.textContent = money(offer.latest_price_minor, offer.currency);
  priceBlock.append(label, price);
  const date = document.createElement("small");
  date.textContent = formatDate(offer.last_observed_at);
  bottom.append(priceBlock, date);
  body.appendChild(bottom);
  const actions = document.createElement("div");
  actions.className = "offer-actions";
  const inspect = document.createElement("button");
  inspect.type = "button";
  inspect.textContent = "Inspect evidence";
  inspect.setAttribute("aria-pressed", "false");
  inspect.addEventListener("click", () => {
    chooseOffer(offer);
    document.getElementById("analysis").scrollIntoView({behavior: "auto", block: "start"});
  });
  actions.appendChild(inspect);
  if (productURL) {
    const link = document.createElement("a");
    link.href = productURL;
    link.className = "external-offer";
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.title = "Open source listing (external)";
    link.setAttribute("aria-label", "Open " + (offer.title || "source listing") + " externally");
    link.appendChild(makeIcon("#i-arrow"));
    actions.appendChild(link);
  }
  body.appendChild(actions);
  card.appendChild(body);
  return card;
}

async function renderOverview() {
  try {
    const [stats, data] = await Promise.all([
      api("/api/verified/status"),
      api("/api/verified/offers?limit=100")
    ]);
    $("offer-count").textContent = stats.offers;
    $("observation-count").textContent = stats.observations;
    $("latest-record").textContent = formatDate(stats.last_observed_at);
    $("sidebar-offer-count").textContent = stats.offers;
    const grid = $("offers-body");
    grid.replaceChildren();
    for (const offer of data.offers) {
      const card = renderOfferCard(offer);
      if (currentOffer && currentOffer.offer_id === offer.offer_id) {
        card.classList.add("is-selected");
        card.querySelector(".offer-actions button").setAttribute("aria-pressed", "true");
      }
      grid.appendChild(card);
    }
    if (!data.offers.length) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      const title = document.createElement("strong");
      title.textContent = "No source-backed offers stored yet";
      const hint = document.createElement("p");
      hint.textContent = "Search a product above to retrieve provider-reported offers. The dashboard never fills empty states with fictional products.";
      empty.append(title, hint);
      grid.appendChild(empty);
    }
    showMessage("overview-status",
      "Local database refreshed. All displayed prices are timestamped source-attributed observations.");
  } catch (error) {
    showMessage("overview-status", "Unable to load local source records: " + error.message);
  }
}

$("budget-form").addEventListener("submit", async event => {
  event.preventDefault();
  if (!currentOffer) { showMessage("decision", "Select an offer first."); return; }
  const budget = $("budget").value.trim();
  if (!/^[0-9,]+(\.[0-9]{1,2})?$/.test(budget)) {
    showMessage("decision", "Enter a valid numeric budget."); return;
  }
  try {
    const url = "/api/verified/offers/" + encodeURIComponent(currentOffer.offer_id) +
      "/analysis?budget=" + encodeURIComponent(budget) +
      "&currency=" + encodeURIComponent($("currency").value);
    const result = await api(url);
    $("decision").textContent = result.decision + " — Current price " + result.price +
      ". 30-day source samples: " + result.sample_count_30d +
      " across " + result.unique_days_30d + " days.";
    $("decision").className = result.decision === "ALERT" ? "good" : "neutral";
    const checks = $("checks"); checks.replaceChildren();
    for (const [name, ok] of Object.entries(result.checks)) {
      const li = document.createElement("li");
      li.textContent = (ok ? "PASS" : "UNVERIFIED / FAIL") + " — " + name.replaceAll("_", " ");
      li.className = ok ? "good" : "warn";
      checks.appendChild(li);
    }
  } catch (error) {
    showMessage("decision", "Analysis unavailable: " + error.message);
    $("checks").replaceChildren();
  }
});

renderOverview();



async function postAPI(path, data) {
  const response = await fetch(path, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    cache: "no-store",
    credentials: "same-origin",
    body: JSON.stringify(data || {})
  });
  let body;
  try { body = await response.json(); } catch { throw new Error("Server returned invalid JSON"); }
  if (!response.ok) {
    throw new Error(typeof body.detail === "string" ? body.detail : "Request failed");
  }
  return body;
}

function validBudget(value) {
  return /^[0-9,]+(\.[0-9]{1,2})?$/.test(value) && value.length <= 30;
}

$("search-form").addEventListener("submit", async event => {
  event.preventDefault();
  const query = $("search-query").value.trim();
  const budget = $("search-budget").value.trim();
  const currency = $("search-currency").value;
  if (query.length < 2 || query.length > 120 || !validBudget(budget)) {
    showMessage("search-status", "Use a 2–120 character query and valid positive amount.");
    return;
  }
  const submit = $("search-form").querySelector("button[type=submit]");
  submit.disabled = true;
  showMessage("search-status", "Requesting source-attributed offers…");
  try {
    const result = await postAPI("/api/verified/search", {query, budget, currency, limit: 5});
    showMessage("search-status",
      "Retrieved " + result.analyses.length + " matching offers; stored " +
      result.inserted + " new observations. Provider-reported only.");
    await renderOverview();
  } catch (error) {
    showMessage("search-status", "Search unavailable: " + error.message);
  } finally {
    submit.disabled = false;
  }
});

async function refreshWatches() {
  const tbody = $("watches-body");
  try {
    const response = await api("/api/verified/watches?limit=100");
    tbody.replaceChildren();
    for (const watch of response.watches) {
      const row = document.createElement("tr");
      cell(row, watch.query_text);
      cell(row, money(watch.budget_minor, watch.currency));
      cell(row, watch.enabled ? "Enabled (worker required)" : "Disabled");
      const actions = document.createElement("td");
      if (watch.enabled) {
        const disable = document.createElement("button");
        disable.type = "button"; disable.textContent = "Disable";
        disable.addEventListener("click", async () => {
          if (!window.confirm("Disable this price watch?")) return;
          try {
            await postAPI("/api/verified/watches/" + encodeURIComponent(watch.watch_id) + "/disable", {});
            showMessage("watch-status", "Watch disabled.");
            await refreshWatches();
          } catch (error) { showMessage("watch-status", error.message); }
        });
        actions.appendChild(disable);
        for (const channel of ["EMAIL", "TELEGRAM"]) {
          const button = document.createElement("button");
          button.type = "button"; button.textContent = "Enable " + channel;
          button.addEventListener("click", async () => {
            const description = "Enable " + channel + " alerts for " +
              watch.query_text + "? This requires private server credentials and an explicitly running delivery worker.";
            if (!window.confirm(description)) return;
            try {
              await postAPI("/api/verified/alerts/channel", {
                watch_id: watch.watch_id, channel, enabled: true, confirmed: true
              });
              showMessage("watch-status", channel + " alerts enabled. Delivery worker is not automatically started.");
            } catch (error) { showMessage("watch-status", error.message); }
          });
          actions.appendChild(button);
        }
      }
      row.appendChild(actions);
      tbody.appendChild(row);
    }
    if (response.watches.length === 0) {
      const row = document.createElement("tr"), td = document.createElement("td");
      td.colSpan = 4; td.textContent = "No saved watch queries.";
      row.appendChild(td); tbody.appendChild(row);
    }
  } catch (error) {
    showMessage("watch-status", "Watchlist unavailable: " + error.message);
  }
}

$("watch-form").addEventListener("submit", async event => {
  event.preventDefault();
  const query = $("watch-query").value.trim();
  const budget = $("watch-budget").value.trim();
  const currency = $("watch-currency").value;
  const interval_minutes = Number($("watch-interval").value);
  if (query.length < 2 || query.length > 120 || !validBudget(budget)) {
    showMessage("watch-status", "Use a valid query and numeric price threshold.");
    return;
  }
  try {
    const result = await postAPI("/api/verified/watches", {
      query, budget, currency, interval_minutes
    });
    showMessage("watch-status",
      "Watch saved: " + result.watch_id + ". Monitoring has not been started automatically.");
    await refreshWatches();
  } catch (error) {
    showMessage("watch-status", "Unable to save watch: " + error.message);
  }
});

refreshWatches();


$("compare-form").addEventListener("submit", async event => {
  event.preventDefault();
  const query = $("compare-query").value.trim();
  const budget = $("compare-budget").value.trim();
  const currency = $("compare-currency").value;
  if (query.length < 2 || query.length > 120 || !validBudget(budget)) {
    showMessage("compare-status", "Enter a valid search term and price threshold.");
    return;
  }
  const url = "/api/verified/research?q=" + encodeURIComponent(query) +
      "&budget=" + encodeURIComponent(budget) +
      "&currency=" + encodeURIComponent(currency) + "&limit=30";
  try {
    const result = await api(url);
    const rows = result.comparison.rows, tbody = $("comparison-body");
    tbody.replaceChildren();
    const byId = new Map(result.explanations.results.map(x => [x.offer_id, x]));
    for (const offer of rows) {
      const tr = document.createElement("tr");
      cell(tr, offer.title);
      cell(tr, offer.merchant);
      cell(tr, offer.price_display);
      cell(tr, offer.freshness);
      const details = byId.get(offer.offer_id);
      cell(tr, details ? details.research_class.replaceAll("_", " ") : "Unknown");
      tbody.appendChild(tr);
    }
    if (rows.length === 0) {
      const tr = document.createElement("tr"), td = document.createElement("td");
      td.colSpan = 5;
      td.textContent = "No matching source-attributed offers are stored yet.";
      tr.appendChild(td); tbody.appendChild(tr);
    }
    const learning = result.research.personalization;
    if (learning && learning.enabled) {
      const byOffer = new Map(result.research.results.map(x => [x.offer_id, x]));
      const ranking = learning.ranked_offer_ids.slice(0, 5).map(id => {
        const item = byOffer.get(id);
        return item ? item.title + " (" + (item.user_preference || "no vote") + ")" : "";
      }).filter(Boolean);
      $("learning-ranked").textContent = ranking.length
        ? "Your preference order (budget-eligible listings first): " + ranking.join(" • ")
        : "No matching source-attributed listings.";
    } else {
      $("learning-ranked").textContent = "Opt-in learning is off. Standard price ranking remains unchanged.";
    }
    showMessage("compare-status", "Found " + rows.length + " source-attributed listings from " +
      result.comparison.merchant_count + " merchants. Prices are NOT guaranteed for equivalent variants.");
  } catch (error) {
    $("comparison-body").replaceChildren();
    showMessage("compare-status", "Comparison unavailable: " + error.message);
  }
});


let plannedCommand = null;
let commandPlan = null;

$("assistant-command").addEventListener("input", () => {
  plannedCommand = null;
  commandPlan = null;
  $("assistant-confirm").disabled = true;
  $("assistant-preview").textContent = "";
});

$("assistant-plan-form").addEventListener("submit", async event => {
  event.preventDefault();
  plannedCommand = null;
  commandPlan = null;
  $("assistant-confirm").disabled = true;
  const command = $("assistant-command").value.trim();
  try {
    const plan = await postAPI("/api/verified/assistant/plan", {command});
    plannedCommand = command;
    commandPlan = plan;
    $("assistant-preview").textContent = JSON.stringify(plan, null, 2);
    showMessage("assistant-status",
      plan.needs_explicit_confirmation
        ? "Preview created. Watch creation requires an additional confirmation."
        : "Read-only comparison is ready to run.");
    $("assistant-confirm").disabled = false;
  } catch (error) {
    $("assistant-preview").textContent = "";
    showMessage("assistant-status", "Command not recognized: " + error.message);
  }
});

$("assistant-confirm").addEventListener("click", async () => {
  if (!plannedCommand || !commandPlan) return;
  if ($("assistant-command").value.trim() !== plannedCommand) {
    showMessage("assistant-status", "Command changed. Preview it again.");
    $("assistant-confirm").disabled = true;
    return;
  }
  const requiresConsent = commandPlan.needs_explicit_confirmation;
  if (requiresConsent && !window.confirm(
      "Save this product watch? Monitoring and notifications will NOT start automatically.")) return;
  $("assistant-confirm").disabled = true;
  try {
    const output = await postAPI("/api/verified/assistant/execute", {
      command: plannedCommand, confirmed: Boolean(requiresConsent)
    });
    if (output.status === "WATCH_SAVED") {
      showMessage("assistant-status", "Watch saved without starting monitoring.");
      $("assistant-preview").textContent = JSON.stringify(output, null, 2);
      await refreshWatches();
    } else if (output.status === "RESEARCH_COMPLETED") {
      const overview = {
        status: output.status,
        matches: output.research.matching_offers,
        budget_candidates: output.research.budget_candidates,
        listings_are_not_equivalent: true,
        top_observed_listings: output.comparison.rows.slice(0, 5)
      };
      $("assistant-preview").textContent = JSON.stringify(overview, null, 2);
      showMessage("assistant-status", "Read-only saved-offer comparison completed.");
    } else {
      showMessage("assistant-status", output.status || "No command executed");
    }
  } catch (error) {
    showMessage("assistant-status", "Execution unavailable: " + error.message);
  } finally {
    plannedCommand = null;
    commandPlan = null;
  }
});


async function refreshConfiguration() {
  try {
    const info = await api("/api/verified/configuration");
    const provider = info.providers.google_shopping_serpapi;
    const groq = info.providers.groq_explanations;
    showMessage("api-config-status", "SerpApi: " + provider.replaceAll("_", " ") +
      " • Groq: " + groq.replaceAll("_", " ") +
      ". No live credential or provider network check was performed.");
  } catch (error) {
    showMessage("api-config-status", "Credential status unavailable: " + error.message);
  }
}

let learningEnabled = false;

async function refreshLearning() {
  try {
    const state = await api("/api/verified/learning");
    learningEnabled = Boolean(state.enabled);
    showMessage("learning-status",
      (learningEnabled ? "Enabled" : "Disabled") +
      " • " + state.saved_feedback_count + " saved offer preference(s). " +
      "Stored locally, no model training or background retrieval.");
  } catch (error) {
    learningEnabled = false;
    showMessage("learning-status", "Local learning unavailable: " + error.message);
  }
}

$("learning-enable").addEventListener("click", async () => {
  if (!window.confirm("Enable local preference memory for offers you explicitly rate?")) return;
  try {
    await postAPI("/api/verified/learning/opt-in", {enabled: true, confirmed: true});
    await refreshLearning();
  } catch (error) { showMessage("learning-feedback-status", error.message); }
});

$("learning-disable").addEventListener("click", async () => {
  try {
    await postAPI("/api/verified/learning/opt-in", {enabled: false, confirmed: true});
    await refreshLearning();
    $("learning-ranked").textContent = "Preferences paused; standard price order is used.";
  } catch (error) { showMessage("learning-feedback-status", error.message); }
});

$("learning-clear").addEventListener("click", async () => {
  if (!window.confirm("Permanently erase ALL saved offer feedback and disable local learning? Historical prices remain unchanged.")) return;
  try {
    await postAPI("/api/verified/learning/clear", {confirmed: true});
    await refreshLearning();
    $("learning-ranked").textContent = "Offer preferences cleared.";
    showMessage("learning-feedback-status", "All local preference feedback erased.");
  } catch (error) { showMessage("learning-feedback-status", error.message); }
});

for (const [buttonId, preference] of [["learning-prefer", "PREFER"], ["learning-avoid", "AVOID"]]) {
  $(buttonId).addEventListener("click", async () => {
    if (!currentOffer) { showMessage("learning-feedback-status", "Select a saved offer first."); return; }
    if (!learningEnabled) { showMessage("learning-feedback-status", "Enable local learning before rating."); return; }
    try {
      await postAPI("/api/verified/learning/feedback", {
        offer_id: currentOffer.offer_id, preference
      });
      showMessage("learning-feedback-status", preference + " saved for " + currentOffer.title +
        ". Run a new comparison to see personalized ordering.");
      await refreshLearning();
    } catch (error) { showMessage("learning-feedback-status", error.message); }
  });
}

$("learning-forget").addEventListener("click", async () => {
  if (!currentOffer) { showMessage("learning-feedback-status", "Select a saved offer first."); return; }
  try {
    const result = await postAPI("/api/verified/learning/forget", {
      offer_id: currentOffer.offer_id
    });
    showMessage("learning-feedback-status",
      result.removed ? "Feedback for selected offer erased." : "No saved feedback for this offer.");
    await refreshLearning();
  } catch (error) { showMessage("learning-feedback-status", error.message); }
});

refreshConfiguration();
refreshLearning();


// The only new interactions are presentation shortcuts. Server actions and
// consent requirements still use their existing verified API endpoints.
for (const chip of document.querySelectorAll("[data-search]")) {
  chip.addEventListener("click", () => {
    $("search-query").value = chip.dataset.search;
    $("search-query").focus();
  });
}
for (const example of document.querySelectorAll("[data-command]")) {
  example.addEventListener("click", () => {
    $("assistant-command").value = example.dataset.command;
    $("assistant-command").dispatchEvent(new Event("input", {bubbles: true}));
    $("assistant-command").focus();
  });
}
$("offers-refresh").addEventListener("click", () => {
  renderOverview();
});
