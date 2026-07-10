document.addEventListener('DOMContentLoaded', async () => {
    const container = document.getElementById('collage-container');

    // ── Filter buttons ───────────────────────────────────────────────────────
    document.querySelectorAll('.activity-filter-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
            document.querySelectorAll('.activity-filter-btn')
                .forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            container.innerHTML = '<div class="lifelist-loading">Loading...</div>';
            const species = await loadData(btn.dataset.range);
            if (species) renderCollage(species);
        });
    });

    // ── Initial load ─────────────────────────────────────────────────────────
    const species = await loadData('all');
    if (species) renderCollage(species);


    // ── Fetch ────────────────────────────────────────────────────────────────
    async function loadData(range = 'all') {
        try {
            const res = await fetch(`/life-list-data?range=${range}`);
            return await res.json();
        } catch (err) {
            container.innerHTML = '<div class="lifelist-loading">Failed to load life list.</div>';
            return null;
        }
    }


    // ── Render ───────────────────────────────────────────────────────────────
    function renderCollage(species) {
        if (!species.length) {
            container.innerHTML = '<div class="lifelist-loading">No species detected for this period.</div>';
            document.getElementById('ll-total-species').textContent    = 0;
            document.getElementById('ll-total-detections').textContent = 0;
            return;
        }

        // Update header stats
        document.getElementById('ll-total-species').textContent    = species.length;
        document.getElementById('ll-total-detections').textContent = species.reduce((s, d) => s + d.count, 0);

        // Clear and rebuild SVG
        container.innerHTML = '';

        const width  = container.clientWidth || 1100;
        const height = Math.max(600, Math.min(window.innerHeight - 300, 800));

        const svg = d3.select(container)
            .append('svg')
            .attr('class', 'collage-svg')
            .attr('width', width)
            .attr('height', height)
            .style('background', '#111710');

        const defs = svg.append('defs');

        const pack = d3.pack()
            .size([width, height])
            .padding(12);

        const root = d3.hierarchy({ children: species })
            .sum(d => d.count)
            .sort((a, b) => b.value - a.value);

        pack(root);

        const nodes = root.leaves();

        // Clip paths
        nodes.forEach((d, i) => {
            defs.append('clipPath')
                .attr('id', `clip-${i}`)
                .append('circle')
                .attr('cx', d.x)
                .attr('cy', d.y)
                .attr('r',  d.r);
        });

        // Nodes
        const node = svg.selectAll('.bird-node')
            .data(nodes)
            .enter()
            .append('g')
            .attr('class', 'bird-node')
            .attr('data-species-click', d => d.data.species);

        // Background circle
        node.append('circle')
            .attr('cx',           d => d.x)
            .attr('cy',           d => d.y)
            .attr('r',            d => d.r)
            .attr('fill',         '#111710')
            .attr('stroke',       '#1e2b1f')
            .attr('stroke-width', 1);

        // Bird image — only show removed_bg version, placeholder otherwise
        node.each(function(d, i) {
            if (d.data.removed_bg_url) {
                const padding = d.r * 0.1;
                d3.select(this)
                    .append('image')
                    .attr('class',               'bird-image')
                    .attr('href',                d.data.removed_bg_url)
                    .attr('x',                   d.x - d.r + padding)
                    .attr('y',                   d.y - d.r + padding)
                    .attr('width',               (d.r - padding) * 2)
                    .attr('height',              (d.r - padding) * 2)
                    .attr('clip-path',           `url(#clip-${i})`)
                    .attr('preserveAspectRatio', 'xMidYMid slice');
            } else {
                const size = d.r * 0.5;
                d3.select(this)
                    .append('text')
                    .attr('class',       'bird-placeholder')
                    .attr('x',           d.x)
                    .attr('y',           d.y + size * 0.35)
                    .attr('text-anchor', 'middle')
                    .attr('font-size',   size)
                    .attr('opacity',     0.2)
                    .text('🐦');
            }
        });

        // Hover
        const popup = document.getElementById('global-popup');

        node
            .on('mouseenter', function() {
                d3.select(this).select('circle')
                    .attr('stroke',       '#4ade80')
                    .attr('stroke-width', 2);
            })
            .on('mousemove', function(event, d) {
                popup.innerHTML = `
                    <div class="popup-title">${d.data.species}</div>
                    <div class="popup-row">
                        <span class="popup-conf">${d.data.count} detection${d.data.count !== 1 ? 's' : ''}</span>
                    </div>
                    ${d.data.rarity ? `<div class="popup-row"><span class="popup-time">${d.data.rarity}</span></div>` : ''}
                `;
                popup.style.display = 'block';
                popup.style.left    = (event.clientX + 14) + 'px';
                popup.style.top     = (event.clientY - 10) + 'px';
            })
            .on('mouseleave', function() {
                d3.select(this).select('circle')
                    .attr('stroke',       '#1e2b1f')
                    .attr('stroke-width', 1);
                popup.style.display = 'none';
            });

        // ── Background refresh for pending rembg images ──────────────────────
        const pending = species.filter(s => !s.removed_bg_url && s.image_url);
        if (!pending.length) return;

        [8000, 30000].forEach(delay => {
            setTimeout(async () => {
                try {
                    const activeRange = document.querySelector('.activity-filter-btn.active')?.dataset.range || 'all';
                    const res         = await fetch(`/life-list-data?range=${activeRange}`);
                    const updated     = await res.json();

                    updated.forEach(s => {
                        if (!s.removed_bg_url) return;

                        const n = node.filter(d => d.data.species === s.species);
                        // Only update if still showing placeholder (no image element yet)
                        if (!n.select('.bird-image').empty()) return;

                        n.select('.bird-placeholder').remove();

                        const nd  = n.datum();
                        const idx = nodes.indexOf(nd);
                        const pad = nd.r * 0.1;

                        n.append('image')
                            .attr('class',               'bird-image')
                            .attr('href',                s.removed_bg_url)
                            .attr('x',                   nd.x - nd.r + pad)
                            .attr('y',                   nd.y - nd.r + pad)
                            .attr('width',               (nd.r - pad) * 2)
                            .attr('height',              (nd.r - pad) * 2)
                            .attr('clip-path',           `url(#clip-${idx})`)
                            .attr('preserveAspectRatio', 'xMidYMid slice');
                    });
                } catch (e) { /* silent fail */ }
            }, delay);
        });
    }
});