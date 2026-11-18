"use strict";

const byId = id => document.getElementById(id);
const pageSize = 25;
let offset = 0;
let requestSequence = 0;
let typingTimeout;

function cell(text) {
  const element = document.createElement("td");
  element.textContent = text || "—";
  return element;
}

async function fetchJSON(path) {
  const response = await fetch(path, {cache: "no-store"});
  if (!response.ok) throw new Error("HTTP " + response.status);
  return response.json();
}

async function loadStats() {
  const data = await fetchJSON("/api/catalog/stats");
  byId("total").textContent = data.products.toLocaleString();
  return data;
}

function renderResults(data) {
  const body = byId("catalog-results");
  body.replaceChildren();
  if (!data.items.length) {
    const row = document.createElement("tr");
    const empty = cell(data.ready
      ? "No matching products."
      : "Catalog not imported yet. See backend/README.md for import instructions.");
    empty.className = "empty";
    empty.colSpan = 5;
    row.append(empty);
    body.append(row);
  }

  for (const item of data.items) {
    const row = document.createElement("tr");
    const name = cell(item.name);
    name.className = "item-name";
    row.append(name, cell(item.brand), cell(item.category), cell(item.quantity));
    const linkCell = document.createElement("td");
    const link = document.createElement("a");
    link.href = item.source_url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = "View source";
    linkCell.append(link);
    row.append(linkCell);
    body.append(row);
  }

  const end = offset + data.items.length;
  byId("catalog-count").textContent = data.ready
    ? (data.items.length ? "Showing " + (offset + 1).toLocaleString() + "–" + end.toLocaleString() : "No results")
    : "Import required";
  byId("previous").disabled = offset === 0;
  byId("next").disabled = !data.has_more;
}

async function loadPage() {
  const seq = ++requestSequence;
  byId("synced").textContent = "Searching…";
  const q = byId("catalog-query").value.trim();
  const url = "/api/catalog/search?" + new URLSearchParams({
    q, limit: pageSize.toString(), offset: offset.toString()
  });
  try {
    const data = await fetchJSON(url);
    if (seq !== requestSequence) return;
    renderResults(data);
    byId("synced").textContent = "Local catalog · " + new Date().toLocaleTimeString();
  } catch (_error) {
    if (seq !== requestSequence) return;
    byId("synced").textContent = "Catalog unavailable";
    renderResults({ready: false, items: [], has_more: false});
  }
}

byId("catalog-query").addEventListener("input", () => {
  window.clearTimeout(typingTimeout);
  typingTimeout = window.setTimeout(() => {offset = 0; loadPage();}, 250);
});
byId("previous").addEventListener("click", () => {
  offset = Math.max(0, offset - pageSize);
  loadPage();
});
byId("next").addEventListener("click", () => {
  offset += pageSize;
  loadPage();
});
loadStats().catch(() => {byId("total").textContent = "—";});
loadPage();
