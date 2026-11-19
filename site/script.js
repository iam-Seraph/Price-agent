'use strict';
const $ = id => document.getElementById(id);
const commands = {
  dashboard: {
    code: `git clone https://github.com/iam-Seraph/Price-agent.git\ncd Price-agent\npython -m pip install -r backend/requirements-workspace.txt\n# Initialize legacy schema once, without seeding fake quotes:\npython -c "from backend.price_engine.storage import PriceStore; PriceStore('tracker.sqlite3','backend/migrations/001_initial.sql').close()"\ncd backend\npython -m price_engine.workspace --db ../tracker.sqlite3 --workspace-db workspace.sqlite3 --host 127.0.0.1 --port 8000`,
    note: 'Verified offers → http://127.0.0.1:8000/verified · No price quotes are generated on launch.'
  },
  catalog: {
    code: `# From the repository root:\nNew-Item -ItemType Directory -Force backend/data | Out-Null\ncurl.exe -L --fail --retry 3 "https://static.openfoodfacts.org/data/en.openfoodfacts.org.products.csv.gz" -o "backend/data/openfoodfacts.csv.gz"\ncd backend\npython -m price_engine.catalog_import --input data/openfoodfacts.csv.gz --db ../tracker.sqlite3 --max-rows 10000`,
    note: 'The export can be very large. 10,000 is a smoke-test cap, not a claimed product count. Use --max-rows 1000000 to attempt the full target.'
  },
  agent: {
    code: `# From the repository root:\npython -m pip install -r requirements.txt\npython price_agent.py\n\n# For an LLM-backed mock run, configure your own API key\n# in a local .env first; then:\npython price_agent.py --product headphones-a --budget 280`,
    note: 'The AI agent uses mock USD product data and is not connected to SQLite or the real-food catalog.'
  }
};
let activeTab = 'dashboard';
function setTab(tab) {
  if (!Object.prototype.hasOwnProperty.call(commands, tab)) return;
  activeTab = tab;
  $('terminal-code').textContent = commands[tab].code;
  $('terminal-note').textContent = commands[tab].note;
  document.querySelectorAll('.terminal-tab').forEach(button => {
    const selected = button.dataset.tab === tab;
    button.classList.toggle('active', selected);
    button.setAttribute('aria-selected', String(selected));
    button.tabIndex = selected ? 0 : -1;
  });
  $('code-pane').setAttribute('aria-labelledby', 'tab-' + tab);
  $('copy-command').textContent = 'Copy commands';
}
document.querySelectorAll('.terminal-tab').forEach(button => {
  button.addEventListener('click', () => setTab(button.dataset.tab));
  button.addEventListener('keydown', event => {
    const tabs = Array.from(document.querySelectorAll('.terminal-tab'));
    let next;
    if (event.key === 'ArrowRight') next = (tabs.indexOf(button) + 1) % tabs.length;
    else if (event.key === 'ArrowLeft') next = (tabs.indexOf(button) - 1 + tabs.length) % tabs.length;
    else return;
    event.preventDefault();
    tabs[next].focus();
    setTab(tabs[next].dataset.tab);
  });
});
$('copy-command').addEventListener('click', async () => {
  const text = commands[activeTab].code;
  try {
    if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(text);
    else {
      const field = document.createElement('textarea');
      field.value = text; field.style.position = 'fixed'; field.style.opacity = '0';
      document.body.append(field); field.select();
      if (!document.execCommand('copy')) throw new Error('Clipboard unavailable');
      field.remove();
    }
    $('copy-command').textContent = 'Copied!';
  } catch (error) {
    $('copy-command').textContent = 'Select text to copy';
  }
});
const menu = $('menu-button');
menu.addEventListener('click', () => {
  const expanded = menu.getAttribute('aria-expanded') === 'true';
  menu.setAttribute('aria-expanded', String(!expanded));
  $('nav-links').classList.toggle('is-open', !expanded);
});
$('nav-links').querySelectorAll('a').forEach(a => a.addEventListener('click', () => {
  menu.setAttribute('aria-expanded', 'false');
  $('nav-links').classList.remove('is-open');
}));
$('year').textContent = new Date().getFullYear();
setTab('dashboard');
