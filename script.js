/* ════════════════════════════════════════════════════════════════
   ANIS — script.js
   Vanilla JS: Canvas effects · Scroll reveals · Demo · Interactions
   ════════════════════════════════════════════════════════════════ */

'use strict';

/* ─── Utility ────────────────────────────────────────────────── */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), hi);
const lerp = (a, b, t) => a + (b - a) * t;
const rand = (lo, hi) => lo + Math.random() * (hi - lo);

/* ─── Custom cursor ──────────────────────────────────────────── */
(function initCursor() {
  let mx = -200, my = -200;
  let lx = -200, ly = -200;
  const style = document.documentElement.style;

  document.addEventListener('mousemove', e => { mx = e.clientX; my = e.clientY; });
  document.addEventListener('mouseleave', () => { mx = -200; my = -200; });

  function tick() {
    lx = lerp(lx, mx, 0.18);
    ly = lerp(ly, my, 0.18);
    style.setProperty('--cursor-x', mx + 'px');
    style.setProperty('--cursor-y', my + 'px');
    // The lagging ring uses the lerped values via a second pass (CSS only approximation is enough)
    requestAnimationFrame(tick);
  }
  tick();

  // Expand cursor on interactive elements
  document.addEventListener('mouseover', e => {
    if (e.target.closest('a, button, .feat-card, .tech-item, .pipeline, .future-item')) {
      document.body.style.setProperty('--cursor-scale', '2');
    }
  });
  document.addEventListener('mouseout', () => {
    document.body.style.setProperty('--cursor-scale', '1');
  });
})();

/* ─── Navbar scroll effect ───────────────────────────────────── */
(function initNav() {
  const nav = $('#navbar');
  const toggle = $('#navToggle');
  const links = $('#navLinks');

  window.addEventListener('scroll', () => {
    nav.classList.toggle('scrolled', window.scrollY > 60);
  }, { passive: true });

  toggle.addEventListener('click', () => {
    links.classList.toggle('open');
  });

  // Close menu on link click
  $$('a', links).forEach(a => {
    a.addEventListener('click', () => links.classList.remove('open'));
  });
})();

/* ─── Smooth scroll helper ───────────────────────────────────── */
function scrollToSection(id) {
  const el = document.getElementById(id);
  if (el) el.scrollIntoView({ behavior: 'smooth' });
}

/* ─── Intersection Observer: scroll reveals ─────────────────── */
(function initReveal() {
  const io = new IntersectionObserver((entries) => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        e.target.classList.add('visible');
        io.unobserve(e.target);
      }
    });
  }, { threshold: 0.12 });

  $$('.reveal-up, .reveal-fade').forEach(el => io.observe(el));
})();

/* ════════════════════════════════════════════════════════════════
   HERO CANVAS — Particle star field
   ════════════════════════════════════════════════════════════════ */
