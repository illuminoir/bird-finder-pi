// ── Generic fetch helper ─────────────────────────────────────────────────────
async function fetchPartial(url, containerId) {
    const html = await fetch(url).then(r => r.text());
    document.getElementById(containerId).innerHTML = html;
}


// ── Recent detections filter ─────────────────────────────────────────────────
document.querySelectorAll('.filter-btn').forEach(button => {
    button.addEventListener('click', async () => {
        document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        button.classList.add('active');
        await fetchPartial(`/recent-data?range=${button.dataset.range}`, 'recent-container');
    });
});


// ── Species overview filter ──────────────────────────────────────────────────
document.querySelectorAll('.species-filter-btn').forEach(button => {
    button.addEventListener('click', async () => {
        document.querySelectorAll('.species-filter-btn').forEach(b => b.classList.remove('active'));
        button.classList.add('active');
        await fetchPartial(`/species-data?range=${button.dataset.range}`, 'species-container');
    });
});


// ── Activity heatmap filter ──────────────────────────────────────────────────
document.querySelectorAll('.activity-filter-btn').forEach(button => {
    button.addEventListener('click', async () => {
        document.querySelectorAll('.activity-filter-btn').forEach(b => b.classList.remove('active'));
        button.classList.add('active');
        await fetchPartial(`/activity-data?range=${button.dataset.range}`, 'activity-container');
    });
});


// ── Smart popup direction (flip upward when near bottom of viewport) ─────────
const globalPopup = document.getElementById('global-popup');

document.addEventListener('mousemove', function (e) {
    if (globalPopup.style.display === 'block') {
        globalPopup.style.left = (e.clientX + 14) + 'px';
        globalPopup.style.top  = (e.clientY - 10) + 'px';
    }
});

document.addEventListener('mouseover', function (e) {
    const trigger = e.target.closest('[data-popup]');
    if (!trigger) {
        globalPopup.style.display = 'none';
        return;
    }
    globalPopup.innerHTML = trigger.dataset.popup;
    globalPopup.style.display = 'block';
});

document.addEventListener('mouseout', function (e) {
    const trigger = e.target.closest('[data-popup]');
    if (trigger) globalPopup.style.display = 'none';
});