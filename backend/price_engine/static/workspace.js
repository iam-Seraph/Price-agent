'use strict';
const el = id => document.getElementById(id);
const make = (tag, value, className) => {
  const item = document.createElement(tag);
  if (value !== undefined && value !== null) item.textContent = String(value);
  if (className) item.className = className;
  return item;
};
async function api(path, options = {}) {
  const response = await fetch(path, {cache: 'no-store', ...options});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `HTTP ${response.status}`);
  return data;
}
function setMessage(text, error = false) {
  el('workspace-message').textContent = text;
  el('workspace-message').style.color = error ? '#ffb3bd' : '#b4e5d5';
}
const datasetPageSize = 50;
let datasetOffset = 0;
async function status() {
  const data = await api('/api/workspace/status');
  el('active-source').textContent = data.active.toUpperCase();
  el('demo-count').textContent = data.counts.demo.toLocaleString();
  el('upload-count').textContent = data.counts.upload.toLocaleString();
  el('active-count').textContent = data.counts[data.active].toLocaleString();
  el('use-upload').disabled = data.counts.upload === 0;
  el('synced').textContent = 'Local workspace · ' + new Date().toLocaleTimeString();
  return data;
}
function renderDataset(data) {
  const body = el('dataset-results'); body.replaceChildren();
  for (const item of data.items) {
    const row = make('tr');
    const name = make('td', item.name, 'item-name');
    const price = make('td', item.price_display, 'item-price');
    const availability = make('td');
    const style = item.availability === 'IN_STOCK' ? 'valid' : item.availability === 'OUT_OF_STOCK' ? 'out' : 'unknown';
    availability.append(make('span', item.availability.replaceAll('_', ' '), `badge ${style}`));
    row.append(name, make('td', item.retailer), price, availability,
      make('td', item.rating === null ? '—' : `${item.rating} / 5 (${item.review_count ?? '—'} reviews)`));
    body.append(row);
  }
  if (!data.items.length) {
    const row = make('tr'), cell = make('td', 'No matching products.', 'empty');
    cell.colSpan = 5; row.append(cell); body.append(row);
  }
  const last = data.offset + data.items.length;
  el('dataset-count').textContent = data.total ? `Showing ${data.offset + 1}–${last} of ${data.total} matches` : 'No matching products';
  el('dataset-prev').disabled = data.offset === 0;
  el('dataset-next').disabled = last >= data.total;
  el('provenance').textContent = data.provenance === 'SYNTHETIC_DEMO'
    ? 'Synthetic bundled demo; prices and reviews are fictional.'
    : 'User-uploaded data; prices and stock are not independently verified.';
}
let datasetRequest = 0;
async function refreshDataset() {
  const seq = ++datasetRequest;
  const q = el('dataset-query').value.trim();
  const data = await api('/api/workspace/products?' + new URLSearchParams({q, limit: String(datasetPageSize), offset: String(datasetOffset)}));
  if (seq === datasetRequest) renderDataset(data);
}
async function refreshAll() { await status(); datasetOffset = 0; await refreshDataset(); }
el('dataset-prev').addEventListener('click', () => {
  datasetOffset = Math.max(0, datasetOffset - datasetPageSize);
  refreshDataset().catch(err => setMessage(err.message, true));
});
el('dataset-next').addEventListener('click', () => {
  datasetOffset += datasetPageSize;
  refreshDataset().catch(err => setMessage(err.message, true));
});
async function changeSource(path, success) {
  setMessage('Working…');
  try {
    await api(path, {method: 'POST'});
    await refreshAll(); setMessage(success);
  } catch (err) { setMessage(err.message, true); }
}
el('load-demo').addEventListener('click', () => changeSource('/api/workspace/demo', 'Demo data loaded.'));
el('use-demo').addEventListener('click', () => changeSource('/api/workspace/activate/demo', 'Demo dataset active.'));
el('use-upload').addEventListener('click', () => changeSource('/api/workspace/activate/upload', 'Uploaded dataset active.'));
el('upload-form').addEventListener('submit', async event => {
  event.preventDefault();
  const file = el('dataset-file').files[0];
  if (!file) return;
  if (file.size > 2 * 1024 * 1024) { setMessage('Maximum upload size is 2 MB.', true); return; }
  const form = new FormData(); form.append('file', file);
  setMessage('Validating upload…');
  try {
    await api('/api/workspace/upload', {method: 'POST', body: form});
    await refreshAll(); setMessage('Dataset uploaded and activated.');
  } catch (err) { setMessage(err.message, true); }
});
let typing;
el('dataset-query').addEventListener('input', () => {
  clearTimeout(typing);
  typing = setTimeout(() => {datasetOffset = 0; refreshDataset().catch(err => setMessage(err.message, true));}, 200);
});
function formatOfferPrice(offer) {
  if (offer.price_text) return offer.price_text;
  if (offer.price === null) return 'Unavailable';
  if (offer.currency === 'INR' || offer.currency === 'USD') {
    return new Intl.NumberFormat('en-IN', {style: 'currency', currency: offer.currency}).format(offer.price);
  }
  return `${offer.price} (${offer.currency || 'unknown currency'})`;
}
function renderLookup(data) {
  const body = el('lookup-results'); body.replaceChildren();
  for (const offer of data.offers) {
    const row = make('tr');
    const name = make('td', offer.name, 'item-name');
    if (offer.url) {
      const link = make('a', 'View source'); link.href = offer.url;
      link.rel = 'noopener noreferrer'; link.target = '_blank';
      name.append(make('span', ' '), link);
    }
    const specText = Object.entries(offer.specs || {}).slice(0, 3)
      .map(([key, value]) => `${key}: ${value}`).join(' · ');
    if (specText) name.append(make('div', specText, 'item-retailer'));
    const reviews = make('td', offer.rating === null ? 'Unknown' : `${offer.rating} / 5 · ${offer.review_count ?? '—'} reviews`);
    if (Array.isArray(offer.review_highlights) && offer.review_highlights.length) {
      reviews.append(make('div', offer.review_highlights.join(' · '), 'item-retailer'));
    }
    row.append(name, make('td', offer.retailer), make('td', formatOfferPrice(offer), 'item-price'),
      make('td', offer.availability.replaceAll('_', ' ')), reviews);
    body.append(row);
  }
  if (!data.offers.length) {
    const row = make('tr'), cell = make('td', 'No products matched this query.', 'empty');
    cell.colSpan = 5; row.append(cell); body.append(row);
  }
  const source = data.live_retailer_data ? 'PROVIDER-REPORTED SHOPPING RESULTS' : 'SAMPLE / MOCK DATA';
  el('lookup-summary').textContent = `${data.provider} · ${source} · ${data.notice} ${data.warnings.join('; ')}`;
  el('lookup-foot').textContent = `${data.dataset_matches.length} match(es) in the active local dataset · No certified deal alert · No history writes`;
}
el('lookup-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = el('lookup-button'); button.disabled = true;
  el('lookup-summary').textContent = 'Searching provider…';
  try {
    const data = await api('/api/workspace/agent/lookup', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({query: el('lookup-query').value.trim()})
    });
    renderLookup(data);
  } catch (err) { el('lookup-summary').textContent = `Lookup failed: ${err.message}`; }
  finally { button.disabled = false; }
});
refreshAll().catch(err => setMessage(err.message, true));
