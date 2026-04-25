(() => {
  const contextBar = document.querySelector('.library-scroll-context');
  const contextValue = document.querySelector('[data-library-context-value]');
  const entries = Array.from(document.querySelectorAll('.library-entry'));

  if (!contextBar || !contextValue || entries.length === 0) {
    return;
  }

  const siteHeader = document.querySelector('.site-header');
  let lastLabel = '';

  const setContextTopOffset = () => {
    const headerHeight = siteHeader instanceof HTMLElement ? siteHeader.offsetHeight : 0;
    contextBar.style.setProperty('--library-scroll-context-top', `${headerHeight + 10}px`);
  };

  const updateContext = () => {
    const stickyTop = contextBar.getBoundingClientRect().top;
    const triggerY = window.scrollY + stickyTop + 1;

    let activeEntry = null;
    for (const entry of entries) {
      if (entry.offsetTop <= triggerY) {
        activeEntry = entry;
      } else {
        break;
      }
    }

    if (!activeEntry) {
      contextBar.hidden = true;
      return;
    }

    const firstEntry = entries[0];
    if (window.scrollY + stickyTop < firstEntry.offsetTop) {
      contextBar.hidden = true;
      return;
    }

    const arc = activeEntry.dataset.arc?.trim() || 'Unknown Arc';
    const phase = activeEntry.dataset.phase?.trim() || 'Main';
    const label = `${arc} / ${phase}`;

    if (label !== lastLabel) {
      contextValue.textContent = label;
      lastLabel = label;
    }

    contextBar.hidden = false;
  };

  let ticking = false;
  const queueUpdate = () => {
    if (ticking) {
      return;
    }
    ticking = true;
    requestAnimationFrame(() => {
      updateContext();
      ticking = false;
    });
  };

  setContextTopOffset();
  updateContext();

  window.addEventListener('scroll', queueUpdate, { passive: true });
  window.addEventListener('resize', () => {
    setContextTopOffset();
    queueUpdate();
  });
})();