(function initHeroCanvas() {
  const canvas = $('#heroCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  let W, H, particles = [], mouse = { x: -1000, y: -1000 };

  function resize() {
    W = canvas.width  = canvas.offsetWidth;
    H = canvas.height = canvas.offsetHeight;
  }

  class Particle {
    constructor() { this.reset(true); }
    reset(initial = false) {
      this.x  = rand(0, W);
      this.y  = initial ? rand(0, H) : -4;
      this.r  = rand(0.3, 1.4);
      this.vy = rand(0.08, 0.35);
      this.vx = rand(-0.05, 0.05);
      this.op = rand(0.15, 0.55);
      this.life = rand(0.003, 0.008);
    }
    update() {
      this.x += this.vx;
      this.y += this.vy;

      // Mild repulsion from mouse
      const dx = this.x - mouse.x, dy = this.y - mouse.y;
      const dist = Math.sqrt(dx*dx + dy*dy);
      if (dist < 100) {
        const force = (100 - dist) / 100 * 0.3;
        this.vx += (dx / dist) * force;
        this.vy += (dy / dist) * force;
      }
      this.vx *= 0.98;
      this.vy  = clamp(this.vy, 0.05, 0.5);

      if (this.y > H + 4) this.reset();
    }
    draw() {
      ctx.beginPath();
      ctx.arc(this.x, this.y, this.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(255,255,255,${this.op})`;
      ctx.fill();
    }
  }

  function init() {
    resize();
    particles = Array.from({ length: 160 }, () => new Particle());
  }

  function draw() {
    ctx.clearRect(0, 0, W, H);

    // Subtle radial vignette
    const grad = ctx.createRadialGradient(W/2, H/2, 0, W/2, H/2, Math.max(W, H) * 0.7);
    grad.addColorStop(0, 'rgba(20,20,20,0)');
    grad.addColorStop(1, 'rgba(0,0,0,0.6)');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, W, H);

    particles.forEach(p => { p.update(); p.draw(); });

    // Draw subtle grid lines
    ctx.strokeStyle = 'rgba(255,255,255,0.018)';
    ctx.lineWidth = 1;
    const spacing = Math.min(W, H) / 8;
    for (let x = 0; x < W; x += spacing) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke();
    }
    for (let y = 0; y < H; y += spacing) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
    }

    requestAnimationFrame(draw);
  }

  canvas.addEventListener('mousemove', e => {
    const r = canvas.getBoundingClientRect();
    mouse.x = e.clientX - r.left;
    mouse.y = e.clientY - r.top;
  });
  canvas.addEventListener('mouseleave', () => { mouse.x = -1000; mouse.y = -1000; });

  window.addEventListener('resize', () => { resize(); });
  init();
  draw();
})();

/* ════════════════════════════════════════════════════════════════
   ORB CANVAS — Siri-style flowing orb
   ════════════════════════════════════════════════════════════════ */
(function initOrb() {
  const canvas = $('#orbCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  const DPR = window.devicePixelRatio || 1;
  const SIZE = 180;
  canvas.width  = SIZE * DPR;
  canvas.height = SIZE * DPR;
  ctx.scale(DPR, DPR);

  const cx = SIZE / 2, cy = SIZE / 2, R = SIZE / 2 - 6;
  let t = 0;

  // Wave parameters — multiple overlapping sine waves
  const waves = [
    { amp: 14, freq: 1.8, speed: 0.012, phase: 0 },
    { amp: 9,  freq: 2.6, speed: 0.018, phase: 1.2 },
    { amp: 6,  freq: 3.4, speed: 0.009, phase: 2.4 },
    { amp: 4,  freq: 4.2, speed: 0.025, phase: 3.6 },
  ];

  function drawOrb() {
    ctx.clearRect(0, 0, SIZE, SIZE);

    // Clip to circle
    ctx.save();
    ctx.beginPath();
    ctx.arc(cx, cy, R, 0, Math.PI * 2);
    ctx.clip();

    // Background gradient
    const bg = ctx.createRadialGradient(cx, cy - 10, 0, cx, cy, R);
    bg.addColorStop(0,   'rgba(50,50,50,1)');
    bg.addColorStop(0.5, 'rgba(15,15,15,1)');
    bg.addColorStop(1,   'rgba(0,0,0,1)');
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, SIZE, SIZE);

    // Draw flowing wave shape (filled)
    const numPoints = 120;
    for (let layer = 0; layer < 4; layer++) {
      const alpha = 0.06 - layer * 0.01;
      const yBase = cy + (layer - 1.5) * 16;

      ctx.beginPath();
      ctx.moveTo(cx - R, yBase);

      for (let i = 0; i <= numPoints; i++) {
        const x = (cx - R) + (i / numPoints) * R * 2;
        const norm = i / numPoints; // 0..1
        let y = yBase;
        waves.forEach(w => {
          y += Math.sin(norm * Math.PI * 2 * w.freq + w.phase + t * w.speed * 60) * w.amp;
        });
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }

      ctx.lineTo(cx + R, yBase + R + 40);
      ctx.lineTo(cx - R, yBase + R + 40);
      ctx.closePath();
      ctx.fillStyle = `rgba(255,255,255,${alpha})`;
      ctx.fill();
    }

    // Bright sine wave lines (the "Siri strands")
    const strands = [
      { color: 'rgba(255,255,255,0.55)', ampMult: 1.0, yOff: 0 },
      { color: 'rgba(255,255,255,0.25)', ampMult: 0.7, yOff: -8 },
      { color: 'rgba(255,255,255,0.12)', ampMult: 1.3, yOff: 10 },
    ];

    strands.forEach(strand => {
      ctx.beginPath();
      for (let i = 0; i <= numPoints; i++) {
        const x   = (cx - R) + (i / numPoints) * R * 2;
        const norm = i / numPoints;
        let y = cy + strand.yOff;
        waves.forEach(w => {
          y += Math.sin(norm * Math.PI * 2 * w.freq + w.phase + t * w.speed * 60) * w.amp * strand.ampMult;
        });
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.strokeStyle = strand.color;
      ctx.lineWidth   = 1.5;
      ctx.stroke();
    });

    // Inner glow
    const glow = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 0.6);
    glow.addColorStop(0,   'rgba(255,255,255,0.07)');
    glow.addColorStop(0.6, 'rgba(255,255,255,0.02)');
    glow.addColorStop(1,   'rgba(255,255,255,0)');
    ctx.fillStyle = glow;
    ctx.fillRect(0, 0, SIZE, SIZE);

    ctx.restore();

    // Outer glow ring
    ctx.beginPath();
    ctx.arc(cx, cy, R, 0, Math.PI * 2);
    ctx.strokeStyle = 'rgba(255,255,255,0.1)';
    ctx.lineWidth = 1;
    ctx.stroke();

    // Outer halo
    const halo = ctx.createRadialGradient(cx, cy, R - 4, cx, cy, R + 20);
    halo.addColorStop(0,   'rgba(255,255,255,0.18)');
    halo.addColorStop(0.4, 'rgba(255,255,255,0.05)');
    halo.addColorStop(1,   'rgba(255,255,255,0)');
    ctx.beginPath();
    ctx.arc(cx, cy, R + 20, 0, Math.PI * 2);
    ctx.fillStyle = halo;
    ctx.fill();

    t++;
    requestAnimationFrame(drawOrb);
  }

  drawOrb();
})();

/* ════════════════════════════════════════════════════════════════
   WAVEFORM DIVIDER — animated SVG polyline
   ════════════════════════════════════════════════════════════════ */
(function initWaveDivider() {
  const line = $('#waveLine');
  if (!line) return;

  const W = 1200, H = 120, mid = H / 2;
  let t = 0;

  function update() {
    const pts = [];
    const segments = 120;
    for (let i = 0; i <= segments; i++) {
      const x = (i / segments) * W;
      const norm = i / segments;
      const y = mid
        + Math.sin(norm * Math.PI * 6 + t * 0.04) * 22
        + Math.sin(norm * Math.PI * 14 + t * 0.07) * 8
        + Math.sin(norm * Math.PI * 3  - t * 0.025) * 14;
      pts.push(`${x.toFixed(1)},${y.toFixed(1)}`);
    }
    line.setAttribute('points', pts.join(' '));
    t++;
    requestAnimationFrame(update);
  }
  update();
})();

/* ════════════════════════════════════════════════════════════════
   FULL-BLEED WAVE CANVAS
   ════════════════════════════════════════════════════════════════ */
(function initWaveCanvas() {
  const canvas = $('#waveCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  let W, H, t = 0;

  function resize() {
    W = canvas.width  = canvas.offsetWidth;
    H = canvas.height = canvas.offsetHeight;
  }

  function draw() {
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, W, H);

    const layers = [
      { amp: H * 0.10, freq: 2.2, speed: 0.022, alpha: 0.08,  lw: 1.5 },
      { amp: H * 0.14, freq: 1.4, speed: 0.015, alpha: 0.05,  lw: 1 },
      { amp: H * 0.07, freq: 3.6, speed: 0.034, alpha: 0.06,  lw: 1 },
      { amp: H * 0.18, freq: 0.9, speed: 0.009, alpha: 0.035, lw: 1 },
    ];

    layers.forEach(l => {
      ctx.beginPath();
      for (let i = 0; i <= 200; i++) {
        const x = (i / 200) * W;
        const norm = i / 200;
        const y = H/2
          + Math.sin(norm * Math.PI * 2 * l.freq + t * l.speed) * l.amp
          + Math.sin(norm * Math.PI * 2 * l.freq * 2.3 - t * l.speed * 1.7) * l.amp * 0.4;
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.strokeStyle = `rgba(255,255,255,${l.alpha})`;
      ctx.lineWidth   = l.lw;
      ctx.stroke();
    });

    t++;
    requestAnimationFrame(draw);
  }

  window.addEventListener('resize', resize, { passive: true });
  resize();
  draw();
})();

/* ════════════════════════════════════════════════════════════════
   DEMO — Terminal animation + waveform
   ════════════════════════════════════════════════════════════════ */
(function initDemo() {
  const playBtn = $('#demoPlayBtn');
  const termBody = $('#termBody');
  if (!playBtn || !termBody) return;

  const script = [
    { delay: 400,  text: '› <span class="cmd">Listening for voice input...</span>' },
    { delay: 1200, text: '› <span class="out">⣾ Processing audio...</span>' },
    { delay: 2000, text: '› <span class="out">Transcript: <span class="cmd">"open chrome and search weather"</span></span>' },
    { delay: 3000, text: '› <span class="out">Calling Groq LLM...</span>' },
    { delay: 3800, text: '› Intent: <span class="intent">open_app</span> · arg: <span class="cmd">chrome</span> · <span class="conf">conf: 0.94</span>' },
    { delay: 4500, text: '› Intent: <span class="intent">search</span> · arg: <span class="cmd">weather</span> · <span class="conf">conf: 0.97</span>' },
    { delay: 5200, text: '› <span class="out">Executing: open_app("chrome")</span>' },
    { delay: 5800, text: '› <span class="out">Executing: web_search("weather")</span>' },
    { delay: 6400, text: '› <span class="cmd">✓ Done. 2 actions in 312ms.</span>' },
    { delay: 7200, text: '› <span class="out">Listening for next command...</span>' },
  ];

  let running = false;
  let timers  = [];

  function resetTerm() {
    termBody.innerHTML = '<div class="term-line"><span class="prompt">›</span> <span class="cmd">System ready. Listening...</span></div>';
  }

  function addLine(html) {
    const div = document.createElement('div');
    div.className = 'term-line';
    div.innerHTML = html;
    div.style.opacity = '0';
    div.style.transform = 'translateY(4px)';
    div.style.transition = 'opacity 0.3s, transform 0.3s';
    termBody.appendChild(div);
    requestAnimationFrame(() => { div.style.opacity = '1'; div.style.transform = 'none'; });
    termBody.scrollTop = termBody.scrollHeight;
  }

  playBtn.addEventListener('click', () => {
    if (running) {
      timers.forEach(clearTimeout);
      timers = [];
      running = false;
      playBtn.innerHTML = `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg> Run Demo`;
      resetTerm();
      return;
    }
    running = true;
    resetTerm();
    playBtn.innerHTML = `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg> Reset`;

    script.forEach(({ delay, text }) => {
      const t = setTimeout(() => addLine(text), delay);
      timers.push(t);
    });

    const done = setTimeout(() => {
      running = false;
      playBtn.innerHTML = `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg> Run Again`;
    }, 8000);
    timers.push(done);
  });
})();

/* ─── Demo waveform canvas ───────────────────────────────────── */
(function initDemoWave() {
  const canvas = $('#demoWaveCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  let t = 0;

  function resize() {
    canvas.width  = canvas.offsetWidth;
    canvas.height = canvas.offsetHeight;
  }

  function draw() {
    const W = canvas.width, H = canvas.height;
    ctx.clearRect(0, 0, W, H);

    const bars = 60;
    const barW = W / bars;

    for (let i = 0; i < bars; i++) {
      const norm  = i / bars;
      const amp   = Math.abs(Math.sin(norm * Math.PI * 4 + t * 0.1)) * H * 0.5
                  + Math.abs(Math.sin(norm * Math.PI * 9 - t * 0.07)) * H * 0.18;
      const bH    = Math.max(2, amp);
      const alpha = 0.2 + Math.abs(Math.sin(norm * Math.PI * 3 + t * 0.05)) * 0.5;

      ctx.fillStyle = `rgba(255,255,255,${alpha.toFixed(2)})`;
      ctx.fillRect(i * barW + 1, (H - bH) / 2, barW - 2, bH);
    }

    t++;
    requestAnimationFrame(draw);
  }

  window.addEventListener('resize', () => {
    resize();
  }, { passive: true });

  resize();
  draw();
})();

/* ════════════════════════════════════════════════════════════════
   PARALLAX — subtle vertical shift on scroll
   ════════════════════════════════════════════════════════════════ */
(function initParallax() {
  const elements = [
    { el: $('.orb-wrap'),     speed: 0.12 },
    { el: $('.story-bg-text'), speed: 0.08 },
    { el: $('.hero-title'),   speed: 0.06 },
  ].filter(x => x.el);

  window.addEventListener('scroll', () => {
    const sy = window.scrollY;
    elements.forEach(({ el, speed }) => {
      el.style.transform = `translateY(${sy * speed}px)`;
    });
  }, { passive: true });
})();

/* ════════════════════════════════════════════════════════════════
   PIPELINE STEP ANIMATION — cascade active dot on hover
   ════════════════════════════════════════════════════════════════ */
(function initPipelines() {
  $$('.pipeline').forEach(pipe => {
    const steps = $$('.pipe-step', pipe);
    let current = 0, interval = null;

    function setActive(idx) {
      steps.forEach((s, i) => s.classList.toggle('active', i === idx));
    }

    function startCycle() {
      current = 0; setActive(0);
      interval = setInterval(() => {
        current = (current + 1) % steps.length;
        setActive(current);
      }, 800);
    }

    function stopCycle() {
      clearInterval(interval);
      setActive(0);
    }

    pipe.addEventListener('mouseenter', startCycle);
    pipe.addEventListener('mouseleave', stopCycle);
  });
})();

/* ════════════════════════════════════════════════════════════════
   NUMBER COUNTER ANIMATION
   ════════════════════════════════════════════════════════════════ */
(function initCounters() {
  const io = new IntersectionObserver((entries) => {
    entries.forEach(e => {
      if (!e.isIntersecting) return;
      const el = e.target;
      const target = el.dataset.count;
      if (!target) return;
      let start = 0;
      const end  = parseFloat(target);
      const dur  = 1400;
      const step = 16;
      const inc  = end / (dur / step);

      const timer = setInterval(() => {
        start = Math.min(start + inc, end);
        el.textContent = Number.isInteger(end) ? Math.round(start) : start.toFixed(1);
        if (start >= end) clearInterval(timer);
      }, step);

      io.unobserve(el);
    });
  }, { threshold: 0.5 });

  $$('[data-count]').forEach(el => io.observe(el));
})();

/* ════════════════════════════════════════════════════════════════
   FEAT CARD SPOTLIGHT — follow mouse with radial gradient
   ════════════════════════════════════════════════════════════════ */
(function initCardSpotlight() {
  $$('.feat-card').forEach(card => {
    card.addEventListener('mousemove', e => {
      const r   = card.getBoundingClientRect();
      const x   = ((e.clientX - r.left) / r.width  * 100).toFixed(1);
      const y   = ((e.clientY - r.top)  / r.height * 100).toFixed(1);
      card.style.setProperty('--mx', x + '%');
      card.style.setProperty('--my', y + '%');
    });
  });
})();

/* ════════════════════════════════════════════════════════════════
   SCROLL PROGRESS LINE (thin line at top of viewport)
   ════════════════════════════════════════════════════════════════ */
(function initScrollProgress() {
  const bar = document.createElement('div');
  bar.style.cssText = `
    position: fixed; top: 0; left: 0; z-index: 999;
    height: 1px; width: 0%; background: rgba(255,255,255,0.5);
    transition: width 0.1s; pointer-events: none;
  `;
  document.body.appendChild(bar);

  window.addEventListener('scroll', () => {
    const pct = (window.scrollY / (document.body.scrollHeight - window.innerHeight) * 100).toFixed(2);
    bar.style.width = pct + '%';
  }, { passive: true });
})();

/* ════════════════════════════════════════════════════════════════
   STAGGERED REVEAL for tech items (already handled by reveal-fade,
   but we add a richer entrance here via JS)
   ════════════════════════════════════════════════════════════════ */
(function initTechGrid() {
  const io = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      const items = $$('.tech-item', entry.target);
      items.forEach((item, i) => {
        setTimeout(() => {
          item.style.opacity    = '1';
          item.style.transform  = 'translateY(0)';
        }, i * 60);
      });
      io.unobserve(entry.target);
    });
  }, { threshold: 0.15 });

  const grid = $('.tech-grid');
  if (grid) {
    $$('.tech-item', grid).forEach(item => {
      item.style.opacity   = '0';
      item.style.transform = 'translateY(20px)';
      item.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
    });
    io.observe(grid);
  }
})();

/* ════════════════════════════════════════════════════════════════
   HERO ENTRANCE — stagger elements in on load
   ════════════════════════════════════════════════════════════════ */
(function initHeroEntrance() {
  // All reveal elements in hero get triggered immediately
  const elements = $$('.hero .reveal-up, .hero .reveal-fade');
  // Small delay to let fonts load
  setTimeout(() => {
    elements.forEach(el => el.classList.add('visible'));
  }, 200);
})();

/* ════════════════════════════════════════════════════════════════
   ACTIVE NAV LINK on scroll
   ════════════════════════════════════════════════════════════════ */
(function initActiveNav() {
  const sections = $$('section[id], div[id]').filter(s => s.id);
  const navLinks = $$('.nav-links a');

  const io = new IntersectionObserver((entries) => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        navLinks.forEach(a => {
          a.style.color = a.getAttribute('href') === '#' + e.target.id
            ? 'rgba(255,255,255,1)'
            : '';
        });
      }
    });
  }, { threshold: 0.5 });

  sections.forEach(s => io.observe(s));
})();

/* ─── Global scrollTo exposed to HTML onclick ────────────────── */
window.scrollToSection = scrollToSection; // override default with smooth version