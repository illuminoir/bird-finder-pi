const overlay  = document.getElementById('modal-overlay');
const modal    = document.getElementById('species-modal');

// ── Open / close ────────────────────────────────────────────────────────────

function openModal() { overlay.classList.add('open'); }
function closeModal() { overlay.classList.remove('open'); }

overlay.addEventListener('click', e => { if (e.target === overlay) closeModal(); });
document.getElementById('modal-close').addEventListener('click', closeModal);
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });


// ── Helpers ──────────────────────────────────────────────────────────────────

function timeAgo(isoStr) {
    const diff = Math.floor((Date.now() - new Date(isoStr)) / 1000);
    if (diff < 60)     return `${diff}s ago`;
    if (diff < 3600)   return `${Math.floor(diff / 60)}m ago`;
    if (diff < 172800) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
}

function setEl(id, html) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = html;
}


// ── Populate modal ───────────────────────────────────────────────────────────

function populateModal(data) {
    const { species, image_url, description, rarity, stats, recent, sounds } = data;

    // Header
    setEl('modal-species-name', species);
    setEl('modal-rarity', rarity || '');
    setEl('modal-last-seen', stats.last_seen ? `Last seen ${timeAgo(stats.last_seen)}` : '');

    const imgEl = document.getElementById('modal-img');
    const phEl  = document.getElementById('modal-img-placeholder');
    if (image_url) {
        imgEl.src = image_url;
        imgEl.alt = species;
        imgEl.style.display = 'block';
        phEl.style.display  = 'none';
    } else {
        imgEl.style.display = 'none';
        phEl.style.display  = 'flex';
    }

    // Stats
    setEl('modal-stat-day',   stats.today ?? 0);
    setEl('modal-stat-week',  stats.week  ?? 0);
    setEl('modal-stat-month', stats.month ?? 0);
    setEl('modal-stat-total', stats.total ?? 0);

    // Description
    setEl('modal-description', description
        ? `<p>${description}</p>`
        : '<p style="color:var(--text-dim)">No description available.</p>'
    );

    // Recent detections
    setEl('modal-detections', recent.length
        ? recent.map(r => `
            <li class="modal-detection-row">
                <span class="modal-detection-conf">${Math.round(r.confidence * 100 * 10) / 10}%</span>
                <span class="modal-detection-time">${timeAgo(r.timestamp_utc)}</span>
            </li>`).join('')
        : '<li style="color:var(--text-dim);font-size:12px;padding:.5rem 0">No detections recorded.</li>'
    );

    // Sounds
    setEl('modal-sounds', sounds.length
        ? sounds.map(s => `
            <div class="modal-sound-row">
                <div class="modal-sound-meta">${s.recordist} · ${s.country} · ${s.type}</div>
                <audio controls preload="none">
                    <source src="${s.url}" type="audio/mpeg">
                </audio>
            </div>`).join('')
        : '<div class="modal-loading">No recordings found.</div>'
    );
}


// ── Click handler ────────────────────────────────────────────────────────────

document.addEventListener('click', async e => {
    const trigger = e.target.closest('[data-species-click]');
    if (!trigger) return;

    const species = trigger.dataset.speciesClick;
    if (!species) return;

    // Reset and open
    setEl('modal-species-name', species);
    setEl('modal-rarity', '');
    setEl('modal-last-seen', '');
    setEl('modal-description', '<div class="modal-loading">Loading...</div>');
    setEl('modal-detections', '');
    setEl('modal-sounds', '<div class="modal-loading">Loading sounds...</div>');
    document.getElementById('modal-img').style.display = 'none';
    document.getElementById('modal-img-placeholder').style.display = 'flex';
    openModal();

    try {
        const res  = await fetch(`/species-detail?name=${encodeURIComponent(species)}`);
        const data = await res.json();
        populateModal(data);
    } catch (err) {
        setEl('modal-description', '<div class="modal-loading">Failed to load data.</div>');
        console.error(err);
    }
});