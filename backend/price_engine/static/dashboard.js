'use strict';
const $ = (id) => document.getElementById(id);
let listings = [];
function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = String(text);
  if (className) element.className = className;
  return element;
}
function chart(values) {
  if (!Array.isArray(values) || values.length < 2) return node('span', 'Not enough data', 'muted');
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.classList.add('spark');
  svg.setAttribute('viewBox', '0 0 108 37');
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', `Recent values from ${values[0]} to ${values[values.length - 1]} paisa`);
  const min = Math.min(...values), max = Math.max(...values), range = Math.max(max - min, 1);
  const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  const points = values.map((v, i) => `${(i / (values.length - 1) * 105 + 1).toFixed(1)} ${(33 - (v - min) / range * 29).toFixed(1)}`);
  path.setAttribute('d', 'M ' + points.join(' L '));
  svg.appendChild(path);
  return svg;
}
function render() {
  const q = $('filter').value.trim().toLowerCase();
  const shown = listings.filter(x => `${x.name} ${x.retailer}`.toLowerCase().includes(q));
  const body = $('listings');
  body.replaceChildren();
  for (const item of shown) {
    const row = node('tr');
    const product = node('td');
    product.append(node('div', item.name, 'item-name'), node('div', item.retailer, 'item-retailer'));
    const price = node('td');
    price.append(node('div', item.price_display || '—', 'item-price'));
    if (item.stale && item.status === 'VALID_PRICE') price.append(node('span', 'STALE · not a live quote', 'stale'));
    const status = node('td');
    const statusClass = {'VALID_PRICE':'valid','OUT_OF_STOCK':'out','QUARANTINED':'quarantine'}[item.status] || 'unknown';
    status.append(node('span', item.status.replaceAll('_', ' '), `badge ${statusClass}`));
    const trend = node('td'); trend.append(chart(item.trend_paisa));
    const time = node('td', item.observed_at ? new Date(item.observed_at).toLocaleString() : 'No observations', 'time');
    row.append(product, price, status, trend, time);
    body.append(row);
  }
  if (!shown.length) {
    const row = node('tr'); const cell = node('td', 'No matching listings found.', 'empty');
    cell.colSpan = 5; row.append(cell); body.append(row);
  }
  $('count').textContent = `Showing ${shown.length} of ${listings.length} loaded listings`;
}
async function getJSON(url) {
  const response = await fetch(url, {cache:'no-store'});
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}
async function refresh() {
  const btn = $('refresh'); btn.disabled = true;
  try {
    const [records, health] = await Promise.all([getJSON('/api/listings?limit=100'), getJSON('/api/health')]);
    listings = records.items;
    $('metric-listings').textContent = listings.length;
    $('metric-valid').textContent = listings.filter(x => x.status === 'VALID_PRICE').length;
    $('metric-out').textContent = listings.filter(x => x.status === 'OUT_OF_STOCK').length;
    $('metric-quarantine').textContent = listings.filter(x => x.status === 'QUARANTINED').length;
    $('db-status').textContent = health.ok ? 'READABLE' : 'UNAVAILABLE';
    $('scheduler-status').textContent = health.scheduler.replaceAll('_', ' ');
    $('last-check').textContent = health.last_observation_utc ? new Date(health.last_observation_utc).toLocaleString() : 'No observations';
    $('synced').textContent = 'Synced ' + new Date().toLocaleTimeString();
    render();
  } catch (_error) {
    $('synced').textContent = 'Unable to read local database';
    $('db-status').textContent = 'UNAVAILABLE';
    $('scheduler-status').textContent = 'NOT VERIFIED';
    $('count').textContent = 'No data loaded';
    listings = []; render();
  } finally { btn.disabled = false; }
}
$('refresh').addEventListener('click', refresh);
$('filter').addEventListener('input', render);
refresh();
window.setInterval(() => {if (!document.hidden) refresh();}, 30000);
