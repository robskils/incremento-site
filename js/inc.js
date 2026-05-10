/* Incremento — Site JS */

// ── HEADER SCROLL ──────────────────────────────────────────
(function () {
  const header = document.querySelector('.site-header');
  if (!header) return;
  const onScroll = () => {
    header.classList.toggle('scrolled', window.scrollY > 12);
  };
  onScroll();
  window.addEventListener('scroll', onScroll, { passive: true });
})();

// ── MOBILE MENU ────────────────────────────────────────────
(function () {
  const toggle = document.querySelector('.menu-toggle');
  const nav    = document.querySelector('.mobile-nav');
  if (!toggle || !nav) return;

  toggle.addEventListener('click', () => {
    const open = nav.classList.toggle('open');
    toggle.setAttribute('aria-expanded', open);
    toggle.querySelector('.icon-menu').style.display = open ? 'none'  : 'block';
    toggle.querySelector('.icon-close').style.display = open ? 'block' : 'none';
  });

  nav.querySelectorAll('a').forEach(a =>
    a.addEventListener('click', () => {
      nav.classList.remove('open');
      toggle.setAttribute('aria-expanded', false);
      toggle.querySelector('.icon-menu').style.display  = 'block';
      toggle.querySelector('.icon-close').style.display = 'none';
    })
  );
})();

// ── ACTIVE NAV LINK ────────────────────────────────────────
(function () {
  const path = window.location.pathname.replace(/\/$/, '') || '/';
  document.querySelectorAll('.site-nav a, .mobile-nav a').forEach(a => {
    const href = a.getAttribute('href').replace(/\/$/, '') || '/';
    if (href === path) a.classList.add('active');
  });
})();

// ── INTEREST TAG TOGGLES ───────────────────────────────────
(function () {
  document.querySelectorAll('.interest-tag').forEach(tag => {
    tag.addEventListener('click', () => tag.classList.toggle('active'));
  });
})();

// ── CONTACT FORM ───────────────────────────────────────────
(function () {
  const form    = document.getElementById('contact-form');
  const success = document.getElementById('form-success');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const btn = form.querySelector('button[type="submit"]');
    btn.disabled = true;
    btn.textContent = 'Sending…';

    const interests = [...document.querySelectorAll('.interest-tag.active')]
      .map(t => t.dataset.value);

    const payload = {
      name:      form.name.value,
      email:     form.email.value,
      company:   form.company.value,
      interests,
      message:   form.message.value,
      submitted: new Date().toISOString(),
    };

    try {
      const res = await fetch('https://enquiries.incremento.co', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(payload),
      });

      if (res.ok) {
        form.style.display = 'none';
        success.style.display = 'flex';
      } else {
        throw new Error('Server error');
      }
    } catch {
      btn.disabled = false;
      btn.textContent = 'Send message';
      alert('Something went wrong. Please email us directly at hello@incremento.co');
    }
  });
})();

// ── SCROLL REVEAL (light, no deps) ─────────────────────────
(function () {
  if (!('IntersectionObserver' in window)) return;
  const obs = new IntersectionObserver((entries) => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        e.target.style.opacity = '1';
        e.target.style.transform = 'translateY(0)';
        obs.unobserve(e.target);
      }
    });
  }, { threshold: 0.1 });

  document.querySelectorAll('.card, .value-card, .package-card, .blog-card, .work-card, .process-grid > div').forEach(el => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(20px)';
    el.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
    obs.observe(el);
  });
})();
