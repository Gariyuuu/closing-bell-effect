/* W1 — RESEARCH PUBLICATION: shared reading chrome.
   Progressive enhancement only. Nothing here computes, alters or re-renders a
   finding; it builds navigation from headings already in the document and
   reveals content that is fully visible without JavaScript.
   Honours prefers-reduced-motion: no reveal, no smooth scroll, no progress
   animation — the page simply renders. */
(function () {
  'use strict';
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var doc = document;

  function ready(fn) {
    if (doc.readyState !== 'loading') fn();
    else doc.addEventListener('DOMContentLoaded', fn);
  }

  function slug(s) {
    return s.toLowerCase().replace(/[^\w\s-]/g, '').trim().replace(/\s+/g, '-').slice(0, 40);
  }

  ready(function () {

    /* ---- 0. Icon sprite (Lucide, ISC) --------------------------------
       One inline sprite per page, referenced with <use>. No icon library is
       shipped; these are the four Lucide glyphs the publication actually uses,
       drawn with currentColor at the surrounding text's stroke weight. */
    if (!doc.getElementById('pub-icons')) {
      var sp = doc.createElement('div');
      sp.style.cssText = 'position:absolute;width:0;height:0;overflow:hidden';
      sp.setAttribute('aria-hidden', 'true');
      sp.innerHTML =
        '<svg xmlns="http://www.w3.org/2000/svg" id="pub-icons">' +
        '<symbol id="i-github" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
        '<path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.4 5.4 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4"/>' +
        '<path d="M9 18c-4.51 2-5-2-7-2"/></symbol>' +
        '<symbol id="i-external" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
        '<path d="M7 7h10v10"/><path d="M7 17 17 7"/></symbol>' +
        '<symbol id="i-report" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
        '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/>' +
        '<path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/></symbol>' +
        '<symbol id="i-link" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
        '<path d="M9 17H7A5 5 0 0 1 7 7h2"/><path d="M15 7h2a5 5 0 1 1 0 10h-2"/><line x1="8" x2="16" y1="12" y2="12"/></symbol>' +
        '</svg>';
      doc.body.insertBefore(sp, doc.body.firstChild);
    }
    function icon(id, cls) {
      return '<svg class="i' + (cls ? ' ' + cls : '') + '" aria-hidden="true" focusable="false"><use href="#' + id + '"></use></svg>';
    }

    var main = doc.querySelector('main') || doc.body;
    /* A study section is one that carries a heading. Structural <section>
       elements used for sub-components (a diagram, a legend) are not sections
       of the argument and must not enter the index. */
    var sections = [].slice.call(main.querySelectorAll('section'))
      .filter(function (sec) { return !!sec.querySelector('h2'); });

    /* Not every study wraps its parts in <section>. Where the long-form body is
       a flat run of h2 headings instead, each h2 stands in for a section so the
       rhythm, the index and the reveal behave identically across the twelve. */
    var flat = sections.length === 0;
    if (flat) {
      main.classList.add('flat');
      sections = [].slice.call(main.querySelectorAll('h2'));
    }

    /* ---- 1. Section ids + numbers + anchored headings ---- */
    var items = [];
    sections.forEach(function (sec, i) {
      var h2 = flat ? sec : sec.querySelector('h2');
      if (!h2) return;
      var target = flat ? h2 : sec;
      if (!target.id) target.id = 's-' + (i + 1) + '-' + slug(h2.textContent || '');

      /* A section's label is the first eyebrow/kicker/number element that
         appears BEFORE its heading. Position, not nesting depth: it finds the
         label wherever a study happens to wrap it, and can never pick up a
         numeric table cell, which always comes after the heading. */
      var label0 = null;
      if (!flat) {
        var cands = [].slice.call(sec.querySelectorAll('.num, .kicker, .eyebrow'));
        for (var k = 0; k < cands.length; k++) {
          if (h2.compareDocumentPosition(cands[k]) & Node.DOCUMENT_POSITION_PRECEDING) {
            label0 = cands[k];
            break;
          }
        }
      }
      var numbered = label0 && /^\s*\d/.test(label0.textContent);
      var label = numbered ? label0.textContent.trim() : ('0' + (i + 1)).slice(-2);
      items.push({ id: target.id, label: label, el: target });

      /* Every study carries a numbered section rule. Where the markup already
         has one it is left alone; where there is a worded label the number
         joins it; otherwise one is inserted. One rhythm across the twelve. */
      if (flat) {
        var prev = h2.previousElementSibling;
        if (!prev || !prev.classList.contains('pub-secnum')) {
          var n = doc.createElement('p');
          n.className = 'pub-secnum';
          n.textContent = label;
          h2.parentNode.insertBefore(n, h2);
        }
      } else if (label0 && !numbered) {
        if (!label0.querySelector('.pub-n')) {
          label0.insertAdjacentHTML('afterbegin', '<span class="pub-n">' + label + '</span>');
        }
      } else if (!label0) {
        var host = sec.querySelector('.wrap') || sec;
        var n2 = doc.createElement('p');
        n2.className = 'pub-secnum';
        n2.textContent = label;
        host.insertBefore(n2, host.firstChild);
      }

      if (!h2.querySelector('.h-anchor')) {
        var a = doc.createElement('a');
        a.className = 'h-anchor';
        a.href = '#' + target.id;
        a.innerHTML = icon('i-link');
        a.setAttribute('aria-label', 'Link to this section');
        h2.appendChild(a);
      }
    });

    /* ---- 1b. Icon-decorate outbound buttons ---- */
    [].forEach.call(doc.querySelectorAll('a.btn'), function (a) {
      if (a.querySelector('svg')) return;
      var h = a.getAttribute('href') || '';
      var id = 'i-external';
      if (/github\.com/.test(h) && !/\/blob\/|\.md$/.test(h)) id = 'i-github';
      else if (/\.md($|[?#])|\.pdf($|[?#])|report|paper/i.test(h)) id = 'i-report';
      a.insertAdjacentHTML('beforeend', icon(id, id === 'i-external' ? 'arrow' : ''));
      if (/^https?:/i.test(h) && a.hostname !== location.hostname) a.rel = 'noopener';
    });

    /* ---- 2. Reading progress ---- */
    var prog = doc.createElement('div');
    prog.className = 'pub-progress';
    prog.setAttribute('aria-hidden', 'true');
    var fill = doc.createElement('i');
    prog.appendChild(fill);
    doc.body.appendChild(prog);

    /* ---- 3. Sticky bar with section index ---- */
    var titleEl = doc.querySelector('h1, .masthead__word');
    var bar = doc.createElement('div');
    bar.className = 'pub-bar';
    var wrap = doc.createElement('div');
    wrap.className = 'wrap';
    var t = doc.createElement('span');
    t.className = 't';
    /* The bar carries the study's name, not its full headline: anything after
       a dash in the document title is a subtitle, and belongs on the page. */
    t.textContent = (titleEl && titleEl.textContent.trim()) ||
      doc.title.split(/\s[—–-]\s/)[0].trim();
    wrap.appendChild(t);

    var links = [];
    if (items.length > 1) {
      var nav = doc.createElement('nav');
      nav.setAttribute('aria-label', 'Sections');
      items.forEach(function (it) {
        var a = doc.createElement('a');
        a.href = '#' + it.id;
        a.textContent = it.label;
        nav.appendChild(a);
        links.push(a);
      });
      wrap.appendChild(nav);
    }
    bar.appendChild(wrap);
    doc.body.appendChild(bar);

    /* Section jumps scroll smoothly, but only from a real click and only when
       the reader has not asked for reduced motion. */
    doc.addEventListener('click', function (ev) {
      var a = ev.target.closest && ev.target.closest('.pub-bar nav a, .h-anchor');
      if (!a || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.button) return;
      var id = (a.getAttribute('href') || '').replace(/^#/, '');
      var el = id && doc.getElementById(id);
      if (!el) return;
      ev.preventDefault();
      el.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
      if (history.replaceState) history.replaceState(null, '', '#' + id);
      else location.hash = id;
    });

    var mast = doc.querySelector('header.mast, header.masthead, .hero, header');
    var ticking = false;
    var sweep = function () {};
    function onScroll() {
      var st = window.pageYOffset || doc.documentElement.scrollTop;
      var h = doc.documentElement.scrollHeight - window.innerHeight;
      fill.style.width = (h > 0 ? Math.min(100, (st / h) * 100) : 0) + '%';
      var trigger = mast ? mast.offsetHeight * 0.75 : 400;
      bar.classList.toggle('show', st > trigger);

      var active = -1;
      for (var i = 0; i < items.length; i++) {
        if (items[i].el.getBoundingClientRect().top <= 120) active = i;
      }
      links.forEach(function (a, i) {
        if (i === active) a.setAttribute('aria-current', 'true');
        else a.removeAttribute('aria-current');
      });
      sweep();
      ticking = false;
    }
    window.addEventListener('scroll', function () {
      if (!ticking) { ticking = true; window.requestAnimationFrame(onScroll); }
    }, { passive: true });
    window.addEventListener('resize', onScroll, { passive: true });
    onScroll();

    /* ---- 4. Reveal on scroll ----
       An observer alone is not enough: a fast scroll, an anchor jump or a
       scripted scroll can move the viewport past an element between two
       rendered frames, and it would then stay hidden for good. The scroll
       handler therefore also sweeps anything the reader has already scrolled
       to, so nothing can be left invisible. */
    var targets = [].slice.call(main.querySelectorAll(
      flat
        ? 'main > *, main > .wrap > *, figure, .stat-row, .stats, .scroll, .tablewrap, .box, .callout, .cmp, .grid'
        : 'section > .wrap > *, figure, .stat-row, .stats, .scroll, .tablewrap, .box, .callout, .card'
    ));
    /* A reveal target that contains another would fade the inner one twice. */
    targets = targets.filter(function (el) {
      return !targets.some(function (o) { return o !== el && o.contains(el); });
    });

    if (reduce || !('IntersectionObserver' in window)) {
      targets.forEach(function (el) { el.classList.add('in'); });
      return;
    }
    targets.forEach(function (el) {
      if (!el.hasAttribute('data-reveal')) el.setAttribute('data-reveal', '');
    });

    var pending = targets.slice();
    function show(el) {
      el.classList.add('in');
      var i = pending.indexOf(el);
      if (i > -1) pending.splice(i, 1);
    }

    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { show(e.target); io.unobserve(e.target); }
      });
    }, { rootMargin: '160px 0px -6% 0px', threshold: 0 });
    targets.forEach(function (el) { io.observe(el); });

    sweep = function () {
      if (!pending.length) return;
      var h = window.innerHeight;
      for (var i = pending.length - 1; i >= 0; i--) {
        if (pending[i].getBoundingClientRect().top < h) {
          io.unobserve(pending[i]);
          show(pending[i]);
        }
      }
    };
    sweep();
  });
})();
