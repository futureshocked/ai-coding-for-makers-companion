(function () {
  'use strict';

  function initFlashMessages() {
    var flashes = document.querySelectorAll('.flash');
    flashes.forEach(function (el) {
      var timer = setTimeout(function () { dismiss(el); }, 5000);
      el.addEventListener('click', function () {
        clearTimeout(timer);
        dismiss(el);
      });
    });

    function dismiss(el) {
      el.classList.add('fade-out');
      setTimeout(function () {
        if (el.parentNode) el.parentNode.removeChild(el);
      }, 450);
    }
  }

  function initMobileNav() {
    var btn = document.querySelector('.hamburger');
    var links = document.querySelector('.nav-links');
    if (!btn || !links) return;

    btn.addEventListener('click', function () {
      var isOpen = links.classList.toggle('open');
      btn.classList.toggle('open', isOpen);
      btn.setAttribute('aria-expanded', String(isOpen));
    });

    document.addEventListener('click', function (e) {
      if (!btn.contains(e.target) && !links.contains(e.target)) {
        links.classList.remove('open');
        btn.classList.remove('open');
        btn.setAttribute('aria-expanded', 'false');
      }
    });
  }

  function initTabs() {
    var tabBars = document.querySelectorAll('.tab-bar');
    tabBars.forEach(function (bar) {
      var btns = bar.querySelectorAll('.tab-btn');
      btns.forEach(function (btn) {
        btn.addEventListener('click', function () {
          var target = btn.dataset.tab;
          btns.forEach(function (b) { b.classList.remove('active'); });
          btn.classList.add('active');
          document.querySelectorAll('.tab-panel').forEach(function (panel) {
            panel.classList.toggle('active', panel.id === 'tab-' + target);
          });
        });
      });
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    initFlashMessages();
    initMobileNav();
    initTabs();
  });
})();
